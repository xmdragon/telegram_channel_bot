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
    
    async def process_source_message(self, message: TLMessage, chat):
        """处理源频道消息 - 使用统一处理器"""
        try:
            # 获取格式化的频道ID
            raw_chat_id = chat.id
            if raw_chat_id > 0:
                channel_id = f"-100{raw_chat_id}"
            else:
                channel_id = str(raw_chat_id)
            
            # 使用新的处理器管道
            from app.services.processors import MessagePipeline, MessageReceiver, MediaDownloader, MessageFilterProcessor, MessageStorageProcessor
            from app.services.processors.base import MessageContext
            
            # 创建处理上下文
            context = MessageContext(
                telegram_message=message,
                channel_id=channel_id,
                is_history=False
            )
            
            # 创建处理管道
            pipeline = MessagePipeline([
                MessageReceiver(),
                MediaDownloader(),
                MessageFilterProcessor(), 
                MessageStorageProcessor()
            ])
            
            # 执行处理
            result = await pipeline.process(context)
            db_message = result.context.save_data if result.success else None
            
            if not db_message:
                logger.debug(f"消息 {message.id} 处理完成（被过滤或等待组合）")
                
        except Exception as e:
            logger.error(f"处理源频道消息时出错: {e}")
    
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
    
    async def process_and_save_message(self, message, channel_id: str, is_history: bool = False):
        """处理并保存消息（用于历史消息采集）"""
        try:
            # 使用新的处理器管道
            from app.services.processors import MessagePipeline, MessageReceiver, MediaDownloader, MessageFilterProcessor, MessageStorageProcessor
            from app.services.processors.base import MessageContext
            
            # 创建处理上下文
            context = MessageContext(
                telegram_message=message,
                channel_id=channel_id,
                is_history=True
            )
            
            # 创建处理管道
            pipeline = MessagePipeline([
                MessageReceiver(),
                MediaDownloader(),
                MessageFilterProcessor(), 
                MessageStorageProcessor()
            ])
            
            # 执行处理
            result = await pipeline.process(context)
            db_message = result.context.save_data if result.success else None
            
            if not db_message:
                logger.debug(f"历史消息 {message.id} 处理完成（被过滤或等待组合）")
                
        except Exception as e:
            logger.error(f"处理历史消息失败: {e}")
    
    async def common_message_processing(self, message: TLMessage, channel_id: str, is_history: bool = False):
        """
        通用消息处理逻辑
        
        Args:
            message: Telegram消息对象
            channel_id: 频道ID（已格式化）
            is_history: 是否为历史消息
            
        Returns:
            处理后的消息数据字典，如果消息被过滤则返回None
        """
        try:
            # 提取消息内容（包括带caption的媒体消息）
            content = message.text or message.raw_text or message.message or ""
            
            # 对于媒体消息，检查是否有caption
            if not content and message.media:
                if hasattr(message, 'caption'):
                    content = message.caption or ""
                elif hasattr(message, 'raw_text'):
                    content = message.raw_text or ""
            
            # 对于组合消息，某些情况下文本可能在message属性中
            if not content:
                if hasattr(message, 'message') and message.message:
                    content = message.message
                    logger.debug(f"📝 从message属性提取到内容")
            
            # 如果组合消息仍无文本，可能是纯图片组
            if not content and hasattr(message, 'grouped_id') and message.grouped_id:
                logger.debug(f"📝 组合消息 {message.grouped_id} 中的消息 {message.id} 无文本内容")
                    
            # 记录内容提取结果
            if content:
                logger.info(f"📝 提取到消息内容: {content[:100]}...")
            else:
                logger.debug(f"📝 消息无文本内容（纯媒体）")
            
            media_type = None
            media_url = None
            media_info = None
            
            # 处理媒体消息 - 使用媒体处理器
            if message.media:
                from app.telegram.media_processor import media_processor
                media_info = await media_processor.process_media(message)
                
                if media_info:
                    media_type = media_info['media_type']
                    media_url = media_info['file_path']
                    logger.info(f"✅ 媒体处理成功: {media_url}")
                elif media_info is False:  # 明确被拒绝的文件
                    logger.warning(f"🚫 媒体被拒绝，自动过滤")
                    return None
            
            # 内容过滤（包含智能去尾部）
            logger.info(f"📝 开始内容过滤，原始内容长度: {len(content)} 字符")
            is_ad, filtered_content, filter_reason = self.content_filter.filter_message_sync(content, channel_id=channel_id)
            
            # 记录过滤结果和原因
            if filter_reason == "tail_only":
                logger.info(f"📝 内容过滤完成：文本完全是尾部推广，已过滤")
            elif filter_reason == "ad_filtered":
                logger.info(f"📝 内容过滤完成：检测到广告内容")
            elif filter_reason == "normal":
                logger.info(f"📝 内容过滤完成，过滤后长度: {len(filtered_content)} 字符，减少: {len(content) - len(filtered_content)} 字符")
            else:
                logger.info(f"📝 内容过滤完成，长度无变化: {len(filtered_content)} 字符")
            
            # 检测高风险广告内容
            if await self._is_high_risk_content(content):
                logger.warning(f"🚫 拒绝高风险广告消息: {content[:50]}...")
                if media_info and media_info.get('file_path'):
                    await self._cleanup_media_file(media_info['file_path'])
                return None
            
            # 检查图片是否为已知广告
            if media_info and media_info.get('visual_hashes') and media_type and media_type.startswith('image'):
                if await self._is_known_ad_image(media_info['visual_hashes']):
                    logger.warning(f"🚫 检测到广告图片，自动拒绝")
                    if media_info.get('file_path'):
                        await self._cleanup_media_file(media_info['file_path'])
                    return None
            
            # 检查无意义内容+广告图片的组合
            if filtered_content and media_info and media_info.get('visual_hashes'):
                if self.content_filter.is_meaningless_content(filtered_content):
                    if await self._is_ad_image_with_threshold(media_info['visual_hashes'], 50):
                        logger.warning(f"🚫 检测到无意义文本+广告图片组合，自动拒绝")
                        if media_info.get('file_path'):
                            await self._cleanup_media_file(media_info['file_path'])
                        return None
            
            # 检查是否为纯广告
            if await self._is_pure_advertisement(content):
                logger.warning(f"🚫 检测到纯广告，自动拒绝: {content[:50]}...")
                if media_info and media_info.get('file_path'):
                    await self._cleanup_media_file(media_info['file_path'])
                return None
            
            # 处理文本被完全过滤的情况
            if content and not filtered_content:
                if filter_reason == "tail_only":
                    if media_info:
                        logger.info(f"ℹ️ 媒体消息的文本为纯尾部推广，已过滤，保留媒体")
                        filtered_content = ""
                    else:
                        logger.info(f"ℹ️ 纯文本消息完全是尾部推广，已过滤")
                        return None
                else:
                    logger.warning(f"🚫 文本被完全过滤（原因: {filter_reason}），拒绝消息")
                    if media_info and media_info.get('file_path'):
                        await self._cleanup_media_file(media_info['file_path'])
                    return None
            
            # 检查是否为空消息
            if not filtered_content and not media_info:
                logger.warning(f"🚫 消息无内容也无媒体，自动跳过")
                return None
            
            # 返回处理后的消息数据
            return {
                'message': message,
                'content': content,
                'filtered_content': filtered_content,
                'is_ad': is_ad,
                'media_info': media_info,
                'channel_id': channel_id
            }
            
        except Exception as e:
            logger.error(f"通用消息处理失败: {e}")
            # 清理可能已下载的媒体
            if 'media_info' in locals() and media_info and media_info.get('file_path'):
                await self._cleanup_media_file(media_info['file_path'])
            return None
    
    async def _is_high_risk_content(self, content: str) -> bool:
        """检测高风险广告内容"""
        high_risk_keywords = [
            # 色情相关
            '约炮', '一夜情', '包夜', '上门服务', '外围', '兼职模特',
            '性服务', '色情', '成人视频', '激情视频', '裸聊',
            # 赌博相关
            '网赌', '赌场', '百家乐', '德州扑克', '体育投注',
            '彩票代理', '博彩', '棋牌游戏', '时时彩',
            # 诈骗相关
            '刷单', '兼职刷单', '日赚千元', '躺赚', '零投资高回报'
        ]
        
        content_lower = content.lower() if content else ""
        for keyword in high_risk_keywords:
            if keyword in content_lower:
                logger.warning(f"🚨 检测到高风险广告关键词: {keyword}")
                return True
        return False
    
    async def _is_known_ad_image(self, visual_hashes: dict) -> bool:
        """检查图片是否为已知广告"""
        try:
            from app.services.ad_image_detector import ad_image_detector
            is_ad_image, similarity, match_id = await ad_image_detector.is_known_ad(visual_hashes)
            return is_ad_image
        except Exception as e:
            logger.error(f"广告图片检测失败: {e}")
            return False
    
    async def _is_ad_image_with_threshold(self, visual_hashes: dict, threshold: float) -> bool:
        """检查图片是否为广告（带阈值）"""
        try:
            from app.services.ad_image_detector import ad_image_detector
            is_ad_image, similarity, match_id = await ad_image_detector.is_known_ad(visual_hashes)
            return is_ad_image or similarity > threshold
        except Exception as e:
            logger.error(f"广告图片检测失败: {e}")
            return False
    
    async def _is_pure_advertisement(self, content: str) -> bool:
        """检查是否为纯广告"""
        try:
            use_ai_ad_detection = await config_manager.get_config('ai.use_ad_detection', True)
            
            if use_ai_ad_detection:
                # 使用AI检测
                return await self.content_filter.is_pure_advertisement_ai(content)
            else:
                # 使用传统规则检测
                return self.content_filter.is_pure_advertisement(content)
        except Exception as e:
            logger.error(f"广告检测失败，使用传统方法: {e}")
            return self.content_filter.is_pure_advertisement(content)
    
    async def _cleanup_media_file(self, file_path: str):
        """清理媒体文件"""
        try:
            from app.services.media_handler import media_handler
            await media_handler.cleanup_file(file_path)
        except Exception as e:
            logger.error(f"清理媒体文件失败: {e}")
    
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