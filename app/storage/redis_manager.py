"""
Redis管理器 - 桥接模块
SQLite迁移后，redis_manager是DatabaseManager的别名
Redis仅保留用于WebSocket pub/sub
"""
import logging
import threading

from app.storage.database import DatabaseManager, db_manager, get_db_manager

logger = logging.getLogger(__name__)


class RedisPubSub:
    """轻量Redis pub/sub - 仅用于WebSocket跨进程广播"""

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
        self._initialized = True

    def _get_redis(self):
        """延迟初始化Redis连接 - 仅用于pub/sub"""
        if self._redis_client is None:
            try:
                import redis as redis_lib
                from app.core.config import settings
                self._redis_client = redis_lib.Redis.from_url(
                    settings.REDIS_URL, decode_responses=True)
                self._redis_client.ping()
                logger.info("Redis pub/sub 连接已建立")
            except Exception as e:
                logger.warning(f"Redis pub/sub 不可用: {e}")
                self._redis_client = None
        return self._redis_client

    def publish(self, channel: str, message: str) -> bool:
        """发布消息到Redis频道"""
        client = self._get_redis()
        if client is None:
            return False
        try:
            client.publish(channel, message)
            return True
        except Exception as e:
            logger.error(f"Redis publish 失败: {e}")
            self._redis_client = None
            return False

    def subscribe(self, channel: str):
        """订阅Redis频道 - 返回pubsub对象"""
        client = self._get_redis()
        if client is None:
            return None
        try:
            pubsub = client.pubsub()
            pubsub.subscribe(channel)
            return pubsub
        except Exception as e:
            logger.error(f"Redis subscribe 失败: {e}")
            self._redis_client = None
            return None


# =============================================
# 全局实例 - 向后兼容
# =============================================

# redis_manager 现在是 DatabaseManager 实例
redis_manager = db_manager

# RedisManager 类别名
RedisManager = DatabaseManager

# pub/sub 实例
redis_pubsub = RedisPubSub()


# =============================================
# 兼容函数
# =============================================

def get_redis_manager():
    """获取管理器实例 - 返回DatabaseManager"""
    return db_manager


def get_message_store():
    """兼容函数 - 返回DatabaseManager实例"""
    return db_manager


def get_cache_store():
    """兼容函数 - 返回DatabaseManager实例"""
    return db_manager


def get_session_store():
    """兼容函数 - 返回DatabaseManager实例"""
    return db_manager
