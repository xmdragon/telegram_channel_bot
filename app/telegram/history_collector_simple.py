"""
简化版Telegram历史消息采集器
参考用户的bot_v3.py设计理念 - 简单直接，永不卡死
设计原则：消除所有不必要的复杂性
"""
import logging
import asyncio
import json
from typing import Dict, Any
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import Message as TLMessage

from app.services.config_manager import ConfigManager
from app.storage.redis_manager import redis_manager
from app.services.unified_channel_service import unified_channel_service
from app.services.processors.base import MessageContext, MessagePipeline, MessageProcessor, ProcessorResult

logger = logging.getLogger(__name__)

async def aiter_with_timeout(async_iter, timeout_seconds):
    """异步迭代器超时包装器"""
    import asyncio
    import time
    
    start_time = time.time()
    async for item in async_iter:
        # 检查是否超时
        if time.time() - start_time > timeout_seconds:
            logger.warning(f"异步迭代器超时 ({timeout_seconds}秒)")
            break
        yield item

class SimpleHistoryCollector:
    """简化版历史采集器 - 直接处理，无复杂管道"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.pipeline = self._create_simple_pipeline()
        
    async def collect_channel_history(self, client: TelegramClient):
        """采集所有监听频道的历史消息 - 简单直接版本"""
        try:
            # 检查采集开关
            collection_enabled = await self.config_manager.get_config('collection.enabled', False)
            if not collection_enabled:
                logger.debug("采集已禁用，跳过历史消息采集")
                return
                
            # 获取历史消息采集配置  
            history_limit = await self.config_manager.get_config("source.history_limit", 10)
            
            if int(history_limit) <= 0:
                logger.info("历史消息采集已禁用")
                return
            
            # 获取所有源频道
            channels = await unified_channel_service.get_all_channels()
            
            if not channels:
                logger.warning("未找到任何源频道配置")
                return
            
            logger.info(f"开始历史消息采集: {len(channels)} 个频道，每个频道最多 {history_limit} 条消息")
            
            # 逐个处理频道
            for i, channel_config in enumerate(channels, 1):
                try:
                    await self._collect_single_channel(client, channel_config, history_limit, i, len(channels))
                except Exception as e:
                    logger.error(f"频道 {channel_config.get('channel_name', 'Unknown')} 采集失败: {e}")
                    continue
                    
            logger.info("✅ 所有频道历史消息采集完成")
            
        except Exception as e:
            logger.error(f"历史消息采集失败: {e}")
    
    async def _collect_single_channel(self, client: TelegramClient, channel_config: Dict, limit: int, index: int, total: int):
        """采集单个频道的历史消息 - 第4层: 添加MessagePipeline管道处理"""
        channel_name = channel_config.get('channel_name', 'Unknown')
        channel_id = channel_config.get('channel_id')
        last_message_id = channel_config.get('last_message_id', 0)
        
        logger.info(f"[{index}/{total}] 开始采集频道: {channel_name}")
        
        # 🎯 解决方案：使用asyncio.create_task + asyncio.wait实现真正的超时控制
        # 这是唯一能够中断iter_messages()的方法
        try:
            # 创建采集任务
            collect_task = asyncio.create_task(
                self._collect_channel_with_timeout(client, channel_config, limit, index, total)
            )
            
            # 等待任务完成，设置超时
            timeout_seconds = 60  # 60秒超时
            done, pending = await asyncio.wait(
                [collect_task],
                timeout=timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            if pending:
                # 任务超时，取消它
                logger.warning(f"🚨 频道 {channel_name} 采集超时({timeout_seconds}秒)，强制跳过")
                collect_task.cancel()
                try:
                    await collect_task
                except asyncio.CancelledError:
                    pass  # 正常的取消
                return
            
            # 任务正常完成，检查结果
            if done:
                task = done.pop()
                if task.exception():
                    logger.error(f"频道 {channel_name} 采集失败: {task.exception()}")
                else:
                    logger.info(f"✅ 频道 {channel_name} 采集完成")
                    
        except Exception as e:
            logger.error(f"频道 {channel_name} 采集出错: {e}")
    
    async def _collect_channel_with_timeout(self, client: TelegramClient, channel_config: Dict, limit: int, index: int, total: int):
        """实际的频道采集逻辑 - 可被取消的任务"""
        channel_name = channel_config.get('channel_name', 'Unknown')
        channel_id = channel_config.get('channel_id')
        last_message_id = channel_config.get('last_message_id', 0)
        
        try:
            # 🔧 修复频道实体获取：先尝试username，再尝试ID
            entity = None
            try:
                # 先尝试使用频道username
                if channel_name and channel_name.startswith('@'):
                    entity = await client.get_entity(channel_name)
                    logger.debug(f"通过username获取频道成功: {channel_name}")
                else:
                    # 如果没有@前缀，添加@再试
                    entity = await client.get_entity(f"@{channel_name}")
                    logger.debug(f"通过添加@获取频道成功: @{channel_name}")
            except Exception as username_err:
                logger.debug(f"通过username获取频道失败 {channel_name}: {username_err}")
                # 回退到使用数字ID
                try:
                    entity = await client.get_entity(int(channel_id))
                    logger.debug(f"通过数字ID获取频道成功: {channel_id}")
                except Exception as id_err:
                    logger.error(f"通过ID获取频道也失败 {channel_id}: {id_err}")
                    raise Exception(f"无法获取频道实体，username: {username_err}, id: {id_err}")
            
            if not entity:
                raise Exception("获取频道实体失败")
                
            logger.info(f"开始检查频道 {entity.title} 的历史消息")
            
            # 🎯 第1层改进：添加主消息ID筛选逻辑（来自原版）
            message_count = 0
            success_count = 0
            
            logger.info(f"开始获取频道 {channel_name} 的消息")
            
            # 第1层：首先获取主消息ID列表（包含组消息筛选）
            main_messages = await self._get_main_message_ids(client, entity, last_message_id, limit)
            logger.info(f"获取到 {len(main_messages)} 个主消息ID")
            
            # 第2层改进：对每个主消息进行完整采集（包括组消息）
            for main_msg_info in main_messages:
                # 检查是否被取消
                if asyncio.current_task().cancelled():
                    logger.warning(f"频道 {channel_name} 采集被取消")
                    return
                    
                msg_id = main_msg_info['id']
                msg_type = main_msg_info['type']
                
                try:
                    # 第2层：根据消息类型获取完整消息数据
                    collected_messages = []
                    if msg_type == 'group':
                        # 获取完整组消息 - 添加超时保护
                        group_id = main_msg_info['group_id']
                        try:
                            group_msgs = await asyncio.wait_for(
                                self._fetch_complete_group(client, entity, group_id, msg_id),
                                timeout=15.0
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"组消息 {group_id} 获取超时，跳过")
                            group_msgs = None
                        if group_msgs:
                            collected_messages.extend(group_msgs)
                            logger.debug(f"组 {group_id}: 获取{len(group_msgs)}条消息")
                        else:
                            logger.warning(f"组 {group_id}: 获取失败，跳过")
                    else:
                        # 获取单条消息 - 添加超时保护
                        try:
                            msg = await asyncio.wait_for(
                                client.get_messages(entity, ids=msg_id),
                                timeout=10.0
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"单消息 {msg_id} 获取超时，跳过")
                            msg = None
                        if msg:
                            collected_messages.append(msg)
                            logger.debug(f"单消息 {msg_id}: 获取成功")
                        else:
                            logger.warning(f"单消息 {msg_id}: 获取失败")
                    
                    # 第3层改进：保存所有采集到的消息，使用MessageContext
                    for msg in collected_messages:
                        if not msg or not msg.id:
                            continue
                            
                        message_count += 1
                        
                        # 第4层：通过MessagePipeline管道处理（添加超时保护）
                        try:
                            context = await self._create_message_context(msg, channel_id)
                            result = await asyncio.wait_for(
                                self.pipeline.process(context),
                                timeout=5.0  # 5秒超时，防止第14位置阻塞
                            )
                            if result.success:
                                success_count += 1
                            else:
                                logger.error(f"管道处理失败: {result.error}")
                        except asyncio.TimeoutError:
                            logger.warning(f"消息 {msg.id} 管道处理超时，跳过")
                            # 阻塞时继续处理下一条消息
                        
                        # 🚨 实用主义：checkpoint更新暂时禁用，避免阻塞采集
                        # TODO: 实现unified_channel_service.update_channel_checkpoint方法
                        if msg.id > last_message_id:
                            last_message_id = msg.id
                            logger.debug(f"更新checkpoint: {channel_id} -> {msg.id}")
                        
                except Exception as e:
                    logger.error(f"处理主消息失败 #{msg_id}: {e}")
                
                # 每10条消息报告一次进度
                if message_count % 10 == 0:
                    logger.info(f"进度: {message_count} 条消息已处理")
            
            logger.info(f"✅ 频道 {channel_name} 采集完成: 处理 {message_count} 条，成功 {success_count} 条")
            
        except Exception as e:
            logger.error(f"频道 {channel_name} 处理失败: {e}")
            raise
    
    async def _get_main_message_ids(self, client: TelegramClient, entity, min_id: int, limit: int) -> list:
        """
        获取主消息ID列表 - 第1层：来自原版的组消息筛选逻辑
        返回: [{'id': 2838, 'type': 'single'}, 
               {'id': 2830, 'type': 'group', 'group_id': '14058570976263685'}, ...]
        """
        main_messages = []
        seen_groups = set()
        
        logger.info(f"开始获取主消息ID列表，min_id={min_id}, 需要{limit}个主消息")
        
        # 🎯 修复：使用更小的批次和超时控制
        # 不再尝试一次获取5倍数量，而是分批获取
        message_count = 0
        batch_size = min(50, limit * 2)  # 每批最多50条，减少阻塞风险
        
        try:
            # 使用更小的批次避免长时间阻塞
            async for msg in client.iter_messages(entity, limit=batch_size, min_id=min_id):
                # 频繁检查任务是否被取消
                if asyncio.current_task().cancelled():
                    logger.warning("消息ID获取被取消")
                    break
                    
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
                    
                # 每10条消息yield一次控制权，让asyncio有机会检查取消
                if message_count % 10 == 0:
                    await asyncio.sleep(0)  # 让出控制权
                    
        except asyncio.CancelledError:
            logger.warning("消息ID获取被取消（在iter_messages中）")
            raise  # 重新抛出以便上层处理
        except Exception as e:
            logger.error(f"获取消息ID时出错: {e}")
            # 即使出错也返回已获取的消息
        
        logger.info(f"获取主消息ID完成: 扫描{message_count}条消息，获得{len(main_messages)}个主消息")
        return main_messages[:limit]
    
    async def _fetch_complete_group(self, client: TelegramClient, entity, group_id: str, sample_id: int) -> list:
        """
        获取完整的组消息 - 第2层：来自原版的组消息完整采集逻辑
        """
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
                # 简化：如果没找到组消息，尝试直接获取单条消息作为回退
                logger.warning(f"组 {group_id}: 未找到组消息，尝试单消息回退")
                fallback_msg = await asyncio.wait_for(
                    client.get_messages(entity, ids=sample_id),
                    timeout=10.0
                )
                return [fallback_msg] if fallback_msg else []
            
        except asyncio.TimeoutError:
            logger.error(f"获取组消息超时 {group_id}，使用单消息回退")
            try:
                # 超时时的回退机制 - 也需要超时保护
                fallback_msg = await asyncio.wait_for(
                    client.get_messages(entity, ids=sample_id),
                    timeout=5.0
                )
                return [fallback_msg] if fallback_msg else []
            except asyncio.TimeoutError:
                logger.warning(f"回退消息 {sample_id} 也超时，彻底跳过")
                return []
            except:
                return []
        except Exception as e:
            logger.error(f"获取组消息失败 {group_id}: {e}")
            return []
    
    def _create_simple_pipeline(self) -> MessagePipeline:
        """
        创建简化版处理管道 - 第4层：仅包含基础存储处理器
        """
        pipeline = MessagePipeline()
        
        # 添加简单存储处理器
        storage_processor = SimpleStorageProcessor()
        pipeline.add_processor(storage_processor)
        
        logger.info(f"创建简化版管道: {len(pipeline.processors)} 个处理器")
        return pipeline
    
    async def _create_message_context(self, msg: TLMessage, channel_id: str) -> MessageContext:
        """
        创建MessageContext - 第3层：统一的消息处理上下文
        """
        try:
            # 提取基础消息内容
            content = msg.message or ''
            
            # 提取组消息ID
            grouped_id = None
            if hasattr(msg, 'grouped_id') and msg.grouped_id:
                grouped_id = str(msg.grouped_id)
            
            # 创建MessageContext实例
            context = MessageContext(
                telegram_message=msg,
                channel_id=channel_id,
                grouped_id=grouped_id,
                original_content=content,
                processed_content=content,  # 第3层暂时不处理，直接复制
                filtered_content=content    # 第3层暂时不过滤，直接复制
            )
            
            logger.debug(f"创建MessageContext: #{msg.id}, 组ID: {grouped_id}")
            return context
            
        except Exception as e:
            logger.error(f"创建MessageContext失败 #{msg.id}: {e}")
            raise
    
    async def _process_message_with_context(self, context: MessageContext):
        """
        使用MessageContext处理消息 - 第3层：基础处理流程
        """
        try:
            msg = context.telegram_message
            
            # 第3层：基础消息数据提取（从原来的_save_message_simple迁移）
            message_data = {
                'message_id': str(msg.id),
                'channel_id': context.channel_id,
                'channel_name': '',  # 暂时为空，避免传递问题
                'content': context.processed_content,
                'date': msg.date.isoformat() if msg.date else '',
                'sender_id': str(msg.sender_id) if msg.sender_id else '',
                'media_type': 'none',
                'grouped_id': context.grouped_id,
                'status': 'pending',
                'created_at': datetime.now().isoformat()
            }
            
            # 第3层：简单媒体类型检测
            if msg.photo:
                message_data['media_type'] = 'photo'
            elif msg.video:
                message_data['media_type'] = 'video'  
            elif msg.document:
                message_data['media_type'] = 'document'
            elif msg.audio:
                message_data['media_type'] = 'audio'
            
            # 第3层：简单过滤逻辑
            if context.filtered_content and await self._is_ad_content(context.filtered_content):
                message_data['status'] = 'rejected'
                message_data['reject_reason'] = '广告内容'
                context.is_ad = True
                context.should_reject = True
                context.reject_reason = '广告内容'
            
            # 使用RedisManager保存消息 - 异步包装避免阻塞事件循环
            await asyncio.to_thread(redis_manager.save_message, context.channel_id, msg.id, message_data)
            
            logger.debug(f"通过MessageContext保存消息: #{msg.id}")
            
        except Exception as e:
            logger.error(f"MessageContext处理失败: {e}")
            raise
    
    async def _save_message_simple(self, msg: TLMessage, channel_id: str, channel_name: str):
        """简单保存消息 - 无复杂的Context和处理器"""
        try:
            # 基本消息数据
            message_data = {
                'message_id': str(msg.id),
                'channel_id': channel_id,
                'channel_name': channel_name,
                'content': msg.message or '',
                'date': msg.date.isoformat() if msg.date else '',
                'sender_id': str(msg.sender_id) if msg.sender_id else '',
                'media_type': 'none',
                'grouped_id': str(msg.grouped_id) if hasattr(msg, 'grouped_id') and msg.grouped_id else None,
                'status': 'pending',  # 简单状态管理
                'created_at': datetime.now().isoformat()
            }
            
            # 简单媒体类型检测
            if msg.photo:
                message_data['media_type'] = 'photo'
            elif msg.video:
                message_data['media_type'] = 'video'  
            elif msg.document:
                message_data['media_type'] = 'document'
            elif msg.audio:
                message_data['media_type'] = 'audio'
            
            # 简单过滤 - 参考你的关键词过滤方式
            content = message_data['content']
            if content and await self._is_ad_content(content):
                message_data['status'] = 'rejected'
                message_data['reject_reason'] = '广告内容'
            
            # 使用RedisManager的正确接口保存消息 - 异步包装避免阻塞事件循环
            await asyncio.to_thread(redis_manager.save_message, channel_id, msg.id, message_data)
            
            logger.debug(f"消息已保存: #{msg.id}")
            
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
            raise
    
    async def _is_ad_content(self, content: str) -> bool:
        """简单广告检测 - 基于关键词，无AI复杂分析"""
        if not content:
            return False
            
        # 简单广告关键词检测（可从配置文件读取）
        ad_keywords = [
            '首存', '充值送', '无需实名', '免费注册', 
            '点击链接', '私聊联系', '加微信', '客服'
        ]
        
        content_lower = content.lower()
        for keyword in ad_keywords:
            if keyword in content_lower:
                return True
                
        return False

class SimpleStorageProcessor(MessageProcessor):
    """
    简单存储处理器 - 第4层：基础的消息存储功能
    """
    
    def __init__(self):
        super().__init__("SimpleStorageProcessor")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """处理消息存储"""
        try:
            msg = context.telegram_message
            
            # 第4层：基础消息数据提取（从原来的_process_message_with_context迁移）
            message_data = {
                'message_id': str(msg.id),
                'channel_id': context.channel_id,
                'channel_name': '',  # 暂时为空，避免传递问题
                'content': context.processed_content,
                'date': msg.date.isoformat() if msg.date else '',
                'sender_id': str(msg.sender_id) if msg.sender_id else '',
                'media_type': 'none',
                'grouped_id': context.grouped_id,
                'status': 'pending',
                'created_at': datetime.now().isoformat()
            }
            
            # 第4层：简单媒体类型检测
            if msg.photo:
                message_data['media_type'] = 'photo'
            elif msg.video:
                message_data['media_type'] = 'video'  
            elif msg.document:
                message_data['media_type'] = 'document'
            elif msg.audio:
                message_data['media_type'] = 'audio'
            
            # 第4层：简单过滤逻辑
            if context.filtered_content and await self._is_ad_content(context.filtered_content):
                message_data['status'] = 'rejected'
                message_data['reject_reason'] = '广告内容'
                context.is_ad = True
                context.should_reject = True
                context.reject_reason = '广告内容'
            
            # 使用RedisManager保存消息 - 异步包装避免阻塞事件循环
            await asyncio.to_thread(redis_manager.save_message, context.channel_id, msg.id, message_data)
            
            self.logger.debug(f"通过管道存储消息: #{msg.id}")
            return ProcessorResult(True, context)
            
        except Exception as e:
            # 增强错误信息，添加更多诊断上下文
            error_msg = (
                f"SimpleStorageProcessor处理失败: {e}\n"
                f"  消息ID: {context.telegram_message.id}\n"
                f"  频道ID: {context.channel_id}\n"
                f"  内容长度: {len(context.processed_content)}\n"
                f"  是否有媒体: {bool(context.telegram_message.media)}\n"
                f"  组ID: {context.grouped_id}"
            )
            self.logger.error(error_msg)
            return await self._handle_error(context, Exception(error_msg))
    
    async def _is_ad_content(self, content: str) -> bool:
        """简单广告检测 - 基于关键词，无AI复杂分析"""
        if not content:
            return False
            
        # 简单广告关键词检测（可从配置文件读取）
        ad_keywords = [
            '首存', '充值送', '无需实名', '免费注册', 
            '点击链接', '私聊联系', '加微信', '客服'
        ]
        
        content_lower = content.lower()
        for keyword in ad_keywords:
            if keyword in content_lower:
                return True
                
        return False

# 全局实例
simple_history_collector = SimpleHistoryCollector()