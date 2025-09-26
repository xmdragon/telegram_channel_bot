"""
Redis管理器 - 统一、简洁、强健
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
    
    遵循设计哲学：
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
            
            # 连接验证：快速失败，不浪费时间
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
            # 🚀 优化：通过self.client触发lazy初始化
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
            pipeline.zadd(f"index:msg:{channel_id}", {message_id: current_time})
            
            # 根据消息状态添加到对应索引
            status = message_data.get('status', 'pending')
            if status == 'pending':
                pipeline.zadd("index:msg:pending", {f"{channel_id}:{message_id}": current_time})
            elif status == 'approved':
                pipeline.zadd("index:msg:approved", {f"{channel_id}:{message_id}": current_time})
            elif status == 'rejected':
                pipeline.zadd("index:msg:rejected", {f"{channel_id}:{message_id}": current_time})
            
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
                message = self._deserialize_json(message_data)
                
                # 修复：对特殊的JSON字段进行二次解析
                if message:
                    # media_group字段需要二次解析
                    if 'media_group' in message and isinstance(message['media_group'], str):
                        try:
                            message['media_group'] = json.loads(message['media_group'])
                        except (json.JSONDecodeError, TypeError):
                            pass  # 保持原值
                    
                    # combined_messages字段需要二次解析
                    if 'combined_messages' in message and isinstance(message['combined_messages'], str):
                        try:
                            message['combined_messages'] = json.loads(message['combined_messages'])
                        except (json.JSONDecodeError, TypeError):
                            pass  # 保持原值
                            
                    # visual_hash字段需要二次解析
                    if 'visual_hash' in message and isinstance(message['visual_hash'], str):
                        try:
                            message['visual_hash'] = json.loads(message['visual_hash'])
                        except (json.JSONDecodeError, TypeError):
                            pass  # 保持原值
                
                return message
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
    
    def update_message_atomic(self, message_id: str, update_data: Dict[str, Any], user_id: str = None) -> bool:
        """
        原子更新消息 - 唯一的消息更新方法
        
        消除特殊情况：
        1. 所有更新都通过这个方法
        2. 自动处理索引更新
        3. 强制数据一致性
        
        Args:
            message_id: 完整消息ID格式 "channel_id:message_id"
            update_data: 更新数据
            user_id: 操作用户ID (可选)
            
        Returns:
            bool: 是否更新成功
        """
        try:
            # 解析消息ID
            if ':' not in message_id:
                logger.error(f"消息ID格式错误: {message_id}, 应为 channel_id:message_id 格式")
                return False
            
            channel_id, msg_id = message_id.rsplit(':', 1)
            try:
                msg_id = int(msg_id)
            except ValueError:
                logger.error(f"消息ID格式错误: {message_id}, message_id部分必须为数字")
                return False
            
            # 获取现有数据
            existing_data = self.get_message(channel_id, msg_id)
            if existing_data is None:
                logger.error(f"消息不存在: {message_id}")
                return False
            
            # 获取旧状态用于索引更新
            old_status = existing_data.get('status', 'pending')

            # 合并更新数据，处理None值（删除字段）
            for key, value in update_data.items():
                if value is None:
                    # None值表示删除该字段
                    existing_data.pop(key, None)
                else:
                    existing_data[key] = value

            existing_data['updated_at'] = get_current_time().isoformat()
            
            if user_id:
                existing_data['updated_by'] = user_id
            
            # 设计原则：确保所有消息都有有效status
            new_status = existing_data.get('status', 'pending')
            if new_status not in ['pending', 'approved', 'rejected']:
                logger.warning(f"强制修正无效状态 '{new_status}' -> 'pending': {message_id}")
                existing_data['status'] = 'pending'
                new_status = 'pending'
            
            # 原子操作：更新消息数据和索引
            import time
            current_time = time.time()
            pipeline = self.client.pipeline()
            
            # 更新消息数据
            message_key = f"message:{channel_id}:{msg_id}"
            message_json = self._serialize_json(existing_data)
            pipeline.hset(message_key, mapping={
                "data": message_json,
                "updated_at": get_current_time().isoformat()
            })
            
            # 更新索引（仅当状态变更时）
            if old_status != new_status:
                # 从所有状态索引中移除（消除特殊情况，彻底清理）
                for status in ['pending', 'approved', 'rejected']:
                    pipeline.zrem(f"index:msg:{status}", message_id)
                
                # 添加到新状态索引
                if new_status in ['pending', 'approved', 'rejected']:
                    pipeline.zadd(f"index:msg:{new_status}", {message_id: current_time})
            
            # 执行原子操作
            pipeline.execute()
            
            return True
            
        except Exception as e:
            logger.error(f"原子更新消息失败: {e}")
            return False
    
    def update_message_field(self, channel_id: str, message_id: int, field_name: str, field_value: Any, user_id: str = None) -> bool:
        """
        更新消息的单个字段 - 简洁实现
        
        Args:
            channel_id: 频道ID
            message_id: 消息ID
            field_name: 字段名
            field_value: 字段值
            user_id: 操作用户ID (可选)
            
        Returns:
            bool: 是否更新成功
        """
        try:
            # 优化：统一使用原子更新方法
            message_full_id = f"{channel_id}:{message_id}"
            update_data = {field_name: field_value}
            return self.update_message_atomic(message_full_id, update_data, user_id)
            
        except Exception as e:
            logger.error(f"更新消息字段失败 {channel_id}:{message_id}.{field_name}: {e}")
            return False
    
    def update_message(self, channel_id: str, message_id: int, update_data: Dict[str, Any]) -> bool:
        """
        兼容方法 - 支持旧代码，但调用新的原子更新方法
        
        该方法将逐步被废弃，请使用 update_message_atomic()
        
        Args:
            channel_id: 频道ID
            message_id: 消息ID
            update_data: 更新数据
            
        Returns:
            bool: 是否更新成功
        """
        # 转换为新的原子更新方法
        message_full_id = f"{channel_id}:{message_id}"
        return self.update_message_atomic(message_full_id, update_data)
    
    def update_message_status(self, message_id: str, new_status: str, user_id: str = None) -> bool:
        """
        更新消息状态 - 简化实现
        
        Args:
            message_id: 完整消息ID格式 "channel_id:message_id" 
            new_status: 新状态 (pending/approved/rejected)
            user_id: 操作用户ID (可选)
            
        Returns:
            bool: 是否更新成功
        """
        try:
            # 设计原则：消除重复代码，直接使用原子更新方法
            update_data = {'status': new_status}
            return self.update_message_atomic(message_id, update_data, user_id)
            
        except Exception as e:
            logger.error(f"更新消息状态失败: {e}")
            return False
    
    def update_message_fields(self, message_id: str, fields: Dict[str, Any]) -> bool:
        """
        更新消息的多个字段
        
        Args:
            message_id: 完整消息ID格式 "channel_id:message_id"
            fields: 要更新的字段字典
            
        Returns:
            bool: 更新是否成功
        """
        try:
            return self.update_message_atomic(message_id, fields)
            
        except Exception as e:
            logger.error(f"更新消息字段失败: {e}")
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
            full_message_id = f"{channel_id}:{msg_id}"
            
            # 获取消息以确定其状态（用于清理状态索引）
            message_data = self.get_message(channel_id, msg_id, silent=True)
            
            pipeline = self.client.pipeline()
            
            # 1. 删除消息数据
            pipeline.delete(message_key)
            
            # 2. 清理频道索引
            pipeline.zrem(f"index:msg:{channel_id}", msg_id)
            pipeline.zrem(f"channel:{channel_id}:messages", msg_id)
            pipeline.decr(f"channel:{channel_id}:count")
            
            # 3. 清理状态索引（如果消息存在）
            if message_data:
                status = message_data.get('status', 'pending')
                pipeline.zrem(f"index:msg:{status}", full_message_id)

                # 4. 清理媒体哈希索引（如果有媒体）
                if message_data.get('media_hash'):
                    pipeline.srem(f"media:hash:{message_data['media_hash']}", full_message_id)

                # 5. 清理去重SimHash索引
                # 查找所有包含该消息ID的SimHash索引并删除
                simhash_keys = self.client.keys("dup:simhash:*")
                for key in simhash_keys:
                    if self.client.sismember(key, full_message_id):
                        pipeline.srem(key, full_message_id)
                        logger.debug(f"从SimHash索引 {key} 中删除消息: {full_message_id}")
            else:
                # 如果消息不存在，尝试清理所有可能的状态索引（防止孤儿索引）
                for status in ['pending', 'approved', 'rejected']:
                    pipeline.zrem(f"index:msg:{status}", full_message_id)
            
            # 5. 清理全局索引
            pipeline.zrem("index:msg:all", full_message_id)
            
            # 执行所有清理操作
            pipeline.execute()
            
            logger.debug(f"消息已删除并清理所有索引: {channel_id}:{msg_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除消息失败: {e}")
            return False
    
    def get_messages_by_channel(self, channel_id: str, limit: int = 50, offset: int = 0, status: str = None, reverse: bool = True) -> List[Dict[str, Any]]:
        """获取频道消息列表"""
        try:
            if status and status in ['pending', 'approved', 'rejected']:
                # 当指定状态时，从状态索引中获取该频道的消息
                if reverse:
                    status_keys = self.client.zrevrange(f"index:msg:{status}", 0, -1)
                else:
                    status_keys = self.client.zrange(f"index:msg:{status}", 0, -1)
                # 筛选出属于该频道的消息
                channel_message_ids = []
                for key in status_keys:
                    if key.startswith(f"{channel_id}:"):
                        msg_id = key.split(':', 1)[1]
                        channel_message_ids.append(int(msg_id))

                # 排序并分页
                channel_message_ids.sort(reverse=reverse)
                paginated_ids = channel_message_ids[offset:offset + limit]
            else:
                # 无状态筛选时，使用频道索引
                if reverse:
                    message_ids = self.client.zrevrange(f"index:msg:{channel_id}", offset, offset + limit - 1)
                else:
                    message_ids = self.client.zrange(f"index:msg:{channel_id}", offset, offset + limit - 1)
                paginated_ids = [int(msg_id) for msg_id in message_ids]
            
            if not paginated_ids:
                return []
            
            messages = []
            invalid_ids = []
            
            # 批量获取消息数据
            for msg_id in paginated_ids:
                message_data = self.get_message(channel_id, msg_id)
                if message_data:
                    # 如果指定了状态，验证消息状态是否匹配
                    if status and message_data.get('status') != status:
                        continue
                    messages.append(message_data)
                else:
                    invalid_ids.append(msg_id)
            
            # 清理无效索引
            if invalid_ids and not status:
                logger.info(f"清理频道 {channel_id} 中 {len(invalid_ids)} 个无效索引条目")
                pipeline = self.client.pipeline()
                for invalid_id in invalid_ids:
                    pipeline.zrem(f"index:msg:{channel_id}", invalid_id)
                pipeline.execute()
            
            return messages
            
        except Exception as e:
            logger.error(f"获取频道消息失败: {e}")
            return []
    
    def get_pending_messages(self, limit: int = 100, offset: int = 0, reverse: bool = True) -> List[Dict[str, Any]]:
        """获取待审核消息"""
        try:
            if reverse:
                pending_keys = self.client.zrevrange("index:msg:pending", offset, offset + limit - 1)
            else:
                pending_keys = self.client.zrange("index:msg:pending", offset, offset + limit - 1)
            
            messages = []
            invalid_keys = []
            
            for key in pending_keys:
                # 解析消息键格式：channel_id:message_id
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    message_data = self.get_message(channel_id, int(message_id))
                    if message_data:
                        # 🔥 状态验证：确保消息状态与索引匹配
                        actual_status = message_data.get('status', 'pending')
                        if actual_status == 'pending':
                            messages.append(message_data)
                        else:
                            # 状态不匹配，添加到清理列表
                            invalid_keys.append(key)
                            logger.debug(f"状态不匹配的消息从pending索引清理: {key} (实际状态: {actual_status})")
                    else:
                        invalid_keys.append(key)
            
            # 清理无效的待审核索引
            if invalid_keys:
                pipeline = self.client.pipeline()
                for invalid_key in invalid_keys:
                    pipeline.zrem("index:msg:pending", invalid_key)
                pipeline.execute()
                logger.info(f"清理了 {len(invalid_keys)} 个无效的pending索引项")
            
            return messages
            
        except Exception as e:
            logger.error(f"获取待审核消息失败: {e}")
            return []
    
    def get_approved_messages(self, limit: int = 100, offset: int = 0, reverse: bool = True) -> List[Dict[str, Any]]:
        """获取已审核消息"""
        try:
            if reverse:
                approved_keys = self.client.zrevrange("index:msg:approved", offset, offset + limit - 1)
            else:
                approved_keys = self.client.zrange("index:msg:approved", offset, offset + limit - 1)
            
            messages = []
            invalid_keys = []
            
            for key in approved_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    message_data = self.get_message(channel_id, int(message_id))
                    if message_data:
                        # 验证状态匹配
                        actual_status = message_data.get('status', 'pending')
                        if actual_status == 'approved':
                            messages.append(message_data)
                        else:
                            invalid_keys.append(key)
                            logger.debug(f"状态不匹配的消息从approved索引清理: {key} (实际状态: {actual_status})")
                    else:
                        invalid_keys.append(key)
            
            # 清理无效索引
            if invalid_keys:
                pipeline = self.client.pipeline()
                for invalid_key in invalid_keys:
                    pipeline.zrem("index:msg:approved", invalid_key)
                pipeline.execute()
                logger.info(f"清理了 {len(invalid_keys)} 个无效的approved索引项")
            
            return messages
            
        except Exception as e:
            logger.error(f"获取已审核消息失败: {e}")
            return []
    
    def get_rejected_messages(self, limit: int = 100, offset: int = 0, reverse: bool = True) -> List[Dict[str, Any]]:
        """获取已拒绝消息"""
        try:
            if reverse:
                rejected_keys = self.client.zrevrange("index:msg:rejected", offset, offset + limit - 1)
            else:
                rejected_keys = self.client.zrange("index:msg:rejected", offset, offset + limit - 1)
            
            messages = []
            invalid_keys = []
            
            for key in rejected_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    message_data = self.get_message(channel_id, int(message_id))
                    if message_data:
                        # 验证状态匹配
                        actual_status = message_data.get('status', 'pending')
                        if actual_status == 'rejected':
                            messages.append(message_data)
                        else:
                            invalid_keys.append(key)
                            logger.debug(f"状态不匹配的消息从rejected索引清理: {key} (实际状态: {actual_status})")
                    else:
                        invalid_keys.append(key)
            
            # 清理无效索引
            if invalid_keys:
                pipeline = self.client.pipeline()
                for invalid_key in invalid_keys:
                    pipeline.zrem("index:msg:rejected", invalid_key)
                pipeline.execute()
                logger.info(f"清理了 {len(invalid_keys)} 个无效的rejected索引项")
            
            return messages
            
        except Exception as e:
            logger.error(f"获取已拒绝消息失败: {e}")
            return []
    
    def get_messages_by_status(self, status: str, limit: int = 100, offset: int = 0, reverse: bool = True) -> List[Dict[str, Any]]:
        """根据状态获取消息 - 统一接口"""
        if status == "pending":
            return self.get_pending_messages(limit, offset, reverse)
        elif status == "approved":
            return self.get_approved_messages(limit, offset, reverse)
        elif status == "rejected":
            return self.get_rejected_messages(limit, offset, reverse)
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

    def get_earliest_message_timestamp(self) -> Optional[float]:
        """高效获取最早消息的时间戳"""
        try:
            # 获取所有ZSET索引中的最小时间戳
            min_timestamp = None

            # 检查所有状态索引: pending, rejected, 以及各频道索引
            index_keys = self.client.keys("index:msg:*")

            for index_key in index_keys:
                try:
                    # 使用ZRANGE获取最小score（时间戳）
                    # LIMIT 0 1：只取第一个（最小的）
                    result = self.client.zrange(index_key, 0, 0, withscores=True)
                    if result:
                        timestamp = float(result[0][1])  # [0][1]是score
                        if min_timestamp is None or timestamp < min_timestamp:
                            min_timestamp = timestamp
                except Exception as e:
                    logger.debug(f"检查索引{index_key}失败: {e}")
                    continue

            return min_timestamp

        except Exception as e:
            logger.error(f"获取最早消息时间戳失败: {e}")
            return None
    
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
                        pipeline.zrem(f"index:msg:{old_status}", f"{channel_id}:{message_id}")
                    
                    # 添加到新状态索引
                    if new_status in ['pending', 'approved', 'rejected']:
                        pipeline.zadd(f"index:msg:{new_status}", {f"{channel_id}:{message_id}": current_time})
                    
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

            # 先获取所有SimHash索引键
            simhash_keys = self.client.keys("dup:simhash:*")

            for channel_id, message_id in message_ids:
                message_key = f"message:{channel_id}:{message_id}"
                full_message_id = f"{channel_id}:{message_id}"

                # 删除消息数据
                pipeline.delete(message_key)

                # 从各种索引中移除
                pipeline.zrem(f"index:msg:{channel_id}", message_id)
                pipeline.zrem("index:msg:pending", full_message_id)
                pipeline.zrem("index:msg:approved", full_message_id)
                pipeline.zrem("index:msg:rejected", full_message_id)

                # 清理SimHash索引
                for key in simhash_keys:
                    if self.client.sismember(key, full_message_id):
                        pipeline.srem(key, full_message_id)

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
            pipeline.zcard("index:msg:pending")    # 待审核消息数
            pipeline.zcard("index:msg:approved")   # 已通过消息数
            pipeline.zcard("index:msg:rejected")   # 已拒绝消息数
            
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
            pending_keys = self.client.zrange("index:msg:pending", 0, -1)
            for key in pending_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    if not self.get_message(channel_id, int(message_id)):
                        self.client.zrem("index:msg:pending", key)
                        cleanup_stats["cleaned_pending"] += 1
            
            # 清理已通过索引
            approved_keys = self.client.zrange("index:msg:approved", 0, -1)
            for key in approved_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    if not self.get_message(channel_id, int(message_id)):
                        self.client.zrem("index:msg:approved", key)
                        cleanup_stats["cleaned_approved"] += 1
            
            # 清理已拒绝索引
            rejected_keys = self.client.zrange("index:msg:rejected", 0, -1)
            for key in rejected_keys:
                if ':' in key:
                    channel_id, message_id = key.split(':', 1)
                    if not self.get_message(channel_id, int(message_id)):
                        self.client.zrem("index:msg:rejected", key)
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
        """反序列化JSON数据 - 恢复正常处理：失败时返回None"""
        if not data:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"JSON反序列化失败，数据可能损坏: {e}, 数据预览: {str(data)[:100]}...")
            return None  # 返回None而不是原数据，避免类型混淆
    
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
