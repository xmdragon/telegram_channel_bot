"""
简化版重复检测器 - 用于快速启动系统
"""
import logging
from typing import Optional, Tuple
from datetime import datetime
from app.storage.redis_store import get_redis_message_store

logger = logging.getLogger(__name__)

class DuplicateDetector:
    """简化版重复检测器"""
    
    def __init__(self):
        self.message_store = get_redis_message_store()
    
    async def is_duplicate_message(self, 
                                  source_channel: str,
                                  media_hash: Optional[str] = None, 
                                  combined_media_hash: Optional[str] = None,
                                  content: Optional[str] = None,
                                  message_time: Optional[datetime] = None,
                                  message_id: Optional[int] = None,
                                  **kwargs) -> Tuple[bool, Optional[int], str]:
        """
        简化版重复消息检测
        """
        try:
            # 基于媒体哈希检测
            if media_hash:
                duplicates = self.message_store.find_duplicate_by_hash(media_hash)
                if duplicates:
                    logger.info(f"检测到重复媒体: {media_hash}")
                    # 解析第一个重复消息的ID
                    if duplicates:
                        first_dup = duplicates[0]
                        if ':' in first_dup:
                            _, msg_id = first_dup.split(':', 1)
                            return True, int(msg_id), "media_hash"
            
            # 基于组合媒体哈希检测
            if combined_media_hash:
                duplicates = self.message_store.find_duplicate_by_hash(combined_media_hash)
                if duplicates:
                    logger.info(f"检测到重复组合媒体: {combined_media_hash}")
                    if duplicates:
                        first_dup = duplicates[0]
                        if ':' in first_dup:
                            _, msg_id = first_dup.split(':', 1)
                            return True, int(msg_id), "combined_media_hash"
            
            # 如果没有检测到重复
            return False, None, "none"
            
        except Exception as e:
            logger.error(f"重复检测失败: {e}")
            return False, None, "error"
    
    def calculate_text_hash(self, content: str) -> str:
        """计算文本哈希"""
        import hashlib
        return hashlib.md5(content.encode()).hexdigest()
    
    def calculate_combined_media_hash(self, media_list: list) -> Optional[str]:
        """计算组合媒体哈希"""
        if not media_list:
            return None
        
        import hashlib
        combined = ""
        for media in sorted(media_list, key=lambda x: x.get('index', 0)):
            if media.get('hash'):
                combined += media['hash']
        
        if combined:
            return hashlib.sha256(combined.encode()).hexdigest()
        return None