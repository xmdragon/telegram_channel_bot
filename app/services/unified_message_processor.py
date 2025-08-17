"""
统一的消息处理器（重构版）
使用管道模式协调各个处理阶段，确保处理流程的模块化和可维护性
"""
import logging
from typing import Optional, Dict
from telethon.tl.types import Message as TLMessage

from app.services.processors import (
    MessageContext, MessagePipeline, ProcessorResult,
    MessageReceiver, MediaDownloader,
    MessageFilterProcessor, ContentValidator,
    MessageStorageProcessor,
    MessageForwarderProcessor
)

logger = logging.getLogger(__name__)

class UnifiedMessageProcessor:
    """统一的消息处理器（重构版） - 使用管道模式协调处理流程"""
    
    def __init__(self):
        self.pipeline = self._create_pipeline()
        self.logger = logging.getLogger(__name__)
    
    def _create_pipeline(self) -> MessagePipeline:
        """创建消息处理管道"""
        pipeline = MessagePipeline()
        
        # 阶段1: 消息接收和媒体下载
        pipeline.add_processor(MessageReceiver())
        pipeline.add_processor(MediaDownloader())
        
        # 阶段2: 内容过滤和验证
        pipeline.add_processor(MessageFilterProcessor())
        pipeline.add_processor(ContentValidator())
        
        # 阶段3: 消息存储
        pipeline.add_processor(MessageStorageProcessor())
        
        # 阶段4: 消息转发和广播
        pipeline.add_processor(MessageForwarderProcessor())
        
        return pipeline
        
    async def process_telegram_message(
        self, 
        message: TLMessage, 
        channel_id: str, 
        is_history: bool = False
    ) -> Optional[Dict]:
        """
        统一的消息处理入口（重构版）
        使用管道模式处理消息
        
        Args:
            message: Telegram消息对象
            channel_id: 频道ID（已格式化）
            is_history: 是否为历史消息
            
        Returns:
            处理后的消息数据字典，如果消息被过滤则返回None
        """
        try:
            # 创建消息上下文
            context = MessageContext(
                telegram_message=message,
                channel_id=channel_id,
                is_history=is_history
            )
            
            # 执行处理管道
            result = await self.pipeline.process(context)
            
            if result.failed:
                self.logger.error(f"消息处理失败 #{message.id}: {result.error}")
                return None
            
            # 如果消息被拒绝，但仍然保存了，返回保存的数据
            if result.context.should_reject and result.context.save_data:
                self._log_final_result(result.context, "rejected")
                return result.context.save_data
            
            # 正常处理完成
            if result.context.save_data:
                status = result.context.save_data.get('status', 'unknown')
                self._log_final_result(result.context, status)
                return result.context.save_data
            
            # 没有保存数据（可能被完全过滤）
            self.logger.info(f"消息 #{message.id} 被完全过滤，未保存")
            return None
            
        except Exception as e:
            self.logger.error(f"统一消息处理失败 #{message.id}: {e}")
            return None
    
    def _log_final_result(self, context: MessageContext, status: str):
        """记录最终处理结果"""
        status_emoji = {
            'pending': '⏳',
            'approved': '✅', 
            'rejected': '❌',
            'auto_forwarded': '🤖'
        }.get(status, '❓')
        
        message_id = context.telegram_message.id
        save_data = context.save_data
        msg_id = save_data.get('message_id', 'N/A') if save_data else 'N/A'
        is_ad = save_data.get('is_ad', False) if save_data else False
        
        self.logger.info(
            f"{status_emoji} 最终处理结果: 消息 #{message_id} -> Redis {context.channel_id}:{msg_id} "
            f"[状态: {status}] [广告: {'是' if is_ad else '否'}]"
        )


# 全局实例
unified_processor = UnifiedMessageProcessor()