"""
Linus式Redis管理器 - 统一、简洁、强健
单例模式管理所有Redis操作，消除分散的连接管理和初始化噪音
"""
import json
import logging
import redis
import sys
import time
import threading
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime, timedelta
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)


class RedisManager:
    """唯一的Redis管理器 - 单例模式
    
    遵循Linus哲学：
    1. 单一职责：只管Redis，管好Redis
    2. 简洁接口：一行代码解决所有Redis需求
    3. 自动管理：连接、重试、错误处理全部内置
    4. 零配置：lazy初始化，无需显式setup
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._redis_client = None
        self._connection_pool = None
        self._initialized = True
        logger.debug("RedisManager实例已创建")
    
    @property
    def client(self):
        """获取Redis客户端 - lazy初始化"""
        if self._redis_client is None:
            self._initialize_redis()
        return self._redis_client
    
    def _initialize_redis(self):
        """初始化Redis连接 - 内置重试机制"""
        if self._redis_client is not None:
            return
            
        try:
            from app.core.config import settings
            redis_url = settings.REDIS_URL
            
            # 创建连接池
            self._connection_pool = redis.ConnectionPool.from_url(
                redis_url,
                decode_responses=True,
                max_connections=20,
                retry_on_timeout=True,
                retry_on_error=[redis.ConnectionError, redis.TimeoutError],
                socket_keepalive=True,
                socket_keepalive_options={}
            )
            
            self._redis_client = redis.Redis(connection_pool=self._connection_pool)
            
            # Linus式连接验证：快速失败，不浪费时间
            max_retries = 3
            for attempt in range(1, max_retries + 2):
                try:
                    self._redis_client.ping()
                    logger.info("Redis连接已建立")
                    return
                except Exception as e:
                    if attempt <= max_retries:
                        logger.debug(f"Redis连接重试 {attempt}/{max_retries}")
                        time.sleep(0.5 * attempt)  # 递增等待
                    else:
                        logger.error(f"Redis连接失败: {e}")
                        sys.exit(1)  # 快速失败
                        
        except Exception as e:
            logger.error(f"Redis初始化失败: {e}")
            raise RuntimeError(f"Redis初始化失败: {e}")
    
    def is_healthy(self) -> bool:
        """检查Redis连接健康状态"""
        try:
            # 🚀 Linus修复：通过self.client触发lazy初始化
            client = self.client
            if client is None:
                return False
            client.ping()
            return True
        except Exception:
            return False
    
    def reconnect(self):
        """重新连接Redis"""
        self._redis_client = None
        self._connection_pool = None
        self._initialize_redis()
    
    # ===========================================
    # 消息存储功能 - 替换RedisMessageStore
    # ===========================================
    
    def save_message(self, channel_id: str, message_id: int, message_data: Dict[str, Any]) -> bool:
        """保存消息"""
        try:
            message_key = f"message:{channel_id}:{message_id}"
            message_json = self._serialize_json(message_data)
            current_time = time.time()
            
            # 使用pipeline提高性能
            pipeline = self.client.pipeline()
            pipeline.hset(message_key, mapping={
                "data": message_json,
                "created_at": get_current_time().isoformat(),
                "updated_at": get_current_time().isoformat()
            })
            
            # 添加到各种索引
            pipeline.zadd(f"msg:idx:{channel_id}", {message_id: current_time})
            
            # 根据消息状态添加到对应索引
            status = message_data.get('status', 'pending')
            if status == 'pending':
                pipeline.zadd("msg:idx:pending", {f"{channel_id}:{message_id}": current_time})
            elif status == 'approved':
                pipeline.zadd("msg:idx:approved", {f"{channel_id}:{message_id}": current_time})
            elif status == 'rejected':
                pipeline.zadd("msg:idx:rejected", {f"{channel_id}:{message_id}": current_time})
            
            # 更新消息计数
            pipeline.incr(f"channel:{channel_id}:count")
            
            pipeline.execute()
            
            logger.debug(f"消息已保存: {channel_id}:{message_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
            return False
    
    def get_message(self, channel_id: str, message_id: int, silent: bool = False) -> Optional[Dict[str, Any]]:
        """获取消息"""
        try:
            message_key = f"message:{channel_id}:{message_id}"
            message_data = self.client.hget(message_key, "data")
            
            if message_data:
                return self._deserialize_json(message_data)
            return None
            
        except Exception as e:
            if not silent:
                logger.error(f"获取消息失败: {e}")
            return None
    
    def get_message_by_id(self, message_id: str, silent: bool = False) -> Optional[Dict[str, Any]]:
        """
        通过组合ID获取消息
        
        Args:
            message_id: 组合消息ID格式 "channel_id:message_id"
            silent: 是否静默处理错误
            
        Returns:
            消息数据或None
        """
        try:
            # 解析组合ID
            if ':' not in message_id:
                if not silent:
                    logger.error(f"消息ID格式错误: {message_id}, 应为 channel_id:message_id 格式")
                return None
            
            channel_id, msg_id = message_id.rsplit(':', 1)
            try:
                msg_id = int(msg_id)
            except ValueError:
                if not silent:
                    logger.error(f"消息ID格式错误: {message_id}, message_id部分必须为数字")
                return None
            
            # 调用现有的get_message方法
            return self.get_message(channel_id, msg_id, silent)
            
        except Exception as e:
            if not silent:
                logger.error(f"获取消息失败: {e}")
            return None
    
    def update_message(self, channel_id: str, message_id: int, update_data: Dict[str, Any]) -> bool:
        """更新消息"""
        try:
            message_key = f"message:{channel_id}:{message_id}"
            
            # 获取现有数据
            existing_data = self.get_message(channel_id, message_id)
            if existing_data is None:
                return False
            
            # 合并更新
            existing_data.update(update_data)
            message_json = self._serialize_json(existing_data)
            
            # 更新消息
            result = self.client.hset(message_key, mapping={
                "data": message_json,
                "updated_at": get_current_time().isoformat()
            })
            
            logger.debug(f"消息已更新: {channel_id}:{message_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新消息失败: {e}")
            return False
    
    def update_message_status(self, message_id: str, new_status: str, user_id: str = None) -> bool:
        """
        更新消息状态 - 支持完整消息ID格式
        用于恢复功能和状态变更
        
        Args:
            message_id: 完整消息ID格式 "channel_id:message_id" 
            new_status: 新状态 (pending/approved/rejected)
            user_id: 操作用户ID (可选)
            
        Returns:
            bool: 是否更新成功
        """
        try:
            # 解析消息ID：channel_id:message_id
            if ':' not in message_id:
                logger.error(f"消息ID格式错误: {message_id}, 应为 channel_id:message_id 格式")
                return False
            
            channel_id, msg_id = message_id.rsplit(':', 1)
            try:
                msg_id = int(msg_id)
            except ValueError:
                logger.error(f"消息ID格式错误: {message_id}, message_id部分必须为数字")
                return False
            
            # 构建更新数据
            update_data = {
                'status': new_status,
                'updated_at': get_current_time().isoformat()
            }
            
            if user_id:
                update_data['updated_by'] = user_id
                
            # 使用现有的update_message方法
            success = self.update_message(channel_id, msg_id, update_data)
            
            if success:
                logger.info(f"消息状态已更新: {message_id} -> {new_status}" + 
                           (f" (by {user_id})" if user_id else ""))
            else:
                logger.error(f"消息状态更新失败: {message_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"更新消息状态失败: {e}")
            return False
    
    def delete_message(self, channel_id_or_full_id: str, message_id: int = None) -> bool:
        """
        删除消息 - 支持两种调用方式
        
        Args:
            channel_id_or_full_id: 频道ID或组合消息ID（"channel_id:message_id"）
            message_id: 消息ID（当第一个参数是频道ID时使用）
            
        Returns:
            bool: 是否删除成功
        """
        try:
            # 判断是组合ID还是分开的参数
            if message_id is None and ':' in channel_id_or_full_id:
                # 组合ID格式
                channel_id, msg_id = channel_id_or_full_id.rsplit(':', 1)
                try:
                    msg_id = int(msg_id)
                except ValueError:
                    logger.error(f"消息ID格式错误: {channel_id_or_full_id}")
                    return False
            else:
                # 分开的参数格式
                channel_id = channel_id_or_full_id
                msg_id = message_id
                
            message_key = f"message:{channel_id}:{msg_id}"
            
            pipeline = self.client.pipeline()
            pipeline.delete(message_key)
            pipeline.zrem(f"channel:{channel_id}:messages", msg_id)
            pipeline.decr(f"channel:{channel_id}:count")
            
            pipeline.execute()
            
            logger.debug(f"消息已删除: {channel_id}:{msg_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除消息失败: {e}")
            return False
    
    def get_messages_by_channel(self, channel_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """获取频道消息列表"""
        try:
            # 使用与原系统兼容的索引键
            message_ids = self.client.zrevrange(f"msg:idx:{channel_id}", offset, offset + limit - 1)
            
            if not message_ids:
                return []
            
            messages = []
            invalid_ids = []
            
            # 批量获取消息数据
            for msg_id in message_ids:
                message_data = self.get_message(channel_id, int(msg_id))
                if message_data:
                    messages.append(message_data)
                else:
                    invalid_ids.append(msg_id)
            
            # 清理无效索引
            if invalid_ids:
                logger.info(f"清理频道 {channel_id} 中 {len(invalid_ids)} 个无效索引条目")
                pipeline = self.client.pipeline()
                for invalid_id in invalid_ids:
                    pipeline.zrem(f"msg:idx:{channel_id}", invalid_id)
                pipeline.execute()
            
            return messages
            
        except Exception as e:
            logger.error(f"获取频道消息失败: {e}")
            return []
    
    def get_pending_messages(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取待审核消息"""
        try:
            pending_keys = self.client.zrevrange("msg:idx:pending", offset, offset + limit - 1)
            
            messages = []
            invalid_keys = []
            
            for key in pending_keys:
                # 解析消息键格式：channel_id:message_id
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    message_data = self.get_message(channel_id, int(message_id))
                    if message_data:
                        messages.append(message_data)
                    else:
                        invalid_keys.append(key)
            
            # 清理无效的待审核索引
            if invalid_keys:
                pipeline = self.client.pipeline()
                for invalid_key in invalid_keys:
                    pipeline.zrem("msg:idx:pending", invalid_key)
                pipeline.execute()
            
            return messages
            
        except Exception as e:
            logger.error(f"获取待审核消息失败: {e}")
            return []
    
    def get_approved_messages(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取已审核消息"""
        try:
            approved_keys = self.client.zrevrange("msg:idx:approved", offset, offset + limit - 1)
            
            messages = []
            for key in approved_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    message_data = self.get_message(channel_id, int(message_id))
                    if message_data:
                        messages.append(message_data)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取已审核消息失败: {e}")
            return []
    
    def get_rejected_messages(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取已拒绝消息"""
        try:
            rejected_keys = self.client.zrevrange("msg:idx:rejected", offset, offset + limit - 1)
            
            messages = []
            for key in rejected_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    message_data = self.get_message(channel_id, int(message_id))
                    if message_data:
                        messages.append(message_data)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取已拒绝消息失败: {e}")
            return []
    
    def get_messages_by_status(self, status: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """根据状态获取消息 - 统一接口"""
        if status == "pending":
            return self.get_pending_messages(limit, offset)
        elif status == "approved":
            return self.get_approved_messages(limit, offset)
        elif status == "rejected":
            return self.get_rejected_messages(limit, offset)
        else:
            return []
    
    def search_messages(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """搜索消息 - 简单文本匹配"""
        try:
            # 获取所有消息键
            all_keys = self.client.keys("message:*")
            
            messages = []
            for key in all_keys[:limit * 2]:  # 限制搜索范围
                try:
                    message_data = self.client.hget(key, "data")
                    if message_data:
                        message = self._deserialize_json(message_data)
                        if message and query.lower() in str(message.get('text', '')).lower():
                            # 从键中解析channel_id和message_id
                            parts = key.split(':')
                            if len(parts) >= 3:
                                message['channel_id'] = parts[1] 
                                message['message_id'] = int(parts[2])
                                messages.append(message)
                                
                                if len(messages) >= limit:
                                    break
                except Exception:
                    continue
            
            return messages
            
        except Exception as e:
            logger.error(f"搜索消息失败: {e}")
            return []
    
    def get_message_count(self, channel_id: str) -> int:
        """获取频道消息数量"""
        try:
            count = self.client.get(f"channel:{channel_id}:count")
            return int(count) if count else 0
        except Exception:
            return 0
    
    # ===========================================
    # 缓存功能 - 替换RedisCacheStore
    # ===========================================
    
    def cache_set(self, key: str, value: Any, expire: int = 3600) -> bool:
        """设置缓存"""
        try:
            value_json = self._serialize_json(value)
            if expire > 0:
                return self.client.setex(f"cache:{key}", expire, value_json)
            else:
                return self.client.set(f"cache:{key}", value_json)
        except Exception as e:
            logger.error(f"设置缓存失败: {e}")
            return False
    
    def cache_get(self, key: str) -> Any:
        """获取缓存"""
        try:
            value = self.client.get(f"cache:{key}")
            return self._deserialize_json(value) if value else None
        except Exception as e:
            logger.error(f"获取缓存失败: {e}")
            return None
    
    def cache_delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            return bool(self.client.delete(f"cache:{key}"))
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")
            return False
    
    def cache_exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            return bool(self.client.exists(f"cache:{key}"))
        except Exception:
            return False
    
    # ===========================================
    # 会话管理 - 替换RedisSessionStore
    # ===========================================
    
    def save_session(self, token: str, session_data: Dict[str, Any], expire_seconds: int = 3600) -> bool:
        """保存会话"""
        try:
            session_key = f"session:{token}"
            session_json = self._serialize_json(session_data)
            
            # 设置会话数据和过期时间
            self.client.setex(session_key, expire_seconds, session_json)
            
            # 更新最后活动时间
            self.client.hset("session:activity", token, get_current_time().isoformat())
            
            logger.debug(f"会话已保存: {token}")
            return True
            
        except Exception as e:
            logger.error(f"保存会话失败: {e}")
            return False
    
    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        try:
            session_key = f"session:{token}"
            session_data = self.client.get(session_key)
            
            if session_data:
                # 更新最后活动时间
                self.client.hset("session:activity", token, get_current_time().isoformat())
                return self._deserialize_json(session_data)
            
            return None
            
        except Exception as e:
            logger.error(f"获取会话失败: {e}")
            return None
    
    def delete_session(self, token: str) -> bool:
        """删除会话"""
        try:
            pipeline = self.client.pipeline()
            pipeline.delete(f"session:{token}")
            pipeline.hdel("session:activity", token)
            pipeline.execute()
            
            logger.debug(f"会话已删除: {token}")
            return True
            
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            return False
    
    # ===========================================
    # 频道状态管理 - 替换RedisChannelStore  
    # ===========================================
    
    def set_channel_state(self, channel_id: str, state_data: Dict[str, Any]) -> bool:
        """设置频道状态"""
        try:
            channel_key = f"channel:{channel_id}:state"
            state_json = self._serialize_json(state_data)
            
            result = self.client.hset(channel_key, mapping={
                "data": state_json,
                "updated_at": get_current_time().isoformat()
            })
            
            logger.debug(f"频道状态已设置: {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"设置频道状态失败: {e}")
            return False
    
    def get_channel_state(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """获取频道状态"""
        try:
            channel_key = f"channel:{channel_id}:state"
            state_data = self.client.hget(channel_key, "data")
            
            return self._deserialize_json(state_data) if state_data else None
            
        except Exception as e:
            logger.error(f"获取频道状态失败: {e}")
            return None
    
    # ===========================================
    # 分布式锁管理 - 替换RedisLockManager
    # ===========================================
    
    def acquire_lock(self, lock_name: str, timeout: int = 10) -> bool:
        """获取分布式锁"""
        try:
            lock_key = f"lock:{lock_name}"
            identifier = f"{time.time()}_{id(self)}"
            
            # 尝试获取锁
            result = self.client.set(lock_key, identifier, nx=True, ex=timeout)
            
            if result:
                logger.debug(f"锁已获取: {lock_name}")
                return True
            else:
                logger.debug(f"锁获取失败: {lock_name}")
                return False
                
        except Exception as e:
            logger.error(f"获取锁失败: {e}")
            return False
    
    def release_lock(self, lock_name: str) -> bool:
        """释放分布式锁"""
        try:
            lock_key = f"lock:{lock_name}"
            result = self.client.delete(lock_key)
            
            if result:
                logger.debug(f"锁已释放: {lock_name}")
            
            return bool(result)
            
        except Exception as e:
            logger.error(f"释放锁失败: {e}")
            return False
    
    # ===========================================
    # 批量操作和统计功能
    # ===========================================
    
    def batch_update_message_status(self, message_ids: List[Tuple[str, int]], new_status: str) -> int:
        """批量更新消息状态"""
        try:
            pipeline = self.client.pipeline()
            updated_count = 0
            
            for channel_id, message_id in message_ids:
                message_key = f"message:{channel_id}:{message_id}"
                
                # 获取现有消息数据
                existing_data = self.get_message(channel_id, message_id)
                if existing_data:
                    # 更新状态
                    existing_data['status'] = new_status
                    message_json = self._serialize_json(existing_data)
                    
                    pipeline.hset(message_key, mapping={
                        "data": message_json,
                        "updated_at": get_current_time().isoformat()
                    })
                    
                    # 更新索引
                    old_status = existing_data.get('status', 'pending')
                    current_time = time.time()
                    
                    # 从旧状态索引中移除
                    if old_status in ['pending', 'approved', 'rejected']:
                        pipeline.zrem(f"msg:idx:{old_status}", f"{channel_id}:{message_id}")
                    
                    # 添加到新状态索引
                    if new_status in ['pending', 'approved', 'rejected']:
                        pipeline.zadd(f"msg:idx:{new_status}", {f"{channel_id}:{message_id}": current_time})
                    
                    updated_count += 1
            
            pipeline.execute()
            logger.info(f"批量更新了 {updated_count} 条消息状态为 {new_status}")
            return updated_count
            
        except Exception as e:
            logger.error(f"批量更新消息状态失败: {e}")
            return 0
    
    def batch_delete_messages(self, message_ids: List[Tuple[str, int]]) -> int:
        """批量删除消息"""
        try:
            pipeline = self.client.pipeline()
            deleted_count = 0
            
            for channel_id, message_id in message_ids:
                message_key = f"message:{channel_id}:{message_id}"
                
                # 删除消息数据
                pipeline.delete(message_key)
                
                # 从各种索引中移除
                pipeline.zrem(f"msg:idx:{channel_id}", message_id)
                pipeline.zrem("msg:idx:pending", f"{channel_id}:{message_id}")
                pipeline.zrem("msg:idx:approved", f"{channel_id}:{message_id}")
                pipeline.zrem("msg:idx:rejected", f"{channel_id}:{message_id}")
                
                # 更新计数
                pipeline.decr(f"channel:{channel_id}:count")
                
                deleted_count += 1
            
            pipeline.execute()
            logger.info(f"批量删除了 {deleted_count} 条消息")
            return deleted_count
            
        except Exception as e:
            logger.error(f"批量删除消息失败: {e}")
            return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        try:
            pipeline = self.client.pipeline()
            
            # 获取各种计数
            pipeline.zcard("msg:idx:pending")    # 待审核消息数
            pipeline.zcard("msg:idx:approved")   # 已通过消息数
            pipeline.zcard("msg:idx:rejected")   # 已拒绝消息数
            
            # 获取所有频道
            pipeline.keys("channel:*:count")
            
            results = pipeline.execute()
            
            pending_count = results[0] or 0
            approved_count = results[1] or 0 
            rejected_count = results[2] or 0
            channel_keys = results[3] or []
            
            # 计算频道数量和消息总数
            channel_count = len(channel_keys)
            total_messages = pending_count + approved_count + rejected_count
            
            return {
                "total_messages": total_messages,
                "pending_messages": pending_count,
                "approved_messages": approved_count,
                "rejected_messages": rejected_count,
                "total_channels": channel_count,
                "updated_at": get_current_time().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "total_messages": 0,
                "pending_messages": 0,
                "approved_messages": 0,
                "rejected_messages": 0,
                "total_channels": 0,
                "updated_at": get_current_time().isoformat()
            }
    
    def cleanup_invalid_references(self) -> Dict[str, int]:
        """清理无效的索引引用"""
        try:
            cleanup_stats = {
                "cleaned_pending": 0,
                "cleaned_approved": 0,
                "cleaned_rejected": 0,
                "cleaned_channels": 0
            }
            
            # 清理待审核索引
            pending_keys = self.client.zrange("msg:idx:pending", 0, -1)
            for key in pending_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    if not self.get_message(channel_id, int(message_id)):
                        self.client.zrem("msg:idx:pending", key)
                        cleanup_stats["cleaned_pending"] += 1
            
            # 清理已通过索引
            approved_keys = self.client.zrange("msg:idx:approved", 0, -1)
            for key in approved_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    if not self.get_message(channel_id, int(message_id)):
                        self.client.zrem("msg:idx:approved", key)
                        cleanup_stats["cleaned_approved"] += 1
            
            # 清理已拒绝索引
            rejected_keys = self.client.zrange("msg:idx:rejected", 0, -1)
            for key in rejected_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    if not self.get_message(channel_id, int(message_id)):
                        self.client.zrem("msg:idx:rejected", key)
                        cleanup_stats["cleaned_rejected"] += 1
            
            logger.info(f"清理完成: {cleanup_stats}")
            return cleanup_stats
            
        except Exception as e:
            logger.error(f"清理无效引用失败: {e}")
            return {"error": str(e)}
    
    # ===========================================
    # 内部工具方法
    # ===========================================
    
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
    
    def clear_all(self, confirm_pattern: str = None):
        """清除所有数据 - 危险操作，需要确认"""
        if confirm_pattern != "CONFIRM_DELETE_ALL":
            raise ValueError("请提供正确的确认字符串")
            
        try:
            self.client.flushdb()
            logger.warning("所有Redis数据已清除")
        except Exception as e:
            logger.error(f"清除数据失败: {e}")
            raise
    
    # ===========================================
    # TODO: 临时方法 - 防止系统崩溃
    # ===========================================
    
    def find_duplicate_by_hash(self, media_hash: str) -> List[str]:
        """根据媒体哈希查找重复消息 - TODO: 从Git历史恢复完整实现"""
        # TODO: 临时实现 - 返回空列表避免系统崩溃
        # 需要从Git历史中恢复完整实现
        logger.debug(f"TODO: find_duplicate_by_hash({media_hash}) - 返回空结果")
        return []
    
    @property
    def redis(self):
        """兼容性属性 - 返回client"""
        # TODO: 临时兼容属性，一些老代码使用.redis而不是.client
        return self.client


# ===========================================
# 全局单例实例和便捷函数
# ===========================================

# 全局RedisManager实例
redis_manager = RedisManager()

def get_redis_manager() -> RedisManager:
    """获取Redis管理器实例"""
    return redis_manager

# 便捷函数 - 与旧API兼容的过渡接口
def get_message_store():
    """临时兼容函数 - 返回RedisManager实例"""
    return redis_manager

def get_cache_store():
    """临时兼容函数 - 返回RedisManager实例"""
    return redis_manager

def get_session_store():
    """临时兼容函数 - 返回RedisManager实例"""
    return redis_manager