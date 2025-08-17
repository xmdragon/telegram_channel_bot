"""
消息状态管理Mixin
处理消息状态更新、审核相关的状态变更操作
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)


class MessageStatusMixin:
    """消息状态管理功能"""
    
    def _update_message_status_core(self, channel_id: str, message_id: int, new_status: str, 
                            reviewed_by: str = None) -> bool:
        """更新消息状态核心逻辑"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            
            # 检查消息是否存在
            if not self.redis.exists(msg_key):
                logger.warning(f"消息不存在: {channel_id}:{message_id}")
                return False
            
            # 获取当前状态
            old_status = self.redis.hget(msg_key, 'status') or 'pending'
            
            pipe = self.redis.pipeline()
            
            # 更新消息数据
            update_data = {
                'status': new_status,
                'updated_at': get_current_time().isoformat()
            }
            
            if reviewed_by:
                update_data['reviewed_by'] = reviewed_by
                update_data['review_time'] = get_current_time().isoformat()
            
            pipe.hset(msg_key, mapping=update_data)
            
            # 更新索引
            timestamp = datetime.now().timestamp()
            key = f"{channel_id}:{message_id}"
            
            # 从旧状态索引移除
            pipe.zrem(f"msg:idx:{old_status}", key)
            
            # 添加到新状态索引
            pipe.zadd(f"msg:idx:{new_status}", {key: timestamp})
            
            # 更新计数器
            if old_status != new_status:
                pipe.decr(f"msg:count:{channel_id}:{old_status}")
                pipe.incr(f"msg:count:{channel_id}:{new_status}")
            
            pipe.execute()
            
            logger.debug(f"消息状态已更新: {channel_id}:{message_id} {old_status} -> {new_status}")
            return True
            
        except Exception as e:
            logger.error(f"更新消息状态失败 {channel_id}:{message_id}: {e}")
            return False
    
    async def update_message_review_id(self, channel_id: str, message_id: int, review_message_id: int) -> bool:
        """更新消息的审核消息ID"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            
            # 检查消息是否存在
            if not self.redis.exists(msg_key):
                logger.warning(f"消息不存在: {channel_id}:{message_id}")
                return False
            
            # 更新review_message_id
            update_data = {
                'review_message_id': review_message_id,
                'updated_at': get_current_time().isoformat()
            }
            
            self.redis.hset(msg_key, mapping=update_data)
            return True
            
        except Exception as e:
            logger.error(f"更新消息审核ID失败 {channel_id}:{message_id}: {e}")
            return False