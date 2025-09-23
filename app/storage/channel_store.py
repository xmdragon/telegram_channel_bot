"""
频道状态管理模块
处理频道采集点、状态追踪和统计
"""
import logging
import json
from typing import Dict, Optional, List, Any
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class RedisChannelStore:
    """频道状态管理"""
    
    def __init__(self, redis_client):
        """初始化频道存储"""
        self.redis = redis_client
    
    def _serialize_json(self, data: Any) -> str:
        """序列化JSON数据"""
        return json.dumps(data, ensure_ascii=False)
    
    def _deserialize_json(self, data: str) -> Any:
        """反序列化JSON数据"""
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        return json.loads(data)
    
    def set_checkpoint(self, channel_id: str, last_message_id: int) -> bool:
        """设置频道采集点 - 强制int类型"""
        try:
            # 强制转换为int，确保类型统一
            message_id_int = int(last_message_id)

            # 🔧 临时调试：添加强制ERROR级别日志
            current_time = get_current_time().isoformat()
            logger.error(f"[CHECKPOINT_DEBUG] 开始写入: {channel_id} -> {message_id_int}, time: {current_time}")

            result1 = self.redis.hset(f"channel:checkpoint", channel_id, str(message_id_int))
            result2 = self.redis.hset(f"channel:checkpoint:time", channel_id, current_time)

            logger.error(f"[CHECKPOINT_DEBUG] Redis写入结果: checkpoint={result1}, time={result2}")
            logger.debug(f"采集点已更新: {channel_id} -> {message_id_int}")
            return True
            
        except (ValueError, TypeError) as e:
            logger.error(f"采集点类型错误 {channel_id}: {last_message_id} -> {e}")
            return False
        except Exception as e:
            logger.error(f"设置采集点失败 {channel_id}: {e}")
            return False
    
    def get_checkpoint(self, channel_id: str) -> Optional[int]:
        """获取频道采集点 - 强制返回int类型"""
        try:
            checkpoint = self.redis.hget("channel:checkpoint", channel_id)
            if checkpoint is None:
                return None
            
            # 强制转换为int，确保类型统一
            return int(checkpoint)
            
        except (ValueError, TypeError) as e:
            logger.error(f"采集点类型转换失败 {channel_id}: {checkpoint} -> {e}")
            return None
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
                # 如果是bytes类型需要decode
                time_str = checkpoint_time.decode() if isinstance(checkpoint_time, bytes) else checkpoint_time

                # 🕐 时区修复：确保返回的时间字符串包含UTC标识
                if time_str and not time_str.endswith('Z') and '+' not in time_str and 'UTC' not in time_str:
                    # 如果没有时区标识，添加Z表示UTC时间
                    time_str = time_str + 'Z'

                return time_str
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
    
    def set_channel_status(self, channel_id: str, status: str, details: Dict[str, Any] = None) -> bool:
        """设置频道状态"""
        try:
            # 保存状态信息
            status_data = {
                'status': status,
                'updated_at': get_current_time().isoformat()
            }
            
            if details:
                status_data.update(details)
            
            self.redis.hset(f"channel:status", channel_id, self._serialize_json(status_data))
            logger.debug(f"频道状态已更新: {channel_id} -> {status}")
            return True
            
        except Exception as e:
            logger.error(f"设置频道状态失败 {channel_id}: {e}")
            return False
    
    def get_channel_status(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """获取频道状态"""
        try:
            status_data = self.redis.hget("channel:status", channel_id)
            if status_data:
                return self._deserialize_json(status_data)
            return None
            
        except Exception as e:
            logger.error(f"获取频道状态失败 {channel_id}: {e}")
            return None
    
    def get_all_channel_statuses(self) -> Dict[str, Dict[str, Any]]:
        """获取所有频道状态"""
        try:
            all_statuses = self.redis.hgetall("channel:status")
            result = {}
            
            for channel_id, status_data in all_statuses.items():
                try:
                    result[channel_id] = self._deserialize_json(status_data)
                except Exception as e:
                    logger.warning(f"解析频道状态失败 {channel_id}: {e}")
                    result[channel_id] = {'status': 'unknown', 'error': str(e)}
            
            return result
            
        except Exception as e:
            logger.error(f"获取所有频道状态失败: {e}")
            return {}
    
    def delete_channel_status(self, channel_id: str) -> bool:
        """删除频道状态"""
        try:
            self.redis.hdel("channel:status", channel_id)
            logger.debug(f"已删除频道状态: {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除频道状态失败 {channel_id}: {e}")
            return False
    
    def set_channel_stats(self, channel_id: str, stats: Dict[str, Any]) -> bool:
        """设置频道统计信息"""
        try:
            stats_data = {
                **stats,
                'updated_at': get_current_time().isoformat()
            }
            
            self.redis.hset(f"channel:stats", channel_id, self._serialize_json(stats_data))
            logger.debug(f"频道统计已更新: {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"设置频道统计失败 {channel_id}: {e}")
            return False
    
    def get_channel_stats(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """获取频道统计信息"""
        try:
            stats_data = self.redis.hget("channel:stats", channel_id)
            if stats_data:
                return self._deserialize_json(stats_data)
            return None
            
        except Exception as e:
            logger.error(f"获取频道统计失败 {channel_id}: {e}")
            return None
    
    def get_all_channel_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有频道统计信息"""
        try:
            all_stats = self.redis.hgetall("channel:stats")
            result = {}
            
            for channel_id, stats_data in all_stats.items():
                try:
                    result[channel_id] = self._deserialize_json(stats_data)
                except Exception as e:
                    logger.warning(f"解析频道统计失败 {channel_id}: {e}")
                    result[channel_id] = {'error': str(e)}
            
            return result
            
        except Exception as e:
            logger.error(f"获取所有频道统计失败: {e}")
            return {}
    
    def increment_channel_counter(self, channel_id: str, counter_name: str, increment: int = 1) -> int:
        """增加频道计数器"""
        try:
            counter_key = f"channel:counter:{channel_id}:{counter_name}"
            new_value = self.redis.incrby(counter_key, increment)
            
            # 设置过期时间（30天）
            self.redis.expire(counter_key, 30 * 24 * 3600)
            
            logger.debug(f"频道计数器已更新: {channel_id}.{counter_name} = {new_value}")
            return new_value
            
        except Exception as e:
            logger.error(f"增加频道计数器失败 {channel_id}.{counter_name}: {e}")
            return 0
    
    def get_channel_counter(self, channel_id: str, counter_name: str) -> int:
        """获取频道计数器值"""
        try:
            counter_key = f"channel:counter:{channel_id}:{counter_name}"
            value = self.redis.get(counter_key)
            return int(value) if value else 0
            
        except Exception as e:
            logger.error(f"获取频道计数器失败 {channel_id}.{counter_name}: {e}")
            return 0
    
    def get_channel_counters(self, channel_id: str) -> Dict[str, int]:
        """获取频道所有计数器"""
        try:
            pattern = f"channel:counter:{channel_id}:*"
            counter_keys = self.redis.keys(pattern)
            
            result = {}
            for key in counter_keys:
                counter_name = key.split(':')[-1]  # 获取计数器名称
                value = self.redis.get(key)
                result[counter_name] = int(value) if value else 0
            
            return result
            
        except Exception as e:
            logger.error(f"获取频道计数器失败 {channel_id}: {e}")
            return {}
    
    def reset_channel_counter(self, channel_id: str, counter_name: str) -> bool:
        """重置频道计数器"""
        try:
            counter_key = f"channel:counter:{channel_id}:{counter_name}"
            self.redis.set(counter_key, 0)
            self.redis.expire(counter_key, 30 * 24 * 3600)
            
            logger.debug(f"频道计数器已重置: {channel_id}.{counter_name}")
            return True
            
        except Exception as e:
            logger.error(f"重置频道计数器失败 {channel_id}.{counter_name}: {e}")
            return False
    
    def cleanup_channel_data(self, channel_id: str) -> bool:
        """清理频道相关的所有数据"""
        try:
            pipe = self.redis.pipeline()
            
            # 删除采集点
            pipe.hdel("channel:checkpoint", channel_id)
            pipe.hdel("channel:checkpoint:time", channel_id)
            
            # 删除状态
            pipe.hdel("channel:status", channel_id)
            
            # 删除统计
            pipe.hdel("channel:stats", channel_id)
            
            # 删除计数器
            counter_pattern = f"channel:counter:{channel_id}:*"
            counter_keys = self.redis.keys(counter_pattern)
            for key in counter_keys:
                pipe.delete(key)
            
            pipe.execute()
            
            logger.info(f"已清理频道数据: {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"清理频道数据失败 {channel_id}: {e}")
            return False
    
    def get_channel_summary(self, channel_id: str) -> Dict[str, Any]:
        """获取频道完整摘要信息"""
        try:
            return {
                'channel_id': channel_id,
                'checkpoint': self.get_checkpoint_info(channel_id),
                'status': self.get_channel_status(channel_id),
                'stats': self.get_channel_stats(channel_id),
                'counters': self.get_channel_counters(channel_id)
            }
            
        except Exception as e:
            logger.error(f"获取频道摘要失败 {channel_id}: {e}")
            return {
                'channel_id': channel_id,
                'error': str(e),
                'checkpoint': None,
                'status': None,
                'stats': None,
                'counters': {}
            }