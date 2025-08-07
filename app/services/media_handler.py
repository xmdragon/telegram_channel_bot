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

from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from app.core.config import db_settings

logger = logging.getLogger(__name__)

class MediaHandler:
    """媒体文件处理器"""
    
    def __init__(self):
        self.temp_dir = Path("./temp_media")
        self.temp_dir.mkdir(exist_ok=True)
        self.cleanup_interval = 7200  # 2小时清理一次
        self.file_ttl = 86400  # 文件保留24小时
        self._cleanup_task = None
        
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
            
    async def download_media(self, client: TelegramClient, message, message_id: int) -> Optional[Dict[str, Any]]:
        """
        下载消息中的媒体文件
        
        Args:
            client: Telegram客户端
            message: Telegram消息对象
            message_id: 消息ID（用于文件命名）
            
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
                "download_time": datetime.utcnow()
            }
            
            if isinstance(message.media, MessageMediaPhoto):
                # 处理图片
                media_info["media_type"] = "photo"
                file_name = f"{file_prefix}_photo.jpg"
                file_path = self.temp_dir / file_name
                
                # 下载图片
                await client.download_media(message.media, file_path)
                
                media_info.update({
                    "file_path": str(file_path),
                    "file_name": file_name,
                    "file_size": file_path.stat().st_size if file_path.exists() else 0,
                    "mime_type": "image/jpeg"
                })
                
                logger.info(f"图片下载完成: {file_name} ({media_info['file_size']} bytes)")
                
            elif isinstance(message.media, MessageMediaDocument):
                # 处理文档/视频/动图等
                document = message.media.document
                
                # 确定文件类型
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
                    
                # 尝试从文档属性获取文件名
                original_name = None
                for attr in document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        original_name = attr.file_name
                        extension = os.path.splitext(original_name)[1] or extension
                        break
                        
                file_name = f"{file_prefix}_{media_info['media_type']}{extension}"
                file_path = self.temp_dir / file_name
                
                # 检查文件大小限制（50MB）
                if document.size > 50 * 1024 * 1024:
                    logger.warning(f"文件太大，跳过下载: {document.size} bytes")
                    return None
                    
                # 下载文件
                await client.download_media(message.media, file_path)
                
                media_info.update({
                    "file_path": str(file_path),
                    "file_name": file_name,
                    "file_size": file_path.stat().st_size if file_path.exists() else 0,
                    "mime_type": mime_type,
                    "original_name": original_name
                })
                
                logger.info(f"{media_info['media_type']}下载完成: {file_name} ({media_info['file_size']} bytes)")
                
            return media_info
            
        except Exception as e:
            logger.error(f"下载媒体文件失败: {e}")
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
            return f"/media/{rel_path}"
            
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
                "exists": True
            }
            
        except Exception as e:
            logger.error(f"获取文件信息失败: {file_path}, 错误: {e}")
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