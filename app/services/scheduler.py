"""
消息调度服务 - 纯asyncio实现
"""
import asyncio
import logging
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from app.services.message_processor import MessageProcessor
from app.core.media_paths import media_paths
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class MessageScheduler:
    """消息调度器 - 使用纯asyncio实现"""

    def __init__(self):
        self.message_processor = MessageProcessor()
        self.is_running = False
        self.tasks: Dict[str, asyncio.Task] = {}

    async def start(self):
        """启动所有调度任务"""
        if self.is_running:
            logger.warning("调度器已经在运行中")
            return

        self.is_running = True

        # 启动各个调度任务
        self.tasks['cleanup_data'] = asyncio.create_task(
            self._run_periodic_task(
                self.cleanup_old_data,
                interval_seconds=600,  # 10分钟
                initial_delay=0,  # 立即执行
                task_name="cleanup_data"
            )
        )

        self.tasks['cleanup_orphan_media'] = asyncio.create_task(
            self._run_periodic_task(
                self.cleanup_orphan_media_files,
                interval_seconds=600,  # 10分钟
                initial_delay=300,  # 延迟5分钟开始，错开执行
                task_name="cleanup_orphan_media"
            )
        )

        self.tasks['cleanup_logs'] = asyncio.create_task(
            self._run_periodic_task(
                self.cleanup_old_logs,
                interval_seconds=3600,  # 1小时
                initial_delay=0,  # 立即执行
                task_name="cleanup_logs"
            )
        )

        logger.info("✅ 消息调度器已启动 (纯asyncio实现)")

    async def _run_periodic_task(self, func, interval_seconds: int, initial_delay: int = 0, task_name: str = ""):
        """运行周期性任务的通用方法"""
        try:
            # 初始延迟
            if initial_delay > 0:
                logger.debug(f"任务 {task_name} 将在 {initial_delay} 秒后开始")
                await asyncio.sleep(initial_delay)

            while self.is_running:
                try:
                    logger.debug(f"执行定时任务: {task_name}")
                    await func()
                except asyncio.CancelledError:
                    logger.info(f"任务 {task_name} 被取消")
                    break
                except Exception as e:
                    logger.error(f"任务 {task_name} 执行失败: {e}")

                # 等待下次执行
                await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            logger.info(f"周期任务 {task_name} 已停止")
        except Exception as e:
            logger.error(f"周期任务 {task_name} 异常退出: {e}")

    async def shutdown(self):
        """关闭所有调度任务"""
        logger.info("正在关闭消息调度器...")
        self.is_running = False

        # 取消所有运行中的任务
        for task_name, task in self.tasks.items():
            if task and not task.done():
                logger.debug(f"取消任务: {task_name}")
                task.cancel()

        # 等待所有任务完成
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

        self.tasks.clear()
        logger.info("消息调度器已关闭")
    
    async def cleanup_old_data(self):
        """清理旧数据 - 删除创建时间超过配置时间的消息"""
        try:
            from datetime import datetime, timedelta
            from app.services.config_manager import config_manager

            logger.debug(f"⏰ [清理任务] 开始执行数据清理 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # 从配置文件读取清理时间间隔（小时）
            cleanup_interval_hours = await config_manager.get_config('scheduler.data_cleanup_interval_hours', 8)  # 默认值从24改为8
            cleanup_interval_hours = int(cleanup_interval_hours)

            logger.debug(f"[清理任务] 使用配置的清理间隔: {cleanup_interval_hours}小时")

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

    async def get_earliest_pending_message_time(self):
        """获取最早待审核消息的创建时间"""
        try:
            from datetime import datetime

            # 获取所有待审核消息
            pending_messages = redis_manager.get_messages_by_status('pending', limit=1000)

            if not pending_messages:
                return None

            # 找出最早的创建时间
            earliest_time = None
            for msg in pending_messages:
                created_at = msg.get('created_at')
                if created_at:
                    try:
                        # 解析时间
                        msg_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        if earliest_time is None or msg_time < earliest_time:
                            earliest_time = msg_time
                    except Exception:
                        continue

            return earliest_time

        except Exception as e:
            logger.error(f"获取最早待审核消息时间失败: {e}")
            return None

    async def cleanup_orphan_media_files(self):
        """独立清理超时的孤儿媒体文件 - 基于最早待审核消息时间的智能清理"""
        try:
            from datetime import datetime, timedelta
            from app.services.config_manager import config_manager
            from app.core.path_config import PathConfig

            logger.debug(f"⏰ [媒体清理] 开始执行智能媒体文件清理 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # 获取最早待审核消息的创建时间
            earliest_pending_time = await self.get_earliest_pending_message_time()

            # 根据是否有待审核消息决定清理策略
            if earliest_pending_time:
                # 有待审核消息：使用最早待审核时间减10分钟作为清理界限
                cutoff_time = earliest_pending_time - timedelta(minutes=10)
                logger.info(f"[媒体清理] 基于最早待审核消息时间 {earliest_pending_time.strftime('%Y-%m-%d %H:%M:%S')} 清理")
                cleanup_strategy = "pending_based"
            else:
                # 没有待审核消息：使用配置的清理间隔
                cleanup_interval_hours = await config_manager.get_config('scheduler.data_cleanup_interval_hours', 8)
                cleanup_interval_hours = int(cleanup_interval_hours)
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(hours=cleanup_interval_hours)
                logger.info(f"[媒体清理] 无待审核消息，使用配置间隔 {cleanup_interval_hours}小时 清理")
                cleanup_strategy = "config_based"

            logger.debug(f"[媒体清理] 清理界限时间: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # 确保媒体目录存在
            if not PathConfig.TEMP_MEDIA_DIR.exists():
                logger.debug("[媒体清理] temp_media目录不存在，跳过清理")
                return

            deleted_count = 0
            deleted_size = 0
            skipped_count = 0
            protected_count = 0  # 受保护的文件数量

            # 直接扫描temp_media目录
            for file_path in PathConfig.TEMP_MEDIA_DIR.iterdir():
                if file_path.is_file():
                    try:
                        # 获取文件修改时间
                        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        file_size = file_path.stat().st_size
                        file_name = file_path.name

                        # 如果文件超过清理时间，删除它
                        if file_mtime < cutoff_time:
                            try:
                                file_path.unlink()
                                deleted_count += 1
                                deleted_size += file_size
                                logger.debug(f"[媒体清理] 删除孤立文件: {file_name} (修改时间: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')}, 大小: {file_size} bytes)")
                            except Exception as e:
                                logger.error(f"[媒体清理] 删除文件失败 {file_name}: {e}")
                        else:
                            # 文件在清理界限之后，跳过
                            if cleanup_strategy == "pending_based":
                                protected_count += 1
                                logger.debug(f"[媒体清理] 保护文件: {file_name} (可能属于待审核消息)")
                            else:
                                skipped_count += 1

                    except Exception as e:
                        logger.error(f"[媒体清理] 处理文件时出错 {file_path.name}: {e}")

            # 格式化文件大小
            if deleted_size > 1024 * 1024 * 1024:  # GB
                size_str = f"{deleted_size / (1024 * 1024 * 1024):.2f} GB"
            elif deleted_size > 1024 * 1024:  # MB
                size_str = f"{deleted_size / (1024 * 1024):.2f} MB"
            elif deleted_size > 1024:  # KB
                size_str = f"{deleted_size / 1024:.2f} KB"
            else:
                size_str = f"{deleted_size} bytes"

            # 生成详细的清理报告
            if deleted_count > 0:
                if cleanup_strategy == "pending_based":
                    logger.info(f"✅ [媒体清理] 智能清理完成 - 删除{deleted_count}个孤立文件，释放{size_str}空间（保护{protected_count}个可能属于待审核消息的文件）")
                else:
                    logger.info(f"✅ [媒体清理] 常规清理完成 - 删除{deleted_count}个过期文件，释放{size_str}空间（保留{skipped_count}个新文件）")
            else:
                if cleanup_strategy == "pending_based":
                    logger.debug(f"[媒体清理] 没有需要清理的孤立文件（{protected_count}个文件受保护）")
                else:
                    logger.debug(f"[媒体清理] 没有需要清理的文件（{skipped_count}个文件未到期）")

        except Exception as e:
            logger.error(f"❌ [媒体清理] 独立媒体文件清理失败: {e}")


