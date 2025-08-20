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
        """获取所有消息列表 - Linus式优化：使用索引合并，避免扫描所有key"""
        try:
            # 🚀 Linus式优化：使用ZUNIONSTORE合并所有状态索引，避免keys()扫描
            temp_key = f"msg:tmp:all:{id(self)}"
            
            # 合并所有状态的索引（pending、approved、rejected、auto_forwarded等）
            status_indexes = [
                "msg:idx:pending",
                "msg:idx:approved", 
                "msg:idx:rejected",
                "msg:idx:auto_forwarded"
            ]
            
            # 检查哪些索引实际存在
            existing_indexes = []
            for idx in status_indexes:
                if self.redis.exists(idx):
                    existing_indexes.append(idx)
            
            # 同时添加所有频道的索引
            channel_patterns = self.redis.keys('msg:idx:*')
            for pattern in channel_patterns:
                key_str = pattern.decode('utf-8') if isinstance(pattern, bytes) else pattern
                # 跳过状态索引和临时索引
                if (not any(key_str.endswith(status) for status in ['pending', 'approved', 'rejected', 'auto_forwarded']) 
                    and not key_str.startswith('msg:tmp:')):
                    existing_indexes.append(key_str)
            
            if not existing_indexes:
                logger.debug("没有找到任何消息索引")
                return []
            
            # 使用ZUNIONSTORE合并所有索引，Redis自动按分数排序
            if len(existing_indexes) == 1:
                # 只有一个索引，直接使用
                temp_key = existing_indexes[0]
                cleanup_temp = False
            else:
                # 合并多个索引
                self.redis.zunionstore(temp_key, existing_indexes)
                cleanup_temp = True
                # 设置临时key过期时间（60秒）
                self.redis.expire(temp_key, 60)
            
            # 直接从合并后的有序集合分页获取（按分数倒序）
            msg_keys = self.redis.zrevrange(temp_key, offset, offset + limit - 1)
            
            messages = []
            for key in msg_keys:
                # key格式：channel_id:message_id
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                parts = key_str.split(':')
                if len(parts) == 2:
                    channel_id, message_id = parts[0], parts[1]
                    msg_data = self.get_message(channel_id, int(message_id), silent=True)
                    if msg_data:
                        messages.append(msg_data)
                        
            # 清理临时key
            if cleanup_temp:
                self.redis.delete(temp_key)
            
            logger.debug(f"通过索引合并获取到 {len(messages)} 条消息")
            return messages
            
        except Exception as e:
            logger.error(f"获取所有消息失败: {e}")
            return []
    
    def get_duplicate_messages(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取重复消息列表 - 专用方法避免扫描所有消息"""
        try:
            # 🚀 性能优化：使用专用索引获取重复消息
            # 从重复消息索引获取消息ID列表
            duplicate_keys = self.redis.zrevrange("msg:idx:duplicates", offset, offset + limit - 1)
            
            messages = []
            for key in duplicate_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                parts = key_str.split(':')
                if len(parts) == 2:
                    channel_id, message_id = parts[0], parts[1]
                    msg_data = self.get_message(channel_id, int(message_id), silent=True)
                    if msg_data and msg_data.get('duplicate_original_id'):
                        messages.append(msg_data)
            
            # 如果专用索引为空，回退到扫描方式（用于兼容性）
            if not messages and offset == 0:
                logger.debug("重复消息索引为空，回退到状态筛选")
                # 从各状态索引中查找有duplicate_original_id的消息
                all_messages = self.get_all_messages(limit=limit * 3, offset=0)  # 多取一些以确保有足够重复消息
                for msg in all_messages:
                    if msg.get('duplicate_original_id') and len(messages) < limit:
                        messages.append(msg)
                        # 同时补充到重复消息索引中
                        msg_key = f"{msg.get('source_channel')}:{msg.get('message_id')}"
                        timestamp = msg.get('created_at')
                        if timestamp:
                            try:
                                from datetime import datetime
                                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp()
                                self.redis.zadd("msg:idx:duplicates", {msg_key: ts})
                            except:
                                pass
            
            logger.debug(f"获取到 {len(messages)} 条重复消息")
            return messages
            
        except Exception as e:
            logger.error(f"获取重复消息失败: {e}")
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