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
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class MessageScheduler:
    """消息调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.message_processor = MessageProcessor()

    def start(self):
        """启动调度器 - 包含数据清理和自动转发"""
        from datetime import datetime

        # 每小时清理过期数据
        self.scheduler.add_job(
            self.cleanup_old_data,
            'interval',
            hours=1,
            id='cleanup_data',
            next_run_time=datetime.now(),  # 立即执行一次
            max_instances=1  # 防止重叠执行
        )

        # 每小时清理日志文件（保留1天的日志，error.log除外）
        self.scheduler.add_job(
            self.cleanup_old_logs,
            'interval',
            hours=1,
            id='cleanup_logs',
            next_run_time=datetime.now(),  # 立即执行一次
            max_instances=1  # 防止重叠执行
        )

        # 自动转发任务 - 改为持续运行模式
        self.scheduler.add_job(
            auto_forwarder.run_continuous,
            'date',  # 只运行一次，内部会持续循环
            run_date=datetime.now(),
            id='auto_forward_continuous',
            max_instances=1  # 确保只有一个实例
        )

        # 新增：频道信息同步任务 - 每小时执行一次
        self.scheduler.add_job(
            self.sync_channel_info,
            'interval',
            hours=1,
            id='channel_sync',
            max_instances=1,  # 防止任务重叠
            misfire_grace_time=300  # 错过执行时间5分钟内仍会执行
        )

        self.scheduler.start()
        logger.info("消息调度器已启动 (包含自动转发和频道同步)")
    
    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("消息调度器已关闭")
    
    async def cleanup_old_data(self):
        """清理旧数据 - 删除配置时间前已发布或拒绝的消息"""
        try:
            from datetime import datetime, timedelta
            from app.services.config_manager import config_manager

            logger.info(f"⏰ [清理任务] 开始执行数据清理 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # 从配置文件读取清理时间间隔（小时）
            cleanup_interval_hours = await config_manager.get_config('scheduler.data_cleanup_interval_hours', 24)
            cleanup_interval_hours = int(cleanup_interval_hours)

            logger.info(f"[清理任务] 使用配置的清理间隔: {cleanup_interval_hours}小时")

            # 计算清理时间点
            cleanup_time_ago = get_current_time() - timedelta(hours=cleanup_interval_hours)

            # 使用MessageProcessor获取旧消息（业务逻辑层）
            messages_to_delete = await self.message_processor.get_old_messages_for_cleanup(cleanup_time_ago)

            if not messages_to_delete:
                logger.info(f"[清理任务] 没有需要清理的旧消息（清理间隔: {cleanup_interval_hours}小时）")
                return

            logger.info(f"[清理任务] 找到 {len(messages_to_delete)} 条需要清理的消息")
            
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

            logger.info(f"✅ [清理任务] 完成 - 清理{deleted_count}条消息，{deleted_media_count}个媒体文件（间隔: {cleanup_interval_hours}小时）")
            
        except Exception as e:
            logger.error(f"❌ [清理任务] 数据清理失败: {e}")

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

    async def sync_channel_info(self):
        """同步频道信息 - 检查名称和标题变化"""
        try:
            logger.info("开始同步频道信息...")

            # 导入频道同步服务
            from app.services.channel_info_sync import channel_info_sync

            # 执行同步
            result = await channel_info_sync.sync_all_channels()

            if result["success"]:
                if result["updated_count"] > 0:
                    logger.info(f"频道信息同步完成: 更新了 {result['updated_count']} 个频道")

                    # 记录具体的更新信息
                    for update in result["updates"]:
                        logger.info(f"频道 {update['channel_name']} 发生变化: {', '.join(update['changes'])}")
                else:
                    logger.debug("频道信息同步完成: 没有发现变化")
            else:
                logger.error(f"频道信息同步失败: {result.get('errors', [])}")

        except Exception as e:
            logger.error(f"频道信息同步异常: {e}")

