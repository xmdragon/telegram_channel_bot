"""
媒体处理器
负责媒体文件的下载、处理、哈希计算和清理
"""
import logging
import os
from typing import Dict, Optional, Any, Union

logger = logging.getLogger(__name__)

class MediaProcessor:
    """媒体处理器"""
    
    def __init__(self):
        pass
    
    async def process_media(self, message, timeout: float = None) -> Optional[Dict[str, Any]]:
        """
        处理媒体消息
        
        Args:
            message: Telegram消息对象
            timeout: 下载超时时间（秒）
            
        Returns:
            媒体信息字典，如果处理失败返回None，如果被拒绝返回False
        """
        try:
            if not message.media:
                return None
            
            media_type = None
            if hasattr(message.media, 'photo'):
                media_type = "photo"
            elif hasattr(message.media, 'document'):
                media_type = "document"
            else:
                media_type = "other"
            
            # 🔥 Linus式修复：统一超时设置
            if timeout is None:
                timeout = 1800.0  # 30分钟，统一处理所有媒体类型
            
            # 检查是否为危险文件
            if await self._is_dangerous_file(message):
                logger.warning(f"🚫 消息包含危险文件，自动过滤")
                return False  # 明确被拒绝
            
            # 下载媒体文件
            from app.services.media_handler import media_handler
            media_info = await media_handler.download_media(
                None,  # 这里需要传入客户端，但为了避免循环依赖，先传None
                message, 
                message.id, 
                timeout=timeout
            )
            
            if media_info:
                logger.debug(f"✅ 媒体下载成功: {media_info.get('file_path')}")
                return media_info
            else:
                # 下载失败，创建占位信息
                logger.warning(f"⏳ 媒体下载失败（超时{timeout}秒） (message_id={message.id})")
                return {
                    'message_id': message.id,
                    'media_type': media_type,
                    'file_path': None,
                    'file_size': 0,
                    'download_failed': True,
                    'timeout': timeout
                }
                
        except Exception as e:
            logger.error(f"媒体处理异常 (message_id={message.id}): {e}")
            # 创建占位信息
            return {
                'message_id': message.id,
                'media_type': media_type if 'media_type' in locals() else 'unknown',
                'file_path': None,
                'file_size': 0,
                'download_failed': True,
                'error': str(e)
            }
    
    async def _is_dangerous_file(self, message) -> bool:
        """检查是否为危险文件"""
        try:
            if not message.media or not hasattr(message.media, 'document'):
                return False
            
            document = message.media.document
            dangerous_extensions = [
                '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', 
                '.vbs', '.js', '.jar', '.msi', '.dll', '.bin'
            ]
            
            for attr in document.attributes:
                if hasattr(attr, 'file_name') and attr.file_name:
                    if any(attr.file_name.lower().endswith(ext) for ext in dangerous_extensions):
                        return True
            
            return False
        except Exception as e:
            logger.error(f"检查危险文件失败: {e}")
            return False
    
    async def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """计算文件哈希"""
        try:
            from app.services.media_handler import media_handler
            return await media_handler._calculate_file_hash(file_path)
        except Exception as e:
            logger.error(f"计算文件哈希失败: {e}")
            return None
    
    async def calculate_visual_hash(self, file_path: str, media_type: str) -> Optional[Dict]:
        """计算视觉哈希（仅对图片）"""
        try:
            if media_type not in ['photo', 'animation']:
                return None
            
            from app.services.visual_similarity import visual_detector
            if not visual_detector or not os.path.exists(file_path):
                return None
            
            with open(file_path, 'rb') as f:
                image_data = f.read()
            
            visual_hashes = visual_detector.calculate_perceptual_hashes(image_data)
            logger.info(f"📊 视觉哈希计算完成")
            return visual_hashes
            
        except Exception as e:
            logger.debug(f"计算视觉哈希失败: {e}")
            return None
    
    async def process_media_group(self, media_list: list) -> Optional[str]:
        """处理媒体组哈希"""
        try:
            from app.services.media_handler import media_handler
            return await media_handler.process_media_group(media_list)
        except Exception as e:
            logger.error(f"处理媒体组失败: {e}")
            return None
    
    async def cleanup_file(self, file_path: str):
        """清理媒体文件"""
        try:
            from app.services.media_handler import media_handler
            await media_handler.cleanup_file(file_path)
        except Exception as e:
            logger.error(f"清理媒体文件失败: {e}")
    
    async def cleanup_message_files(self, message):
        """清理消息相关的媒体文件"""
        try:
            if message.is_combined and message.media_group:
                # 清理组合消息的所有媒体文件
                for media_item in message.media_group:
                    file_path = media_item['file_path']
                    if os.path.exists(file_path):
                        await self.cleanup_file(file_path)
            elif message.media_url and os.path.exists(message.media_url):
                # 清理单个媒体文件
                await self.cleanup_file(message.media_url)
        except Exception as e:
            logger.error(f"清理消息文件时出错: {e}")
    
    async def get_media_info(self, message) -> Dict[str, Any]:
        """获取媒体基本信息（不下载）"""
        try:
            if not message.media:
                return {}
            
            media_info = {
                'has_media': True,
                'media_type': None,
                'file_size': 0,
                'mime_type': None,
                'file_name': None
            }
            
            if hasattr(message.media, 'photo'):
                media_info['media_type'] = 'photo'
                # 获取最大尺寸的图片信息
                if hasattr(message.media.photo, 'sizes'):
                    largest_size = max(message.media.photo.sizes, key=lambda x: getattr(x, 'size', 0))
                    media_info['file_size'] = getattr(largest_size, 'size', 0)
            
            elif hasattr(message.media, 'document'):
                document = message.media.document
                media_info['media_type'] = 'document'
                media_info['file_size'] = document.size or 0
                media_info['mime_type'] = document.mime_type or 'application/octet-stream'
                
                # 获取文件名
                for attr in document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        media_info['file_name'] = attr.file_name
                        break
                
                # 根据MIME类型细分类型
                mime_type = media_info['mime_type']
                if mime_type.startswith('video/'):
                    media_info['media_type'] = 'video'
                elif mime_type.startswith('audio/'):
                    media_info['media_type'] = 'audio'
                elif mime_type.startswith('image/'):
                    media_info['media_type'] = 'photo'
            
            return media_info
            
        except Exception as e:
            logger.error(f"获取媒体信息失败: {e}")
            return {'has_media': False}
    
    def format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        try:
            if size_bytes == 0:
                return "0 B"
            
            size_names = ["B", "KB", "MB", "GB", "TB"]
            import math
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"
        except:
            return f"{size_bytes} B"
    
    async def validate_media_file(self, file_path: str) -> bool:
        """验证媒体文件是否有效"""
        try:
            if not os.path.exists(file_path):
                return False
            
            # 检查文件大小
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logger.warning(f"媒体文件为空: {file_path}")
                return False
            
            # 检查文件是否可读
            try:
                with open(file_path, 'rb') as f:
                    # 尝试读取前几个字节
                    f.read(1024)
                return True
            except Exception as e:
                logger.error(f"媒体文件无法读取: {file_path}, 错误: {e}")
                return False
                
        except Exception as e:
            logger.error(f"验证媒体文件失败: {e}")
            return False

# 全局实例
media_processor = MediaProcessor()