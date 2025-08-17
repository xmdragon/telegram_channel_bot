"""
Redis客户端连接和基础操作模块
提供单例模式的Redis连接池管理和基础数据操作
"""
import json
import logging
import redis
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 全局Redis连接池，避免重复创建连接
_redis_pool = None
_redis_client = None

def get_redis_client(redis_url: str = "redis://localhost:6379"):
    """获取Redis客户端，使用连接池模式"""
    global _redis_pool, _redis_client
    
    if _redis_client is None:
        try:
            # 创建连接池
            _redis_pool = redis.ConnectionPool.from_url(
                redis_url, 
                decode_responses=True,
                max_connections=20,  # 最大连接数
                retry_on_timeout=True
            )
            _redis_client = redis.Redis(connection_pool=_redis_pool)
            
            # 测试连接
            _redis_client.ping()
            logger.info("Redis连接池初始化成功")
            
        except Exception as e:
            logger.error(f"Redis连接池初始化失败: {e}")
            raise
    
    return _redis_client

class RedisBaseStore:
    """Redis存储基类，提供通用的连接和序列化功能"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        # 使用共享的Redis连接池
        self.redis = get_redis_client(redis_url)
        logger.debug(f"Redis存储实例已创建: {self.__class__.__name__}")
    
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
            # 如果不是JSON，返回原始数据
            return data
    
    def ping(self) -> bool:
        """测试Redis连接"""
        try:
            return self.redis.ping()
        except Exception as e:
            logger.error(f"Redis连接测试失败: {e}")
            return False
    
    def flushdb(self) -> bool:
        """清空当前数据库（仅用于测试）"""
        try:
            self.redis.flushdb()
            logger.warning("Redis数据库已清空")
            return True
        except Exception as e:
            logger.error(f"清空数据库失败: {e}")
            return False
    
    def get_memory_usage(self) -> dict:
        """获取Redis内存使用情况"""
        try:
            info = self.redis.info('memory')
            return {
                'used_memory': info.get('used_memory', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'used_memory_peak': info.get('used_memory_peak', 0),
                'used_memory_peak_human': info.get('used_memory_peak_human', '0B'),
                'maxmemory': info.get('maxmemory', 0),
                'maxmemory_human': info.get('maxmemory_human', '0B')
            }
        except Exception as e:
            logger.error(f"获取内存使用情况失败: {e}")
            return {}
    
    def get_db_size(self) -> int:
        """获取数据库键数量"""
        try:
            return self.redis.dbsize()
        except Exception as e:
            logger.error(f"获取数据库大小失败: {e}")
            return 0
    
    def get_connection_info(self) -> dict:
        """获取连接信息"""
        try:
            info = self.redis.info('clients')
            return {
                'connected_clients': info.get('connected_clients', 0),
                'max_clients': info.get('maxclients', 0),
                'blocked_clients': info.get('blocked_clients', 0)
            }
        except Exception as e:
            logger.error(f"获取连接信息失败: {e}")
            return {}

async def get_async_redis_client():
    """获取Redis客户端（异步兼容）"""
    return get_redis_client()