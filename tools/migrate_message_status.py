#!/usr/bin/env python3
"""
消息状态迁移脚本
将现有的3状态系统迁移到新的7状态系统
"""

import sys
import os
import logging
from datetime import datetime

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.storage.redis_manager import redis_manager
from app.core.message_status import MessageStatus, map_legacy_status

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_messages():
    """迁移所有消息的状态"""
    logger.info("开始消息状态迁移...")

    try:
        # 统计信息
        stats = {
            'total': 0,
            'migrated': 0,
            'skipped': 0,
            'failed': 0,
            'status_count': {}
        }

        # 获取所有频道
        from app.storage.json_store import get_json_channel_store
        channel_store = get_json_channel_store()
        all_channels = channel_store.get_all_channels()

        logger.info(f"找到 {len(all_channels)} 个频道")

        # 遍历所有频道的消息
        for channel in all_channels:
            if isinstance(channel, dict):
                channel_id = channel.get('id')
                if not channel_id:
                    continue

                # 统一频道ID格式
                if isinstance(channel_id, (int, float)):
                    channel_id = str(int(channel_id))
                else:
                    channel_id = str(channel_id)

                if not channel_id.startswith('-100'):
                    channel_id = f'-100{channel_id}'

                logger.info(f"处理频道: {channel_id}")

                # 获取该频道的所有消息
                messages = redis_manager.get_messages_by_channel(channel_id, limit=10000)

                for msg in messages:
                    stats['total'] += 1
                    msg_id = msg.get('message_id')
                    current_status = msg.get('status', 'pending')

                    # 检查是否已经是新状态
                    if current_status in [s.value for s in MessageStatus]:
                        stats['skipped'] += 1
                        continue

                    # 迁移状态
                    new_status = None

                    # 1. 检查send_failed字段
                    if msg.get('send_failed') or msg.get('auto_forward_failed'):
                        new_status = MessageStatus.SEND_FAILED.value

                    # 2. 根据状态和拒绝原因迁移
                    elif current_status == 'approved':
                        # 区分自动/手动发布
                        if msg.get('auto_forwarded'):
                            new_status = MessageStatus.AUTO_APPROVED.value
                        else:
                            new_status = MessageStatus.MANUAL_APPROVED.value

                    elif current_status == 'rejected':
                        reject_reason = msg.get('rejection_reason', '') or msg.get('reject_reason', '') or msg.get('filter_reason', '')
                        new_status = map_legacy_status(current_status, reject_reason)

                    elif current_status == 'pending':
                        new_status = MessageStatus.PENDING.value

                    else:
                        # 未知状态，保持不变
                        stats['skipped'] += 1
                        continue

                    # 更新状态
                    if new_status and new_status != current_status:
                        try:
                            message_full_id = f"{channel_id}:{msg_id}"
                            success = redis_manager.update_message_status(message_full_id, new_status)

                            if success:
                                stats['migrated'] += 1
                                stats['status_count'][new_status] = stats['status_count'].get(new_status, 0) + 1
                                logger.debug(f"迁移成功: {channel_id}:{msg_id} - {current_status} -> {new_status}")
                            else:
                                stats['failed'] += 1
                                logger.error(f"迁移失败: {channel_id}:{msg_id}")
                        except Exception as e:
                            stats['failed'] += 1
                            logger.error(f"迁移错误 {channel_id}:{msg_id}: {e}")

        # 打印统计信息
        logger.info("迁移完成")
        logger.info(f"总计: {stats['total']} 条消息")
        logger.info(f"迁移: {stats['migrated']} 条")
        logger.info(f"跳过: {stats['skipped']} 条")
        logger.info(f"失败: {stats['failed']} 条")

        logger.info("状态分布:")
        for status, count in sorted(stats['status_count'].items()):
            logger.info(f"  {status}: {count} 条")

        return stats

    except Exception as e:
        logger.error(f"迁移过程出错: {e}")
        raise


def verify_migration():
    """验证迁移结果"""
    logger.info("验证迁移结果...")

    # 统计各状态消息数量
    status_counts = {}

    for status in MessageStatus:
        count = len(redis_manager.client.zrange(f"index:msg:{status.value}", 0, -1))
        status_counts[status.value] = count
        logger.info(f"{status.value}: {count} 条")

    # 检查兼容索引
    legacy_counts = {}
    for status in ['pending', 'approved', 'rejected']:
        count = len(redis_manager.client.zrange(f"index:msg:{status}", 0, -1))
        legacy_counts[status] = count
        logger.info(f"兼容索引 {status}: {count} 条")

    return status_counts, legacy_counts


if __name__ == '__main__':
    try:
        # 执行迁移
        stats = migrate_messages()

        # 验证结果
        logger.info("\n" + "="*50)
        status_counts, legacy_counts = verify_migration()

        logger.info("\n迁移完成！")

    except Exception as e:
        logger.error(f"迁移失败: {e}")
        sys.exit(1)