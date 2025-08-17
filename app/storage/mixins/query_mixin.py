"""
消息查询和检索Mixin
处理各种消息查询、列表获取和筛选功能
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class MessageQueryMixin:
    """消息查询和检索功能"""
    
    def get_messages_by_channel(self, channel_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """获取频道消息列表"""
        try:
            # 从索引获取消息ID列表（按时间倒序）
            msg_ids = self.redis.zrevrange(f"msg:idx:{channel_id}", offset, offset + limit - 1)
            
            messages = []
            invalid_ids = []  # 记录无效的消息ID
            
            for msg_id in msg_ids:
                msg_data = self.get_message(channel_id, int(msg_id), silent=True)
                if msg_data:
                    messages.append(msg_data)
                else:
                    # 记录无效ID，但不立即清理（避免在遍历时修改索引）
                    invalid_ids.append(msg_id)
            
            # 批量清理无效的索引条目
            if invalid_ids:
                logger.info(f"清理频道 {channel_id} 中 {len(invalid_ids)} 个无效的索引条目")
                pipe = self.redis.pipeline()
                for invalid_id in invalid_ids:
                    pipe.zrem(f"msg:idx:{channel_id}", invalid_id)
                pipe.execute()
            
            return messages
            
        except Exception as e:
            logger.error(f"获取频道消息失败 {channel_id}: {e}")
            return []
    
    def get_pending_messages(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取待审核消息"""
        try:
            # 从待审核索引获取消息，支持分页
            pending_keys = self.redis.zrevrange("msg:idx:pending", offset, offset + limit - 1)
            
            messages = []
            invalid_keys = []
            
            for key in pending_keys:
                try:
                    channel_id, message_id = key.split(':', 1)
                    msg_data = self.get_message(channel_id, int(message_id), silent=True)
                    if msg_data:
                        messages.append(msg_data)
                    else:
                        invalid_keys.append(key)
                except Exception as e:
                    logger.debug(f"处理待审核消息键失败 {key}: {e}")
                    invalid_keys.append(key)
            
            # 清理无效的待审核索引条目
            if invalid_keys:
                logger.info(f"清理 {len(invalid_keys)} 个无效的待审核消息索引条目")
                pipe = self.redis.pipeline()
                for invalid_key in invalid_keys:
                    pipe.zrem("msg:idx:pending", invalid_key)
                pipe.execute()
            
            return messages
            
        except Exception as e:
            logger.error(f"获取待审核消息失败: {e}")
            return []
    
    def get_messages_by_status(self, status: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """按状态获取消息列表"""
        try:
            # 从状态索引获取消息，支持分页
            status_keys = self.redis.zrevrange(f"msg:idx:{status}", offset, offset + limit - 1)
            
            messages = []
            for key in status_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    msg_data = self.get_message(channel_id, int(message_id), silent=True)
                    if msg_data:
                        messages.append(msg_data)
            
            return messages
            
        except Exception as e:
            logger.error(f"按状态获取消息失败 {status}: {e}")
            return []
    
    def get_all_messages(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取所有消息列表"""
        try:
            # 获取所有消息key，支持分页
            all_msg_keys = self.redis.keys("msg:*:*")
            # 过滤出索引和计数器key，只保留消息数据key
            msg_keys = [key for key in all_msg_keys 
                       if not key.startswith('msg:idx:') 
                       and not key.startswith('msg:count:') 
                       and not key.startswith('msg:hash:') 
                       and not key.startswith('msg:group:')]
            
            # 按时间排序（获取创建时间并排序）
            msg_with_time = []
            for key in msg_keys:
                created_at = self.redis.hget(key, 'created_at')
                if created_at:
                    try:
                        timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
                        msg_with_time.append((key, timestamp))
                    except:
                        msg_with_time.append((key, 0))  # 默认时间
            
            # 按时间倒序排列
            msg_with_time.sort(key=lambda x: x[1], reverse=True)
            
            # 支持分页：跳过offset，取limit数量
            selected_keys = [item[0] for item in msg_with_time[offset:offset + limit]]
            
            messages = []
            for key in selected_keys:
                # 从 key 中提取 channel_id 和 message_id
                parts = key.split(':')
                if len(parts) == 3:  # msg:channel_id:message_id
                    channel_id, message_id = parts[1], parts[2]
                    msg_data = self.get_message(channel_id, int(message_id), silent=True)
                    if msg_data:
                        messages.append(msg_data)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取所有消息失败: {e}")
            return []
    
    def find_duplicate_by_hash(self, media_hash: str) -> List[str]:
        """根据媒体哈希查找重复消息"""
        try:
            return list(self.redis.smembers(f"msg:hash:media:{media_hash}"))
        except Exception as e:
            logger.error(f"查找重复消息失败: {e}")
            return []
    
    async def get_old_messages_for_cleanup(self, cutoff_time):
        """获取需要清理的旧消息"""
        try:
            # 获取所有已完成状态的消息
            old_messages = []
            
            for status in ['approved', 'rejected', 'auto_forwarded']:
                # 获取指定状态的所有消息
                message_keys = self.redis.zrange(f"msg:idx:{status}", 0, -1)
                
                for key in message_keys:
                    if ':' not in key:
                        continue
                    
                    channel_id, message_id = key.split(':', 1)
                    msg_data = self.get_message(channel_id, int(message_id), silent=True)
                    
                    if not msg_data:
                        continue
                    
                    # 检查消息是否足够旧
                    created_at = msg_data.get('created_at')
                    review_time = msg_data.get('review_time') 
                    forwarded_time = msg_data.get('forwarded_time')
                    
                    # 解析时间字符串
                    times_to_check = []
                    for time_str in [created_at, review_time, forwarded_time]:
                        if time_str:
                            try:
                                time_obj = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                                times_to_check.append(time_obj)
                            except:
                                continue
                    
                    # 如果任何时间早于cutoff_time，则加入清理列表
                    if times_to_check and any(t < cutoff_time for t in times_to_check):
                        # 构造消息对象以兼容原有清理逻辑
                        message_obj = type('Message', (), {
                            'channel_id': channel_id,
                            'message_id': int(message_id),
                            'status': msg_data.get('status'),
                            'media_url': msg_data.get('media_url'),
                            'created_at': created_at,
                            'review_time': review_time,
                            'forwarded_time': forwarded_time
                        })()
                        old_messages.append(message_obj)
            
            return old_messages
            
        except Exception as e:
            logger.error(f"获取旧消息失败: {e}")
            return []