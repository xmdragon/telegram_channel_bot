"""
Telegram历史消息采集器
专门负责历史消息采集相关功能 - 完全使用Redis+JSON存储
"""
import logging
import asyncio
from typing import Optional, Callable
from datetime import datetime
from telethon import TelegramClient

from app.services.config_manager import ConfigManager
from app.storage.redis_store import get_redis_message_store
from app.services.unified_channel_service import unified_channel_service

logger = logging.getLogger(__name__)

class HistoryCollector:
    """历史消息采集器 - 使用Redis+JSON存储"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self._message_processor: Optional[Callable] = None
        
    def set_message_processor(self, processor: Callable):
        """设置消息处理器回调"""
        self._message_processor = processor
    
    async def collect_channel_history(self, client: TelegramClient):
        """采集所有监听频道的历史消息"""
        try:
            # 检查采集开关
            collection_enabled = await self.config_manager.get_config('collection.enabled', True)
            if not collection_enabled:
                logger.debug("采集已禁用，跳过历史消息采集")
                return
                
            # 获取历史消息采集配置
            history_limit = await self.config_manager.get_config("source.history_limit", 50)
            
            if history_limit <= 0:
                logger.info("历史消息采集已禁用")
                return
            
            # 获取所有源频道 (使用新的统一服务)
            channels = await unified_channel_service.get_all_channels(channel_type="source", active_only=True)
            
            if not channels:
                logger.warning("未找到活跃的源频道")
                return
                
            logger.info(f"找到 {len(channels)} 个源频道，开始采集历史消息")
            
            # 为每个频道采集历史消息
            for channel in channels:
                try:
                    await self._collect_single_channel_history(client, channel, history_limit)
                    await asyncio.sleep(2)  # 避免频率限制
                except Exception as e:
                    logger.error(f"采集频道 {channel.get('channel_name')} 历史消息失败: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"采集频道历史消息失败: {e}")
    
    async def _collect_single_channel_history(self, client: TelegramClient, channel: dict, limit: int):
        """采集单个频道的历史消息（支持增量采集）- 使用Redis存储"""
        try:
            channel_id = channel.get('channel_id')
            channel_name = channel.get('channel_name', 'unknown')
            
            # 获取频道实体
            try:
                entity = await client.get_entity(int(channel_id))
                logger.info(f"开始检查频道 {entity.title} 的历史消息")
            except Exception as e:
                logger.error(f"获取频道 {channel_name} 实体失败: {e}")
                return
            
            # 获取Redis消息存储
            message_store = get_redis_message_store()
            if not message_store:
                logger.error(f"无法获取Redis消息存储，跳过频道 {channel_name}")
                return
            
            # 🔥 Linus式简化：checkpoint是唯一真相源
            from app.storage.redis_store import get_redis_channel_store
            from app.services.config_manager import config_manager
            
            redis_channel_store = get_redis_channel_store()
            checkpoint_id = redis_channel_store.get_checkpoint(channel_id)
            
            if checkpoint_id:
                # 继续增量采集
                logger.info(f"从checkpoint {checkpoint_id} 继续增量采集")
                min_id = checkpoint_id
                batch_limit = 500  # 增量采集限制
            else:
                # 首次采集历史消息
                history_limit = await config_manager.get_config('source.history_limit', 50)
                logger.info(f"首次采集，获取最近 {history_limit} 条历史消息")
                min_id = 0
                batch_limit = history_limit
            
            # 采集历史消息 - 先收集到列表，然后按时间顺序处理
            collected_messages = []
            latest_message_id = checkpoint_id or 0
            
            logger.info(f"开始采集，min_id={min_id}, limit={batch_limit}")
            
            message_count = 0
            async for message in client.iter_messages(entity, limit=batch_limit, min_id=min_id):
                try:
                    # 与实时监听保持一致，处理所有消息（包括纯媒体）
                    if not message or not message.id:
                        continue
                    
                    message_count += 1
                    if message_count % 100 == 0:
                        logger.info(f"已获取 {message_count} 条消息...")
                    
                    # 记录最新的消息ID
                    if message.id and message.id > latest_message_id:
                        latest_message_id = message.id
                    
                    collected_messages.append(message)
                        
                except Exception as e:
                    logger.error(f"收集历史消息失败: {e}")
                    continue
            
            # 如果没有新消息
            if not collected_messages:
                if is_new_channel:
                    logger.info(f"新频道 {channel_name} 没有历史消息")
                else:
                    logger.info(f"频道 {channel_name} 没有新消息，已是最新")
                    
                # 更新Redis采集点为最新值
                if latest_message_id > last_collected_id:
                    redis_channel_store.set_checkpoint(channel_id, latest_message_id)
                    logger.info(f"更新Redis采集点: {channel_id} -> {latest_message_id}")
                return
            
            # 按时间顺序（旧的在前）处理消息，这样媒体组能正确组合
            collected_messages.reverse()
            
            # 🔥 Linus式简化：不需要区分新频道还是增量，统一日志
            collection_type = "历史消息" if not checkpoint_id else "增量消息"
            logger.info(f"收集到 {len(collected_messages)} 条{collection_type}，开始处理...")
            
            # 处理收集到的消息
            collected = 0
            for message in collected_messages:
                try:
                    # 调用消息处理器处理消息
                    if self._message_processor:
                        await self._message_processor(message, channel_id, is_history=True)
                    else:
                        logger.warning("未设置消息处理器，跳过消息")
                        
                    collected += 1
                    
                    if collected % 10 == 0:
                        logger.info(f"已处理 {collected}/{len(collected_messages)} 条历史消息...")
                        
                except Exception as e:
                    logger.error(f"处理历史消息失败: {e}")
                    continue
                    
            # 强制完成所有待处理的组合消息
            from app.services.message_grouper import message_grouper
            logger.info(f"强制完成所有待处理的组合消息...")
            await message_grouper.force_complete_all_groups()
            
            # 等待一小段时间确保操作完成
            await asyncio.sleep(1)
            
            # 更新Redis采集点
            if latest_message_id > last_collected_id:
                redis_channel_store.set_checkpoint(channel_id, latest_message_id)
                logger.info(f"更新Redis采集点: {channel_id} -> {latest_message_id}")
            
            if is_new_channel:
                logger.info(f"新频道 {channel_name} 历史消息采集完成，共处理 {collected} 条")
            else:
                logger.info(f"频道 {channel_name} 增量采集完成，新增 {collected} 条消息")
            
        except Exception as e:
            import traceback
            logger.error(f"采集频道 {channel.get('channel_name', 'unknown')} 历史消息失败: {e}")
            logger.error(f"详细错误信息: {traceback.format_exc()}")

# 全局历史采集器实例
history_collector = HistoryCollector()