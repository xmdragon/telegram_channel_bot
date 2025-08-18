"""
Redis数据存储层 - 重构后的统一入口点
处理消息、会话、缓存等数据的存储

本模块经过重构，将原有的903行代码拆分为专门化的模块：
- redis_client.py: Redis客户端连接和基础操作
- message_store.py: 消息数据存储操作
- session_store.py: 会话存储操作
- channel_store.py: 频道状态管理
- cache_store.py: 缓存操作
- lock_manager.py: 分布式锁管理

该文件保持向后兼容性，提供统一的API接口
"""
import logging
from typing import Dict, List, Optional, Any

# 导入重构后的专门化模块
from .redis_client import get_redis_client, RedisBaseStore
from .message_store import RedisMessageStore
from .session_store import RedisSessionStore
from .channel_store import RedisChannelStore
from .cache_store import RedisCacheStore
from .lock_manager import RedisLockManager

logger = logging.getLogger(__name__)

# 保持向后兼容的类名映射
class RedisStore(RedisBaseStore):
    """Redis存储基类 - 向后兼容"""
    pass

# 全局实例变量（保持原有API）
redis_message_store = None
redis_session_store = None 
redis_channel_store = None
redis_cache_store = None
redis_lock_manager = None

def init_redis_stores(redis_url: str = None):
    """初始化Redis存储实例 - 单例模式，避免重复初始化
    
    这个函数保持与原有API完全兼容
    """
    global redis_message_store, redis_session_store, redis_channel_store
    global redis_cache_store, redis_lock_manager
    
    # 检查是否已经初始化
    if (redis_message_store is not None and redis_session_store is not None and 
        redis_channel_store is not None):
        logger.debug("Redis存储层已经初始化，跳过重复初始化")
        return True
    
    try:
        if redis_url is None:
            from app.core.config import settings
            redis_url = settings.REDIS_URL
        
        # 创建专门化的存储实例（共享连接池）
        redis_message_store = RedisMessageStore(redis_url)
        redis_session_store = RedisSessionStore(redis_url)
        redis_channel_store = RedisChannelStore(redis_url)
        redis_cache_store = RedisCacheStore(redis_url)
        redis_lock_manager = RedisLockManager(redis_url)
        
        logger.info("Redis存储层初始化成功 (消息、会话、频道、缓存、锁管理)")
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

def get_redis_cache_store() -> RedisCacheStore:
    """获取缓存存储实例"""
    if redis_cache_store is None:
        raise RuntimeError("Redis存储层未初始化")
    return redis_cache_store

def get_redis_lock_manager() -> RedisLockManager:
    """获取锁管理器实例"""
    if redis_lock_manager is None:
        raise RuntimeError("Redis存储层未初始化")
    return redis_lock_manager

def get_redis_store() -> RedisStore:
    """获取基础Redis存储实例 - 向后兼容"""
    if redis_message_store is None:
        raise RuntimeError("Redis存储层未初始化")
    return redis_message_store

async def get_async_redis_client():
    """获取Redis客户端（异步兼容）"""
    if redis_message_store is None:
        return None
    return redis_message_store.redis

# ============================================================================
# 向后兼容的API - 保持原有接口不变
# ============================================================================

# 为了完全向后兼容，我们需要重新暴露所有原有的类
# 但现在它们指向重构后的专门化类

# 将原有的类重新导出，保持API兼容性
RedisMessageStore = RedisMessageStore
RedisSessionStore = RedisSessionStore  
RedisChannelStore = RedisChannelStore

