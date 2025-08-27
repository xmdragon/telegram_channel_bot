"""
消息处理核心逻辑
负责消息的处理、过滤、保存和转发
"""
import logging
import os
from typing import Dict, Optional, Any
from datetime import datetime
from telethon.tl.types import Message as TLMessage

from app.utils.timezone import format_for_api
from app.storage.redis_store import get_redis_message_store
from app.services.message_processor import MessageProcessor
from app.services.unified_filter_engine import filter_engine_compat
from app.services.config_manager import config_manager

logger = logging.getLogger(__name__)

class MessageHandler:
    """消息处理器"""
    
    def __init__(self):
        self.message_processor = MessageProcessor()
        self.content_filter = filter_engine_compat
        
    async def handle_message_from_event(self, message: TLMessage, chat, chat_info: dict, message_type: str):
        """处理来自事件处理器的消息"""
        try:
            if message_type == "source_channel":
                logger.info(f"消息来自监听的源频道: {chat_info['title']}")
                await self.process_source_message(message, chat)
            elif message_type == "review_group":
                logger.info(f"消息来自审核群: {chat_info['title']}")
                await self.process_review_message(message, chat)
            else:
                logger.debug(f"消息来自未监听的频道/群组: {chat_info['title']} (ID: {chat_info['formatted_id']})")
                
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    async def process_message_unified(self, message: TLMessage, channel_id: str, chat=None):
        """统一的消息处理入口（符合Linus的好品味原则）
        
        消除重复代码路径，所有消息处理都使用相同的管道和性能监控
        
        Args:
            message: Telegram消息对象
            channel_id: 频道ID（格式化后）
            chat: 聊天对象（用于获取频道信息）
        """
        # 导入性能监控
        try:
            from app.services.performance_monitor import performance_monitor
        except ImportError:
            from contextlib import nullcontext
            performance_monitor = nullcontext
        
        # 获取频道信息
        channel_name = getattr(chat, 'title', 'Unknown') if chat else 'Unknown'
        
        # 获取消息基本信息
        content = getattr(message, 'text', '') or getattr(message, 'caption', '')
        media_type = 'text'
        if hasattr(message, 'media') and message.media:
            media_type = type(message.media).__name__.replace('MessageMedia', '').lower()
        
        operation_name = "process_source_message"
        
        # 统一的性能监控（所有消息都有）
        async with performance_monitor(
            operation_name,
            channel_id=channel_id,
            channel_name=channel_name,
            message_id=message.id,
            message_type=media_type,
            content_length=len(content) if content else 0
        ) as perf_ctx:
            try:
                # 阶段1: 管道初始化
                perf_ctx.start_stage("pipeline_setup")
                
                # 使用统一的处理器管道
                from app.services.processors import MessagePipeline, MessageReceiver, MediaDownloader, MessageFilterProcessor, MessageStorageProcessor
                from app.services.processors.base import MessageContext
                
                # 创建处理上下文
                context = MessageContext(
                    telegram_message=message,
                    channel_id=channel_id
                )
                
                # 创建处理管道
                pipeline = MessagePipeline([
                    MessageReceiver(),
                    MediaDownloader(),
                    MessageFilterProcessor(), 
                    MessageStorageProcessor()
                ])
                
                perf_ctx.end_stage("pipeline_setup")
                
                # 阶段2: 执行处理管道
                perf_ctx.start_stage("pipeline_execution")
                result = await pipeline.process(context)
                perf_ctx.end_stage("pipeline_execution", 
                                 success=result.success,
                                 processors_count=len(pipeline.processors))
                
                db_message = result.context.save_data if result.success else None
                
                # 记录处理结果元数据
                perf_ctx.set_metadata(
                    processing_success=result.success,
                    message_saved=db_message is not None,
                    final_content_length=len(result.context.filtered_content or '') if hasattr(result.context, 'filtered_content') else 0
                )
                
                # 统一的结果处理
                return await self._handle_processing_result(
                    result, db_message, message
                )
                
            except Exception as e:
                perf_ctx.set_metadata(error=str(e), error_type=type(e).__name__)
                logger.error(f"处理消息时出错: {e}")
                return "error"
    
    async def _handle_processing_result(self, result, db_message, message):
        """统一的处理结果处理"""
        message_id = message.id
        
        if db_message:
            # 处理成功并保存
            status = db_message.get('status', 'unknown')
            content_len = len(db_message.get('content', ''))
            media_type = db_message.get('media_type', 'none')
            logger.info(f"✅ 消息 #{message_id} 处理成功 - 状态:{status}, 内容:{content_len}字符, 媒体:{media_type}")
            return "saved"
        else:
            # 分析未保存的原因
            return await self._analyze_no_save_reason(result, message_id)
    
    async def _analyze_no_save_reason(self, result, message_id):
        """分析消息未保存的原因"""
        if not result.success:
            reason = getattr(result, 'error_message', '未知错误')
            logger.info(f"❌ 消息 #{message_id} 处理失败 - 原因: {reason}")
            return "failed"
        
        # 成功但未保存的各种情况
        if hasattr(result.context, 'filter_result') and result.context.filter_result:
            filter_reason = result.context.filter_result.get('reason', '被过滤')
            logger.info(f"🚫 消息 #{message_id} 被过滤 - 原因: {filter_reason}")
            return "filtered"
        elif hasattr(result.context, 'is_duplicate') and result.context.is_duplicate:
            logger.info(f"🔄 消息 #{message_id} 检测为重复消息")
            return "duplicate"
        elif hasattr(result.context, 'pending_group'):
            logger.info(f"⏳ 消息 #{message_id} 等待媒体组合并")
            return "pending_group"
        elif result.context.save_data is None and hasattr(result.context, 'telegram_message'):
            # 检查组消息
            telegram_msg = result.context.telegram_message
            if hasattr(telegram_msg, 'grouped_id') and telegram_msg.grouped_id:
                logger.info(f"⏳ 消息 #{message_id} 等待媒体组合并 (grouped_id: {telegram_msg.grouped_id})")
                return "pending_group"
            else:
                logger.info(f"❓ 消息 #{message_id} 处理完成但未保存（原因未知）")
                return "unknown"
        else:
            logger.info(f"❓ 消息 #{message_id} 处理完成但未保存（原因未知）")
            return "unknown"

    async def process_source_message(self, message: TLMessage, chat):
        """处理源频道消息 - 改为快速入队模式"""
        from app.services.message_queue import get_message_queue, CollectedMessage
        
        # 获取格式化的频道ID
        raw_chat_id = chat.id
        if raw_chat_id > 0:
            channel_id = f"-100{raw_chat_id}"
        else:
            channel_id = str(raw_chat_id)
        
        return await self.process_source_message_async_queue(message, channel_id, chat)
    
    async def process_source_message_async_queue(self, message: TLMessage, channel_id: str, chat):
        """Linus式异步队列处理 - 采集器只管采集，不等处理结果"""
        try:
            # 1. 快速提取基础信息（< 1ms）
            collected_msg = await self._extract_message_quickly(message, channel_id, chat)
            
            # 2. 立即入队（不等待处理）
            queue = get_message_queue()
            success = await queue.enqueue_message(collected_msg)
            
            if success:
                logger.debug(f"⚡ 消息快速入队: {collected_msg.message_key}")
                return "queued"  # 立即返回
            else:
                logger.error(f"消息入队失败: {collected_msg.message_key}")
                # 失败时回退到同步处理
                return await self.process_message_unified(message, channel_id, chat)
                
        except Exception as e:
            logger.error(f"异步队列处理失败: {e}, 回退到同步模式")
            # 任何错误都回退到原有的同步处理
            return await self.process_message_unified(message, channel_id, chat)
    
    async def _extract_message_quickly(self, message: TLMessage, channel_id: str, chat) -> 'CollectedMessage':
        """快速提取消息基础信息 - Linus式最小必要信息"""
        from app.services.message_queue import CollectedMessage
        from app.utils.timezone import get_current_time
        
        # 基础文本内容
        content = ""
        if hasattr(message, 'message') and message.message:
            content = message.message.strip()
        elif hasattr(message, 'caption') and message.caption:
            content = message.caption.strip()
        elif hasattr(message, 'text') and message.text:
            content = message.text.strip()
        
        # 媒体信息（暂不下载，处理时再下载）
        media_type = None
        media_url = None
        if hasattr(message, 'media') and message.media:
            media_type = type(message.media).__name__.replace('MessageMedia', '').lower()
        
        # 组消息ID
        grouped_id = None
        if hasattr(message, 'grouped_id') and message.grouped_id:
            grouped_id = str(message.grouped_id)
        
        return CollectedMessage(
            channel_id=channel_id,
            message_id=message.id,
            grouped_id=grouped_id,
            content=content,
            media_type=media_type,
            media_url=media_url,
            timestamp=message.date or get_current_time(),
            raw_data={
                'chat_title': getattr(chat, 'title', 'Unknown'),
                'sender_id': getattr(message.sender, 'id', None) if hasattr(message, 'sender') and message.sender else None,
                'reply_to_msg_id': message.reply_to_msg_id if hasattr(message, 'reply_to_msg_id') else None,
                'forward_info': str(message.forward) if hasattr(message, 'forward') and message.forward else None,
                'has_media': media_type is not None
            }
        )
    
    async def process_source_message_sync(self, message: TLMessage, chat):
        """同步处理模式 - 保留原有功能作为回退方案"""
        # 获取格式化的频道ID
        raw_chat_id = chat.id
        if raw_chat_id > 0:
            channel_id = f"-100{raw_chat_id}"
        else:
            channel_id = str(raw_chat_id)
        
        # 调用统一的处理方法
        return await self.process_message_unified(
            message=message,
            channel_id=channel_id,
            chat=chat
        )
    
    async def process_review_message(self, message: TLMessage, chat):
        """处理审核群中的消息"""
        try:
            text = message.text or ""
            
            # 处理命令
            if text.startswith('/approve_'):
                message_id = int(text.split('_')[1])
                await self.approve_message(message_id, message.sender.username)
            elif text.startswith('/reject_'):
                message_id = int(text.split('_')[1])
                await self.reject_message(message_id, message.sender.username)
            elif text.startswith('/edit_'):
                message_id = int(text.split('_')[1])
                await self.edit_message(message_id)
            elif text.startswith('/detail_'):
                message_id = int(text.split('_')[1])
                await self.show_message_detail(message_id)
                
        except Exception as e:
            logger.error(f"处理审核群消息时出错: {e}")
    
    
    async def save_processed_message(self, message_data: dict, channel_id: str, is_history: bool = False, original_media_info: dict = None):
        """保存处理后的消息"""
        try:
            # 检查是否已经有过滤后的内容
            if 'filtered_content' in message_data:
                filtered_content = message_data['filtered_content']
                is_ad = message_data.get('is_ad', False)
                logger.info(f"📝 使用预过滤内容，长度: {len(filtered_content)} 字符")
            else:
                # 未过滤，进行过滤
                logger.info(f"📝 开始内容过滤，原始内容长度: {len(message_data.get('content', ''))} 字符")
                if message_data.get('content'):
                    logger.info(f"📝 内容预览: {message_data['content'][:100]}...")
                
                # 内容过滤
                is_ad, filtered_content, filter_reason = self.content_filter.filter_message_sync(message_data['content'], channel_id=channel_id)
                
                # 对于组合消息，如果文本被判定为广告，保留原始内容供审核
                if message_data.get('is_combined') and is_ad and not filtered_content:
                    logger.info(f"📝 组合消息被判定为广告，保留原始文本供审核")
                    filtered_content = message_data['content']
                
                # 添加过滤后的日志
                if message_data.get('content') != filtered_content:
                    logger.info(f"📝 内容过滤完成，长度变化: {len(message_data.get('content', ''))} -> {len(filtered_content)} 字符")
                else:
                    logger.info(f"📝 内容过滤完成，长度无变化: {len(filtered_content)} 字符")
            
            # 计算媒体哈希
            media_hash, combined_media_hash, visual_hash = await self._calculate_media_hashes(message_data, original_media_info)
            
            # 执行重复检测
            is_duplicate = await self._check_duplicate_message(
                channel_id, media_hash, combined_media_hash, 
                message_data.get('content'), message_data.get('date'), visual_hash
            )
            
            if is_duplicate:
                logger.info(f"{'历史' if is_history else '实时'}消息：发现重复消息，跳过处理")
                await self._cleanup_message_media(message_data)
                return
            
            # 使用消息处理器进行处理
            process_message_data = {
                'source_channel': channel_id,
                'message_id': message_data['message_id'],
                'content': message_data['content'],
                'media_type': message_data.get('media_type'),
                'media_url': message_data.get('media_url'),
                'grouped_id': str(message_data.get('grouped_id')) if message_data.get('grouped_id') else None,
                'is_combined': message_data.get('is_combined', False),
                'combined_messages': message_data.get('combined_messages'),
                'media_hash': media_hash,
                'combined_media_hash': combined_media_hash,
                'visual_hash': visual_hash,
                'media_group': message_data.get('media_group'),
                'is_ad': is_ad,
                'filtered_content': filtered_content,
                'status': 'pending',
                'created_at': message_data.get('date').replace(tzinfo=None) if message_data.get('date') and hasattr(message_data.get('date'), 'tzinfo') else (message_data.get('date') or datetime.now())
            }
            
            db_message = await self.message_processor.process_new_message(process_message_data)
            
            if not db_message:
                logger.info(f"{'历史' if is_history else '实时'}消息 {message_data['message_id']} 被重复检测拒绝")
                return
                
            # 转发到审核群
            await self.forward_to_review(db_message)
                
            # 广播新消息到WebSocket客户端
            await self._broadcast_new_message(db_message)
                    
        except Exception as e:
            logger.error(f"保存处理后的消息失败: {e}")
            await self._cleanup_message_media(message_data)
    
    async def _calculate_media_hashes(self, message_data: dict, original_media_info: dict = None):
        """计算媒体哈希"""
        from app.services.media_handler import media_handler
        
        media_hash = None
        combined_media_hash = None
        visual_hash = None
        
        logger.info(f"📊 开始计算媒体哈希: is_combined={message_data.get('is_combined')}")
        
        # 单个媒体哈希
        if message_data.get('media_type') and message_data.get('media_url'):
            media_hash = await media_handler._calculate_file_hash(message_data['media_url'])
            logger.info(f"📊 单个媒体哈希计算完成: {media_hash}")
            
            # 处理视觉哈希
            if original_media_info and original_media_info.get('visual_hashes'):
                import json
                visual_hash = json.dumps(original_media_info['visual_hashes'])
                logger.info(f"📊 使用已计算的视觉哈希")
        
        # 组合媒体哈希
        if message_data.get('is_combined'):
            combined_media_list = []
            combined_visual_hashes = []
            
            if message_data.get('media_group'):
                logger.info(f"📊 处理媒体组: {len(message_data['media_group'])} 个文件")
                for i, media_item in enumerate(message_data['media_group']):
                    if media_item.get('file_path'):
                        file_hash = await media_handler._calculate_file_hash(media_item['file_path'])
                        logger.info(f"📊 媒体{i+1}哈希: {file_hash}")
                        if file_hash:
                            combined_media_list.append({
                                'hash': file_hash,
                                'message_id': media_item.get('message_id', 0)
                            })
                        
                        if media_item.get('visual_hashes'):
                            combined_visual_hashes.append(media_item['visual_hashes'])
            
            if combined_media_list:
                combined_media_hash = await media_handler.process_media_group(combined_media_list)
                logger.info(f"📊 组合媒体哈希计算完成: {combined_media_hash}")
            
            if combined_visual_hashes:
                import json
                visual_hash = json.dumps(combined_visual_hashes)
                logger.info(f"📊 组合媒体包含 {len(combined_visual_hashes)} 个视觉哈希")
        
        return media_hash, combined_media_hash, visual_hash
    
    async def _check_duplicate_message(self, channel_id: str, media_hash: str, combined_media_hash: str, 
                                     content: str, message_time, visual_hash: str) -> bool:
        """检查消息是否重复"""
        try:
            from app.services.duplicate_detector import DuplicateDetector
            duplicate_detector = DuplicateDetector()
            
            visual_hashes_dict = None
            if visual_hash:
                try:
                    import json
                    if isinstance(visual_hash, str):
                        visual_hashes_dict = json.loads(visual_hash)
                    else:
                        visual_hashes_dict = visual_hash
                    if isinstance(visual_hashes_dict, list) and visual_hashes_dict:
                        visual_hashes_dict = visual_hashes_dict[0]
                except:
                    pass
            
            is_duplicate, original_msg_id, duplicate_type = await duplicate_detector.is_duplicate_message(
                source_channel=channel_id,
                media_hash=media_hash,
                combined_media_hash=combined_media_hash,
                content=content,
                message_time=message_time or datetime.now(),
                visual_hashes=visual_hashes_dict
            )
            
            return is_duplicate
        except Exception as e:
            logger.error(f"重复检测失败: {e}")
            return False
    
    async def _cleanup_message_media(self, message_data: dict):
        """清理消息媒体文件"""
        try:
            from app.services.media_handler import media_handler
            
            if message_data.get('media_url') and os.path.exists(message_data['media_url']):
                await media_handler.cleanup_file(message_data['media_url'])
            
            if message_data.get('media_group'):
                for media_item in message_data['media_group']:
                    if media_item.get('file_path') and os.path.exists(media_item['file_path']):
                        await media_handler.cleanup_file(media_item['file_path'])
        except Exception as e:
            logger.error(f"清理消息媒体文件失败: {e}")
    
    async def forward_to_review(self, db_message):
        """转发消息到审核群"""
        try:
            from app.telegram.bot_manager import bot_manager
            from app.telegram.message_forwarder import message_forwarder
            
            client = bot_manager.get_client()
            if client:
                await message_forwarder.forward_to_review(client, db_message)
            else:
                logger.error("客户端未连接，无法转发消息")
        except Exception as e:
            logger.error(f"转发消息到审核群失败: {e}")
    
    async def _broadcast_new_message(self, db_message):
        """广播新消息到WebSocket客户端"""
        try:
            from app.api.websocket import websocket_manager
            
            # 准备消息数据
            message_data = {
                "id": db_message.id,
                "message_id": db_message.message_id,
                "source_channel": db_message.source_channel,
                "content": db_message.content,
                "filtered_content": db_message.filtered_content,
                "media_type": db_message.media_type,
                "media_url": db_message.media_url,
                "is_ad": db_message.is_ad,
                "status": db_message.status,
                "created_at": format_for_api(db_message.created_at),
                "is_combined": db_message.is_combined,
                "media_group_display": self._prepare_media_group_display(db_message),
                "media_group": db_message.media_group if db_message.is_combined else None,
                "combined_messages": db_message.combined_messages if db_message.is_combined else None
            }
            
            # 广播到所有WebSocket客户端
            await websocket_manager.broadcast_new_message(message_data)
            logger.info(f"✅ 成功广播新消息 ID:{db_message.id} 到 {len(websocket_manager.active_connections)} 个WebSocket连接")
            
        except ImportError as e:
            logger.error(f"导入WebSocket管理器失败: {e}")
        except Exception as e:
            logger.error(f"广播新消息到WebSocket时出错: {e}")
    
    def _prepare_media_group_display(self, db_message):
        """准备媒体组显示数据"""
        try:
            if not db_message.is_combined or not db_message.media_group:
                return None
                
            media_display = []
            for media_item in db_message.media_group:
                # 转换本地文件路径为web访问路径
                file_path = media_item.get('file_path', '')
                from app.core.path_config import PathConfig
                temp_media_local = f"./{PathConfig.TEMP_MEDIA_DIR.name}/"
                temp_media_web = f"/{PathConfig.TEMP_MEDIA_DIR.name}/"
                if file_path.startswith(temp_media_local):
                    web_path = file_path.replace(temp_media_local, temp_media_web)
                else:
                    web_path = file_path
                    
                media_display.append({
                    'media_type': media_item.get('media_type'),
                    'url': web_path,
                    'file_size': media_item.get('file_size'),
                    'mime_type': media_item.get('mime_type')
                })
            
            return media_display
            
        except Exception as e:
            logger.error(f"准备媒体组显示数据时出错: {e}")
            return None
    
    # 兼容接口
    async def approve_message(self, message_id: int, reviewer: str):
        """批准消息 - 兼容接口"""
        logger.warning(f"使用了旧的approve_message接口，消息ID: {message_id}")
        logger.info("建议使用新的统一消息处理器进行消息审核")
    
    async def reject_message(self, message_id: int, reviewer: str):
        """拒绝消息 - 兼容接口"""
        logger.warning(f"使用了旧的reject_message接口，消息ID: {message_id}")
        logger.info("建议使用新的统一消息处理器进行消息审核")
    
    async def edit_message(self, message_id: int):
        """编辑消息（预留功能）"""
        pass
    
    async def show_message_detail(self, message_id: int):
        """显示消息详情（预留功能）"""
        pass

# 全局实例
message_handler = MessageHandler()