"""
Redis数据存储层
处理消息、会话、缓存等数据的存储
"""
import json
import logging
import redis
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class RedisStore:
    """Redis存储基类"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            # 测试连接
            self.redis.ping()
            logger.info("Redis连接成功")
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            raise
    
    def _serialize_json(self, data: Any) -> str:
        """序列化JSON数据"""
        if isinstance(data, (dict, list)):
            return json.dumps(data, ensure_ascii=False, default=str)
        return str(data)
    
    def _deserialize_json(self, data: str) -> Any:
        """反序列化JSON数据"""
        if not data:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data

class RedisMessageStore(RedisStore):
    """消息存储管理"""
    
    # 过期时间配置
    MESSAGE_TTL = 30 * 24 * 3600  # 30天
    INDEX_TTL = 90 * 24 * 3600    # 索引保留90天
    
    def save_message(self, channel_id: str, message_id: int, data: Dict[str, Any]) -> bool:
        """保存消息"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            
            # 准备存储数据
            redis_data = {}
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    redis_data[key] = self._serialize_json(value)
                elif value is not None:
                    redis_data[key] = str(value)
            
            # 添加时间戳
            now = get_current_time()
            timestamp = now.timestamp()
            redis_data['created_at'] = now.isoformat()
            redis_data['updated_at'] = now.isoformat()
            
            # 使用pipeline进行原子操作
            pipe = self.redis.pipeline()
            
            # 存储消息数据
            pipe.hset(msg_key, mapping=redis_data)
            pipe.expire(msg_key, self.MESSAGE_TTL)
            
            # 添加到各种索引
            pipe.zadd(f"msg:idx:{channel_id}", {str(message_id): timestamp})
            
            # 根据状态添加到相应索引
            status = data.get('status', 'pending')
            if status == 'pending':
                pipe.zadd("msg:idx:pending", {f"{channel_id}:{message_id}": timestamp})
            elif status == 'approved':
                pipe.zadd("msg:idx:approved", {f"{channel_id}:{message_id}": timestamp})
            elif status == 'rejected':
                pipe.zadd("msg:idx:rejected", {f"{channel_id}:{message_id}": timestamp})
            elif status == 'auto_forwarded':
                pipe.zadd("msg:idx:auto_forwarded", {f"{channel_id}:{message_id}": timestamp})
            
            # 更新计数器
            pipe.incr(f"msg:count:{channel_id}:total")
            pipe.incr(f"msg:count:{channel_id}:{status}")
            pipe.incr("msg:count:global:today")
            
            # 如果有媒体哈希，添加到哈希索引
            if data.get('media_hash'):
                pipe.sadd(f"msg:hash:media:{data['media_hash']}", f"{channel_id}:{message_id}")
            
            if data.get('visual_hash'):
                pipe.sadd(f"msg:hash:visual:{data['visual_hash']}", f"{channel_id}:{message_id}")
            
            # 如果是组合消息，添加到组合索引
            if data.get('grouped_id'):
                pipe.sadd(f"msg:group:{data['grouped_id']}", f"{channel_id}:{message_id}")
            
            # 执行pipeline
            pipe.execute()
            
            logger.debug(f"消息已保存: {channel_id}:{message_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存消息失败 {channel_id}:{message_id}: {e}")
            return False
    
    def get_message(self, channel_id: str, message_id: int) -> Optional[Dict[str, Any]]:
        """获取单条消息"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            data = self.redis.hgetall(msg_key)
            
            if not data:
                return None
            
            # 反序列化JSON字段
            json_fields = ['entities', 'removed_hidden_links', 'combined_messages', 
                          'media_group', 'visual_hash', 'ocr_text', 'qr_codes']
            
            for field in json_fields:
                if field in data:
                    data[field] = self._deserialize_json(data[field])
            
            # 转换数值字段
            int_fields = ['message_id', 'review_message_id', 'target_message_id', 'ocr_ad_score']
            for field in int_fields:
                if field in data and data[field]:
                    try:
                        data[field] = int(data[field])
                    except (ValueError, TypeError):
                        pass
            
            # 转换布尔字段
            bool_fields = ['is_combined', 'is_ad', 'ocr_processed']
            for field in bool_fields:
                if field in data:
                    data[field] = data[field].lower() == 'true' if data[field] else False
            
            return data
            
        except Exception as e:
            logger.error(f"获取消息失败 {channel_id}:{message_id}: {e}")
            return None
    
    def get_messages_by_channel(self, channel_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """获取频道消息列表"""
        try:
            # 从索引获取消息ID列表（按时间倒序）
            msg_ids = self.redis.zrevrange(f"msg:idx:{channel_id}", offset, offset + limit - 1)
            
            messages = []
            for msg_id in msg_ids:
                msg_data = self.get_message(channel_id, int(msg_id))
                if msg_data:
                    messages.append(msg_data)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取频道消息失败 {channel_id}: {e}")
            return []
    
    def get_pending_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取待审核消息"""
        try:
            # 从待审核索引获取消息
            pending_keys = self.redis.zrevrange("msg:idx:pending", 0, limit - 1)
            
            messages = []
            for key in pending_keys:
                channel_id, message_id = key.split(':', 1)
                msg_data = self.get_message(channel_id, int(message_id))
                if msg_data:
                    messages.append(msg_data)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取待审核消息失败: {e}")
            return []
    
    def get_messages_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """按状态获取消息列表"""
        try:
            # 从状态索引获取消息
            status_keys = self.redis.zrevrange(f"msg:idx:{status}", 0, limit - 1)
            
            messages = []
            for key in status_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    msg_data = self.get_message(channel_id, int(message_id))
                    if msg_data:
                        messages.append(msg_data)
            
            return messages
            
        except Exception as e:
            logger.error(f"按状态获取消息失败 {status}: {e}")
            return []
    
    def get_all_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有消息列表"""
        try:
            # 获取所有消息key
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
            
            # 只取需要的数量
            selected_keys = [item[0] for item in msg_with_time[:limit]]
            
            messages = []
            for key in selected_keys:
                # 从 key 中提取 channel_id 和 message_id
                parts = key.split(':')
                if len(parts) == 3:  # msg:channel_id:message_id
                    channel_id, message_id = parts[1], parts[2]
                    msg_data = self.get_message(channel_id, int(message_id))
                    if msg_data:
                        messages.append(msg_data)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取所有消息失败: {e}")
            return []
    
    def update_message_status(self, channel_id: str, message_id: int, new_status: str, 
                            reviewed_by: str = None) -> bool:
        """更新消息状态"""
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
    
    async def update_message_field(self, channel_id: str, message_id: int, field: str, value: Any) -> bool:
        """更新消息的任意字段"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            
            # 检查消息是否存在
            if not self.redis.exists(msg_key):
                logger.warning(f"消息不存在: {channel_id}:{message_id}")
                return False
            
            # 更新字段
            update_data = {
                field: self._serialize_json(value) if isinstance(value, (dict, list)) else str(value),
                'updated_at': get_current_time().isoformat()
            }
            
            self.redis.hset(msg_key, mapping=update_data)
            return True
            
        except Exception as e:
            logger.error(f"更新消息字段失败 {channel_id}:{message_id}.{field}: {e}")
            return False
    
    async def update_message(self, channel_id: str, message_id: int, update_data: dict) -> bool:
        """更新消息的多个字段"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            
            # 检查消息是否存在
            if not self.redis.exists(msg_key):
                logger.warning(f"消息不存在: {channel_id}:{message_id}")
                return False
            
            # 准备更新数据
            redis_update_data = {}
            for field, value in update_data.items():
                if isinstance(value, (dict, list)):
                    redis_update_data[field] = self._serialize_json(value)
                else:
                    redis_update_data[field] = str(value)
            
            # 添加更新时间
            redis_update_data['updated_at'] = get_current_time().isoformat()
            
            self.redis.hset(msg_key, mapping=redis_update_data)
            return True
            
        except Exception as e:
            logger.error(f"更新消息失败 {channel_id}:{message_id}: {e}")
            return False
    
    def delete_message(self, channel_id: str, message_id: int) -> bool:
        """删除消息"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            
            # 获取消息数据用于清理索引
            msg_data = self.get_message(channel_id, message_id)
            if not msg_data:
                return False
            
            pipe = self.redis.pipeline()
            
            # 删除消息数据
            pipe.delete(msg_key)
            
            # 从各种索引中移除
            pipe.zrem(f"msg:idx:{channel_id}", str(message_id))
            
            status = msg_data.get('status', 'pending')
            pipe.zrem(f"msg:idx:{status}", f"{channel_id}:{message_id}")
            
            # 更新计数器
            pipe.decr(f"msg:count:{channel_id}:total")
            pipe.decr(f"msg:count:{channel_id}:{status}")
            
            # 清理哈希索引
            if msg_data.get('media_hash'):
                pipe.srem(f"msg:hash:media:{msg_data['media_hash']}", f"{channel_id}:{message_id}")
            
            # 清理组合消息索引
            if msg_data.get('grouped_id'):
                pipe.srem(f"msg:group:{msg_data['grouped_id']}", f"{channel_id}:{message_id}")
            
            pipe.execute()
            
            logger.debug(f"消息已删除: {channel_id}:{message_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除消息失败 {channel_id}:{message_id}: {e}")
            return False
    
    def get_message_count(self, channel_id: str = None, status: str = None) -> int:
        """获取消息计数"""
        try:
            if channel_id and status:
                key = f"msg:count:{channel_id}:{status}"
            elif channel_id:
                key = f"msg:count:{channel_id}:total"
            elif status:
                # 全局状态计数需要遍历所有频道
                pattern = f"msg:count:*:{status}"
                keys = self.redis.keys(pattern)
                total = 0
                for key in keys:
                    count = self.redis.get(key)
                    if count:
                        total += int(count)
                return total
            else:
                key = "msg:count:global:today"
            
            count = self.redis.get(key)
            return int(count) if count else 0
            
        except Exception as e:
            logger.error(f"获取消息计数失败: {e}")
            return 0
    
    def find_duplicate_by_hash(self, media_hash: str) -> List[str]:
        """根据媒体哈希查找重复消息"""
        try:
            return list(self.redis.smembers(f"msg:hash:media:{media_hash}"))
        except Exception as e:
            logger.error(f"查找重复消息失败: {e}")
            return []
    
    def cleanup_expired_indexes(self):
        """清理过期的索引"""
        try:
            # 清理今日计数器
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            self.redis.delete(f"msg:count:global:today:{yesterday}")
            
            # 清理过期的状态索引（保留最近30天）
            cutoff_time = (datetime.now() - timedelta(days=30)).timestamp()
            
            for status in ['pending', 'approved', 'rejected']:
                self.redis.zremrangebyscore(f"msg:idx:{status}", 0, cutoff_time)
            
            logger.debug("索引清理完成")
            
        except Exception as e:
            logger.error(f"索引清理失败: {e}")
    
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
                    msg_data = self.get_message(channel_id, int(message_id))
                    
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

