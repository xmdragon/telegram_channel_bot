"""
消息调度服务
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.message_processor import MessageProcessor

logger = logging.getLogger(__name__)

class MessageScheduler:
    """消息调度器"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.message_processor = MessageProcessor()
    
    def start(self):
        """启动调度器"""
        # 每分钟检查一次需要自动转发的消息
        self.scheduler.add_job(
            self.check_auto_forward,
            'interval',
            minutes=1,
            id='auto_forward_check'
        )
        
        # 每小时清理过期数据
        self.scheduler.add_job(
            self.cleanup_old_data,
            'interval',
            hours=1,
            id='cleanup_data'
        )
        
        self.scheduler.start()
        logger.info("消息调度器已启动")
    
    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("消息调度器已关闭")
    
    async def check_auto_forward(self):
        """检查并处理自动转发"""
        try:
            messages = await self.message_processor.get_auto_forward_messages()
            for message in messages:
                await self.message_processor.auto_forward_message(message)
                
        except Exception as e:
            logger.error(f"自动转发检查失败: {e}")
    
    async def cleanup_old_data(self):
        """清理旧数据"""
        try:
            # 这里可以添加清理逻辑，比如删除30天前的已处理消息
            logger.info("执行数据清理任务")
            
        except Exception as e:
            logger.error(f"数据清理失败: {e}")