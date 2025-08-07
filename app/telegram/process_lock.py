"""
进程锁机制，防止多进程同时访问Telegram
使用Redis作为分布式锁
"""
import asyncio
import time
import uuid
import logging
from typing import Optional, AsyncContextManager
from contextlib import asynccontextmanager
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

class TelegramProcessLock:
    """Telegram进程锁，确保只有一个进程可以访问Telegram"""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self.lock_key = "telegram:process:lock"
        self.lock_owner_key = "telegram:process:owner"
        self.heartbeat_key = "telegram:process:heartbeat"
        self.lock_timeout = 30  # 锁超时时间（秒）
        self.heartbeat_interval = 10  # 心跳间隔（秒）
        self.process_id = str(uuid.uuid4())  # 进程唯一标识
        self._redis: Optional[redis.Redis] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
    
    async def _get_redis(self) -> redis.Redis:
        """获取Redis连接"""
        if not self._redis:
            self._redis = await redis.from_url(self.redis_url, decode_responses=True)
        return self._redis
    
    async def acquire(self, timeout: float = 10.0) -> bool:
        """
        尝试获取锁
        
        Args:
            timeout: 获取锁的超时时间（秒）
            
        Returns:
            bool: 是否成功获取锁
        """
        redis_client = await self._get_redis()
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 尝试获取锁
                lock_acquired = await redis_client.set(
                    self.lock_key,
                    self.process_id,
                    nx=True,  # 仅当键不存在时设置
                    ex=self.lock_timeout
                )
                
                if lock_acquired:
                    # 记录锁拥有者信息
                    await redis_client.setex(
                        self.lock_owner_key,
                        self.lock_timeout,
                        f"{self.process_id}:{time.time()}"
                    )
                    
                    # 启动心跳
                    self._start_heartbeat()
                    
                    logger.info(f"进程 {self.process_id} 成功获取Telegram锁")
                    return True
                
                # 检查当前锁是否由自己持有
                current_owner = await redis_client.get(self.lock_key)
                if current_owner == self.process_id:
                    # 刷新锁超时时间
                    await redis_client.expire(self.lock_key, self.lock_timeout)
                    return True
                
                # 检查锁是否已经超时（心跳机制）
                last_heartbeat = await redis_client.get(self.heartbeat_key)
                if last_heartbeat:
                    last_heartbeat_time = float(last_heartbeat)
                    if time.time() - last_heartbeat_time > self.lock_timeout:
                        # 锁已超时，尝试强制获取
                        logger.warning(f"检测到锁超时，尝试强制获取")
                        await redis_client.delete(self.lock_key)
                        continue
                
                # 等待一段时间后重试
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"获取锁时出错: {e}")
                await asyncio.sleep(0.5)
        
        logger.warning(f"进程 {self.process_id} 获取Telegram锁超时")
        return False
    
    async def release(self):
        """释放锁"""
        try:
            redis_client = await self._get_redis()
            
            # 停止心跳
            self._stop_heartbeat()
            
            # 检查锁是否由自己持有
            current_owner = await redis_client.get(self.lock_key)
            if current_owner == self.process_id:
                await redis_client.delete(self.lock_key)
                await redis_client.delete(self.lock_owner_key)
                await redis_client.delete(self.heartbeat_key)
                logger.info(f"进程 {self.process_id} 释放Telegram锁")
            else:
                logger.warning(f"进程 {self.process_id} 尝试释放不属于自己的锁")
                
        except Exception as e:
            logger.error(f"释放锁时出错: {e}")
    
    def _start_heartbeat(self):
        """启动心跳任务"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    def _stop_heartbeat(self):
        """停止心跳任务"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        try:
            redis_client = await self._get_redis()
            while True:
                try:
                    # 更新心跳时间
                    await redis_client.setex(
                        self.heartbeat_key,
                        self.lock_timeout,
                        str(time.time())
                    )
                    
                    # 刷新锁超时时间
                    await redis_client.expire(self.lock_key, self.lock_timeout)
                    
                except Exception as e:
                    logger.error(f"心跳更新失败: {e}")
                
                await asyncio.sleep(self.heartbeat_interval)
                
        except asyncio.CancelledError:
            pass
    
    @asynccontextmanager
    async def lock(self, timeout: float = 10.0):
        """
        上下文管理器，自动获取和释放锁
        
        Usage:
            async with process_lock.lock():
                # 执行Telegram操作
                pass
        """
        acquired = await self.acquire(timeout)
        if not acquired:
            raise RuntimeError("无法获取Telegram进程锁")
        try:
            yield
        finally:
            await self.release()
    
    async def is_locked(self) -> bool:
        """检查锁是否被持有"""
        try:
            redis_client = await self._get_redis()
            return await redis_client.exists(self.lock_key) == 1
        except Exception as e:
            logger.error(f"检查锁状态时出错: {e}")
            return False
    
    async def get_lock_info(self) -> Optional[dict]:
        """获取锁信息"""
        try:
            redis_client = await self._get_redis()
            
            lock_owner = await redis_client.get(self.lock_key)
            owner_info = await redis_client.get(self.lock_owner_key)
            last_heartbeat = await redis_client.get(self.heartbeat_key)
            
            if not lock_owner:
                return None
            
            info = {
                "owner_id": lock_owner,
                "is_mine": lock_owner == self.process_id,
                "owner_info": owner_info,
                "last_heartbeat": float(last_heartbeat) if last_heartbeat else None,
                "heartbeat_age": time.time() - float(last_heartbeat) if last_heartbeat else None
            }
            
            return info
            
        except Exception as e:
            logger.error(f"获取锁信息时出错: {e}")
            return None
    
    async def force_release(self):
        """强制释放锁（仅用于紧急情况）"""
        try:
            redis_client = await self._get_redis()
            await redis_client.delete(self.lock_key)
            await redis_client.delete(self.lock_owner_key)
            await redis_client.delete(self.heartbeat_key)
            logger.warning(f"进程 {self.process_id} 强制释放了Telegram锁")
        except Exception as e:
            logger.error(f"强制释放锁时出错: {e}")
    
    async def cleanup(self):
        """清理资源"""
        self._stop_heartbeat()
        if self._redis:
            await self._redis.close()
            self._redis = None

# 全局锁实例
telegram_lock = TelegramProcessLock()