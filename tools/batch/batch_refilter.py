#!/usr/bin/env python3
"""
批量重新过滤消息工具
使用最新的训练数据重新过滤所有pending状态的消息
"""
import asyncio
import sys
import logging
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

from app.storage.redis_store import init_redis_stores, get_redis_message_store
from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.services.content_filter import content_filter

# 直接使用Redis URL，避免复杂的配置依赖
REDIS_URL = "redis://localhost:6379"

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def batch_refilter(status_filter="pending", limit=None):
    """
    批量重新过滤消息
    
    Args:
        status_filter: 过滤消息状态 (pending/all)
        limit: 限制处理数量
    """
    # 初始化Redis存储
    init_redis_stores(REDIS_URL)
    redis_store = get_redis_message_store()
    
    # 获取消息列表
    if status_filter == "all":
        messages = redis_store.get_all_messages(limit=limit or 1000)
    else:
        messages = redis_store.get_messages_by_status(status_filter, limit=limit or 1000)
    
    logger.info(f"找到 {len(messages)} 条{status_filter}消息")
    
    if not messages:
        logger.info("没有需要处理的消息")
        return
    
    # 强制重新加载训练数据
    logger.info("重新加载训练数据...")
    intelligent_tail_filter._load_training_data(force_reload=True)
    
    # 统计
    total = len(messages)
    updated = 0
    reduced_total = 0
    
    for i, msg in enumerate(messages, 1):
        if not msg.get('content'):
            logger.debug(f"消息 {msg.get('channel_id')}:{msg.get('message_id')} 内容为空，跳过")
            continue
        
        try:
            # 重新过滤
            filtered_content = content_filter.filter_promotional_content(
                msg['content'],
                channel_id=str(msg.get('channel_id')) if msg.get('channel_id') else None
            )
            
            # 计算变化
            original_len = len(msg['content'])
            new_len = len(filtered_content)
            reduction = original_len - new_len
            
            # 只有内容变化时才更新
            old_filtered = msg.get('filtered_content', '')
            if old_filtered != filtered_content:
                # 更新Redis中的消息
                channel_id = str(msg['channel_id'])
                message_id = int(msg['message_id'])
                
                # 获取完整消息数据并更新
                full_msg = redis_store.get_message(channel_id, message_id)
                if full_msg:
                    full_msg['filtered_content'] = filtered_content
                    redis_store.save_message(channel_id, message_id, full_msg)
                    
                    updated += 1
                    reduced_total += reduction
                    logger.info(f"[{i}/{total}] 消息 {channel_id}:{message_id}: {original_len} -> {new_len} (-{reduction})")
                else:
                    logger.warning(f"[{i}/{total}] 无法获取完整消息数据: {channel_id}:{message_id}")
            else:
                logger.debug(f"[{i}/{total}] 消息 {msg.get('channel_id')}:{msg.get('message_id')}: 内容未变化")
                
        except Exception as e:
            logger.error(f"处理消息 {msg.get('channel_id')}:{msg.get('message_id')} 失败: {e}")
    
    # 显示结果
    if updated > 0:
        logger.info(f"\n✅ 批量过滤完成:")
        logger.info(f"  - 处理消息: {total} 条")
        logger.info(f"  - 更新消息: {updated} 条")
        logger.info(f"  - 总计减少: {reduced_total} 字符")
        logger.info(f"  - 平均减少: {reduced_total//updated if updated else 0} 字符/消息")
    else:
        logger.info("\n没有消息需要更新")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="批量重新过滤消息")
    parser.add_argument(
        "--status",
        default="pending",
        choices=["pending", "all"],
        help="过滤消息状态 (默认: pending)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制处理数量"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="测试运行，不实际更新数据库"
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("🔍 测试模式，不会实际更新数据库")
    
    await batch_refilter(args.status, args.limit)


if __name__ == "__main__":
    asyncio.run(main())