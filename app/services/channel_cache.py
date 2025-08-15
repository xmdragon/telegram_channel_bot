"""
频道ID缓存管理器
用于在Redis中缓存解析后的频道ID，提供高性能访问
"""
import logging
from typing import Dict, List, Optional
import redis.asyncio as redis
from app.storage.redis_store import get_redis_message_store
from app.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class ChannelCache:
    """频道ID缓存管理器"""
    
    def __init__(self):
        self.redis_store = None
        self.config_manager = ConfigManager()
        
    async def _ensure_redis(self):
        """确保Redis连接"""
        if self.redis_store is None:
            self.redis_store = get_redis_message_store()
    
    async def resolve_channel(self, channel_input: str) -> Optional[str]:
        """解析频道用户名为数字ID"""
        if not channel_input:
            return None
            
        try:
            # 如果已经是数字ID格式，直接返回
            if channel_input.startswith('-100'):
                return channel_input
            
            # 尝试使用频道ID解析器
            from app.services.channel_id_resolver import channel_id_resolver
            from app.telegram.auth import auth_manager
            
            # 检查Telegram客户端是否已连接
            if not auth_manager.client:
                logger.debug(f"Telegram客户端未连接，跳过频道解析: {channel_input}")
                return None
            
            # 获取频道信息
            channel_info = await channel_id_resolver.get_channel_info(channel_input)
            if channel_info and channel_info.get('id'):
                resolved_id = str(channel_info['id'])
                # 确保ID格式正确
                if not resolved_id.startswith('-100'):
                    resolved_id = f"-100{resolved_id}" if not resolved_id.startswith('-') else resolved_id
                logger.info(f"频道解析成功: {channel_input} -> {resolved_id}")
                return resolved_id
            else:
                logger.warning(f"频道解析失败: {channel_input}")
                return None
                
        except Exception as e:
            logger.debug(f"解析频道时出错 {channel_input}: {e}")
            return None
    
    async def resolve_group(self, group_input: str) -> Optional[str]:
        """解析审核群链接/ID为数字ID"""
        if not group_input:
            return None
            
        try:
            # 如果已经是数字ID格式，直接返回
            if group_input.startswith('-100'):
                return group_input
            
            # 尝试使用链接解析器
            from app.services.telegram_link_resolver import link_resolver
            
            resolved_id = await link_resolver.resolve_and_cache_group_id(group_input)
            if resolved_id:
                logger.info(f"审核群解析成功: {group_input} -> {resolved_id}")
                return str(resolved_id)
            else:
                logger.warning(f"审核群解析失败: {group_input}")
                return None
                
        except Exception as e:
            logger.debug(f"解析审核群时出错 {group_input}: {e}")
            return None
    
    async def init_cache(self):
        """应用启动时预加载所有频道ID到Redis缓存"""
        try:
            await self._ensure_redis()
            logger.info("开始初始化频道ID缓存...")
            
            # 解析并缓存目标频道
            target_channel = await self.config_manager.get_config('channels.target_channel_name', '')
            if target_channel:
                resolved_id = await self.resolve_channel(target_channel)
                if resolved_id:
                    await self.redis_store.redis.set('cache:target_channel_id', resolved_id)
                    logger.info(f"目标频道ID已缓存: {target_channel} -> {resolved_id}")
            
            # 解析并缓存审核群
            review_group = await self.config_manager.get_config('channels.review_group_name', '')
            if review_group:
                resolved_id = await self.resolve_group(review_group)
                if resolved_id:
                    await self.redis_store.redis.set('cache:review_group_id', resolved_id)
                    logger.info(f"审核群ID已缓存: {review_group} -> {resolved_id}")
            
            # 解析并缓存所有监听频道
            from app.storage.json_store import get_json_channel_store
            channel_store = get_json_channel_store()
            source_channels = channel_store.get_all_channels()
            
            if source_channels:
                cache_data = {}
                for channel_data in source_channels:
                    channel_name = channel_data.get('channel_name', '')
                    if channel_name and channel_data.get('channel_type') == 'source':
                        resolved_id = await self.resolve_channel(channel_name)
                        if resolved_id:
                            cache_data[channel_name] = resolved_id
                            logger.info(f"监听频道ID已缓存: {channel_name} -> {resolved_id}")
                
                if cache_data:
                    await self.redis_store.redis.hset('cache:source_channels', mapping=cache_data)
            
            logger.info("频道ID缓存初始化完成")
            
        except Exception as e:
            logger.error(f"初始化频道ID缓存失败: {e}", exc_info=True)
    
    async def get_target_channel_id(self) -> Optional[str]:
        """获取目标频道ID（从Redis缓存）"""
        try:
            await self._ensure_redis()
            cached_id = await self.redis_store.redis.get('cache:target_channel_id')
            return cached_id.decode('utf-8') if cached_id else None
        except Exception as e:
            logger.error(f"获取目标频道ID缓存失败: {e}")
            return None
    
    async def get_review_group_id(self) -> Optional[str]:
        """获取审核群ID（从Redis缓存）"""
        try:
            await self._ensure_redis()
            cached_id = await self.redis_store.redis.get('cache:review_group_id')
            return cached_id.decode('utf-8') if cached_id else None
        except Exception as e:
            logger.error(f"获取审核群ID缓存失败: {e}")
            return None
    
    async def get_source_channel_id(self, channel_name: str) -> Optional[str]:
        """获取指定监听频道的ID（从Redis缓存）"""
        try:
            await self._ensure_redis()
            cached_id = await self.redis_store.redis.hget('cache:source_channels', channel_name)
            return cached_id.decode('utf-8') if cached_id else None
        except Exception as e:
            logger.error(f"获取监听频道ID缓存失败 {channel_name}: {e}")
            return None
    
    async def refresh_target_channel_cache(self):
        """刷新目标频道缓存"""
        try:
            target_channel = await self.config_manager.get_config('channels.target_channel_name', '')
            if target_channel:
                resolved_id = await self.resolve_channel(target_channel)
                if resolved_id:
                    await self._ensure_redis()
                    await self.redis_store.redis.set('cache:target_channel_id', resolved_id)
                    logger.info(f"目标频道缓存已刷新: {target_channel} -> {resolved_id}")
                    return resolved_id
            return None
        except Exception as e:
            logger.error(f"刷新目标频道缓存失败: {e}")
            return None
    
    async def refresh_review_group_cache(self):
        """刷新审核群缓存"""
        try:
            review_group = await self.config_manager.get_config('channels.review_group_name', '')
            if review_group:
                resolved_id = await self.resolve_group(review_group)
                if resolved_id:
                    await self._ensure_redis()
                    await self.redis_store.redis.set('cache:review_group_id', resolved_id)
                    logger.info(f"审核群缓存已刷新: {review_group} -> {resolved_id}")
                    return resolved_id
            return None
        except Exception as e:
            logger.error(f"刷新审核群缓存失败: {e}")
            return None
    
    async def refresh_source_channels_cache(self):
        """刷新所有监听频道缓存"""
        try:
            from app.storage.json_store import get_json_channel_store
            channel_store = get_json_channel_store()
            source_channels = channel_store.get_all_channels()
            
            if source_channels:
                # 清除旧缓存
                await self._ensure_redis()
                await self.redis_store.redis.delete('cache:source_channels')
                
                # 重新缓存
                cache_data = {}
                for channel_data in source_channels:
                    channel_name = channel_data.get('channel_name', '')
                    if channel_name and channel_data.get('channel_type') == 'source':
                        resolved_id = await self.resolve_channel(channel_name)
                        if resolved_id:
                            cache_data[channel_name] = resolved_id
                            logger.info(f"监听频道缓存已刷新: {channel_name} -> {resolved_id}")
                
                if cache_data:
                    await self.redis_store.redis.hset('cache:source_channels', mapping=cache_data)
                
                logger.info("所有监听频道缓存已刷新")
                return True
            return False
        except Exception as e:
            logger.error(f"刷新监听频道缓存失败: {e}")
            return False
    
    async def clear_all_cache(self):
        """清除所有频道ID缓存"""
        try:
            await self._ensure_redis()
            await self.redis_store.redis.delete(
                'cache:target_channel_id',
                'cache:review_group_id', 
                'cache:source_channels'
            )
            logger.info("所有频道ID缓存已清除")
        except Exception as e:
            logger.error(f"清除频道ID缓存失败: {e}")

# 全局实例
channel_cache = ChannelCache()