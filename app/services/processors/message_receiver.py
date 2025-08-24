"""
消息接收处理器
负责提取原始消息内容、媒体类型检测和基础数据准备
"""
import logging
from typing import Optional
from datetime import datetime

from app.services.processors.base import MessageProcessor, ProcessorResult, MessageContext
from app.utils.timezone import parse_telegram_time
from telethon.tl.types import Message as TLMessage

logger = logging.getLogger(__name__)


class MessageReceiver(MessageProcessor):
    """消息接收处理器 - 提取和准备消息基础数据"""
    
    def __init__(self):
        super().__init__("MessageReceiver")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理消息接收阶段
        - 提取原始内容
        - 检测媒体类型
        - 准备基础时间戳
        """
        try:
            message = context.telegram_message
            
            # 步骤1: 提取原始内容
            original_content = await self._extract_original_content(message)
            context.original_content = original_content
            context.processed_content = original_content  # 初始化处理后内容
            
            # 步骤2: 检测媒体类型信息（即使无法下载也要记录）
            if message.media:
                media_type_info = {
                    'has_media': True,
                    'media_type': self._get_media_type(message.media),
                    'download_failed': False  # 将在后续处理中更新
                }
                context.media_type_info = media_type_info
                self.logger.info(f"检测到媒体类型: {media_type_info['media_type']}")
            
            # 步骤3: 设置时间戳
            context.created_at = parse_telegram_time(message.date)
            
            # 步骤4: 验证消息有效性
            if not self._is_valid_message(context):
                context.should_reject = True
                context.reject_reason = "消息无有效内容"
                self.logger.info(f"消息 #{message.id} 无有效内容，标记为拒绝")
                return ProcessorResult(True, context)
            
            self.logger.info(f"消息接收完成: ID#{message.id}, 内容长度:{len(original_content)}, 媒体:{bool(message.media)}")
            return ProcessorResult(True, context)
            
        except Exception as e:
            return await self._handle_error(context, e)
    
    async def _extract_original_content(self, message: TLMessage) -> str:
        """
        提取消息的原始内容 - 与Telegram官方保持一致
        优先使用message字段（纯文本），避免格式化标记和重复拼接
        
        Args:
            message: Telegram消息对象
            
        Returns:
            原始内容字符串
        """
        # 按Telegram官方优先级提取，只取第一个有效字段
        # 不拼接多个字段，避免重复 - 修复消息#2261重复显示问题
        
        # 优先级：message → raw_text → text → caption
        # message字段是Telegram标准纯文本，与官方客户端显示一致
        if hasattr(message, 'message') and message.message:
            content = message.message.strip()
            self.logger.debug(f"使用message字段: {len(content)}字符")
            return content
        elif hasattr(message, 'raw_text') and message.raw_text:
            content = message.raw_text.strip()
            self.logger.debug(f"使用raw_text字段: {len(content)}字符")
            return content
        elif hasattr(message, 'text') and message.text:
            content = message.text.strip()
            self.logger.debug(f"使用text字段: {len(content)}字符")
            return content
        elif hasattr(message, 'caption') and message.caption:
            content = message.caption.strip()
            self.logger.debug(f"使用caption字段: {len(content)}字符")
            return content
        
        self.logger.debug("未找到有效文本内容")
        return ""
    
    def _get_media_type(self, media) -> str:
        """获取媒体类型"""
        try:
            from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
            from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio
            from telethon.tl.types import DocumentAttributeAnimated, DocumentAttributeSticker
            
            if isinstance(media, MessageMediaPhoto):
                return 'photo'
            elif isinstance(media, MessageMediaDocument):
                document = media.document
                if document and hasattr(document, 'attributes'):
                    for attr in document.attributes:
                        if isinstance(attr, DocumentAttributeVideo):
                            return 'animation' if attr.round_message else 'video'
                        elif isinstance(attr, DocumentAttributeAnimated):
                            return 'animation'
                        elif isinstance(attr, DocumentAttributeAudio):
                            return 'audio'
                        elif isinstance(attr, DocumentAttributeSticker):
                            return 'sticker'
                    
                    # 如果没有特殊属性，判断MIME类型
                    if document.mime_type:
                        if document.mime_type.startswith('video/'):
                            return 'video'
                        elif document.mime_type.startswith('audio/'):
                            return 'audio'
                        elif document.mime_type.startswith('image/'):
                            return 'photo'
                return 'document'
            else:
                return 'unknown'
        except Exception as e:
            self.logger.debug(f"获取媒体类型失败: {e}")
            return 'unknown'
    
    def _is_valid_message(self, context: MessageContext) -> bool:
        """
        检查消息是否有效（有内容或媒体）
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否有效
        """
        # 有文本内容
        if context.original_content.strip():
            return True
        
        # 有媒体内容
        if context.media_type_info and context.media_type_info.get('has_media'):
            return True
        
        return False


class MediaDownloader(MessageProcessor):
    """媒体下载处理器 - 专门处理媒体文件下载"""
    
    def __init__(self):
        super().__init__("MediaDownloader")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理媒体下载
        - 下载媒体文件
        - 计算文件哈希
        - 更新媒体信息
        """
        try:
            # 如果没有媒体，跳过
            if not context.media_type_info or not context.media_type_info.get('has_media'):
                return ProcessorResult(True, context)
            
            message = context.telegram_message
            
            # 尝试下载媒体
            media_info = await self._download_media(message, context.channel_id)
            
            if media_info:
                context.media_info = media_info
                self.logger.info(f"媒体下载成功: {media_info.get('file_path')}")
            else:
                # 标记下载失败
                context.media_type_info['download_failed'] = True
                self.logger.warning(f"媒体下载失败，但已记录媒体类型: {context.media_type_info['media_type']}")
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            return await self._handle_error(context, e)
    
    async def _download_media(self, message: TLMessage, channel_id: str) -> Optional[dict]:
        """下载媒体文件"""
        try:
            if not message.media:
                return None
            
            # 确定超时时间
            timeout = 30.0  # 默认30秒
            if hasattr(message.media, 'document'):
                document = message.media.document
                if document:
                    mime_type = getattr(document, 'mime_type', '') or ""
                    if mime_type.startswith("video/"):
                        timeout = 120.0  # 视频文件2分钟
                    else:
                        timeout = 60.0   # 其他文档1分钟
            
            # 获取Telegram客户端
            from app.telegram.bot import telegram_bot
            if not telegram_bot or not telegram_bot.client:
                self.logger.warning("Telegram客户端未连接，无法下载媒体")
                return None
            
            # 下载媒体
            from app.services.media_handler import media_handler
            media_info = await media_handler.download_media(
                telegram_bot.client,
                message,
                message.id,
                timeout=timeout
            )
            
            if not media_info or not media_info.get('file_path'):
                return None
            
            return media_info
            
        except Exception as e:
            self.logger.error(f"媒体下载失败: {e}")
            return None