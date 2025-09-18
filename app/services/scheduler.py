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
from app.core.media_paths import media_paths
from app.services.auto_forwarder import auto_forwarder

logger = logging.getLogger(__name__)

class MessageScheduler:
    """消息调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.message_processor = MessageProcessor()

    def start(self):
        """启动调度器 - 包含数据清理和自动转发"""
        # 每小时清理过期数据
        self.scheduler.add_job(
            self.cleanup_old_data,
            'interval',
            hours=1,
            id='cleanup_data'
        )

        # 删除独立的媒体清理任务，统一由cleanup_old_data处理
        # 避免消息和媒体文件不同步的问题

        # 每小时清理日志文件（保留1天的日志，error.log除外）
        self.scheduler.add_job(
            self.cleanup_old_logs,
            'interval',
            hours=1,
            id='cleanup_logs'
        )

        # 新增：自动转发任务 - 每30秒执行一次
        self.scheduler.add_job(
            auto_forwarder.check_and_forward,
            'interval',
            seconds=30,
            id='auto_forward',
            max_instances=1,  # 防止任务重叠
            misfire_grace_time=10  # 错过执行时间10秒内仍会执行
        )

        self.scheduler.start()
        logger.info("消息调度器已启动 (包含自动转发)")
    
    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("消息调度器已关闭")
    
    async def cleanup_old_data(self):
        """清理旧数据 - 删除配置时间前已发布或拒绝的消息"""
        try:
            from datetime import datetime, timedelta
            from app.services.config_manager import config_manager
            
            # 从配置文件读取清理时间间隔（小时）
            cleanup_interval_hours = await config_manager.get_config('scheduler.data_cleanup_interval_hours', 24)
            cleanup_interval_hours = int(cleanup_interval_hours)
            
            # 计算清理时间点
            cleanup_time_ago = datetime.utcnow() - timedelta(hours=cleanup_interval_hours)
            
            # 使用MessageProcessor获取旧消息（业务逻辑层）
            messages_to_delete = await self.message_processor.get_old_messages_for_cleanup(cleanup_time_ago)
            
            if not messages_to_delete:
                logger.debug(f"没有需要清理的旧消息（清理间隔: {cleanup_interval_hours}小时）")
                return
            
            logger.info(f"开始清理{cleanup_interval_hours}小时前的数据，找到 {len(messages_to_delete)} 条消息待处理")
            
            deleted_count = 0
            deleted_media_count = 0
            
            # 收集要删除的媒体文件路径
            media_files_to_delete = []
            
            for message in messages_to_delete:
                # 检查是否有媒体文件
                if message.media_url:
                    # 媒体URL格式通常是 /temp_media/xxxxx 或本地路径
                    if message.media_url.startswith(media_paths.TEMP_MEDIA_PATH):
                        # 转换为本地文件路径
                        media_path = Path('temp_media') / message.media_url.replace(media_paths.TEMP_MEDIA_PATH + '/', '')
                        if media_path.exists():
                            media_files_to_delete.append(media_path)
                
                # 如果是组合消息，检查组合消息中的媒体
                if message.is_combined and message.combined_messages:
                    for combined_msg in message.combined_messages:
                        if isinstance(combined_msg, dict) and 'media_url' in combined_msg:
                            media_url = combined_msg['media_url']
                            if media_url and media_url.startswith('/temp_media/'):
                                from app.core.path_config import PathConfig
                                media_path = PathConfig.TEMP_MEDIA_DIR / media_url.replace('/temp_media/', '')
                                if media_path.exists():
                                    media_files_to_delete.append(media_path)
                
                # 删除Redis中的消息记录 - 使用MessageProcessor
                if await self.message_processor.delete_message(message.channel_id, message.message_id):
                    deleted_count += 1
                
            # 删除媒体文件
            for media_path in media_files_to_delete:
                try:
                    media_path.unlink()
                    deleted_media_count += 1
                    logger.debug(f"删除媒体文件: {media_path.name}")
                except Exception as e:
                    logger.error(f"删除媒体文件失败 {media_path.name}: {e}")
            
            logger.info(f"数据清理完成（间隔: {cleanup_interval_hours}小时）: 删除 {deleted_count} 条消息记录, {deleted_media_count} 个媒体文件")
            
        except Exception as e:
            logger.error(f"数据清理失败: {e}")
    
    # cleanup_temp_media方法已删除
    # 所有清理逻辑统一由cleanup_old_data处理，避免不一致
    
    async def cleanup_old_logs(self):
        """清理旧日志文件（保留1天的日志，error.log除外）"""
        try:
            logs_dir = Path("logs")
            
            if not logs_dir.exists():
                logger.debug("logs目录不存在，跳过清理")
                return
            
            # 获取当前时间
            current_time = time.time()
            # 1天前的时间戳（86400秒 = 24小时）
            one_day_ago = current_time - 86400
            
            deleted_count = 0
            deleted_size = 0
            skipped_files = []
            
            # 遍历logs目录下的所有文件
            for file_path in logs_dir.iterdir():
                if file_path.is_file():
                    file_name = file_path.name
                    
                    # 跳过error.log文件
                    if file_name == "error.log":
                        skipped_files.append(file_name)
                        logger.debug(f"跳过保留文件: {file_name}")
                        continue
                    
                    # 只处理.log文件（包括.log.xxx格式的旋转日志）
                    if '.log' not in file_name:
                        continue
                    
                    # 获取文件的修改时间
                    file_mtime = file_path.stat().st_mtime
                    
                    # 如果文件超过1天没有修改，删除它
                    if file_mtime < one_day_ago:
                        file_size = file_path.stat().st_size
                        try:
                            file_path.unlink()
                            deleted_count += 1
                            deleted_size += file_size
                            logger.debug(f"删除过期日志文件: {file_name}")
                        except Exception as e:
                            logger.error(f"删除日志文件失败 {file_name}: {e}")
            
            if deleted_count > 0:
                # 转换文件大小为可读格式
                if deleted_size > 1024 * 1024:  # MB
                    size_str = f"{deleted_size / (1024 * 1024):.2f} MB"
                elif deleted_size > 1024:  # KB
                    size_str = f"{deleted_size / 1024:.2f} KB"
                else:
                    size_str = f"{deleted_size} bytes"
                
                logger.info(f"清理日志文件完成: 删除 {deleted_count} 个文件，释放 {size_str} 空间")
                if skipped_files:
                    logger.info(f"保留的文件: {', '.join(skipped_files)}")
            else:
                logger.debug("没有需要清理的日志文件")
                
        except Exception as e:
            logger.error(f"清理日志文件失败: {e}")
    
