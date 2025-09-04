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
            
            # 步骤4: Linus式源头拦截 - 直接丢弃空消息
            if not self._is_valid_message(context):
                self.logger.debug(f"消息 #{message.id} 无有效内容，直接丢弃（不进入处理流程）")
                # 返回失败结果，表示此消息应被丢弃，不进入后续处理
                return ProcessorResult(False, context, "无有效内容，直接丢弃")
            
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
        # 重写logger使用正确的模块名称
        self.logger = logging.getLogger(f"{__name__}.MediaDownloader")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理媒体下载（带性能监控）
        - 下载媒体文件
        - 计算文件哈希
        - 处理OCR（如果是图片）
        - 更新媒体信息
        """
        # 导入性能监控
        try:
            from app.services.performance_monitor import PerformanceTimer, perf_logger
            media_timer = PerformanceTimer("media_downloader").start()
        except ImportError:
            media_timer = None
        
        try:
            # 如果没有媒体，跳过
            if not context.media_type_info or not context.media_type_info.get('has_media'):
                return ProcessorResult(True, context)
            
            # 如果媒体已经在collector中处理完成，直接跳过
            if context.media_info and context.media_info.get('processed_in') == 'collector':
                self.logger.debug("媒体已在collector中处理完成，跳过重复处理")
                return ProcessorResult(True, context)
            
            message = context.telegram_message
            media_type = context.media_type_info.get('media_type', 'unknown')
            
            if media_timer:
                media_timer.set_metric("media_type", media_type)
                media_timer.set_metric("message_id", message.id)
            
            # 阶段1: 媒体下载
            if media_timer:
                download_timer = media_timer.add_child("media_download").start()
            
            media_info = await self._download_media(message, context.channel_id)
            
            if media_timer:
                download_timer.stop()
                download_timer.set_metric("download_success", media_info is not None)
                if media_info:
                    download_timer.set_metric("file_size", media_info.get('file_size', 0))
                    download_timer.set_metric("file_path", media_info.get('file_path', ''))
            
            if media_info:
                context.media_info = media_info
                
                # 阶段2: OCR处理（如果是图片）
                if media_type in ['photo', 'sticker'] and media_info.get('file_path'):
                    if media_timer:
                        ocr_timer = media_timer.add_child("ocr_processing").start()
                    
                    try:
                        # OCR处理在这里会被调用（通过其他模块）
                        # 记录OCR阶段耗时
                        pass  # OCR处理在后续的过滤阶段进行
                    finally:
                        if media_timer:
                            ocr_timer.stop()
                
                # 根据环境选择日志级别
                if media_info.get('processed_in') == 'collector':
                    self.logger.debug(f"媒体下载成功: {media_info.get('file_path')}")
                else:
                    self.logger.debug(f"媒体元数据处理完成: {media_type}")
            else:
                # 检测运行环境
                from app.telegram.bot import telegram_bot
                has_client = telegram_bot and getattr(telegram_bot, 'client', None) is not None
                
                if has_client:
                    # collector环境：真正的下载失败
                    context.media_type_info['download_failed'] = True
                    self.logger.warning(f"媒体下载失败，但已记录媒体类型: {media_type}")
                else:
                    # processor环境：正常跳过，不记录为失败
                    context.media_type_info['download_skipped'] = True  
                    self.logger.debug(f"processor环境跳过媒体下载: {media_type}")
            
            # 记录性能数据
            if media_timer:
                total_time = media_timer.stop()
                media_timer.set_metric("total_time_ms", total_time)
                
                # 如果媒体处理耗时过长，记录详细日志
                if total_time > 5000:  # 超过5秒
                    perf_data = {
                        "operation": "media_downloader",
                        "channel_id": context.channel_id,
                        "message_id": message.id,
                        "media_type": media_type,
                        "total_time_ms": total_time,
                        "performance_breakdown": media_timer.to_dict(),
                        "bottleneck_warning": True
                    }
                    perf_logger.log_performance(perf_data)
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            if media_timer:
                media_timer.stop()
                media_timer.set_metric("error", str(e))
            return await self._handle_error(context, e)
    
    async def _download_media(self, message: TLMessage, channel_id: str) -> Optional[dict]:
        """智能媒体处理 - 根据运行环境决定行为
        
        collector环境：下载媒体文件
        processor环境：跳过下载，记录媒体类型信息
        """
        try:
            if not message.media:
                return None
            
            # 获取Telegram客户端连接状态
            from app.telegram.bot import telegram_bot
            has_client = telegram_bot and getattr(telegram_bot, 'client', None) is not None
            
            if has_client:
                # collector环境：正常下载媒体
                return await self._download_media_with_client(message, channel_id)
            else:
                # processor环境：静默记录媒体类型，不显示警告
                self.logger.debug("processor环境，跳过媒体下载")
                return await self._process_media_metadata_only(message)
                
        except Exception as e:
            # 检测运行环境，processor环境降级为debug
            from app.telegram.bot import telegram_bot
            has_client = telegram_bot and getattr(telegram_bot, 'client', None) is not None
            
            if has_client:
                # collector环境：记录为错误
                self.logger.error(f"媒体处理失败: {e}")
            else:
                # processor环境：降级为debug，避免噪音
                self.logger.debug(f"processor环境媒体处理异常（正常）: {e}")
            return None
    
    async def _download_media_with_client(self, message: TLMessage, channel_id: str) -> Optional[dict]:
        """在有Telegram客户端的环境中下载媒体"""
        # 🔥 Linus式修复：统一使用1800秒超时，不区分媒体类型
        timeout = 1800.0  # 30分钟，统一处理所有媒体
        
        # 下载媒体
        from app.telegram.bot import telegram_bot
        from app.services.media_handler import media_handler
        
        media_info = await media_handler.download_media(
            telegram_bot.client,
            message,
            message.id,
            timeout=timeout
        )
        
        if not media_info or not media_info.get('file_path'):
            return None
        
        # 标记为collector环境处理
        media_info['processed_in'] = 'collector'
        self.logger.debug(f"媒体下载完成: {media_info.get('file_path')}")
        return media_info
    
    async def _process_media_metadata_only(self, message: TLMessage) -> Optional[dict]:
        """在processor环境中只处理媒体元数据，不下载文件"""
        try:
            # 创建基本的媒体信息记录
            media_type = 'unknown'
            if hasattr(message.media, '__class__'):
                media_type = message.media.__class__.__name__.replace('MessageMedia', '').lower()
            
            media_info = {
                'media_type': media_type,
                'file_path': None,  # processor环境不下载文件
                'file_size': 0,
                'has_media': True,
                'processed_in': 'processor',  # 标记处理环境
                'download_skipped': True
            }
            
            self.logger.debug(f"媒体元数据记录: {media_type} (processor环境，跳过下载)")
            return media_info
            
        except Exception as e:
            # processor环境的元数据处理异常，降级为debug避免噪音
            self.logger.debug(f"processor环境媒体元数据处理异常: {e}")
            return None