class RedisSessionStore(RedisStore):
    """会话管理存储"""
    
    def save_session(self, token: str, session_data: Dict[str, Any], expire_seconds: int = 3600) -> bool:
        """保存会话"""
        try:
            session_key = f"session:{token}"
            session_json = self._serialize_json(session_data)
            
            # 设置会话数据和过期时间
            self.redis.setex(session_key, expire_seconds, session_json)
            
            # 更新最后活动时间
            self.redis.hset(f"session:activity", token, get_current_time().isoformat())
            
            logger.debug(f"会话已保存: {token}")
            return True
            
        except Exception as e:
            logger.error(f"保存会话失败 {token}: {e}")
            return False
    
    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        try:
            session_key = f"session:{token}"
            session_data = self.redis.get(session_key)
            
            if not session_data:
                return None
            
            # 更新最后活动时间
            self.redis.hset(f"session:activity", token, get_current_time().isoformat())
            
            return self._deserialize_json(session_data)
            
        except Exception as e:
            logger.error(f"获取会话失败 {token}: {e}")
            return None
    
    def delete_session(self, token: str) -> bool:
        """删除会话"""
        try:
            session_key = f"session:{token}"
            self.redis.delete(session_key)
            self.redis.hdel("session:activity", token)
            
            logger.debug(f"会话已删除: {token}")
            return True
            
        except Exception as e:
            logger.error(f"删除会话失败 {token}: {e}")
            return False
    
    def get_active_sessions(self) -> List[str]:
        """获取所有活跃会话"""
        try:
            return [key.replace('session:', '') for key in self.redis.keys('session:*') 
                   if ':' in key and not key.endswith(':activity')]
        except Exception as e:
            logger.error(f"获取活跃会话失败: {e}")
            return []

