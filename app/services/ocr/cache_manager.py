"""
OCR缓存管理模块
负责OCR结果的缓存、内存管理和性能优化
"""
import asyncio
import hashlib
import logging
import sys
from typing import Dict, Any

logger = logging.getLogger(__name__)


class CacheManager:
    """OCR缓存管理器"""
    
    def __init__(self, max_size: int = 100, memory_limit: int = 50 * 1024 * 1024):
        self.cache: Dict[str, Any] = {}
        self.max_size = max_size
        self.memory_limit = memory_limit  # 50MB默认限制
        self._lock = asyncio.Lock()
    
    def calculate_image_hash(self, image_data: bytes) -> str:
        """计算图片数据的哈希值用于缓存"""
        return hashlib.md5(image_data).hexdigest()[:16]
    
    async def get(self, key: str) -> Any:
        """异步获取缓存项"""
        async with self._lock:
            return self.cache.get(key)
    
    async def set(self, key: str, value: Any):
        """异步设置缓存项"""
        async with self._lock:
            # 检查缓存大小和内存使用
            if (len(self.cache) >= self.max_size or 
                self._estimate_cache_memory() > self.memory_limit):
                await self._cleanup_cache()
            
            # 限制单个结果大小，避免大对象占用过多内存
            if self._estimate_object_size(value) < 1024 * 1024:  # 1MB限制
                self.cache[key] = value
    
    async def clear(self):
        """清除所有缓存"""
        async with self._lock:
            self.cache.clear()
            import gc
            gc.collect()  # 强制垃圾回收
        logger.info("OCR缓存已清除")
    
    async def _cleanup_cache(self):
        """清理缓存（LRU策略）"""
        # LRU：删除最老的1/3项
        items = list(self.cache.items())
        keep_count = int(len(items) * 2/3)
        self.cache = dict(items[-keep_count:])
        logger.debug(f"缓存清理：保留 {keep_count} 项")
    
    def _estimate_cache_memory(self) -> int:
        """估算缓存占用的内存（字节）"""
        total_size = 0
        for key, value in self.cache.items():
            total_size += sys.getsizeof(key)
            total_size += self._estimate_object_size(value)
        return total_size
    
    def _estimate_object_size(self, obj) -> int:
        """递归估算对象大小"""
        size = sys.getsizeof(obj)
        
        if isinstance(obj, dict):
            size += sum(self._estimate_object_size(k) + self._estimate_object_size(v) 
                       for k, v in obj.items())
        elif isinstance(obj, (list, tuple)):
            size += sum(self._estimate_object_size(item) for item in obj)
        
        return size
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            'cache_size': len(self.cache),
            'cache_max_size': self.max_size,
            'memory_usage_bytes': self._estimate_cache_memory(),
            'memory_limit_bytes': self.memory_limit,
            'memory_usage_mb': round(self._estimate_cache_memory() / 1024 / 1024, 2),
            'memory_limit_mb': round(self.memory_limit / 1024 / 1024, 2)
        }