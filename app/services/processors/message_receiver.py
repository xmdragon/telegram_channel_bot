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
# Python 3.13兼容性修复：在模块顶部导入所有需要的类型
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    DocumentAttributeVideo, DocumentAttributeAudio,
    DocumentAttributeAnimated, DocumentAttributeSticker
)

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
            
            # 步骤4: Linus式源头拦截 - 直接丢弃空消息
            if not self._is_valid_message(context):
                self.logger.debug(f"消息 #{message.id} 无有效内容，直接丢弃（不进入处理流程）")
                # 返回成功但标记为空消息，让后续处理器跳过（不记录错误）
                context.is_empty_message = True
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
        # 按Telethon实际属性优先级提取，只取第一个有效字段
        # 不拼接多个字段，避免重复 - 修复消息#2261重复显示问题
        
        # 优先级：text → raw_text → caption
        # Telethon的Message对象使用text属性，没有message属性
        if hasattr(message, 'text') and message.text:
            content = message.text.strip()
            self.logger.debug(f"使用text字段: {len(content)}字符")
            return content
        elif hasattr(message, 'raw_text') and message.raw_text:
            content = message.raw_text.strip()
            self.logger.debug(f"使用raw_text字段: {len(content)}字符")
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
            elif isinstance(media, MessageMediaWebPage):
                # 链接预览类型（可能包含缩略图或嵌入媒体）
                return 'webpage'
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


class MediaMetadataProcessor(MessageProcessor):
    """媒体元数据处理器 - 只记录媒体元数据，不进行下载"""
    
    def __init__(self):
        super().__init__("MediaMetadataProcessor")
        self.logger = logging.getLogger(f"{__name__}.MediaMetadataProcessor")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理媒体元数据记录 - 不进行实际下载
        媒体下载应该在collector服务中完成
        """
        try:
            # 如果没有媒体，直接通过
            if not context.media_type_info or not context.media_type_info.get('has_media'):
                return ProcessorResult(True, context)
            
            message = context.telegram_message
            media_type = context.media_type_info.get('media_type', 'unknown')
            
            # 只记录媒体元数据信息
            media_info = {
                'media_type': media_type,
                'message_id': message.id,
                'channel_id': context.channel_id,
                'has_media': True,
                'note': 'Media should be downloaded in collector service'
            }
            
            self.logger.debug(f"记录媒体元数据: {message.id} ({media_type})")
            
            context.media_info = media_info
            return ProcessorResult(True, context)
            
        except Exception as e:
            # fail-fast: 错误直接报告
            self.logger.error(f"媒体元数据处理失败: {e}", exc_info=True)
            return await self._handle_error(context, e)
    
    # MediaMetadataProcessor不需要下载相关方法