class RedisChannelStore(RedisStore):
    """频道状态管理"""
    
    def set_checkpoint(self, channel_id: str, last_message_id: int) -> bool:
        """设置频道采集点"""
        try:
            self.redis.hset(f"channel:checkpoint", channel_id, str(last_message_id))
            self.redis.hset(f"channel:checkpoint:time", channel_id, get_current_time().isoformat())
            
            logger.debug(f"采集点已更新: {channel_id} -> {last_message_id}")
            return True
            
        except Exception as e:
            logger.error(f"设置采集点失败 {channel_id}: {e}")
            return False
    
    def get_checkpoint(self, channel_id: str) -> Optional[int]:
        """获取频道采集点"""
        try:
            checkpoint = self.redis.hget("channel:checkpoint", channel_id)
            return int(checkpoint) if checkpoint else None
            
        except Exception as e:
            logger.error(f"获取采集点失败 {channel_id}: {e}")
            return None
    
    def get_all_checkpoints(self) -> Dict[str, int]:
        """获取所有频道采集点"""
        try:
            checkpoints = self.redis.hgetall("channel:checkpoint")
            return {k: int(v) for k, v in checkpoints.items()}
            
        except Exception as e:
            logger.error(f"获取所有采集点失败: {e}")
            return {}
    
    def delete_checkpoint(self, channel_id: str) -> bool:
        """删除频道采集点"""
        try:
            self.redis.hdel("channel:checkpoint", channel_id)
            self.redis.hdel("channel:checkpoint:time", channel_id)
            logger.debug(f"已删除频道采集点: {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除采集点失败 {channel_id}: {e}")
            return False
    
    def get_checkpoint_time(self, channel_id: str) -> Optional[str]:
        """获取频道采集点更新时间"""
        try:
            checkpoint_time = self.redis.hget("channel:checkpoint:time", channel_id)
            if checkpoint_time:
                # 如果是bytes类型需要decode，如果是字符串直接返回
                return checkpoint_time.decode() if isinstance(checkpoint_time, bytes) else checkpoint_time
            return None
            
        except Exception as e:
            logger.error(f"获取采集点时间失败 {channel_id}: {e}")
            return None
    
    def get_checkpoint_info(self, channel_id: str) -> Dict[str, any]:
        """获取频道采集点完整信息"""
        try:
            checkpoint = self.get_checkpoint(channel_id)
            checkpoint_time = self.get_checkpoint_time(channel_id)
            
            return {
                'channel_id': channel_id,
                'checkpoint': checkpoint,
                'updated_at': checkpoint_time,
                'exists': checkpoint is not None
            }
            
        except Exception as e:
            logger.error(f"获取采集点信息失败 {channel_id}: {e}")
            return {'channel_id': channel_id, 'checkpoint': None, 'updated_at': None, 'exists': False}

