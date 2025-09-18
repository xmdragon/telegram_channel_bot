"""
自动转发服务 - 极简实现
负责定时检查并自动转发符合条件的消息
"""
import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import List

from app.storage.redis_manager import redis_manager
from app.services.config_manager import config_manager

logger = logging.getLogger(__name__)

class AutoForwarder:
    """自动转发服务"""

    async def check_and_forward(self):
        """检查并转发符合条件的消息 - 30秒执行一次"""
        start_time = time.time()

        try:
            # 1. 检查是否启用自动转发
            enabled = await config_manager.get_config('review.auto_forward_enabled', False)
            if not enabled:
                logger.debug("自动转发未启用")
                return

            # 2. 获取延迟配置（默认1800秒 = 30分钟）
            delay_seconds = await config_manager.get_config('review.auto_forward_delay', 1800)
            delay_seconds = int(delay_seconds)
            cutoff_time = datetime.utcnow() - timedelta(seconds=delay_seconds)

            logger.debug(f"自动转发检查: 延迟={delay_seconds}秒, 截止时间={cutoff_time}")

            # 3. 获取所有待审核消息
            pending_messages = redis_manager.get_messages_by_status('pending', limit=1000)

            if not pending_messages:
                logger.debug("没有待审核消息")
                return

            # 4. 筛选符合时间条件的消息ID
            eligible_ids = []

            for msg in pending_messages:
                try:
                    # 检查创建时间
                    created_at_str = msg.get('created_at')
                    if not created_at_str:
                        continue

                    # 解析时间
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    if created_at.tzinfo:
                        created_at = created_at.replace(tzinfo=None)

                    # 时间符合条件就加入
                    if created_at <= cutoff_time:
                        message_id = f"{msg.get('source_channel')}:{msg.get('message_id')}"
                        eligible_ids.append(message_id)

                except Exception as e:
                    logger.error(f"处理消息时间时出错: {e}")
                    continue

            if not eligible_ids:
                logger.debug(f"检查了 {len(pending_messages)} 条消息，没有符合时间条件的")
                return

            # 5. 直接调用现有的批量发送逻辑
            logger.info(f"🔄 自动转发: 发现 {len(eligible_ids)} 条符合条件的消息")

            # 直接导入并调用批量发送的内部逻辑
            from app.api.messages_batch import process_batch_approve

            # 调用内部批量发送函数（跳过HTTP和认证）
            result = await process_batch_approve(
                message_ids=eligible_ids,
                user_id="auto_forward"  # 标记为自动转发
            )

            if result.get('success'):
                logger.info(f"✅ 自动转发完成: 成功 {result.get('approved_count', 0)} 条, 失败 {result.get('failed_count', 0)} 条")
            else:
                logger.error(f"自动转发失败: {result.get('message', 'Unknown error')}")

        except Exception as e:
            logger.error(f"自动转发异常: {e}")

        finally:
            # 6. 确保任务间隔为30秒
            elapsed = time.time() - start_time
            if elapsed < 30:
                sleep_time = 30 - elapsed
                logger.debug(f"任务耗时 {elapsed:.2f} 秒，等待 {sleep_time:.2f} 秒")
                await asyncio.sleep(sleep_time)

# 全局实例
auto_forwarder = AutoForwarder()