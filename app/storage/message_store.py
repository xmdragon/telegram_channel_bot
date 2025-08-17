"""
消息数据存储操作模块
处理Telegram消息的存储、检索、更新、删除和统计
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from app.utils.timezone import get_current_time
from .redis_client import RedisBaseStore

logger = logging.getLogger(__name__)

class RedisMessageStore(RedisBaseStore):
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
    
    def get_message(self, channel_id: str, message_id: int, silent: bool = False) -> Optional[Dict[str, Any]]:
        """获取单条消息
        
        Args:
            channel_id: 频道ID
            message_id: 消息ID  
            silent: 静默模式，不输出"消息不存在"的警告（用于存在性检查）
        """
        msg_key = f"msg:{channel_id}:{message_id}"
        try:
            logger.debug(f"获取消息: {msg_key}")
            data = self.redis.hgetall(msg_key)
            
            if not data:
                if not silent:
                    logger.warning(f"消息不存在于Redis: {msg_key}")
                return None
            
            logger.debug(f"Redis原始数据字段: {list(data.keys())}")
            
            # 反序列化JSON字段
            json_fields = ['entities', 'removed_hidden_links', 'combined_messages', 
                          'media_group', 'visual_hash', 'ocr_text', 'qr_codes']
            
            for field in json_fields:
                if field in data:
                    try:
                        data[field] = self._deserialize_json(data[field])
                        logger.debug(f"成功反序列化JSON字段: {field}")
                    except Exception as e:
                        logger.warning(f"反序列化JSON字段 {field} 失败: {e}, 将设为空值")
                        data[field] = [] if field in ['entities', 'removed_hidden_links', 'combined_messages', 'media_group', 'qr_codes'] else {}
            
            # 转换数值字段
            int_fields = ['message_id', 'review_message_id', 'target_message_id', 'ocr_ad_score']
            for field in int_fields:
                if field in data and data[field]:
                    try:
                        data[field] = int(data[field])
                        logger.debug(f"成功转换数值字段: {field} = {data[field]}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"转换数值字段 {field} 失败: {e}, 原值: {data[field]}")
                        # 保持原值，不进行转换
            
            # 转换布尔字段
            bool_fields = ['is_combined', 'is_ad', 'ocr_processed']
            for field in bool_fields:
                if field in data:
                    try:
                        if isinstance(data[field], bytes):
                            data[field] = data[field].decode('utf-8')
                        data[field] = data[field].lower() == 'true' if data[field] else False
                        logger.debug(f"成功转换布尔字段: {field} = {data[field]}")
                    except Exception as e:
                        logger.warning(f"转换布尔字段 {field} 失败: {e}, 原值: {data[field]}")
                        data[field] = False
            
            # 确保关键字段存在
            if 'source_channel' not in data:
                data['source_channel'] = channel_id
            if 'message_id' not in data:
                data['message_id'] = message_id
            
            logger.debug(f"成功获取并处理消息: {msg_key}")
            return data
            
        except Exception as e:
            logger.error(f"获取消息失败 {msg_key}: {e}", exc_info=True)
            # 尝试提供基本的消息数据
            try:
                basic_data = self.redis.hgetall(msg_key)
                if basic_data:
                    logger.info(f"返回基本消息数据: {msg_key}")
                    return {
                        'source_channel': channel_id,
                        'message_id': message_id,
                        'content': basic_data.get('content', ''),
                        'filtered_content': basic_data.get('filtered_content', ''),
                        'status': basic_data.get('status', 'pending'),
                        'created_at': basic_data.get('created_at', ''),
                        'is_ad': False,
                        'is_combined': False,
                        'entities': [],
                        'removed_hidden_links': []
                    }
            except Exception as basic_e:
                logger.error(f"连基本数据也无法获取: {basic_e}")
            
            return None
    
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
    
    def _update_message_status_old(self, channel_id: str, message_id: int, new_status: str, 
                            reviewed_by: str = None) -> bool:
        """原始的更新消息状态方法（内部使用）"""
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
    
    def _delete_message_old(self, channel_id: str, message_id: int) -> bool:
        """原始的删除消息方法（内部使用）"""
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
            
    def cleanup_invalid_indexes(self):
        """清理无效的索引条目（指向不存在消息的索引）"""
        try:
            logger.info("开始清理无效的索引条目...")
            cleaned_count = 0
            
            # 获取所有频道索引
            channel_indexes = self.redis.keys("msg:idx:-*")
            
            for index_key in channel_indexes:
                try:
                    # 获取频道ID
                    channel_id = index_key.decode('utf-8').replace("msg:idx:", "")
                    
                    # 获取该频道索引中的所有消息ID
                    msg_ids = self.redis.zrange(index_key, 0, -1)
                    invalid_ids = []
                    
                    # 检查每个消息是否存在
                    for msg_id in msg_ids:
                        msg_key = f"msg:{channel_id}:{msg_id.decode('utf-8')}"
                        if not self.redis.exists(msg_key):
                            invalid_ids.append(msg_id)
                    
                    # 批量删除无效索引
                    if invalid_ids:
                        pipe = self.redis.pipeline()
                        for invalid_id in invalid_ids:
                            pipe.zrem(index_key, invalid_id)
                        pipe.execute()
                        cleaned_count += len(invalid_ids)
                        logger.debug(f"从 {channel_id} 清理了 {len(invalid_ids)} 个无效索引")
                        
                except Exception as e:
                    logger.warning(f"清理索引 {index_key} 时出错: {e}")
                    continue
            
            # 清理状态索引
            for status in ['pending', 'approved', 'rejected', 'auto_forwarded']:
                try:
                    status_keys = self.redis.zrange(f"msg:idx:{status}", 0, -1)
                    invalid_keys = []
                    
                    for key in status_keys:
                        try:
                            channel_id, message_id = key.decode('utf-8').split(':', 1)
                            msg_key = f"msg:{channel_id}:{message_id}"
                            if not self.redis.exists(msg_key):
                                invalid_keys.append(key)
                        except ValueError:
                            invalid_keys.append(key)  # 格式错误的键也删除
                    
                    if invalid_keys:
                        pipe = self.redis.pipeline()
                        for invalid_key in invalid_keys:
                            pipe.zrem(f"msg:idx:{status}", invalid_key)
                        pipe.execute()
                        cleaned_count += len(invalid_keys)
                        logger.debug(f"从状态索引 {status} 清理了 {len(invalid_keys)} 个无效条目")
                        
                except Exception as e:
                    logger.warning(f"清理状态索引 {status} 时出错: {e}")
            
            if cleaned_count > 0:
                logger.info(f"索引清理完成，共清理了 {cleaned_count} 个无效条目")
            else:
                logger.debug("没有发现需要清理的无效索引条目")
                
        except Exception as e:
            logger.error(f"清理无效索引失败: {e}")
    
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
    
    def get_message_by_id(self, message_key: str) -> Optional[Dict[str, Any]]:
        """
        兼容方法：根据消息键获取消息
        支持格式：channel_id:message_id 或 msg:channel_id:message_id
        """
        try:
            # 处理不同格式的message_key
            if message_key.startswith('msg:'):
                # 格式: msg:channel_id:message_id
                parts = message_key.split(':', 2)
                if len(parts) >= 3:
                    channel_id, message_id = parts[1], parts[2]
                else:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return None
            elif ':' in message_key:
                # 格式: channel_id:message_id
                try:
                    channel_id, message_id = message_key.rsplit(':', 1)
                except ValueError:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return None
            else:
                logger.warning(f"不支持的消息键格式: {message_key}")
                return None
            
            # 转换message_id为整数
            try:
                message_id = int(message_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的消息ID: {message_id}")
                return None
            
            # 使用现有的get_message方法
            return self.get_message(channel_id, message_id)
            
        except Exception as e:
            logger.error(f"获取消息失败 {message_key}: {e}")
            return None
    
    def update_message_status_by_key(self, message_key: str, new_status: str, reviewer_id: str = None, reason: str = None) -> bool:
        """
        兼容方法：根据消息键更新消息状态
        """
        try:
            # 解析消息键获取channel_id和message_id
            if message_key.startswith('msg:'):
                parts = message_key.split(':', 2)
                if len(parts) >= 3:
                    channel_id, message_id = parts[1], parts[2]
                else:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return False
            elif ':' in message_key:
                try:
                    channel_id, message_id = message_key.rsplit(':', 1)
                except ValueError:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return False
            else:
                logger.warning(f"不支持的消息键格式: {message_key}")
                return False
            
            # 转换message_id为整数
            try:
                message_id = int(message_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的消息ID: {message_id}")
                return False
            
            # 使用内部的update_message_status方法
            return self._update_message_status_old(channel_id, message_id, new_status, reviewer_id)
            
        except Exception as e:
            logger.error(f"更新消息状态失败 {message_key}: {e}")
            return False
    
    def delete_message_by_key(self, message_key: str) -> bool:
        """
        兼容方法：根据消息键删除消息
        """
        try:
            # 解析消息键获取channel_id和message_id
            if message_key.startswith('msg:'):
                parts = message_key.split(':', 2)
                if len(parts) >= 3:
                    channel_id, message_id = parts[1], parts[2]
                else:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return False
            elif ':' in message_key:
                try:
                    channel_id, message_id = message_key.rsplit(':', 1)
                except ValueError:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return False
            else:
                logger.warning(f"不支持的消息键格式: {message_key}")
                return False
            
            # 转换message_id为整数
            try:
                message_id = int(message_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的消息ID: {message_id}")
                return False
            
            # 使用内部的delete_message方法
            return self._delete_message_old(channel_id, message_id)
            
        except Exception as e:
            logger.error(f"删除消息失败 {message_key}: {e}")
            return False
    
    # 添加兼容别名方法，保持API一致性
    def update_message_status(self, message_key_or_channel: str, message_id_or_status=None, new_status_or_reviewer=None, reviewer_id_or_reason=None, reason=None):
        """
        兼容的update_message_status方法
        支持两种调用方式：
        1. update_message_status(channel_id, message_id, new_status, reviewer_id, reason)  # 原始方式
        2. update_message_status(message_key, new_status, reviewer_id, reason)  # 新方式
        """
        if isinstance(message_id_or_status, int):
            # 原始方式：update_message_status(channel_id, message_id, new_status, reviewer_id, reason)
            channel_id = message_key_or_channel
            message_id = message_id_or_status
            new_status = new_status_or_reviewer
            reviewer_id = reviewer_id_or_reason
            return self._update_message_status_old(channel_id, message_id, new_status, reviewer_id)
        else:
            # 新方式：update_message_status(message_key, new_status, reviewer_id, reason)
            message_key = message_key_or_channel
            new_status = message_id_or_status
            reviewer_id = new_status_or_reviewer
            reason = reviewer_id_or_reason
            return self.update_message_status_by_key(message_key, new_status, reviewer_id, reason)
    
    def delete_message(self, message_key_or_channel: str, message_id=None):
        """
        兼容的delete_message方法
        支持两种调用方式：
        1. delete_message(channel_id, message_id)  # 原始方式
        2. delete_message(message_key)  # 新方式
        """
        if message_id is not None:
            # 原始方式：delete_message(channel_id, message_id)
            channel_id = message_key_or_channel
            return self._delete_message_old(channel_id, message_id)
        else:
            # 新方式：delete_message(message_key)
            message_key = message_key_or_channel
            return self.delete_message_by_key(message_key)