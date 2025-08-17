"""
视觉重复检测器
使用视觉哈希进行图片相似度检测
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)


class VisualDuplicateDetector:
    """视觉重复检测器"""
    
    def __init__(self, redis_store=None):
        self.redis_store = redis_store
        # 导入视觉相似度检测器
        try:
            from app.services.visual_similarity import visual_detector
            self.visual_detector = visual_detector
        except ImportError:
            self.visual_detector = None
            logger.warning("视觉相似度检测器未可用")
    
    async def check_duplicate(self, media_data: Optional[bytes],
                             visual_hashes: Optional[dict],
                             message_time: datetime,
                             message_id: Optional[int] = None) -> Tuple[bool, Optional[int], float]:
        """
        检查视觉相似度重复（使用Redis存储）
        
        Args:
            media_data: 媒体文件数据
            visual_hashes: 预计算的视觉哈希
            message_time: 消息时间
            message_id: 当前消息ID
            
        Returns:
            (是否重复, 原始消息ID, 相似度分数)
        """
        if not self.visual_detector:
            return False, None, 0.0
        
        # 如果有媒体数据但没有视觉哈希，先计算
        if media_data and not visual_hashes:
            visual_hashes = self.visual_detector.calculate_perceptual_hashes(media_data)
        
        if not visual_hashes:
            return False, None, 0.0
        
        try:
            # 确保时间没有时区信息
            if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
                message_time = message_time.replace(tzinfo=None)
            
            # 计算时间阈值（96小时窗口）
            time_threshold = message_time - timedelta(hours=96)
            
            # 获取Redis中有视觉哈希的消息
            messages_to_check = await self._get_recent_messages_with_visual_hash(
                time_threshold, message_id
            )
            
            # 检查每个历史消息的视觉相似度
            for msg_data in messages_to_check:
                try:
                    # 获取存储的视觉哈希
                    stored_visual_hash = msg_data.get('visual_hash')
                    if not stored_visual_hash:
                        continue
                    
                    # 解析视觉哈希
                    if isinstance(stored_visual_hash, str):
                        try:
                            stored_hashes = json.loads(stored_visual_hash)
                        except:
                            stored_hashes = eval(stored_visual_hash)  # 兼容旧格式
                    else:
                        stored_hashes = stored_visual_hash
                    
                    # 比较视觉相似度
                    is_similar, similarity = self.visual_detector.is_visually_similar(visual_hashes, stored_hashes)
                    if is_similar:
                        orig_msg_id = msg_data.get('message_id')
                        logger.info(f"发现视觉相似图片，消息ID: {orig_msg_id}, 相似度: {similarity:.1f}%")
                        return True, orig_msg_id, similarity
                        
                except Exception as e:
                    logger.debug(f"比较视觉哈希时出错: {e}")
                    continue
            
            return False, None, 0.0
            
        except Exception as e:
            logger.error(f"检查视觉重复时出错: {e}")
            return False, None, 0.0
    
    async def _get_recent_messages_with_visual_hash(self, time_threshold: datetime, 
                                                   exclude_message_id: Optional[int] = None) -> List[Dict]:
        """获取最近有视觉哈希的消息"""
        if not self.redis_store:
            return []
        
        try:
            # 格式化时间
            time_threshold_str = time_threshold.strftime('%Y-%m-%dT%H:%M:%S')
            
            # 扫描所有消息键
            message_keys = self.redis_store.redis_client.keys("msg:*")
            
            messages_with_visual_hash = []
            for key in message_keys:
                try:
                    # 获取消息数据
                    message_data = self.redis_store.redis_client.hgetall(key)
                    if not message_data:
                        continue
                    
                    # 检查是否有视觉哈希
                    if not message_data.get('visual_hash'):
                        continue
                    
                    # 检查时间条件
                    created_at = message_data.get('created_at', '')
                    if created_at < time_threshold_str:
                        continue
                    
                    # 排除当前消息
                    msg_id = message_data.get('message_id')
                    if exclude_message_id and str(msg_id) == str(exclude_message_id):
                        continue
                    
                    # 排除被拒绝的消息
                    status = message_data.get('status', '')
                    if status == 'rejected':
                        continue
                    
                    messages_with_visual_hash.append(message_data)
                    
                except Exception as e:
                    logger.debug(f"处理消息键 {key} 时出错: {e}")
                    continue
            
            return messages_with_visual_hash[:100]  # 限制检查数量
            
        except Exception as e:
            logger.error(f"获取带视觉哈希的消息失败: {e}")
            return []