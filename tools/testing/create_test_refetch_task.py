#!/usr/bin/env python3
"""
创建测试媒体补抓任务
"""
import asyncio
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def create_test_task():
    """创建测试媒体补抓任务"""
    logger.info("🔧 创建测试媒体补抓任务...")
    
    try:
        # 初始化Redis连接
        from app.storage.redis_store import init_redis_stores
        from app.services.media_refetch_service import media_refetch_service
        
        # 初始化Redis存储
        if not init_redis_stores():
            logger.error("❌ Redis初始化失败")
            return
        
        # 创建新的测试任务
        test_message_id = "-1001956665373:57742"  # 用户报告的问题消息
        
        task_id = media_refetch_service.submit_task(test_message_id)
        logger.info(f"✅ 测试任务已创建: {task_id} for message {test_message_id}")
        
        # 检查队列状态
        from app.storage.redis_store import get_redis_message_store
        redis_store = get_redis_message_store()
        queue_length = redis_store.redis.llen(media_refetch_service.TASK_QUEUE_KEY)
        logger.info(f"📊 当前队列长度: {queue_length}")
        
    except Exception as e:
        logger.error(f"❌ 创建任务失败: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(create_test_task())