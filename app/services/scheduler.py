"""
消息调度服务
"""
import logging
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
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
        
        # 每6小时清理临时媒体文件
        self.scheduler.add_job(
            self.cleanup_temp_media,
            'interval',
            hours=6,
            id='cleanup_temp_media'
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
    
    async def cleanup_temp_media(self):
        """清理临时媒体文件目录"""
        try:
            temp_media_dir = Path("temp_media")
            
            if not temp_media_dir.exists():
                logger.debug("temp_media目录不存在，跳过清理")
                return
            
            # 获取当前时间
            current_time = time.time()
            # 1天前的时间戳（86400秒 = 24小时）
            one_day_ago = current_time - 86400
            
            deleted_count = 0
            deleted_size = 0
            
            # 遍历temp_media目录下的所有文件
            for file_path in temp_media_dir.iterdir():
                if file_path.is_file():
                    # 获取文件的修改时间
                    file_mtime = file_path.stat().st_mtime
                    
                    # 如果文件超过1天没有修改，删除它
                    if file_mtime < one_day_ago:
                        file_size = file_path.stat().st_size
                        try:
                            file_path.unlink()
                            deleted_count += 1
                            deleted_size += file_size
                            logger.debug(f"删除过期媒体文件: {file_path.name}")
                        except Exception as e:
                            logger.error(f"删除文件失败 {file_path.name}: {e}")
            
            if deleted_count > 0:
                # 转换文件大小为可读格式
                if deleted_size > 1024 * 1024:  # MB
                    size_str = f"{deleted_size / (1024 * 1024):.2f} MB"
                elif deleted_size > 1024:  # KB
                    size_str = f"{deleted_size / 1024:.2f} KB"
                else:
                    size_str = f"{deleted_size} bytes"
                
                logger.info(f"清理临时媒体文件完成: 删除 {deleted_count} 个文件，释放 {size_str} 空间")
            else:
                logger.debug("没有需要清理的临时媒体文件")
                
        except Exception as e:
            logger.error(f"清理临时媒体文件失败: {e}")