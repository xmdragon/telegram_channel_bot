"""
媒体资源处理服务
下载、管理和清理媒体文件
"""
import asyncio
import os
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
import time

from telethon import TelegramClient
# Python 3.13兼容性修复：必须在模块顶部导入所有类型
from telethon.tl.types import (
    MessageMediaPhoto, 
    MessageMediaDocument, 
    MessageMediaWebPage
)
from app.core.config import db_settings

logger = logging.getLogger(__name__)

# 视觉哈希计算功能已移除，保持下载功能的单一职责
# 视觉相似度检测应在后续处理阶段进行，而不是在下载阶段

class MediaHandler:
    """媒体文件处理器"""
    
    def __init__(self):
        from app.core.path_config import PathConfig
        self.temp_dir = PathConfig.TEMP_MEDIA_DIR
        self.temp_dir.mkdir(exist_ok=True)
        self.cleanup_interval = 7200  # 2小时清理一次
        self.file_ttl = 86400  # 文件保留24小时
        self._cleanup_task = None
        
        # 下载进度监控
        self._download_progress = {}  # {message_id: {"last_progress": current, "last_time": time}}
        self._progress_stall_timeout = 300  # 5分钟无进度则认为卡住
        
        # 进度输出控制
        self._download_started = set()  # 已开始下载的消息ID
        self._last_mb_logged = {}  # {message_id: last_mb_logged}
        
        # 下载优化配置
        self.max_download_size = 1024 * 1024 * 1024  # 1GB（从512MB提升）
        self.default_timeout = 1800.0  # 30分钟统一超时
        self.max_retry_attempts = 2  # 最大重试次数
        self._last_percent_logged = {}  # {message_id: last_percent_logged}
        self._download_start_time = {}  # {message_id: start_time}
        
    async def start(self):
        """启动媒体处理器"""
        # 启动定期清理任务
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("媒体处理器已启动")
            
    async def stop(self):
        """停止媒体处理器"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("媒体处理器已停止")
            
    async def _download_progress_callback(self, current: int, total: int, message_id: str, media_type: str):
        """下载进度回调函数 - 显示详细的MB进度"""
        now = time.time()
        
        # MB转换
        mb_current = current / (1024 * 1024)
        mb_total = total / (1024 * 1024) if total > 0 else 0
        
        # 检测卡住
        if message_id in self._download_progress:
            last_progress = self._download_progress[message_id]["last_progress"]
            last_time = self._download_progress[message_id]["last_time"]
            
            # 检测是否卡住（进度无变化超过5分钟）
            if current == last_progress and now - last_time > self._progress_stall_timeout:
                logger.error(f"🚨 下载卡住: 消息 {message_id} 在{self._progress_stall_timeout/60:.1f}分钟内无进度")
                # 抛出异常中断下载
                raise asyncio.TimeoutError(f"下载卡住超过{self._progress_stall_timeout}秒")
        
        # 更新进度记录
        self._download_progress[message_id] = {
            "last_progress": current,
            "last_time": now
        }
        
        # 首次下载日志
        if message_id not in self._download_started:
            self._download_started.add(message_id)
            self._download_start_time[message_id] = now
            if total > 0:
                logger.info(f"🚀 开始下载 [{media_type}] 消息 {message_id}: 总大小 {mb_total:.2f}MB")
            else:
                logger.info(f"🚀 开始下载 [{media_type}] 消息 {message_id}: 大小未知")
        
        # 进度日志
        if total > 0:
            percent = current * 100 / total
            
            # 根据文件大小决定进度报告频率
            should_log = False
            if mb_total > 10:  # 大于10MB的文件
                # 每1MB报告一次
                last_mb = self._last_mb_logged.get(message_id, -1)
                if int(mb_current) != int(last_mb):
                    should_log = True
                    self._last_mb_logged[message_id] = int(mb_current)
            else:
                # 小文件每10%报告一次
                last_percent = self._last_percent_logged.get(message_id, -1)
                if int(percent / 10) != int(last_percent / 10):
                    should_log = True
                    self._last_percent_logged[message_id] = percent
            
            # 输出进度（包括最后1%确保显示100%）
            if should_log or percent >= 99:
                logger.info(f"📥 [{media_type}] {message_id}: {mb_current:.1f}MB/{mb_total:.1f}MB ({percent:.0f}%)")
            
            # 完成日志
            if percent >= 100 and message_id in self._download_start_time:
                elapsed = now - self._download_start_time[message_id]
                speed = mb_total / elapsed if elapsed > 0 else 0
                logger.info(f"✅ 下载完成 [{media_type}] {message_id}: {mb_total:.2f}MB, 耗时{elapsed:.1f}秒, 速度{speed:.1f}MB/s")
                
                # 清理记录
                self._download_started.discard(message_id)
                self._last_mb_logged.pop(message_id, None)
                self._last_percent_logged.pop(message_id, None)
                self._download_start_time.pop(message_id, None)
                self._download_progress.pop(message_id, None)
        else:
            # 大小未知的情况
            logger.info(f"📥 [{media_type}] {message_id}: 已下载 {mb_current:.1f}MB (大小未知)")
    
    async def download_media_with_retry(self, client: TelegramClient, message, message_id: int, max_retries: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """带重试机制的媒体下载"""
        if max_retries is None:
            max_retries = self.max_retry_attempts
        
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = await self.download_media(client, message, message_id)
                if result:  # 成功
                    if attempt > 0:
                        logger.info(f"媒体下载重试成功 (第{attempt+1}次尝试): {message_id}")
                    return result
                elif attempt < max_retries:  # 失败但还能重试
                    logger.warning(f"媒体下载失败，准备重试 {attempt+1}/{max_retries}: {message_id}")
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                    
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"媒体下载异常，重试 {attempt+1}/{max_retries}: {e}")
                    await asyncio.sleep(2 ** attempt)  # 指数退避
        
        logger.error(f"媒体下载最终失败 (已重试{max_retries}次): {message_id}, 最后错误: {last_error}")
        return None

    async def download_media(self, client: TelegramClient, message, message_id: int, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        下载消息中的媒体文件
        
        Args:
            client: Telegram客户端
            message: Telegram消息对象
            message_id: 消息ID（用于文件命名）
            timeout: 自定义超时时间（秒），None则使用默认值
            
        Returns:
            媒体文件信息字典或None
        """
        try:
            if not message.media:
                return None
                
            # 生成唯一文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_prefix = f"{message_id}_{timestamp}"
            
            media_info = {
                "message_id": message_id,
                "media_type": None,
                "file_path": None,
                "file_size": 0,
                "file_name": None,
                "mime_type": None,
                "download_time": datetime.utcnow().isoformat()
            }
            
            if isinstance(message.media, MessageMediaPhoto):
                # 处理图片
                media_info["media_type"] = "photo"
                file_name = f"{file_prefix}_photo.jpg"
                file_path = self.temp_dir / file_name
                
                # 🔥 Linus式修复：统一超时设置
                if timeout:
                    download_timeout = timeout
                else:
                    # 统一使用1800秒，图片和大文件一视同仁
                    download_timeout = 1800.0
                try:
                    # 创建进度回调函数
                    progress_callback = lambda current, total: asyncio.create_task(
                        self._download_progress_callback(current, total, str(message_id), "photo")
                    )
                    
                    await asyncio.wait_for(
                        client.download_media(
                            message.media, 
                            file_path,
                            progress_callback=progress_callback
                        ),
                        timeout=download_timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"下载图片超时（{download_timeout}秒）: {file_name}")
                    # 检查文件是否实际已经下载完成
                    if file_path.exists() and file_path.stat().st_size > 0:
                        logger.debug(f"✅ 虽然超时，但图片下载完成: {file_name} ({file_path.stat().st_size} bytes)")
                    else:
                        logger.error(f"❌ 图片下载真正失败，文件不存在: {file_name}")
                        return None
                
                # 🔥 Linus式修复：下载功能保持简单，不做额外处理
                media_info.update({
                    "file_path": str(file_path),
                    "file_name": file_name,
                    "file_size": file_path.stat().st_size if file_path.exists() else 0,
                    "mime_type": "image/jpeg"
                })
                
                logger.debug(f"图片下载完成: {file_name} ({media_info['file_size']} bytes)")
                return media_info  # 🔥 关键修复：添加缺少的return语句
                
            elif isinstance(message.media, MessageMediaDocument):
                # 处理文档/视频/动图/音频等
                document = message.media.document
                
                # 确定文件类型和扩展名
                mime_type = document.mime_type or "application/octet-stream"
                if mime_type.startswith("video/"):
                    media_info["media_type"] = "video"
                    extension = ".mp4"
                elif mime_type.startswith("image/"):
                    if "gif" in mime_type:
                        media_info["media_type"] = "animation"
                        extension = ".gif"
                    else:
                        media_info["media_type"] = "photo"
                        extension = ".jpg"
                elif mime_type.startswith("audio/"):
                    media_info["media_type"] = "audio"
                    extension = ".mp3"
                else:
                    media_info["media_type"] = "document"
                    extension = ".bin"
                
                # 尝试从文档属性获取原始文件名
                original_name = None
                for attr in document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        original_name = attr.file_name
                        extension = os.path.splitext(original_name)[1] or extension
                        break
                
                # 检查危险文件类型
                dangerous_extensions = ['.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js', '.jar', '.msi', '.dll']
                if extension.lower() in dangerous_extensions:
                    logger.warning(f"🚫 检测到危险文件类型: {original_name or extension}，跳过下载")
                    return None
                
                file_name = f"{file_prefix}_{media_info['media_type']}{extension}"
                file_path = self.temp_dir / file_name
                
                # 检查文件大小限制
                if document.size > self.max_download_size:
                    logger.warning(f"文件太大，跳过下载: {document.size/1024/1024:.1f}MB > {self.max_download_size/1024/1024:.1f}MB")
                    return None
                
                # 下载文档
                download_timeout = timeout if timeout else self.default_timeout
                
                try:
                    # 创建进度回调函数
                    progress_callback = lambda current, total: asyncio.create_task(
                        self._download_progress_callback(current, total, str(message_id), media_info["media_type"])
                    )
                    
                    await asyncio.wait_for(
                        client.download_media(
                            message.media, 
                            file_path,
                            progress_callback=progress_callback
                        ),
                        timeout=download_timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"下载{media_info['media_type']}超时（{download_timeout}秒）: {file_name}")
                    # 检查文件是否实际已经下载完成
                    if file_path.exists() and file_path.stat().st_size > 0:
                        logger.debug(f"✅ 虽然超时，但文件下载完成: {file_name} ({file_path.stat().st_size} bytes)")
                    else:
                        logger.error(f"❌ 文件下载真正失败: {file_name}")
                        return None
                
                # 更新媒体信息
                media_info.update({
                    "file_path": str(file_path),
                    "file_name": file_name,
                    "file_size": file_path.stat().st_size if file_path.exists() else 0,
                    "mime_type": mime_type,
                    "original_name": original_name
                })
                
                logger.debug(f"{media_info['media_type']}下载完成: {file_name} ({media_info['file_size']} bytes)")
                return media_info
                
            elif isinstance(message.media, MessageMediaWebPage):
                # 处理链接预览（智能提取真实媒体内容）
                webpage = message.media.webpage
                
                # 检查预览图片或嵌入媒体（如视频）
                if (hasattr(webpage, 'photo') and webpage.photo) or (hasattr(webpage, 'document') and webpage.document):
                    return await self._download_preview_image(client, webpage, file_prefix, timeout, message_id)
                
                # 最后尝试从URL解析媒体
                elif hasattr(webpage, 'url') and webpage.url:
                    return await self._extract_media_from_url(webpage.url, file_prefix)
                
                else:
                    # 纯链接，没有可下载的媒体
                    logger.debug(f"链接预览没有可下载的媒体: {webpage.url if hasattr(webpage, 'url') else 'unknown'}")
                    return None
                    
            else:
                # 不支持的媒体类型
                logger.debug(f"不支持的媒体类型: {type(message.media)}")
                return None
                
        except Exception as e:
            logger.error(f"下载媒体文件失败: {e}")
            return None
        finally:
            # 清理进度监控记录
            message_id_str = str(message_id)
            if message_id_str in self._download_progress:
                del self._download_progress[message_id_str]
    
    async def _download_preview_image(self, client: TelegramClient, webpage, file_prefix: str, timeout: Optional[float], message_id: int) -> Optional[Dict[str, Any]]:
        """下载网页预览图片或嵌入媒体"""
        try:
            media_info = {}
            
            # 检查是否有预览图片
            if hasattr(webpage, 'photo') and webpage.photo:
                media_info["media_type"] = "webpage_photo"
                file_name = f"{file_prefix}_webpage_photo.jpg"
                file_path = self.temp_dir / file_name
                
                # 下载预览图片
                download_timeout = timeout if timeout else 1800.0
                
                try:
                    # 创建进度回调函数
                    progress_callback = lambda current, total: asyncio.create_task(
                        self._download_progress_callback(current, total, str(message_id), "webpage_photo")
                    )
                    
                    await asyncio.wait_for(
                        client.download_media(
                            webpage.photo, 
                            file_path,
                            progress_callback=progress_callback
                        ),
                        timeout=download_timeout
                    )
                    
                    # 🔥 简化：专注于下载，不做额外处理
                    media_info.update({
                        "file_path": str(file_path),
                        "file_name": file_name,
                        "file_size": file_path.stat().st_size if file_path.exists() else 0,
                        "mime_type": "image/jpeg",
                        "webpage_url": webpage.url if hasattr(webpage, 'url') else None,
                        "webpage_title": webpage.title if hasattr(webpage, 'title') else None
                    })
                    
                    logger.debug(f"链接预览图片下载完成: {file_name} ({media_info['file_size']} bytes)")
                    return media_info
                        
                except asyncio.TimeoutError:
                    logger.debug(f"下载链接预览图片超时: {file_name}")
                    return None
                except Exception as e:
                    logger.debug(f"下载链接预览图片失败: {e}")
                    return None
            
            # 检查是否有嵌入文档（如嵌入视频）
            elif hasattr(webpage, 'document') and webpage.document:
                document = webpage.document
                
                # 确定文件类型
                mime_type = document.mime_type or "application/octet-stream"
                if mime_type.startswith("video/"):
                    media_info["media_type"] = "webpage_video"
                    extension = ".mp4"
                else:
                    media_info["media_type"] = "webpage_document"
                    extension = ".bin"
                
                file_name = f"{file_prefix}_webpage{extension}"
                file_path = self.temp_dir / file_name
                
                # 检查文件大小限制
                if document.size > self.max_download_size:
                    logger.warning(f"链接嵌入文件太大，跳过下载: {document.size/1024/1024:.1f}MB > {self.max_download_size/1024/1024:.1f}MB")
                    return None
                
                # 下载嵌入文档
                download_timeout = timeout if timeout else 1800.0
                
                try:
                    # 创建进度回调函数
                    progress_callback = lambda current, total: asyncio.create_task(
                        self._download_progress_callback(current, total, str(message_id), "webpage_document")
                    )
                    
                    await asyncio.wait_for(
                        client.download_media(
                            webpage.document, 
                            file_path,
                            progress_callback=progress_callback
                        ),
                        timeout=download_timeout
                    )
                    
                    # 计算文件哈希
                    file_hash = None
                    if file_path.exists():
                        # 可以在这里添加哈希计算逻辑
                        pass
                    
                    media_info.update({
                        "file_path": str(file_path),
                        "file_name": file_name,
                        "file_size": file_path.stat().st_size if file_path.exists() else 0,
                        "mime_type": mime_type,
                        "hash": file_hash,
                        "webpage_url": webpage.url if hasattr(webpage, 'url') else None,
                        "webpage_title": webpage.title if hasattr(webpage, 'title') else None
                    })
                    
                    logger.debug(f"链接嵌入媒体下载完成: {file_name} ({media_info['file_size']} bytes)")
                    return media_info
                    
                except asyncio.TimeoutError:
                    logger.debug(f"下载链接嵌入媒体超时: {file_name}")
                    return None
                except Exception as e:
                    logger.debug(f"下载链接嵌入媒体失败: {e}")
                    return None
            
            else:
                # 纯链接，没有可下载的媒体
                logger.debug(f"链接预览没有可下载的媒体: {webpage.url if hasattr(webpage, 'url') else 'unknown'}")
                return None
                
        except Exception as e:
            logger.error(f"下载网页预览媒体失败: {e}")
            return None
            
    async def _extract_media_from_url(self, url: str, file_prefix: str) -> Optional[Dict[str, Any]]:
        """从URL中提取媒体内容（简化版本）"""
        logger.debug(f"尝试从URL提取媒体: {url}")
        # 这里可以添加更复杂的URL媒体提取逻辑
        # 目前只是占位符
        return None
    async def get_media_url(self, file_path: str) -> Optional[str]:
        """
        获取媒体文件的访问URL
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件访问URL
        """
        try:
            if not os.path.exists(file_path):
                return None
                
            # 生成相对于temp_media目录的路径
            rel_path = os.path.relpath(file_path, self.temp_dir)
            return f"/{self.temp_dir.name}/{rel_path}"
            
        except Exception as e:
            logger.error(f"生成媒体URL失败: {e}")
            return None
            
    async def cleanup_file(self, file_path: str):
        """
        清理指定文件
        
        Args:
            file_path: 要清理的文件路径
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"已清理文件: {file_path}")
        except Exception as e:
            logger.error(f"清理文件失败: {file_path}, 错误: {e}")
            
    async def cleanup_message_files(self, message_id: int):
        """
        清理指定消息的所有媒体文件
        
        Args:
            message_id: 消息ID
        """
        try:
            # 查找以message_id开头的文件
            pattern = f"{message_id}_*"
            for file_path in self.temp_dir.glob(pattern):
                await self.cleanup_file(str(file_path))
                
            logger.info(f"已清理消息 {message_id} 的所有媒体文件")
            
        except Exception as e:
            logger.error(f"清理消息媒体文件失败: {message_id}, 错误: {e}")
            
    async def _cleanup_loop(self):
        """定期清理过期文件"""
        while True:
            try:
                await self._cleanup_expired_files()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                logger.error(f"清理循环出错: {e}")
                await asyncio.sleep(60)  # 出错时等待1分钟
                
    async def _cleanup_expired_files(self):
        """清理过期文件"""
        try:
            cutoff_time = datetime.now() - timedelta(seconds=self.file_ttl)
            cleaned_count = 0
            
            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    # 检查文件修改时间
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff_time:
                        await self.cleanup_file(str(file_path))
                        cleaned_count += 1
                        
            if cleaned_count > 0:
                logger.info(f"定期清理完成，已清理 {cleaned_count} 个过期文件")
                
        except Exception as e:
            logger.error(f"定期清理失败: {e}")
            
    async def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        获取文件信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件信息字典
        """
        try:
            if not os.path.exists(file_path):
                return None
                
            stat = os.stat(file_path)
            return {
                "file_path": file_path,
                "file_name": os.path.basename(file_path),
                "file_size": stat.st_size,
                "created_time": datetime.fromtimestamp(stat.st_ctime),
                "modified_time": datetime.fromtimestamp(stat.st_mtime),
                "exists": True,
                "hash": None
            }
            
        except Exception as e:
            logger.error(f"获取文件信息失败: {file_path}, 错误: {e}")
            return None
            
    
    async def process_media_group(self, media_list: List[Dict[str, Any]]) -> Optional[str]:
        """
        处理媒体组合并计算组合哈希
        
        Args:
            media_list: 媒体信息列表
            
        Returns:
            组合媒体的哈希值
        """
        try:
            if not media_list:
                return None
            
            # 收集所有媒体的哈希值
            hash_list = []
            for media in sorted(media_list, key=lambda x: x.get('message_id', 0)):
                if media.get('hash'):
                    hash_list.append(media['hash'])
            
            if hash_list:
                # 将所有哈希值组合起来计算最终哈希
                combined_hash_data = ''.join(hash_list)
                return hashlib.sha256(combined_hash_data.encode()).hexdigest()
            
            return None
            
        except Exception as e:
            logger.error(f"处理媒体组合哈希失败: {e}")
            return None
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            total_size = 0
            file_count = 0
            
            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    total_size += file_path.stat().st_size
                    file_count += 1
                    
            return {
                "temp_dir": str(self.temp_dir),
                "total_files": file_count,
                "total_size": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "dir_exists": self.temp_dir.exists()
            }
            
        except Exception as e:
            logger.error(f"获取存储统计失败: {e}")
            return {
                "temp_dir": str(self.temp_dir),
                "total_files": 0,
                "total_size": 0,
                "total_size_mb": 0,
                "dir_exists": False,
                "error": str(e)
            }

# 全局媒体处理器实例
media_handler = MediaHandler()