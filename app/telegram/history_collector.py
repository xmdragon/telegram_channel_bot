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
            # 获取历史消息采集配置
            history_limit = await self.config_manager.get_config("channels.history_message_limit", 50)
            
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
            
            # 检查现有消息数量
            existing_count = message_store.get_message_count(channel_id)
            logger.info(f"频道 {channel_name} 现有消息数量: {existing_count}")
            
            # 获取最后采集的消息ID (从频道配置中获取)
            last_collected_id = channel.get('last_collected_message_id', 0)
            is_new_channel = last_collected_id == 0
            
            if is_new_channel:
                # 新频道：检查现有消息数量，采集指定数量的历史消息
                if existing_count >= limit:
                    logger.info(f"新频道 {channel_name} 已有 {existing_count} 条消息，跳过初始采集")
                    # 获取最新的消息ID作为last_collected_message_id
                    latest_messages = message_store.get_messages_by_channel(channel_id, limit=1)
                    if latest_messages:
                        max_message_id = latest_messages[0].get('message_id')
                        if max_message_id:
                            # 更新频道配置中的last_collected_message_id
                            await unified_channel_service.update_channel_last_collected_id(
                                channel_id, max_message_id)
                    return
                    
                need_collect = limit - existing_count
                logger.info(f"新频道 {channel_name} 需要采集 {need_collect} 条历史消息")
                min_id = 0  # 新频道从最早的消息开始
            else:
                # 已有频道：增量采集，从上次采集位置继续
                logger.info(f"频道 {channel_name} 上次采集到消息ID: {last_collected_id}，开始增量采集")
                need_collect = None  # 增量采集不限制数量，采集所有新消息
                min_id = last_collected_id  # 从上次位置继续
            
            # 采集历史消息 - 先收集到列表，然后按时间顺序处理
            collected_messages = []
            latest_message_id = last_collected_id
            
            # 使用min_id参数实现增量采集
            batch_limit = need_collect if need_collect else 500  # 增量采集每次最多500条
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
                        
                    # 检查消息是否已存在
                    existing_message = await message_store.get_message(channel_id, message.id)
                    if existing_message:
                        logger.debug(f"消息ID {message.id} 已存在，跳过")
                        continue  # 消息已存在，跳过
                    
                    collected_messages.append(message)
                    
                    # 如果是新频道且达到采集限制，停止
                    if is_new_channel and need_collect is not None and len(collected_messages) >= need_collect:
                        break
                        
                except Exception as e:
                    logger.error(f"收集历史消息失败: {e}")
                    continue
            
            # 如果没有新消息
            if not collected_messages:
                if is_new_channel:
                    logger.info(f"新频道 {channel_name} 没有历史消息")
                else:
                    logger.info(f"频道 {channel_name} 没有新消息，已是最新")
                    
                # 更新last_collected_message_id为最新值
                if latest_message_id > last_collected_id:
                    await unified_channel_service.update_channel_last_collected_id(
                        channel_id, latest_message_id)
                return
            
            # 按时间顺序（旧的在前）处理消息，这样媒体组能正确组合
            collected_messages.reverse()
            if is_new_channel:
                logger.info(f"新频道收集到 {len(collected_messages)} 条历史消息，开始处理...")
            else:
                logger.info(f"增量采集到 {len(collected_messages)} 条新消息，开始处理...")
            
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
            
            # 更新最后采集的消息ID
            if latest_message_id > last_collected_id:
                await unified_channel_service.update_channel_last_collected_id(
                    channel_id, latest_message_id)
                logger.info(f"更新频道 {channel_name} 最后采集消息ID: {latest_message_id}")
            
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