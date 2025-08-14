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
        
        # 每小时清理日志文件（保留1天的日志，error.log除外）
        self.scheduler.add_job(
            self.cleanup_old_logs,
            'interval',
            hours=1,
            id='cleanup_logs'
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
            # 检查是否启用自动转发
            from app.services.config_manager import config_manager
            auto_forward_enabled = await config_manager.get_config("review.auto_forward_enabled", True)
            
            if not auto_forward_enabled:
                # 自动转发已禁用
                return
            
            messages = await self.message_processor.get_auto_forward_messages()
            if messages:
                logger.info(f"发现 {len(messages)} 条消息需要自动转发")
            
            for message in messages:
                await self.message_processor.auto_forward_message(message)
                
        except Exception as e:
            logger.error(f"自动转发检查失败: {e}")
    
    async def cleanup_old_data(self):
        """清理旧数据 - 删除7天前已发布或拒绝的消息"""
        try:
            from app.storage.redis_store import get_redis_message_store
            from datetime import datetime, timedelta
            
            # 计算7天前的时间
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            
            # 使用Redis存储获取旧消息
            message_store = get_redis_message_store()
            messages_to_delete = await message_store.get_old_messages_for_cleanup(seven_days_ago)
            
            if not messages_to_delete:
                logger.debug("没有需要清理的旧消息")
                return
                
                deleted_count = 0
                deleted_media_count = 0
                
                # 收集要删除的媒体文件路径
                media_files_to_delete = []
                
                for message in messages_to_delete:
                    # 检查是否有媒体文件
                    if message.media_url:
                        # 媒体URL格式通常是 /temp_media/xxxxx 或本地路径
                        if message.media_url.startswith('/temp_media/'):
                            # 转换为本地文件路径
                            media_path = Path('temp_media') / message.media_url.replace('/temp_media/', '')
                            if media_path.exists():
                                media_files_to_delete.append(media_path)
                    
                    # 如果是组合消息，检查组合消息中的媒体
                    if message.is_combined and message.combined_messages:
                        for combined_msg in message.combined_messages:
                            if isinstance(combined_msg, dict) and 'media_url' in combined_msg:
                                media_url = combined_msg['media_url']
                                if media_url and media_url.startswith('/temp_media/'):
                                    media_path = Path('temp_media') / media_url.replace('/temp_media/', '')
                                    if media_path.exists():
                                        media_files_to_delete.append(media_path)
                    
                    # 删除Redis中的消息记录
                    if await message_store.delete_message(message.channel_id, message.message_id):
                        deleted_count += 1
                
                # 删除媒体文件
                for media_path in media_files_to_delete:
                    try:
                        media_path.unlink()
                        deleted_media_count += 1
                        logger.debug(f"删除媒体文件: {media_path.name}")
                    except Exception as e:
                        logger.error(f"删除媒体文件失败 {media_path.name}: {e}")
                
                logger.info(f"数据清理完成: 删除 {deleted_count} 条消息记录, {deleted_media_count} 个媒体文件")
            
        except Exception as e:
            logger.error(f"数据清理失败: {e}")
    
    async def cleanup_temp_media(self):
        """清理临时媒体文件目录（只删除未被引用的文件）"""
        try:
            temp_media_dir = Path("temp_media")
            
            if not temp_media_dir.exists():
                logger.debug("temp_media目录不存在，跳过清理")
                return
            
            # 获取当前时间
            current_time = time.time()
            # 1天前的时间戳（86400秒 = 24小时）
            one_day_ago = current_time - 86400
            
            # 获取Redis中所有引用的媒体文件
            from app.storage.redis_store import get_redis_message_store
            message_store = get_redis_message_store()
            referenced_files = set()
            
            # 从所有频道获取消息信息
            channel_patterns = message_store.redis.keys('msg:idx:*')
            for pattern in channel_patterns:
                if pattern.startswith(b'msg:idx:') and b':' in pattern[8:]:
                    try:
                        channel_id = pattern[8:].decode('utf-8')
                        if channel_id in ['pending', 'approved', 'rejected', 'auto_forwarded']:
                            continue
                        
                        messages = message_store.get_messages_by_channel(channel_id, limit=1000)
                        for msg in messages:
                            # 添加主媒体文件
                            if msg.get('media_url'):
                                referenced_files.add(os.path.basename(msg['media_url']))
                            
                            # 添加媒体组中的文件
                            if msg.get('media_group'):
                                try:
                                    import json
                                    media_group = json.loads(msg['media_group']) if isinstance(msg['media_group'], str) else msg['media_group']
                                    if isinstance(media_group, list):
                                        for item in media_group:
                                            if isinstance(item, dict) and item.get('file_path'):
                                                referenced_files.add(os.path.basename(item['file_path']))
                                except:
                                    pass
                    except Exception as e:
                        logger.debug(f'处理频道 {pattern} 失败: {e}')
                        continue
            
            logger.debug(f"数据库中引用了 {len(referenced_files)} 个媒体文件")
            
            deleted_count = 0
            deleted_size = 0
            skipped_count = 0
            
            # 遍历temp_media目录下的所有文件
            for file_path in temp_media_dir.iterdir():
                if file_path.is_file():
                    file_name = file_path.name
                    
                    # 检查文件是否被数据库引用
                    if file_name in referenced_files:
                        skipped_count += 1
                        logger.debug(f"跳过被引用的文件: {file_name}")
                        continue
                    
                    # 获取文件的修改时间
                    file_mtime = file_path.stat().st_mtime
                    
                    # 如果文件超过1天没有修改且未被引用，删除它
                    if file_mtime < one_day_ago:
                        file_size = file_path.stat().st_size
                        try:
                            file_path.unlink()
                            deleted_count += 1
                            deleted_size += file_size
                            logger.debug(f"删除过期且未被引用的文件: {file_name}")
                        except Exception as e:
                            logger.error(f"删除文件失败 {file_name}: {e}")
            
            if deleted_count > 0 or skipped_count > 0:
                # 转换文件大小为可读格式
                if deleted_size > 1024 * 1024:  # MB
                    size_str = f"{deleted_size / (1024 * 1024):.2f} MB"
                elif deleted_size > 1024:  # KB
                    size_str = f"{deleted_size / 1024:.2f} KB"
                else:
                    size_str = f"{deleted_size} bytes"
                
                if deleted_count > 0:
                    logger.info(f"清理临时媒体文件完成: 删除 {deleted_count} 个文件，释放 {size_str} 空间，跳过 {skipped_count} 个被引用的文件")
                else:
                    logger.info(f"清理临时媒体文件: 跳过 {skipped_count} 个被引用的文件，无文件被删除")
            else:
                logger.debug("没有需要清理的临时媒体文件")
                
        except Exception as e:
            logger.error(f"清理临时媒体文件失败: {e}")
    
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