"""
权限缓存模块
用于减少权限检查的数据库查询
"""
from typing import Set, Optional
from datetime import datetime, timedelta
import asyncio
from collections import defaultdict

class PermissionCache:
    """权限缓存类"""
    
    def __init__(self, ttl_seconds: int = 300):  # 默认5分钟缓存
        self.cache = {}  # {admin_id: {'permissions': set(), 'expires_at': datetime}}
        self.ttl = timedelta(seconds=ttl_seconds)
        self.lock = asyncio.Lock()
    
    async def get_permissions(self, admin_id: int) -> Optional[Set[str]]:
        """获取缓存的权限"""
        async with self.lock:
            if admin_id in self.cache:
                cache_entry = self.cache[admin_id]
                if cache_entry['expires_at'] > datetime.utcnow():
                    return cache_entry['permissions']
                else:
                    # 缓存过期，删除
                    del self.cache[admin_id]
            return None
    
    async def set_permissions(self, admin_id: int, permissions: Set[str]):
        """设置权限缓存"""
        async with self.lock:
            self.cache[admin_id] = {
                'permissions': permissions,
                'expires_at': datetime.utcnow() + self.ttl
            }
    
    async def invalidate(self, admin_id: int):
        """使某个管理员的权限缓存失效"""
        async with self.lock:
            if admin_id in self.cache:
                del self.cache[admin_id]
    
    async def clear_all(self):
        """清空所有缓存"""
        async with self.lock:
            self.cache.clear()
    
    async def cleanup_expired(self):
        """清理过期的缓存项"""
        async with self.lock:
            now = datetime.utcnow()
            expired_keys = [
                admin_id for admin_id, entry in self.cache.items()
                if entry['expires_at'] <= now
            ]
            for key in expired_keys:
                del self.cache[key]

# 全局权限缓存实例
permission_cache = PermissionCache()

# 定期清理任务
async def periodic_cleanup():
    """定期清理过期缓存"""
    while True:
        await asyncio.sleep(600)  # 每10分钟清理一次
        await permission_cache.cleanup_expired()