# 全局实例
redis_message_store = None
redis_session_store = None 
redis_channel_store = None

def init_redis_stores(redis_url: str = "redis://localhost:6379"):
    """初始化Redis存储实例"""
    global redis_message_store, redis_session_store, redis_channel_store
    
    try:
        redis_message_store = RedisMessageStore(redis_url)
        redis_session_store = RedisSessionStore(redis_url)
        redis_channel_store = RedisChannelStore(redis_url)
        
        logger.info("Redis存储层初始化成功")
        return True
        
    except Exception as e:
        logger.error(f"Redis存储层初始化失败: {e}")
        return False

def get_redis_message_store() -> RedisMessageStore:
    """获取消息存储实例"""
    if redis_message_store is None:
        raise RuntimeError("Redis存储层未初始化")
    return redis_message_store

def get_redis_session_store() -> RedisSessionStore:
    """获取会话存储实例"""
    if redis_session_store is None:
        raise RuntimeError("Redis存储层未初始化")
    return redis_session_store

def get_redis_channel_store() -> RedisChannelStore:
    """获取频道存储实例"""
    if redis_channel_store is None:
        raise RuntimeError("Redis存储层未初始化")
    return redis_channel_store

def get_redis_store() -> RedisStore:
    """获取基础Redis存储实例"""
    if redis_message_store is None:
        raise RuntimeError("Redis存储层未初始化")
    return redis_message_store