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
from app.storage.redis_manager import redis_manager
from app.services.unified_channel_service import unified_channel_service

logger = logging.getLogger(__name__)

class HistoryCollector:
    """历史消息采集器 - 使用Redis+JSON存储"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self._message_processor: Optional[Callable] = None
        self.collection_tasks = {}  # channel_id -> task
        
    def set_message_processor(self, processor: Callable):
        """设置消息处理器回调"""
        self._message_processor = processor
    
    def calculate_dynamic_timeout(self, message) -> float:
        """统一超时设置 - Linus式简化：直接返回1800秒"""
        # 🔥 Linus式修复：删除复杂的动态计算，统一使用1800秒
        # - 快速下载仍然快速完成（不会等到超时）
        # - 大文件有充足时间下载
        # - 避免复杂算法导致的超时过短问题
        return 1800.0  # 30分钟，足够处理任何大小的媒体文件
    
    def get_media_file_size(self, message) -> int:
        """从消息中提取媒体文件大小（字节）"""
        if not message or not message.media:
            return 0
            
        # 文档类型（视频、音频等）
        if hasattr(message.media, 'document') and message.media.document:
            return message.media.document.size or 0
        
        # 图片类型（通常较小，估算）
        elif message.photo:
            # 图片大小通常在几百KB，预估500KB
            return 500 * 1024
        
        return 0
    
    async def collect_channel_history(self, client: TelegramClient):
        """采集所有监听频道的历史消息"""
        try:
            # 检查采集开关
            collection_enabled = await self.config_manager.get_config('collection.enabled', False)
            if not collection_enabled:
                logger.debug("采集已禁用，跳过历史消息采集")
                return
                
            # 获取历史消息采集配置
            history_limit = await self.config_manager.get_config("source.history_limit", 50)
            
            if int(history_limit) <= 0:
                logger.info("历史消息采集已禁用")
                return
            
            # 获取所有源频道 (使用新的统一服务)
            channels = await unified_channel_service.get_all_channels(channel_type="source", active_only=True)
            
            if not channels:
                logger.warning("未找到活跃的源频道")
                return
                
            logger.info(f"找到 {len(channels)} 个源频道，开始采集历史消息")
            
            # 为每个频道采集历史消息
            for idx, channel in enumerate(channels, 1):
                try:
                    channel_name = channel.get('channel_name', 'unknown')
                    logger.info(f"[{idx}/{len(channels)}] 开始采集频道: {channel_name}")
                    await self._collect_single_channel_history(client, channel, history_limit)
                    logger.info(f"[{idx}/{len(channels)}] 频道 {channel_name} 采集完成")
                    await asyncio.sleep(0.5)  # 避免频率限制（优化：2秒->0.5秒）
                except Exception as e:
                    import traceback
                    channel_name = channel.get('channel_name', 'unknown')
                    logger.error(f"❌ 频道 {channel_name} 历史消息采集失败: {e}")
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    continue
            
            logger.info(f"所有 {len(channels)} 个频道历史消息采集完成")
                    
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
            
            # 🔥 Linus式简化：checkpoint是唯一真相源
            from app.storage.channel_store import RedisChannelStore
            from app.storage.redis_manager import redis_manager
            
            # 获取Redis消息存储
            if not redis_manager:
                logger.error(f"无法获取Redis消息存储，跳过频道 {channel_name}")
                return
            
            # 直接使用redis_manager作为频道存储
            redis_channel_store = RedisChannelStore(redis_manager.client)
            checkpoint_id = redis_channel_store.get_checkpoint(channel_id)
            
            # 🔥 Linus式解决方案：在源头确保类型安全
            min_id = int(checkpoint_id) if checkpoint_id else 0
            batch_limit = int(limit)  # 确保limit也是int类型
            
            if checkpoint_id:
                # 继续增量采集
                logger.info(f"从checkpoint {checkpoint_id} 继续增量采集")
            else:
                # 首次采集历史消息 - 使用传入的limit参数
                logger.info(f"首次采集，获取最近 {limit} 条历史消息")
            
            # 采集历史消息 - 先收集到列表，然后按时间顺序处理
            collected_messages = []
            latest_message_id = int(checkpoint_id or 0)
            
            logger.info(f"开始采集，min_id={min_id}, limit={batch_limit}")
            
            message_count = 0
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    async for message in client.iter_messages(entity, limit=batch_limit, min_id=min_id):
                        try:
                            # 与实时监听保持一致，处理所有消息（包括纯媒体）
                            if not message or not message.id:
                                continue
                            
                            message_count += 1
                            if message_count % 10 == 0:  # 更频繁的进度日志
                                logger.info(f"已获取 {message_count} 条消息 (最新ID: {message.id})")
                            
                            # 记录最新的消息ID
                            if message.id and message.id > latest_message_id:
                                latest_message_id = message.id
                            
                            collected_messages.append(message)
                                
                        except Exception as e:
                            logger.error(f"收集单条消息失败: {e}")
                            continue
                    
                    # 成功获取消息，跳出重试循环
                    break
                    
                except Exception as e:
                    retry_count += 1
                    import traceback
                    error_msg = str(e).lower()
                    
                    # 检查是否是网络连接错误
                    is_network_error = any(keyword in error_msg for keyword in [
                        'connection', 'network', 'timeout', 'server closed', 
                        'bytes read', 'connection lost', 'socket'
                    ])
                    
                    if is_network_error and retry_count < max_retries:
                        wait_time = 2 ** retry_count  # 指数退避
                        logger.warning(f"网络连接错误，{wait_time}秒后重试 ({retry_count}/{max_retries}): {e}")
                        await asyncio.sleep(wait_time)
                        
                        # 尝试重新连接客户端
                        try:
                            if not client.is_connected():
                                logger.info("重新连接Telegram客户端...")
                                await client.connect()
                        except Exception as reconnect_e:
                            logger.error(f"重新连接失败: {reconnect_e}")
                        
                        continue
                    else:
                        # 非网络错误或重试次数用完
                        logger.error(f"iter_messages异常 (重试{retry_count}次后失败): {e}")
                        logger.error(f"详细错误: {traceback.format_exc()}")
                        
                        # 如果有部分消息已收集，保存中间进度
                        if collected_messages and latest_message_id > int(checkpoint_id or 0):
                            logger.info(f"保存中间进度: {len(collected_messages)} 条消息")
                            redis_channel_store.set_checkpoint(channel_id, latest_message_id)
                        
                        return
                        
            logger.info(f"消息获取完成: 共获取 {message_count} 条消息，范围 min_id={min_id}, limit={batch_limit}")
            if retry_count > 0:
                logger.info(f"网络重试 {retry_count} 次后成功")
            
            # 如果没有新消息
            if not collected_messages:
                collection_type = "新频道" if not checkpoint_id else "频道"
                logger.info(f"{collection_type} {channel_name} 没有新消息，已是最新")
                    
                # 更新Redis采集点为最新值（如果有更新的消息ID）
                if latest_message_id > int(checkpoint_id or 0):
                    redis_channel_store.set_checkpoint(channel_id, latest_message_id)
                    logger.info(f"更新Redis采集点: {channel_id} -> {latest_message_id}")
                return
            
            # 按时间顺序（旧的在前）处理消息，这样媒体组能正确组合
            collected_messages.reverse()
            
            # 🔥 Linus式简化：不需要区分新频道还是增量，统一日志
            collection_type = "历史消息" if not checkpoint_id else "增量消息"
            logger.info(f"收集到 {len(collected_messages)} 条{collection_type}，开始处理...")
            
            # 处理收集到的消息
            logger.info(f"开始处理 {len(collected_messages)} 条消息...")
            
            # 详细统计各种处理结果
            stats = {
                'saved': 0,         # 成功保存
                'queued': 0,        # 异步入队（视为成功）
                'filtered': 0,      # 被过滤
                'duplicate': 0,     # 重复消息
                'pending_group': 0, # 等待媒体组合并
                'failed': 0,        # 处理失败
                'error': 0,         # 异常错误
                'unknown': 0        # 未知原因
            }
            
            for idx, message in enumerate(collected_messages, 1):
                try:
                    # 调用消息处理器处理消息（添加动态超时保护）
                    if self._message_processor:
                        try:
                            # 根据媒体文件大小动态计算超时时间
                            dynamic_timeout = self.calculate_dynamic_timeout(message)
                            file_size = self.get_media_file_size(message)
                            file_size_mb = file_size / (1024 * 1024) if file_size > 0 else 0
                            
                            logger.debug(f"消息#{message.id} 动态超时: {dynamic_timeout:.1f}秒 "
                                       f"(文件大小: {file_size_mb:.1f}MB)")
                            
                            result = await asyncio.wait_for(
                                self._message_processor(message, entity),  # entity 就是 chat
                                timeout=dynamic_timeout  # 动态超时保护
                            )
                            if result and result in stats:
                                stats[result] += 1
                            else:
                                stats['unknown'] += 1
                        except asyncio.TimeoutError:
                            file_size = self.get_media_file_size(message)
                            file_size_mb = file_size / (1024 * 1024) if file_size > 0 else 0
                            timeout_used = self.calculate_dynamic_timeout(message)
                            
                            logger.error(f"处理消息#{message.id if message else 'None'}超时"
                                       f"（{timeout_used:.1f}秒，文件大小: {file_size_mb:.1f}MB），跳过该消息")
                            stats['error'] += 1
                            continue
                    else:
                        logger.debug("未设置消息处理器，跳过消息")
                        stats['error'] += 1
                        
                    # 每处理10条消息报告进度
                    if idx % 10 == 0:
                        processed = sum(stats.values())
                        logger.info(f"已处理 {processed}/{len(collected_messages)} 条历史消息...")
                        
                except Exception as e:
                    import traceback
                    stats['error'] += 1
                    logger.error(f"处理历史消息 #{message.id if message else 'None'} 失败: {e}")
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    continue
            
            # 详细的统计报告
            total_processed = sum(stats.values())
            logger.info(f"📊 消息处理完成统计:")
            logger.info(f"   总共采集: {len(collected_messages)} 条")
            logger.info(f"   成功保存: {stats['saved']} 条")
            logger.info(f"   异步入队: {stats['queued']} 条")
            logger.info(f"   被过滤掉: {stats['filtered']} 条")
            logger.info(f"   重复消息: {stats['duplicate']} 条")
            logger.info(f"   等待合并: {stats['pending_group']} 条")
            logger.info(f"   处理失败: {stats['failed']} 条")
            logger.info(f"   异常错误: {stats['error']} 条")
            logger.info(f"   未知原因: {stats['unknown']} 条")
            logger.info(f"   处理率: {total_processed}/{len(collected_messages)} ({(total_processed/len(collected_messages)*100):.1f}%)")
            
            # 计算成功处理的消息数（保存 + 入队）
            success_count = stats['saved'] + stats['queued']
            
            # 如果成功数量太少，发出警告
            if success_count < len(collected_messages) * 0.1:  # 少于10%
                logger.warning(f"⚠️ 保存率较低: {success_count}/{len(collected_messages)} ({(success_count/len(collected_messages)*100):.1f}%)，请检查过滤规则")
            
            # 更新Redis采集点
            if latest_message_id > int(checkpoint_id or 0):
                redis_channel_store.set_checkpoint(channel_id, latest_message_id)
                logger.info(f"更新Redis采集点: {channel_id} -> {latest_message_id}")
            
            collection_type = "历史消息" if not checkpoint_id else "增量"
            logger.info(f"✅ 频道 {channel_name} {collection_type}采集完成: 保存 {stats['saved']} 条，入队 {stats['queued']} 条，过滤 {stats['filtered']} 条，重复 {stats['duplicate']} 条，总计 {len(collected_messages)} 条")
            
        except Exception as e:
            import traceback
            logger.error(f"采集频道 {channel.get('channel_name', 'unknown')} 历史消息失败: {e}")
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            
    async def stop_collection(self, channel_id: str) -> bool:
        """停止特定频道的采集任务"""
        try:
            if channel_id in self.collection_tasks:
                task = self.collection_tasks[channel_id]
                if not task.done():
                    task.cancel()
                    logger.info(f"已停止频道 {channel_id} 的历史消息采集")
                    return True
            return False
        except Exception as e:
            logger.error(f"停止历史消息采集失败: {e}")
            return False
            
    async def stop_all_collections(self):
        """停止所有采集任务"""
        for channel_id in list(self.collection_tasks.keys()):
            await self.stop_collection(channel_id)

# 全局历史采集器实例
history_collector = HistoryCollector()