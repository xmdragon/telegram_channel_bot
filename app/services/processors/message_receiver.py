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


class MediaDownloader(MessageProcessor):
    """媒体下载处理器 - Linus式简化，只记录媒体元数据"""
    
    def __init__(self):
        super().__init__("MediaDownloader")
        self.logger = logging.getLogger(f"{__name__}.MediaDownloader")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理媒体元数据记录
        Linus原则：只做一件事 - 记录媒体信息，不下载
        实际下载由MediaDownloadService异步处理
        """
        try:
            # 如果没有媒体，直接通过
            if not context.media_type_info or not context.media_type_info.get('has_media'):
                return ProcessorResult(True, context)
            
            message = context.telegram_message
            media_type = context.media_type_info.get('media_type', 'unknown')
            
            # 只记录媒体元数据，不进行实际下载
            media_info = {
                'media_type': media_type,
                'message_id': message.id,
                'channel_id': context.channel_id,
                'has_media': True,
                'pending_download': True  # 标记为待下载
            }
            
            context.media_info = media_info
            
            # 提交到下载队列（如果需要）
            if self._should_download(media_type):
                from app.services.media_download_service import media_download_service
                task_id = media_download_service.submit_task(
                    message_id=str(message.id),
                    channel_id=context.channel_id,
                    message_obj=message,
                    media_type=media_type
                )
                media_info['download_task_id'] = task_id
                self.logger.info(f"媒体下载任务已提交: {task_id} ({media_type})")
            else:
                self.logger.debug(f"媒体类型 {media_type} 不需要下载")
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            # fail-fast: 错误直接报告
            self.logger.error(f"媒体处理失败: {e}", exc_info=True)
            return await self._handle_error(context, e)
    
    def _should_download(self, media_type: str) -> bool:
        """判断媒体类型是否需要下载"""
        # webpage类型通常不需要下载
        return media_type not in ['webpage', 'unknown']
    
    # Linus式简化：删除_download_media方法，不再需要环境判断
    
    # Linus式简化：删除_download_media_with_client方法，由MediaDownloadService统一处理
    
    # Linus式简化：删除_process_media_metadata_only方法，统一处理流程