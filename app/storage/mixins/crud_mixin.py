"""
消息基础CRUD操作Mixin
处理消息的创建、读取、更新、删除基础操作
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)


class MessageCrudMixin:
    """消息基础CRUD操作"""
    
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
            
            # 🚀 Linus式修复：visual_hash可能是复杂对象，不直接用作键名
            if data.get('visual_hash'):
                # 为复杂的visual_hash生成稳定的键名
                import hashlib
                visual_hash_value = str(data['visual_hash'])
                visual_hash_key = hashlib.md5(visual_hash_value.encode('utf-8')).hexdigest()
                pipe.sadd(f"msg:hash:visual:{visual_hash_key}", f"{channel_id}:{message_id}")
            
            # 如果是组合消息，添加到组合索引
            if data.get('grouped_id'):
                pipe.sadd(f"msg:group:{data['grouped_id']}", f"{channel_id}:{message_id}")
            
            # 🚀 性能优化：如果是重复消息，添加到重复消息索引
            if data.get('duplicate_original_id'):
                pipe.zadd("msg:idx:duplicates", {f"{channel_id}:{message_id}": timestamp})
            
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
    
    async def update_message(self, channel_id: str, message_id: int, update_data: dict) -> bool:
        """更新消息的多个字段"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            logger.debug(f"开始更新消息: {msg_key}, 更新数据: {update_data}")
            
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
            
            logger.debug(f"执行Redis更新: {msg_key}, 数据: {redis_update_data}")
            self.redis.hset(msg_key, mapping=redis_update_data)
            logger.info(f"消息更新成功: {channel_id}:{message_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新消息失败 {channel_id}:{message_id}: {e}")
            import traceback
            logger.error(f"更新消息异常堆栈: {traceback.format_exc()}")
            return False
    
    def update_message_field(self, channel_id: str, message_id: int, field: str, value: Any) -> bool:
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
    
    def _update_message_status_core(self, channel_id: str, message_id: int, new_status: str, 
                            reviewed_by: str = None) -> bool:
        """更新消息状态核心逻辑 - Linus式单一数据源版本"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            
            # 检查消息是否存在
            if not self.redis.exists(msg_key):
                logger.warning(f"消息不存在: {channel_id}:{message_id}")
                return False
            
            # 获取当前状态
            old_status = self.redis.hget(msg_key, 'status') or 'pending'
            
            # 如果状态没变，直接返回
            if old_status == new_status:
                logger.debug(f"状态未变: {channel_id}:{message_id} 保持 {old_status}")
                return True
            
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
            
            # 更新索引 - 这是唯一的真相源
            timestamp = datetime.now().timestamp()
            key = f"{channel_id}:{message_id}"
            
            # 从旧状态索引移除
            pipe.zrem(f"msg:idx:{old_status}", key)
            
            # 添加到新状态索引
            pipe.zadd(f"msg:idx:{new_status}", {key: timestamp})
            
            # 暂时同步Linus统计（过渡期，后续会删除）
            from app.storage.linus_stats_store import get_linus_stats_store
            stats_store = get_linus_stats_store()
            
            # 使用Linus统计的原子更新
            if old_status == 'pending':
                stats_store.decrement_pending()
            elif old_status == 'approved':
                stats_store.decrement_approved()
            elif old_status == 'rejected':
                stats_store.decrement_rejected()
                
            if new_status == 'pending':
                stats_store.increment_pending()
            elif new_status == 'approved':
                stats_store.increment_approved()
            elif new_status == 'rejected':
                stats_store.increment_rejected()
                # 获取拒绝原因并更新
                msg_data = self.redis.hgetall(msg_key)
                rejection_reason = msg_data.get('rejection_reason', 'other')
                stats_store.increment_rejection_reason(rejection_reason)
            
            pipe.execute()
            
            logger.debug(f"✅ 消息状态已更新: {channel_id}:{message_id} {old_status} -> {new_status}")
            return True
            
        except Exception as e:
            logger.error(f"更新消息状态失败 {channel_id}:{message_id}: {e}")
            return False
    
    def _delete_message_core(self, channel_id: str, message_id: int) -> bool:
        """删除消息核心逻辑"""
        try:
            msg_key = f"msg:{channel_id}:{message_id}"
            logger.info(f"开始删除消息核心逻辑: {msg_key}")
            
            # 获取消息数据用于清理索引
            msg_data = self.get_message(channel_id, message_id, silent=True)
            logger.info(f"获取消息数据结果: {msg_key} -> {msg_data is not None}")
            
            if not msg_data:
                logger.warning(f"消息不存在，无法删除: {msg_key}")
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
            
            # 🚀 Linus式修复：清理visual_hash索引
            if msg_data.get('visual_hash'):
                import hashlib
                visual_hash_value = str(msg_data['visual_hash'])
                visual_hash_key = hashlib.md5(visual_hash_value.encode('utf-8')).hexdigest()
                pipe.srem(f"msg:hash:visual:{visual_hash_key}", f"{channel_id}:{message_id}")
            
            # 清理组合消息索引
            if msg_data.get('grouped_id'):
                pipe.srem(f"msg:group:{msg_data['grouped_id']}", f"{channel_id}:{message_id}")
            
            pipe.execute()
            
            logger.debug(f"消息已删除: {channel_id}:{message_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除消息失败 {channel_id}:{message_id}: {e}")
            return False