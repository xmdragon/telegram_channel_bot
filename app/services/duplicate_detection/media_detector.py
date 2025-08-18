"""
媒体重复检测器
基于媒体哈希进行重复检测
"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)


class MediaDuplicateDetector:
    """媒体重复检测器"""
    
    def __init__(self, redis_store=None, cache_hours: int = 72):
        self.redis_store = redis_store
        self.cache_hours = cache_hours
    
    def calculate_media_hash(self, media_data: bytes) -> str:
        """计算媒体文件的哈希值"""
        return hashlib.sha256(media_data).hexdigest()
    
    def calculate_combined_hash(self, media_list: List[Dict]) -> str:
        """计算组合媒体的哈希值"""
        # 将所有媒体的哈希值组合起来
        combined = ""
        for media in sorted(media_list, key=lambda x: x.get('index', 0)):
            if media.get('hash'):
                combined += media['hash']
        
        if combined:
            return hashlib.sha256(combined.encode()).hexdigest()
        return None
    
    async def check_duplicate(self, media_hash: Optional[str], 
                             combined_media_hash: Optional[str],
                             message_time: datetime,
                             message_id: Optional[int] = None) -> Tuple[bool, Optional[int]]:
        """检查媒体重复（跨频道，使用Redis）"""
        if not media_hash and not combined_media_hash:
            return False, None
            
        if not self.redis_store:
            return False, None
            
        try:
            # 确保时间没有时区信息
            if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
                message_time = message_time.replace(tzinfo=None)
            
            # 计算时间阈值
            time_threshold = message_time - timedelta(hours=self.cache_hours)
            
            # 检查媒体哈希重复
            duplicate_keys = []
            
            # 检查单个媒体哈希
            if media_hash:
                duplicates = self.redis_store.find_duplicate_by_hash(media_hash)
                duplicate_keys.extend(duplicates)
            
            # 检查组合媒体哈希
            if combined_media_hash:
                duplicates = self.redis_store.find_duplicate_by_hash(combined_media_hash)
                duplicate_keys.extend(duplicates)
            
            # 检查重复消息是否在时间窗口内且不是被拒绝的
            for key in duplicate_keys:
                try:
                    # 解析消息键获取信息
                    if ':' not in key:
                        continue
                    
                    # 获取消息数据
                    message_data = self.redis_store.redis.hgetall(key)
                    if not message_data:
                        continue
                    
                    # 检查消息状态
                    status = message_data.get('status', '')
                    if status == 'rejected':
                        continue
                    
                    # 检查时间条件
                    created_at_str = message_data.get('created_at', '')
                    if created_at_str:
                        try:
                            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
                            if created_at < time_threshold:
                                continue
                        except:
                            continue
                    
                    # 排除当前消息
                    orig_msg_id = message_data.get('message_id')
                    if message_id and str(orig_msg_id) == str(message_id):
                        continue
                    
                    logger.info(f"发现媒体哈希重复，原消息ID: {orig_msg_id}")
                    return True, orig_msg_id
                    
                except Exception as e:
                    logger.debug(f"检查重复消息 {key} 时出错: {e}")
                    continue
            
            return False, None
            
        except Exception as e:
            logger.error(f"检查媒体重复时出错: {e}")
            return False, None