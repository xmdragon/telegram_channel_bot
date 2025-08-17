"""
分布式锁管理模块
提供Redis分布式锁功能，确保数据操作的原子性
"""
import logging
import time
import uuid
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from app.utils.timezone import get_current_time
from .redis_client import RedisBaseStore

logger = logging.getLogger(__name__)

class RedisLockManager(RedisBaseStore):
    """Redis分布式锁管理器"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", default_timeout: int = 30):
        super().__init__(redis_url)
        self.default_timeout = default_timeout
        self.locks = {}  # 本地锁记录
    
    def acquire_lock(self, lock_name: str, timeout: int = None, retry_delay: float = 0.1, max_retries: int = 10) -> Optional[str]:
        """获取分布式锁
        
        Args:
            lock_name: 锁名称
            timeout: 锁超时时间（秒）
            retry_delay: 重试间隔（秒）
            max_retries: 最大重试次数
            
        Returns:
            锁令牌，如果获取失败返回None
        """
        if timeout is None:
            timeout = self.default_timeout
        
        lock_key = f"lock:{lock_name}"
        lock_token = str(uuid.uuid4())
        
        retries = 0
        while retries < max_retries:
            try:
                # 尝试获取锁
                if self.redis.set(lock_key, lock_token, nx=True, ex=timeout):
                    # 记录本地锁信息
                    self.locks[lock_name] = {
                        'token': lock_token,
                        'acquired_at': get_current_time().isoformat(),
                        'timeout': timeout
                    }
                    
                    logger.debug(f"分布式锁已获取: {lock_name} (token: {lock_token[:8]}...)")
                    return lock_token
                
                # 锁已被占用，等待重试
                retries += 1
                if retries < max_retries:
                    time.sleep(retry_delay)
                    
            except Exception as e:
                logger.error(f"获取分布式锁失败 {lock_name}: {e}")
                break
        
        logger.warning(f"获取分布式锁超时 {lock_name} (重试 {retries} 次)")
        return None
    
    def release_lock(self, lock_name: str, lock_token: str) -> bool:
        """释放分布式锁
        
        Args:
            lock_name: 锁名称
            lock_token: 锁令牌
            
        Returns:
            是否成功释放
        """
        try:
            lock_key = f"lock:{lock_name}"
            
            # 使用Lua脚本确保原子性释放
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            
            result = self.redis.eval(lua_script, 1, lock_key, lock_token)
            
            if result:
                # 清除本地锁记录
                if lock_name in self.locks:
                    del self.locks[lock_name]
                
                logger.debug(f"分布式锁已释放: {lock_name} (token: {lock_token[:8]}...)")
                return True
            else:
                logger.warning(f"释放分布式锁失败，令牌无效: {lock_name}")
                return False
                
        except Exception as e:
            logger.error(f"释放分布式锁失败 {lock_name}: {e}")
            return False
    
    def extend_lock(self, lock_name: str, lock_token: str, extend_time: int) -> bool:
        """延长锁的过期时间
        
        Args:
            lock_name: 锁名称
            lock_token: 锁令牌
            extend_time: 延长时间（秒）
            
        Returns:
            是否成功延长
        """
        try:
            lock_key = f"lock:{lock_name}"
            
            # 使用Lua脚本确保原子性延长
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("expire", KEYS[1], ARGV[2])
            else
                return 0
            end
            """
            
            result = self.redis.eval(lua_script, 1, lock_key, lock_token, extend_time)
            
            if result:
                # 更新本地锁记录
                if lock_name in self.locks:
                    self.locks[lock_name]['timeout'] = extend_time
                
                logger.debug(f"分布式锁已延长: {lock_name} ({extend_time}s)")
                return True
            else:
                logger.warning(f"延长分布式锁失败，令牌无效: {lock_name}")
                return False
                
        except Exception as e:
            logger.error(f"延长分布式锁失败 {lock_name}: {e}")
            return False
    
    def is_locked(self, lock_name: str) -> bool:
        """检查锁是否被占用"""
        try:
            lock_key = f"lock:{lock_name}"
            return self.redis.exists(lock_key) > 0
        except Exception as e:
            logger.error(f"检查锁状态失败 {lock_name}: {e}")
            return False
    
    def get_lock_info(self, lock_name: str) -> Optional[Dict[str, Any]]:
        """获取锁信息"""
        try:
            lock_key = f"lock:{lock_name}"
            
            if not self.redis.exists(lock_key):
                return None
            
            lock_token = self.redis.get(lock_key)
            ttl = self.redis.ttl(lock_key)
            
            info = {
                'lock_name': lock_name,
                'token': lock_token,
                'ttl': ttl,
                'is_mine': lock_name in self.locks and self.locks[lock_name]['token'] == lock_token
            }
            
            # 如果是本地持有的锁，添加更多信息
            if info['is_mine']:
                local_info = self.locks[lock_name]
                info.update({
                    'acquired_at': local_info['acquired_at'],
                    'original_timeout': local_info['timeout']
                })
            
            return info
            
        except Exception as e:
            logger.error(f"获取锁信息失败 {lock_name}: {e}")
            return None
    
    def force_release_lock(self, lock_name: str) -> bool:
        """强制释放锁（管理员操作）"""
        try:
            lock_key = f"lock:{lock_name}"
            result = self.redis.delete(lock_key)
            
            # 清除本地锁记录
            if lock_name in self.locks:
                del self.locks[lock_name]
            
            if result:
                logger.warning(f"分布式锁已强制释放: {lock_name}")
                return True
            else:
                logger.warning(f"强制释放锁失败，锁不存在: {lock_name}")
                return False
                
        except Exception as e:
            logger.error(f"强制释放锁失败 {lock_name}: {e}")
            return False
    
    def cleanup_expired_locks(self) -> int:
        """清理过期的锁（通常由Redis自动处理，这里做备份清理）"""
        try:
            lock_pattern = "lock:*"
            lock_keys = self.redis.keys(lock_pattern)
            
            cleaned_count = 0
            for lock_key in lock_keys:
                ttl = self.redis.ttl(lock_key)
                if ttl == -1:  # 没有过期时间的锁
                    self.redis.delete(lock_key)
                    cleaned_count += 1
                    logger.warning(f"清理无过期时间的锁: {lock_key}")
            
            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个异常锁")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理过期锁失败: {e}")
            return 0
    
    def get_all_locks(self) -> List[Dict[str, Any]]:
        """获取所有锁信息"""
        try:
            lock_pattern = "lock:*"
            lock_keys = self.redis.keys(lock_pattern)
            
            locks = []
            for lock_key in lock_keys:
                lock_name = lock_key.replace('lock:', '')
                lock_info = self.get_lock_info(lock_name)
                if lock_info:
                    locks.append(lock_info)
            
            return locks
            
        except Exception as e:
            logger.error(f"获取所有锁信息失败: {e}")
            return []
    
    def get_lock_stats(self) -> Dict[str, Any]:
        """获取锁统计信息"""
        try:
            all_locks = self.get_all_locks()
            
            stats = {
                'total_locks': len(all_locks),
                'my_locks': len(self.locks),
                'locks_by_ttl': {
                    'expiring_soon': 0,  # TTL < 60s
                    'normal': 0,         # 60s <= TTL < 300s
                    'long_term': 0       # TTL >= 300s
                }
            }
            
            for lock in all_locks:
                ttl = lock.get('ttl', 0)
                if ttl < 60:
                    stats['locks_by_ttl']['expiring_soon'] += 1
                elif ttl < 300:
                    stats['locks_by_ttl']['normal'] += 1
                else:
                    stats['locks_by_ttl']['long_term'] += 1
            
            return stats
            
        except Exception as e:
            logger.error(f"获取锁统计失败: {e}")
            return {
                'total_locks': 0,
                'my_locks': 0,
                'locks_by_ttl': {'expiring_soon': 0, 'normal': 0, 'long_term': 0}
            }
    
    @contextmanager
    def lock(self, lock_name: str, timeout: int = None, retry_delay: float = 0.1, max_retries: int = 10):
        """上下文管理器形式的锁
        
        使用方式:
        with lock_manager.lock('my_lock'):
            # 在锁保护下的代码
            pass
        """
        lock_token = None
        try:
            # 获取锁
            lock_token = self.acquire_lock(lock_name, timeout, retry_delay, max_retries)
            
            if lock_token is None:
                raise Exception(f"无法获取锁: {lock_name}")
            
            yield lock_token
            
        finally:
            # 确保锁被释放
            if lock_token:
                self.release_lock(lock_name, lock_token)
    
    def __del__(self):
        """析构函数，清理所有本地持有的锁"""
        for lock_name, lock_info in self.locks.items():
            try:
                self.release_lock(lock_name, lock_info['token'])
            except:
                pass