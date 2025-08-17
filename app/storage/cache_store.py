"""
缓存操作模块
处理配置缓存、临时数据缓存和通用缓存操作
"""
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
from app.utils.timezone import get_current_time
from .redis_client import RedisBaseStore

logger = logging.getLogger(__name__)

class RedisCacheStore(RedisBaseStore):
    """Redis缓存存储管理"""
    
    # 默认缓存过期时间
    DEFAULT_TTL = 3600  # 1小时
    CONFIG_TTL = 24 * 3600  # 配置缓存24小时
    TEMP_TTL = 300  # 临时缓存5分钟
    
    def set_cache(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存"""
        try:
            cache_key = f"cache:{key}"
            cache_value = self._serialize_json(value)
            
            if ttl is None:
                ttl = self.DEFAULT_TTL
            
            self.redis.setex(cache_key, ttl, cache_value)
            logger.debug(f"缓存已设置: {key} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.error(f"设置缓存失败 {key}: {e}")
            return False
    
    def get_cache(self, key: str) -> Any:
        """获取缓存"""
        try:
            cache_key = f"cache:{key}"
            cache_value = self.redis.get(cache_key)
            
            if cache_value is None:
                return None
            
            return self._deserialize_json(cache_value)
            
        except Exception as e:
            logger.error(f"获取缓存失败 {key}: {e}")
            return None
    
    def delete_cache(self, key: str) -> bool:
        """删除缓存"""
        try:
            cache_key = f"cache:{key}"
            result = self.redis.delete(cache_key)
            logger.debug(f"缓存已删除: {key}")
            return result > 0
            
        except Exception as e:
            logger.error(f"删除缓存失败 {key}: {e}")
            return False
    
    def cache_exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            cache_key = f"cache:{key}"
            return self.redis.exists(cache_key) > 0
        except Exception as e:
            logger.error(f"检查缓存存在性失败 {key}: {e}")
            return False
    
    def get_cache_ttl(self, key: str) -> int:
        """获取缓存剩余过期时间"""
        try:
            cache_key = f"cache:{key}"
            return self.redis.ttl(cache_key)
        except Exception as e:
            logger.error(f"获取缓存TTL失败 {key}: {e}")
            return -1
    
    def extend_cache_ttl(self, key: str, ttl: int) -> bool:
        """延长缓存过期时间"""
        try:
            cache_key = f"cache:{key}"
            if self.redis.exists(cache_key):
                self.redis.expire(cache_key, ttl)
                logger.debug(f"缓存TTL已延长: {key} ({ttl}s)")
                return True
            return False
        except Exception as e:
            logger.error(f"延长缓存TTL失败 {key}: {e}")
            return False
    
    # 配置缓存专用方法
    def set_config_cache(self, config_key: str, config_value: Any) -> bool:
        """设置配置缓存（长期缓存）"""
        return self.set_cache(f"config:{config_key}", config_value, self.CONFIG_TTL)
    
    def get_config_cache(self, config_key: str) -> Any:
        """获取配置缓存"""
        return self.get_cache(f"config:{config_key}")
    
    def delete_config_cache(self, config_key: str) -> bool:
        """删除配置缓存"""
        return self.delete_cache(f"config:{config_key}")
    
    def refresh_config_cache(self, config_key: str, config_value: Any) -> bool:
        """刷新配置缓存"""
        self.delete_config_cache(config_key)
        return self.set_config_cache(config_key, config_value)
    
    # 临时缓存专用方法
    def set_temp_cache(self, temp_key: str, temp_value: Any, ttl: int = None) -> bool:
        """设置临时缓存（短期缓存）"""
        if ttl is None:
            ttl = self.TEMP_TTL
        return self.set_cache(f"temp:{temp_key}", temp_value, ttl)
    
    def get_temp_cache(self, temp_key: str) -> Any:
        """获取临时缓存"""
        return self.get_cache(f"temp:{temp_key}")
    
    def delete_temp_cache(self, temp_key: str) -> bool:
        """删除临时缓存"""
        return self.delete_cache(f"temp:{temp_key}")
    
    # 列表缓存操作
    def set_list_cache(self, key: str, items: List[Any], ttl: int = None) -> bool:
        """设置列表缓存"""
        try:
            cache_key = f"cache:list:{key}"
            
            # 清除原有列表
            self.redis.delete(cache_key)
            
            # 添加列表项
            if items:
                serialized_items = [self._serialize_json(item) for item in items]
                self.redis.lpush(cache_key, *serialized_items)
            
            # 设置过期时间
            if ttl is None:
                ttl = self.DEFAULT_TTL
            self.redis.expire(cache_key, ttl)
            
            logger.debug(f"列表缓存已设置: {key} ({len(items)} 项)")
            return True
            
        except Exception as e:
            logger.error(f"设置列表缓存失败 {key}: {e}")
            return False
    
    def get_list_cache(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """获取列表缓存"""
        try:
            cache_key = f"cache:list:{key}"
            items = self.redis.lrange(cache_key, start, end)
            
            result = []
            for item in items:
                try:
                    result.append(self._deserialize_json(item))
                except Exception as e:
                    logger.warning(f"反序列化列表项失败: {e}")
                    continue
            
            return result
            
        except Exception as e:
            logger.error(f"获取列表缓存失败 {key}: {e}")
            return []
    
    def add_to_list_cache(self, key: str, item: Any, max_size: int = None) -> bool:
        """向列表缓存添加项"""
        try:
            cache_key = f"cache:list:{key}"
            serialized_item = self._serialize_json(item)
            
            # 添加到列表头部
            self.redis.lpush(cache_key, serialized_item)
            
            # 限制列表大小
            if max_size and max_size > 0:
                self.redis.ltrim(cache_key, 0, max_size - 1)
            
            logger.debug(f"项已添加到列表缓存: {key}")
            return True
            
        except Exception as e:
            logger.error(f"添加到列表缓存失败 {key}: {e}")
            return False
    
    def get_list_cache_size(self, key: str) -> int:
        """获取列表缓存大小"""
        try:
            cache_key = f"cache:list:{key}"
            return self.redis.llen(cache_key)
        except Exception as e:
            logger.error(f"获取列表缓存大小失败 {key}: {e}")
            return 0
    
    # 哈希缓存操作
    def set_hash_cache(self, key: str, field: str, value: Any, ttl: int = None) -> bool:
        """设置哈希缓存字段"""
        try:
            cache_key = f"cache:hash:{key}"
            serialized_value = self._serialize_json(value)
            
            self.redis.hset(cache_key, field, serialized_value)
            
            if ttl is None:
                ttl = self.DEFAULT_TTL
            self.redis.expire(cache_key, ttl)
            
            logger.debug(f"哈希缓存字段已设置: {key}.{field}")
            return True
            
        except Exception as e:
            logger.error(f"设置哈希缓存失败 {key}.{field}: {e}")
            return False
    
    def get_hash_cache(self, key: str, field: str = None) -> Any:
        """获取哈希缓存"""
        try:
            cache_key = f"cache:hash:{key}"
            
            if field:
                # 获取单个字段
                value = self.redis.hget(cache_key, field)
                return self._deserialize_json(value) if value else None
            else:
                # 获取整个哈希
                hash_data = self.redis.hgetall(cache_key)
                result = {}
                for k, v in hash_data.items():
                    try:
                        result[k] = self._deserialize_json(v)
                    except Exception as e:
                        logger.warning(f"反序列化哈希字段失败 {k}: {e}")
                        result[k] = v
                return result
            
        except Exception as e:
            logger.error(f"获取哈希缓存失败 {key}.{field}: {e}")
            return None if field else {}
    
    def delete_hash_cache_field(self, key: str, field: str) -> bool:
        """删除哈希缓存字段"""
        try:
            cache_key = f"cache:hash:{key}"
            result = self.redis.hdel(cache_key, field)
            logger.debug(f"哈希缓存字段已删除: {key}.{field}")
            return result > 0
        except Exception as e:
            logger.error(f"删除哈希缓存字段失败 {key}.{field}: {e}")
            return False
    
    # 集合缓存操作
    def add_to_set_cache(self, key: str, *members: Any, ttl: int = None) -> int:
        """添加到集合缓存"""
        try:
            cache_key = f"cache:set:{key}"
            serialized_members = [self._serialize_json(member) for member in members]
            
            result = self.redis.sadd(cache_key, *serialized_members)
            
            if ttl is None:
                ttl = self.DEFAULT_TTL
            self.redis.expire(cache_key, ttl)
            
            logger.debug(f"已添加到集合缓存: {key} ({len(members)} 项)")
            return result
            
        except Exception as e:
            logger.error(f"添加到集合缓存失败 {key}: {e}")
            return 0
    
    def get_set_cache(self, key: str) -> List[Any]:
        """获取集合缓存"""
        try:
            cache_key = f"cache:set:{key}"
            members = self.redis.smembers(cache_key)
            
            result = []
            for member in members:
                try:
                    result.append(self._deserialize_json(member))
                except Exception as e:
                    logger.warning(f"反序列化集合成员失败: {e}")
                    continue
            
            return result
            
        except Exception as e:
            logger.error(f"获取集合缓存失败 {key}: {e}")
            return []
    
    def is_in_set_cache(self, key: str, member: Any) -> bool:
        """检查成员是否在集合缓存中"""
        try:
            cache_key = f"cache:set:{key}"
            serialized_member = self._serialize_json(member)
            return self.redis.sismember(cache_key, serialized_member)
        except Exception as e:
            logger.error(f"检查集合缓存成员失败 {key}: {e}")
            return False
    
    def remove_from_set_cache(self, key: str, *members: Any) -> int:
        """从集合缓存中移除成员"""
        try:
            cache_key = f"cache:set:{key}"
            serialized_members = [self._serialize_json(member) for member in members]
            result = self.redis.srem(cache_key, *serialized_members)
            logger.debug(f"已从集合缓存移除: {key} ({len(members)} 项)")
            return result
        except Exception as e:
            logger.error(f"从集合缓存移除失败 {key}: {e}")
            return 0
    
    # 缓存管理
    def get_all_cache_keys(self, pattern: str = "cache:*") -> List[str]:
        """获取所有缓存键"""
        try:
            keys = self.redis.keys(pattern)
            # 移除cache:前缀
            return [key.replace('cache:', '') for key in keys]
        except Exception as e:
            logger.error(f"获取缓存键失败: {e}")
            return []
    
    def clear_cache_pattern(self, pattern: str) -> int:
        """按模式清理缓存"""
        try:
            cache_pattern = f"cache:{pattern}"
            keys = self.redis.keys(cache_pattern)
            
            if keys:
                result = self.redis.delete(*keys)
                logger.info(f"已清理 {result} 个缓存键 (模式: {pattern})")
                return result
            
            return 0
            
        except Exception as e:
            logger.error(f"清理缓存失败 {pattern}: {e}")
            return 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            all_keys = self.redis.keys("cache:*")
            
            stats = {
                'total_keys': len(all_keys),
                'by_type': {
                    'simple': 0,
                    'list': 0,
                    'hash': 0,
                    'set': 0,
                    'config': 0,
                    'temp': 0
                },
                'memory_usage': 0
            }
            
            for key in all_keys:
                key_type = self.redis.type(key)
                
                if key.startswith('cache:list:'):
                    stats['by_type']['list'] += 1
                elif key.startswith('cache:hash:'):
                    stats['by_type']['hash'] += 1
                elif key.startswith('cache:set:'):
                    stats['by_type']['set'] += 1
                elif key.startswith('cache:config:'):
                    stats['by_type']['config'] += 1
                elif key.startswith('cache:temp:'):
                    stats['by_type']['temp'] += 1
                else:
                    stats['by_type']['simple'] += 1
                
                # 累计内存使用（近似）
                try:
                    stats['memory_usage'] += self.redis.memory_usage(key) or 0
                except:
                    pass
            
            return stats
            
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {'total_keys': 0, 'by_type': {}, 'memory_usage': 0}