"""
统一媒体管理服务
负责媒体文件的下载、缓存、重用，避免重复下载
"""
import os
import logging
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class MediaManager:
    """统一的媒体管理服务"""
    
    def __init__(self):
        self.temp_media_dir = PathConfig.TEMP_MEDIA_DIR
        self.temp_media_dir.mkdir(exist_ok=True)
        
        # 媒体缓存：message_id -> file_path
        self._media_cache = {}
        
    async def get_or_download_media(self, message_id: int, telegram_msg, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        获取或下载媒体文件，避免重复下载
        
        Args:
            message_id: 消息ID
            telegram_msg: Telegram消息对象
            channel_id: 频道ID
            
        Returns:
            媒体信息字典，包含file_path等信息
        """
        try:
            if not telegram_msg or not telegram_msg.media:
                return None
            
            # 1. 检查内存缓存
            if message_id in self._media_cache:
                cached_path = self._media_cache[message_id]
                if os.path.exists(cached_path):
                    logger.debug(f"使用缓存媒体: {message_id} -> {cached_path}")
                    return {
                        'file_path': cached_path,
                        'media_type': self._get_media_type_from_path(cached_path),
                        'from_cache': True
                    }
                else:
                    # 缓存失效，清除
                    del self._media_cache[message_id]
            
            # 2. 检查本地文件系统是否已存在
            local_media_info = await self._find_local_media(message_id)
            if local_media_info:
                # 更新缓存
                self._media_cache[message_id] = local_media_info['file_path']
                logger.debug(f"找到本地媒体: {message_id} -> {local_media_info['file_path']}")
                return local_media_info
            
            # 3. 从Telegram下载新媒体
            logger.info(f"开始下载媒体: 消息 #{message_id}")
            media_info = await self._download_media_from_telegram(message_id, telegram_msg, channel_id)
            
            if media_info and media_info.get('file_path'):
                # 更新缓存
                self._media_cache[message_id] = media_info['file_path']
                logger.info(f"媒体下载成功: {message_id} -> {media_info['file_path']}")
                return media_info
            else:
                logger.warning(f"媒体下载失败: 消息 #{message_id}")
                return None
                
        except Exception as e:
            logger.error(f"获取媒体失败 (消息 #{message_id}): {e}")
            return None
    
    async def _find_local_media(self, message_id: int) -> Optional[Dict[str, Any]]:
        """查找本地已存在的媒体文件"""
        try:
            # 搜索以message_id开头的文件
            pattern = f"{message_id}_*"
            matching_files = list(self.temp_media_dir.glob(pattern))
            
            if matching_files:
                # 使用第一个匹配的文件（通常按时间排序）
                file_path = str(matching_files[0])
                media_type = self._get_media_type_from_path(file_path)
                
                return {
                    'file_path': file_path,
                    'media_type': media_type,
                    'file_size': os.path.getsize(file_path),
                    'from_local': True
                }
            
            return None
            
        except Exception as e:
            logger.error(f"查找本地媒体失败 (消息 #{message_id}): {e}")
            return None
    
    async def _download_media_from_telegram(self, message_id: int, telegram_msg, channel_id: str) -> Optional[Dict[str, Any]]:
        """从Telegram下载媒体文件"""
        try:
            from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
            
            if not telegram_msg.media:
                return None
            
            # 确定媒体类型和扩展名
            media_type, file_extension = self._determine_media_type_and_extension(telegram_msg.media)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{message_id}_{timestamp}_{media_type}.{file_extension}"
            file_path = self.temp_media_dir / filename
            
            # 确保目录存在且可写
            if not self.temp_media_dir.exists():
                logger.warning(f"创建媒体目录: {self.temp_media_dir}")
                self.temp_media_dir.mkdir(parents=True, exist_ok=True)
            
            # 检查目录是否可写
            if not os.access(self.temp_media_dir, os.W_OK):
                logger.error(f"媒体目录无写入权限: {self.temp_media_dir}")
                return {
                    'media_type': media_type,
                    'download_failed': True,
                    'error': '目录无写入权限'
                }
            
            # 使用Telethon客户端下载
            # 这里我们需要从message_grouper获取已经初始化的客户端
            from app.services.message_grouper import message_grouper
            
            if not message_grouper.telegram_client:
                await message_grouper._init_telegram_client()
            
            if not message_grouper.telegram_client:
                logger.error("Telegram客户端未初始化，无法下载媒体")
                return None
            
            # 执行下载
            logger.debug(f"准备从Telegram下载媒体到: {file_path}")
            downloaded_file = await message_grouper.telegram_client.download_media(
                telegram_msg.media,
                file=str(file_path)
            )
            logger.debug(f"Telegram下载返回路径: {downloaded_file}")
            
            if downloaded_file and os.path.exists(downloaded_file):
                file_size = os.path.getsize(downloaded_file)
                
                # 计算文件哈希
                file_hash = await self._calculate_file_hash(downloaded_file)
                
                media_info = {
                    'file_path': downloaded_file,
                    'media_type': media_type,
                    'file_size': file_size,
                    'mime_type': getattr(telegram_msg.media, 'mime_type', 'unknown'),
                    'hash': file_hash,
                    'download_failed': False,
                    'downloaded_at': datetime.now().isoformat()
                }
                
                logger.info(f"媒体下载完成: {downloaded_file} ({file_size} bytes)")
                return media_info
            else:
                # 更准确的错误信息
                if downloaded_file is None:
                    logger.error(f"媒体从Telegram下载失败: 服务器返回空结果 (消息 #{message_id})")
                    error_msg = "Telegram下载返回空"
                else:
                    logger.error(f"媒体下载异常: 文件未创建成功 {downloaded_file} (消息 #{message_id})")
                    error_msg = f"文件创建失败: {downloaded_file}"
                
                return {
                    'media_type': media_type,
                    'download_failed': True,
                    'error': error_msg
                }
                
        except Exception as e:
            import traceback
            logger.error(f"下载媒体异常 (消息 #{message_id}): {e}")
            logger.error(f"详细错误堆栈: {traceback.format_exc()}")
            
            # 提供更友好的错误信息
            error_msg = str(e)
            if 'No space left' in str(e).lower():
                error_msg = "磁盘空间不足"
            elif 'permission' in str(e).lower():
                error_msg = "权限不足"
            elif 'network' in str(e).lower() or 'timeout' in str(e).lower():
                error_msg = "网络连接问题"
            
            return {
                'media_type': 'unknown',
                'download_failed': True,
                'error': error_msg
            }
    
    def _determine_media_type_and_extension(self, media) -> tuple:
        """确定媒体类型和文件扩展名"""
        try:
            from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
            from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio
            
            if isinstance(media, MessageMediaPhoto):
                return 'photo', 'jpg'
            elif isinstance(media, MessageMediaDocument):
                document = media.document
                if document:
                    # 检查MIME类型
                    mime_type = getattr(document, 'mime_type', '')
                    
                    if mime_type.startswith('video/'):
                        return 'video', 'mp4'
                    elif mime_type.startswith('audio/'):
                        return 'audio', 'mp3'
                    elif mime_type.startswith('image/'):
                        if 'gif' in mime_type:
                            return 'animation', 'gif'
                        else:
                            return 'photo', 'jpg'
                    else:
                        # 检查属性
                        if hasattr(document, 'attributes'):
                            for attr in document.attributes:
                                if isinstance(attr, DocumentAttributeVideo):
                                    return 'video', 'mp4'
                                elif isinstance(attr, DocumentAttributeAudio):
                                    return 'audio', 'mp3'
                        
                        return 'document', 'bin'
                return 'document', 'bin'
            else:
                return 'unknown', 'bin'
                
        except Exception as e:
            logger.error(f"确定媒体类型失败: {e}")
            return 'unknown', 'bin'
    
    def _get_media_type_from_path(self, file_path: str) -> str:
        """从文件路径推断媒体类型"""
        try:
            filename = os.path.basename(file_path).lower()
            
            if any(ext in filename for ext in ['photo', '.jpg', '.jpeg', '.png']):
                return 'photo'
            elif any(ext in filename for ext in ['video', '.mp4', '.avi', '.mov']):
                return 'video'
            elif any(ext in filename for ext in ['audio', '.mp3', '.wav', '.ogg']):
                return 'audio'
            elif any(ext in filename for ext in ['animation', '.gif']):
                return 'animation'
            else:
                return 'document'
                
        except Exception as e:
            logger.error(f"推断媒体类型失败: {e}")
            return 'unknown'
    
    async def _calculate_file_hash(self, file_path: str) -> Optional[str]:
        """计算文件哈希"""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败: {e}")
            return None
    
    def clear_cache(self):
        """清理内存缓存"""
        self._media_cache.clear()
        logger.debug("媒体缓存已清理")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            'cached_items': len(self._media_cache),
            'temp_media_files': len(list(self.temp_media_dir.glob('*')))
        }


# 全局媒体管理器实例
media_manager = MediaManager()