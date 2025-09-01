"""
整合的消息重复检测服务 - 重构版本
优先媒体哈希跨频道检测，其次jieba文本相似度检测

重构于2025-08-18：模块化架构，遵循500行限制
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple

from app.storage.redis_manager import redis_manager
from .duplicate_detection import VisualDuplicateDetector, MediaDuplicateDetector, TextDuplicateDetector, MessageCompat

logger = logging.getLogger(__name__)


class DuplicateDetector:
    """整合的消息重复检测器：媒体哈希 + jieba文本相似度"""
    
    def __init__(self):
        # Redis存储实例（延迟初始化）
        self.redis_store = None
        
        # 初始化各个检测器（延迟初始化Redis）
        self.visual_detector = None
        self.media_detector = None  
        self.text_detector = None
    
    def _ensure_detectors_initialized(self):
        """确保检测器已初始化"""
        if self.redis_store is None:
            try:
                self.redis_store = redis_manager
            except RuntimeError:
                logger.debug("Redis存储未初始化，跳过重复检测")
                return False
        
        if self.visual_detector is None:
            self.visual_detector = VisualDuplicateDetector(self.redis_store)
        
        if self.media_detector is None:
            self.media_detector = MediaDuplicateDetector(
                redis_store=self.redis_store,
                cache_hours=72  # 媒体检测72小时窗口
            )
        
        if self.text_detector is None:
            self.text_detector = TextDuplicateDetector(
                redis_store=self.redis_store,
                similarity_threshold=0.75,  # 75%相似度阈值（更严格避免误判）
                time_window_minutes=2880  # 48小时时间窗口 (2880分钟)
            )
        
        return True
    
    def calculate_media_hash(self, media_data: bytes) -> str:
        """计算媒体文件的哈希值"""
        if not self._ensure_detectors_initialized():
            return ""
        return self.media_detector.calculate_media_hash(media_data)
    
    def calculate_combined_hash(self, media_list: List[Dict]) -> str:
        """计算组合媒体的哈希值"""
        if not self._ensure_detectors_initialized():
            return ""
        return self.media_detector.calculate_combined_hash(media_list)
    
    async def is_duplicate_message(self, 
                                  source_channel: str,
                                  media_hash: Optional[str] = None, 
                                  combined_media_hash: Optional[str] = None,
                                  content: Optional[str] = None,
                                  message_time: Optional[datetime] = None,
                                  message_id: Optional[int] = None,
                                  media_data: Optional[bytes] = None,
                                  visual_hashes: Optional[dict] = None,
                                  **kwargs) -> Tuple[bool, Optional[int], str]:
        """
        整合的重复消息检测：优先视觉相似度，其次媒体哈希，最后jieba文本相似度
        
        Args:
            source_channel: 源频道
            media_hash: 单个媒体的哈希值
            combined_media_hash: 组合媒体的哈希值
            content: 消息文本内容
            message_time: 消息时间
            message_id: 消息ID
            media_data: 媒体文件的二进制数据（用于视觉相似度检测）
            visual_hashes: 预计算的视觉哈希值
            **kwargs: 其他参数（兼容性）
            
        Returns:
            (is_duplicate, original_message_id, duplicate_type)
        """
        # 初始化检测器
        if not self._ensure_detectors_initialized():
            return False, None, "skip"
        
        if message_time is None:
            message_time = datetime.utcnow()
        # 确保时间没有时区信息（naive datetime）
        if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
            message_time = message_time.replace(tzinfo=None)
        
        # 最优先进行视觉相似度检测（如果有图片数据）
        if media_data or visual_hashes:
            logger.debug(f"开始视觉相似度检测，检测窗口: 96小时")
            is_visual_dup, orig_id, similarity = await self.visual_detector.check_duplicate(
                media_data, visual_hashes, message_time, message_id
            )
            if is_visual_dup:
                logger.info(f"✅ 检测到视觉相似图片，相似度: {similarity:.1f}%，原消息ID: {orig_id}")
                return True, orig_id, "visual"
            else:
                logger.debug(f"视觉相似度检测未发现重复")
            
        # 其次进行媒体哈希检测（跨频道）
        if media_hash or combined_media_hash:
            logger.debug(f"开始媒体哈希检测，检测窗口: 72小时")
            is_media_dup, orig_id = await self.media_detector.check_duplicate(
                media_hash, combined_media_hash, message_time, message_id
            )
            if is_media_dup:
                logger.info(f"✅ 检测到媒体哈希重复，原消息ID: {orig_id}")
                return True, orig_id, "media"
            else:
                logger.debug(f"媒体哈希检测未发现重复")
        
        # 其次进行文本相似度检测（跨频道）
        if content and content.strip():
            logger.debug(f"开始文本相似度检测，阈值: 75%，检测窗口: 48小时")
            is_text_dup, orig_id = await self.text_detector.check_duplicate(
                content, source_channel, message_time, message_id
            )
            if is_text_dup:
                logger.info(f"✅ 检测到文本相似重复，原消息ID: {orig_id}")
                return True, orig_id, "text"
            else:
                logger.debug(f"文本相似度检测未发现重复（检查了{len(content.strip())}字符的内容）")
        
        logger.debug(f"✅ 去重检测完成，未发现重复")
        return False, None, "none"
    
    def _is_text_similar(self, text1: Optional[str], text2: Optional[str], threshold: float = 0.8) -> bool:
        """简化的文本相似度检查（向后兼容）"""
        if not text1 or not text2:
            return False
        
        # 使用文本检测器的相似度计算
        if not self._ensure_detectors_initialized():
            return False
        
        similarity = self.text_detector._calculate_text_similarity(text1, text2)
        return similarity >= threshold
    
    async def get_similar_messages(self, 
                                  content: str,
                                  source_channel: str,
                                  hours_back: int = 48,
                                  similarity_threshold: float = 0.75,
                                  limit: int = 10) -> List[Dict]:
        """
        获取相似消息列表（向后兼容API）
        
        Args:
            content: 要比较的消息内容
            source_channel: 源频道
            hours_back: 向前查找小时数
            similarity_threshold: 相似度阈值
            limit: 结果限制数量
            
        Returns:
            相似消息列表
        """
        if not self._ensure_detectors_initialized():
            return []
        
        try:
            # 使用文本检测器获取相似消息
            from datetime import timedelta
            message_time = datetime.utcnow()
            time_start = message_time - timedelta(hours=hours_back)
            time_end = message_time
            
            recent_messages = await self.text_detector._get_recent_messages_with_content(
                time_start, time_end
            )
            
            similar_messages = []
            for msg_data in recent_messages[:limit * 2]:  # 多获取一些用于筛选
                try:
                    stored_content = msg_data.get('content', '')
                    if not stored_content:
                        continue
                    
                    similarity = self.text_detector._calculate_text_similarity(content, stored_content)
                    if similarity >= similarity_threshold:
                        # 转换为兼容格式
                        similar_messages.append({
                            'id': msg_data.get('message_id'),
                            'content': stored_content,
                            'similarity': similarity,
                            'created_at': msg_data.get('created_at'),
                            'status': msg_data.get('status', 'pending')
                        })
                        
                        if len(similar_messages) >= limit:
                            break
                            
                except Exception as e:
                    logger.debug(f"处理相似消息时出错: {e}")
                    continue
            
            return similar_messages
            
        except Exception as e:
            logger.error(f"获取相似消息失败: {e}")
            return []
    
    async def mark_as_duplicate(self, channel_id: str, message_id: int, original_message_id: int):
        """标记消息为重复（向后兼容API）"""
        if not self._ensure_detectors_initialized():
            return
        
        try:
            # 构造消息键
            message_key = f"msg:{channel_id}:{message_id}"
            
            # 更新消息状态
            self.redis_manager.client.hset(message_key, mapping={
                'status': 'duplicate',
                'original_message_id': str(original_message_id),
                'duplicate_detected_at': datetime.utcnow().isoformat()
            })
            
            logger.info(f"标记消息 {message_id} 为重复，原消息ID: {original_message_id}")
            
        except Exception as e:
            logger.error(f"标记重复消息失败: {e}")
    
    def calculate_text_hash(self, content: str) -> str:
        """计算文本哈希（向后兼容）"""
        if not self._ensure_detectors_initialized():
            return ""
        return self.text_detector.calculate_text_hash(content)
    
    def calculate_combined_media_hash(self, media_list: list) -> Optional[str]:
        """计算组合媒体哈希（向后兼容）"""
        return self.calculate_combined_hash(media_list)


# 懒加载全局实例
_duplicate_detector_instance = None

def get_duplicate_detector():
    """获取重复检测器实例（懒加载）"""
    global _duplicate_detector_instance
    if _duplicate_detector_instance is None:
        _duplicate_detector_instance = DuplicateDetector()
    return _duplicate_detector_instance

# 兼容性：保持duplicate_detector属性访问
class DuplicateDetectorProxy:
    """重复检测器代理，实现懒加载"""
    def __getattr__(self, name):
        return getattr(get_duplicate_detector(), name)
    
    def __setattr__(self, name, value):
        setattr(get_duplicate_detector(), name, value)

duplicate_detector = DuplicateDetectorProxy()