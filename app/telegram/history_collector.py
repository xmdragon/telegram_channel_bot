"""
Telegram历史消息采集器
专门负责历史消息采集相关功能 - 完全使用Redis+JSON存储
"""
import logging
import asyncio
from typing import Optional, Callable, List, Dict
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
    
    # Linus式简化：删除不再需要的超时计算方法
    
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
            channels = await unified_channel_service.get_all_channels()
            
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
    
    async def _get_main_message_ids(self, client: TelegramClient, entity, min_id: int, limit: int) -> List[Dict]:
        """
        获取主消息ID列表（组消息只算一个）
        返回: [{'id': 2838, 'type': 'single'}, 
               {'id': 2830, 'type': 'group', 'group_id': '14058570976263685'}, ...]
        """
        main_messages = []
        seen_groups = set()
        
        logger.info(f"开始获取主消息ID列表，min_id={min_id}, 需要{limit}个主消息")
        
        # 获取5倍数量确保有足够主消息
        message_count = 0
        async for msg in client.iter_messages(entity, limit=limit*5, min_id=min_id):
            if not msg or not msg.id:
                continue
                
            message_count += 1
            
            # 组消息处理
            if hasattr(msg, 'grouped_id') and msg.grouped_id:
                group_id = str(msg.grouped_id)
                if group_id not in seen_groups:
                    seen_groups.add(group_id)
                    main_messages.append({
                        'id': msg.id,
                        'type': 'group',
                        'group_id': group_id
                    })
                    logger.debug(f"发现组消息: ID={msg.id}, 组={group_id}")
            else:
                # 单独消息
                main_messages.append({
                    'id': msg.id,
                    'type': 'single'
                })
                logger.debug(f"发现单独消息: ID={msg.id}")
            
            # 达到需要的主消息数量就停止
            if len(main_messages) >= limit:
                break
        
        logger.info(f"获取主消息ID完成: 扫描{message_count}条消息，获得{len(main_messages)}个主消息")
        return main_messages[:limit]

    async def _get_main_message_ids_v2(self, client: TelegramClient, entity, min_id: int, limit: int) -> List[Dict]:
        """
        获取主消息ID列表 V2版本 - 优化版本，确保获取足够的主消息
        返回: [{'id': 2838, 'type': 'single'}, 
               {'id': 2830, 'type': 'group', 'group_id': '14058570976263685'}, ...]
        """
        main_messages = []
        seen_groups = set()
        
        logger.info(f"开始获取主消息ID列表，min_id={min_id}, 需要{limit}个主消息")
        
        # 获取更多消息确保有足够主消息（每10条消息大约1个主消息）
        scan_limit = max(limit * 10, 10)  # 至少扫描10条
        message_count = 0
        
        try:
            logger.info(f"[DEBUG] 开始iter_messages循环，scan_limit={scan_limit}, min_id={min_id}")
            
            # 添加超时控制 - 防止长时间卡住
            import time
            start_time = time.time()
            timeout_seconds = 300  # 5分钟超时
            
            async for msg in client.iter_messages(entity, limit=scan_limit, min_id=min_id):
                # 超时检查 - Linus式简洁
                if time.time() - start_time > timeout_seconds:
                    logger.warning(f"消息获取超时（{timeout_seconds}秒），已获取{len(main_messages)}个主消息")
                    break
                    
                if not msg or not msg.id:
                    continue
                    
                message_count += 1
                if message_count % 5 == 0:
                    logger.info(f"[DEBUG] 已处理 {message_count} 条消息，主消息数: {len(main_messages)}")
                
                # 组消息处理
                if hasattr(msg, 'grouped_id') and msg.grouped_id:
                    group_id = str(msg.grouped_id)
                    if group_id not in seen_groups:
                        seen_groups.add(group_id)
                        main_messages.append({
                            'id': msg.id,
                            'type': 'group',
                            'group_id': group_id
                        })
                        logger.debug(f"发现组消息: ID={msg.id}, 组={group_id}")
                else:
                    # 单独消息
                    main_messages.append({
                        'id': msg.id,
                        'type': 'single'
                    })
                    logger.debug(f"发现单独消息: ID={msg.id}")
                
                # 达到需要的主消息数量就停止
                if len(main_messages) >= limit:
                    break
                    
        except asyncio.TimeoutError:
            logger.warning(f"消息迭代超时，返回已获取的{len(main_messages)}个主消息")
        except Exception as e:
            logger.error(f"获取主消息ID时异常: {e}")
            # 如果出错，返回已获取的部分
        
        logger.info(f"获取主消息ID完成: 扫描{message_count}条消息，获得{len(main_messages)}个主消息")
        return main_messages[:limit]
    
    async def _fetch_complete_group(self, client: TelegramClient, entity, group_id: str, sample_id: int) -> List:
        """获取完整的组消息 - 带超时和回退机制"""
        try:
            # 添加超时控制到组消息获取
            import asyncio
            
            # 获取附近消息 - 添加超时
            nearby_messages = await asyncio.wait_for(
                client.get_messages(
                    entity,
                    min_id=sample_id - 20,
                    max_id=sample_id + 20,
                    limit=40
                ), 
                timeout=30.0  # 30秒超时
            )
            
            # 过滤出同组消息
            group_messages = [
                msg for msg in nearby_messages
                if hasattr(msg, 'grouped_id') and str(msg.grouped_id) == group_id
            ]
            
            if group_messages:
                logger.debug(f"组 {group_id}: 在附近{len(nearby_messages)}条消息中找到{len(group_messages)}条同组消息")
                return sorted(group_messages, key=lambda x: x.id)
            else:
                # Linus式简化：如果没找到组消息，尝试直接获取单条消息作为回退
                logger.warning(f"组 {group_id}: 未找到组消息，尝试单消息回退")
                fallback_msg = await asyncio.wait_for(
                    client.get_messages(entity, ids=sample_id),
                    timeout=10.0
                )
                return [fallback_msg] if fallback_msg else []
            
        except asyncio.TimeoutError:
            logger.error(f"获取组消息超时 {group_id}，使用单消息回退")
            try:
                # 超时时的回退机制
                fallback_msg = await client.get_messages(entity, ids=sample_id)
                return [fallback_msg] if fallback_msg else []
            except:
                return []
        except Exception as e:
            logger.error(f"获取组消息失败 {group_id}: {e}")
            return []
    
    async def _fetch_messages_by_ids(self, client: TelegramClient, entity, main_messages: List[Dict]) -> List:
        """根据主消息ID获取完整消息数据"""
        all_messages = []
        
        logger.info(f"开始获取{len(main_messages)}个主消息的完整数据")
        
        logger.info(f"[DEBUG] 开始处理 {len(main_messages)} 个主消息")
        for i, main_msg in enumerate(main_messages, 1):
            logger.info(f"[DEBUG] 处理第 {i}/{len(main_messages)} 个主消息: ID={main_msg['id']}, type={main_msg['type']}")
            try:
                if main_msg['type'] == 'group':
                    # 获取整个组的消息
                    group_msgs = await self._fetch_complete_group(
                        client, entity, 
                        main_msg['group_id'], 
                        main_msg['id']
                    )
                    if group_msgs:
                        all_messages.extend(group_msgs)
                        logger.debug(f"[{i}/{len(main_messages)}] 组 {main_msg['group_id']}: 获取{len(group_msgs)}条消息")
                    else:
                        logger.warning(f"[{i}/{len(main_messages)}] 组 {main_msg['group_id']}: 获取失败，跳过")
                else:
                    # 获取单条消息
                    msg = await client.get_messages(entity, ids=main_msg['id'])
                    if msg:
                        all_messages.append(msg)
                        logger.debug(f"[{i}/{len(main_messages)}] 单消息 {main_msg['id']}: 获取成功")
                    else:
                        logger.warning(f"[{i}/{len(main_messages)}] 单消息 {main_msg['id']}: 获取失败")
                        
            except Exception as e:
                logger.error(f"获取消息失败 {main_msg}: {e}")
                continue
        
        logger.info(f"完整数据获取完成: {len(main_messages)}个主消息 → {len(all_messages)}条实际消息")
        return all_messages

    async def _fetch_complete_message(self, client: TelegramClient, entity, main_msg_info: Dict) -> List:
        """根据主消息信息获取完整消息数据"""
        try:
            if main_msg_info['type'] == 'group':
                # 获取整组消息
                logger.debug(f"获取组消息: ID={main_msg_info['id']}, 组={main_msg_info['group_id']}")
                return await self._fetch_complete_group(
                    client, entity,
                    main_msg_info['group_id'],
                    main_msg_info['id']
                )
            else:
                # 获取单条消息
                logger.debug(f"获取单消息: ID={main_msg_info['id']}")
                msg = await client.get_messages(entity, ids=main_msg_info['id'])
                return [msg] if msg else []
                
        except Exception as e:
            logger.error(f"获取完整消息失败 {main_msg_info}: {e}")
            return []

    async def _download_all_media(self, client: TelegramClient, messages: List) -> None:
        """下载所有消息的媒体文件"""
        if not messages:
            return
            
        media_tasks = []
        for msg in messages:
            if hasattr(msg, 'media') and msg.media:
                # 为每个有媒体的消息创建下载任务
                task = self._download_single_media(client, msg)
                media_tasks.append(task)
        
        if media_tasks:
            logger.info(f"开始并发下载 {len(media_tasks)} 个媒体文件...")
            # 并发下载所有媒体
            results = await asyncio.gather(*media_tasks, return_exceptions=True)
            
            # 统计下载结果
            success_count = sum(1 for r in results if r is True)
            failed_count = len(results) - success_count
            logger.info(f"媒体下载完成: 成功 {success_count}, 失败 {failed_count}")
        else:
            logger.debug("没有媒体文件需要下载")

    async def _download_single_media(self, client: TelegramClient, message) -> bool:
        """下载单条消息的媒体文件"""
        try:
            if not hasattr(message, 'media') or not message.media:
                return True  # 没有媒体也算成功
                
            logger.debug(f"下载消息 #{message.id} 的媒体文件...")
            
            # 调用现有的媒体处理逻辑 - 使用全局实例修复
            from app.services.media_handler import media_handler
            
            # 下载媒体文件 - 传递正确的参数
            result = await media_handler.download_media(
                client=client, 
                message=message, 
                message_id=message.id
            )
            return bool(result)  # 转换为布尔值
            
        except Exception as e:
            logger.error(f"下载消息 #{message.id} 媒体失败: {e}")
            return False

    async def _process_main_message(self, messages: List, entity) -> None:
        """处理主消息（单消息或组消息）"""
        try:
            if len(messages) > 1:
                # 组消息：合并处理
                representative = messages[0]
                representative._group_messages = messages
                representative._is_complete_group = True
                representative._group_size = len(messages)
                
                logger.info(f"处理组消息: #{representative.id} ({len(messages)}条)")
                if self._message_processor:
                    logger.info(f"[DEBUG] 开始调用消息处理器处理组消息 #{representative.id}")
                    await self._message_processor(representative, entity)
                    logger.info(f"[DEBUG] 消息处理器完成处理组消息 #{representative.id}")
                else:
                    logger.warning("消息处理器未设置")
            else:
                # 单消息：直接处理
                message = messages[0]
                logger.debug(f"处理单消息: #{message.id}")
                if self._message_processor:
                    await self._message_processor(message, entity)
                else:
                    logger.warning("消息处理器未设置")
                    
        except Exception as e:
            msg_ids = [msg.id for msg in messages]
            logger.error(f"处理消息失败 {msg_ids}: {e}")
            raise

    async def _collect_single_channel_history(self, client: TelegramClient, channel: dict, limit: int):
        """采集单个频道的历史消息（主消息驱动模式）- 使用Redis存储"""
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
            
            if checkpoint_id:
                # 继续增量采集
                logger.info(f"从checkpoint {checkpoint_id} 继续增量采集")
            else:
                # 首次采集历史消息 - 使用传入的limit参数
                logger.info(f"首次采集，获取最近 {limit} 条主消息")
            
            # 🚀 主消息驱动模式：按主消息顺序处理
            logger.info(f"开始主消息驱动采集，min_id={min_id}, 需要{limit}个主消息")
            
            # 步骤1: 获取主消息ID列表
            main_message_ids = await self._get_main_message_ids_v2(
                client, entity, min_id, limit
            )
            
            if not main_message_ids:
                logger.info(f"频道 {channel_name} 没有新的主消息")
                return
            
            logger.info(f"获取到 {len(main_message_ids)} 个主消息，开始逐个处理...")
            
            # 统计信息
            processed_count = 0
            failed_count = 0
            latest_message_id = int(checkpoint_id or 0)
            
            # 步骤2: 逐个处理每个主消息
            for idx, main_msg_info in enumerate(main_message_ids, 1):
                try:
                    main_id = main_msg_info['id']
                    msg_type = main_msg_info['type']
                    
                    logger.info(f"[{idx}/{len(main_message_ids)}] 处理主消息: #{main_id} ({msg_type})")
                    
                    # 获取完整消息数据
                    messages = await self._fetch_complete_message(client, entity, main_msg_info)
                    if not messages:
                        logger.warning(f"主消息 #{main_id} 获取失败，跳过")
                        failed_count += 1
                        continue
                    
                    # 下载所有媒体
                    await self._download_all_media(client, messages)
                    
                    # 处理消息
                    await self._process_main_message(messages, entity)
                    
                    # 更新checkpoint和计数
                    latest_message_id = max(latest_message_id, main_id)
                    redis_channel_store.set_checkpoint(channel_id, latest_message_id)
                    processed_count += 1
                    
                    logger.debug(f"主消息 #{main_id} 处理完成, checkpoint更新到 {latest_message_id}")
                    
                    # 每处理5个主消息报告进度
                    if idx % 5 == 0:
                        logger.info(f"进度: {idx}/{len(main_message_ids)} 主消息 (成功:{processed_count}, 失败:{failed_count})")
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"处理主消息 #{main_msg_info.get('id', 'unknown')} 失败: {e}")
                    continue
            
            # 处理完成统计
            total_processed = len(main_message_ids)
            logger.info(f"主消息处理完成: 总共 {total_processed} 个主消息，成功 {processed_count} 个，失败 {failed_count} 个")
            
            # 如果没有处理任何消息
            if processed_count == 0:
                collection_type = "新频道" if not checkpoint_id else "频道"
                logger.info(f"{collection_type} {channel_name} 没有新主消息需要处理")
                return
            
            # 最终checkpoint已在处理过程中更新
            collection_type = "历史消息" if not checkpoint_id else "增量"
            logger.info(f"✅ 频道 {channel_name} {collection_type}采集完成: 成功处理 {processed_count}/{total_processed} 个主消息")
            
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