# 同时提供一个统一的兼容接口
class UnifiedRedisStore(RedisStore):
    """统一的Redis存储接口 - 向后兼容
    
    这个类提供了一个统一的接口来访问所有重构后的模块
    保持与原有代码的完全兼容性
    """
    
    def __init__(self, redis_url: str = None):
        if redis_url is None:
            from app.core.config import settings
            redis_url = settings.REDIS_URL
        super().__init__(redis_url)
        
        # 初始化所有专门化模块
        self.message_store = RedisMessageStore(redis_url)
        self.session_store = RedisSessionStore(redis_url)
        self.channel_store = RedisChannelStore(redis_url)
        self.cache_store = RedisCacheStore(redis_url)
        self.lock_manager = RedisLockManager(redis_url)
    
    # ========= 消息存储方法代理 =========
    def save_message(self, channel_id: str, message_id: int, data: Dict[str, Any]) -> bool:
        return self.message_store.save_message(channel_id, message_id, data)
    
    def get_message(self, channel_id: str, message_id: int, silent: bool = False) -> Optional[Dict[str, Any]]:
        return self.message_store.get_message(channel_id, message_id, silent)
    
    def get_messages_by_channel(self, channel_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        return self.message_store.get_messages_by_channel(channel_id, limit, offset)
    
    def get_pending_messages(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return self.message_store.get_pending_messages(limit, offset)
    
    def get_messages_by_status(self, status: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return self.message_store.get_messages_by_status(status, limit, offset)
    
    def get_all_messages(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return self.message_store.get_all_messages(limit, offset)
    
    def update_message_status(self, channel_id: str, message_id: int, new_status: str, reviewed_by: str = None) -> bool:
        return self.message_store.update_message_status(channel_id, message_id, new_status, reviewed_by)
    
    async def update_message_review_id(self, channel_id: str, message_id: int, review_message_id: int) -> bool:
        return await self.message_store.update_message_review_id(channel_id, message_id, review_message_id)
    
    async def update_message_field(self, channel_id: str, message_id: int, field: str, value: Any) -> bool:
        return await self.message_store.update_message_field(channel_id, message_id, field, value)
    
    async def update_message(self, channel_id: str, message_id: int, update_data: dict) -> bool:
        return await self.message_store.update_message(channel_id, message_id, update_data)
    
    def delete_message(self, channel_id: str, message_id: int) -> bool:
        return self.message_store.delete_message(channel_id, message_id)
    
    def get_message_count(self, channel_id: str = None, status: str = None) -> int:
        return self.message_store.get_message_count(channel_id, status)
    
    def find_duplicate_by_hash(self, media_hash: str) -> List[str]:
        return self.message_store.find_duplicate_by_hash(media_hash)
    
    def cleanup_expired_indexes(self):
        return self.message_store.cleanup_expired_indexes()
        
    def cleanup_invalid_indexes(self):
        return self.message_store.cleanup_invalid_indexes()
    
    async def get_old_messages_for_cleanup(self, cutoff_time):
        return await self.message_store.get_old_messages_for_cleanup(cutoff_time)
    
    # ========= 会话存储方法代理 =========
    def save_session(self, token: str, session_data: Dict[str, Any], expire_seconds: int = 3600) -> bool:
        return self.session_store.save_session(token, session_data, expire_seconds)
    
    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        return self.session_store.get_session(token)
    
    def delete_session(self, token: str) -> bool:
        return self.session_store.delete_session(token)
    
    def get_active_sessions(self) -> List[str]:
        return self.session_store.get_active_sessions()
    
    # ========= 频道存储方法代理 =========
    def set_checkpoint(self, channel_id: str, last_message_id: int) -> bool:
        return self.channel_store.set_checkpoint(channel_id, last_message_id)
    
    def get_checkpoint(self, channel_id: str) -> Optional[int]:
        return self.channel_store.get_checkpoint(channel_id)
    
    def get_all_checkpoints(self) -> Dict[str, int]:
        return self.channel_store.get_all_checkpoints()
    
    def delete_checkpoint(self, channel_id: str) -> bool:
        return self.channel_store.delete_checkpoint(channel_id)
    
    def get_checkpoint_time(self, channel_id: str) -> Optional[str]:
        return self.channel_store.get_checkpoint_time(channel_id)
    
    def get_checkpoint_info(self, channel_id: str) -> Dict[str, any]:
        return self.channel_store.get_checkpoint_info(channel_id)
    
    # ========= 缓存方法代理 =========
    def set_cache(self, key: str, value: Any, ttl: int = None) -> bool:
        return self.cache_store.set_cache(key, value, ttl)
    
    def get_cache(self, key: str) -> Any:
        return self.cache_store.get_cache(key)
    
    def delete_cache(self, key: str) -> bool:
        return self.cache_store.delete_cache(key)
    
    # ========= 锁管理方法代理 =========
    def acquire_lock(self, lock_name: str, timeout: int = None, retry_delay: float = 0.1, max_retries: int = 10) -> Optional[str]:
        return self.lock_manager.acquire_lock(lock_name, timeout, retry_delay, max_retries)
    
    def release_lock(self, lock_name: str, lock_token: str) -> bool:
        return self.lock_manager.release_lock(lock_name, lock_token)
    
    def is_locked(self, lock_name: str) -> bool:
        return self.lock_manager.is_locked(lock_name)

# 为了完全向后兼容，提供原有的实例创建方式
def create_unified_store(redis_url: str = None) -> UnifiedRedisStore:
    """创建统一的Redis存储实例 - 向后兼容"""
    return UnifiedRedisStore(redis_url)

# ============================================================================
# 系统状态和管理API
# ============================================================================

def get_storage_health() -> Dict[str, Any]:
    """获取存储系统健康状态"""
    try:
        health = {
            'status': 'healthy',
            'modules': {},
            'connections': {},
            'errors': []
        }
        
        # 检查各个模块的状态
        modules_to_check = [
            ('message_store', redis_message_store),
            ('session_store', redis_session_store),
            ('channel_store', redis_channel_store),
            ('cache_store', redis_cache_store),
            ('lock_manager', redis_lock_manager)
        ]
        
        for module_name, module_instance in modules_to_check:
            if module_instance is None:
                health['modules'][module_name] = 'not_initialized'
                health['errors'].append(f"{module_name} not initialized")
            else:
                try:
                    # 测试连接
                    if hasattr(module_instance, 'ping') and module_instance.ping():
                        health['modules'][module_name] = 'healthy'
                    else:
                        health['modules'][module_name] = 'unhealthy'
                        health['errors'].append(f"{module_name} ping failed")
                except Exception as e:
                    health['modules'][module_name] = 'error'
                    health['errors'].append(f"{module_name} error: {str(e)}")
        
        # 获取连接信息
        if redis_message_store:
            try:
                health['connections']['redis'] = redis_message_store.get_connection_info()
                health['connections']['memory'] = redis_message_store.get_memory_usage()
                health['connections']['db_size'] = redis_message_store.get_db_size()
            except Exception as e:
                health['errors'].append(f"Connection info error: {str(e)}")
        
        # 确定整体状态
        if health['errors']:
            health['status'] = 'degraded' if any(status == 'healthy' for status in health['modules'].values()) else 'unhealthy'
        
        return health
        
    except Exception as e:
        logger.error(f"获取存储健康状态失败: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'modules': {},
            'connections': {}
        }

def get_storage_stats() -> Dict[str, Any]:
    """获取存储系统统计信息"""
    try:
        stats = {
            'message_stats': {},
            'session_stats': {},
            'cache_stats': {},
            'lock_stats': {}
        }
        
        # 消息统计
        if redis_message_store:
            try:
                stats['message_stats'] = {
                    'pending_count': redis_message_store.get_message_count(status='pending'),
                    'approved_count': redis_message_store.get_message_count(status='approved'),
                    'rejected_count': redis_message_store.get_message_count(status='rejected'),
                    'total_today': redis_message_store.get_message_count()
                }
            except Exception as e:
                stats['message_stats'] = {'error': str(e)}
        
        # 会话统计
        if redis_session_store:
            try:
                stats['session_stats'] = redis_session_store.get_session_stats()
            except Exception as e:
                stats['session_stats'] = {'error': str(e)}
        
        # 缓存统计
        if redis_cache_store:
            try:
                stats['cache_stats'] = redis_cache_store.get_cache_stats()
            except Exception as e:
                stats['cache_stats'] = {'error': str(e)}
        
        # 锁统计
        if redis_lock_manager:
            try:
                stats['lock_stats'] = redis_lock_manager.get_lock_stats()
            except Exception as e:
                stats['lock_stats'] = {'error': str(e)}
        
        return stats
        
    except Exception as e:
        logger.error(f"获取存储统计失败: {e}")
        return {'error': str(e)}

# ============================================================================
# 向后兼容性保证
# ============================================================================

# 确保所有原有的导入都能正常工作
__all__ = [
    # 原有的类和函数
    'RedisStore',
    'RedisMessageStore', 
    'RedisSessionStore',
    'RedisChannelStore',
    'get_redis_client',
    'init_redis_stores',
    'get_redis_message_store',
    'get_redis_session_store', 
    'get_redis_channel_store',
    'get_redis_store',
    'get_async_redis_client',
    
    # 新增的类和函数
    'RedisCacheStore',
    'RedisLockManager', 
    'UnifiedRedisStore',
    'get_redis_cache_store',
    'get_redis_lock_manager',
    'create_unified_store',
    'get_storage_health',
    'get_storage_stats'
]

logger.info("Redis存储层重构完成 - 所有模块已加载，保持向后兼容性")