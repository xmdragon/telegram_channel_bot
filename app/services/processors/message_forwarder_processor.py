"""
消息转发处理器
负责审核群转发、WebSocket广播和转发配置管理
"""
import logging
from typing import Dict

from app.services.processors.base import MessageProcessor, ProcessorResult, MessageContext

logger = logging.getLogger(__name__)


class MessageForwarderProcessor(MessageProcessor):
    """消息转发处理器 - 处理消息转发和广播"""
    
    def __init__(self):
        super().__init__("MessageForwarderProcessor")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理消息转发阶段
        - 检查转发配置
        - 转发到审核群
        - 广播到WebSocket客户端
        """
        try:
            # 如果保存数据不存在，跳过转发
            if not context.save_data:
                self.logger.warning("保存数据不存在，跳过转发处理")
                return ProcessorResult(True, context)
            
            # 步骤1: 检查是否需要转发到审核群
            if context.should_forward and await self._should_forward_to_review(context):
                await self._forward_to_review(context)
            
            # 步骤2: 广播到WebSocket客户端
            if context.broadcast_enabled:
                await self._broadcast_to_websocket(context)
            
            self.logger.info(f"转发处理完成: 消息#{context.telegram_message.id}")
            return ProcessorResult(True, context)
            
        except Exception as e:
            return await self._handle_error(context, e)
    
    async def _should_forward_to_review(self, context: MessageContext) -> bool:
        """
        检查是否应该转发消息到审核群
        
        Returns:
            是否应该转发到审核群
        """
        try:
            from app.services.config_manager import config_manager
            
            # 获取配置：是否启用审核群转发
            enable_review = await config_manager.get_config('review.enable_forward_to_group')
            if enable_review is False:
                return False
            
            # 对于实时消息，默认转发
            if not context.is_history:
                return True
            
            # 对于历史消息，检查专门的配置
            forward_history = await config_manager.get_config('review.forward_history_messages')
            return forward_history if forward_history is not None else False
            
        except Exception as e:
            self.logger.error(f"检查转发配置失败: {e}")
            # 出错时的默认行为：实时消息转发，历史消息不转发
            return not context.is_history
    
    async def _forward_to_review(self, context: MessageContext):
        """转发消息到审核群"""
        try:
            # 延迟导入避免循环引用
            from app.telegram.message_forwarder import message_forwarder
            from app.telegram.bot import telegram_bot
            
            if not telegram_bot or not telegram_bot.client:
                self.logger.warning("Telegram客户端未连接，无法转发到审核群")
                return
            
            # 创建兼容的消息对象
            temp_message = self._create_message_compat(context.save_data)
            
            # 执行转发
            await message_forwarder.forward_to_review(telegram_bot.client, temp_message)
            self.logger.info(f"消息已转发到审核群: #{context.telegram_message.id}")
            
        except Exception as e:
            self.logger.error(f"转发到审核群失败: {e}")
    
    async def _broadcast_to_websocket(self, context: MessageContext):
        """广播消息到WebSocket客户端"""
        try:
            from app.api.websocket import websocket_manager
            
            # 准备广播数据
            broadcast_data = self._prepare_broadcast_data(context.save_data)
            
            # 执行广播
            await websocket_manager.broadcast_new_message(broadcast_data)
            
            msg_id = context.save_data.get('message_id', 'N/A')
            connection_count = len(websocket_manager.active_connections)
            self.logger.info(f"成功广播新消息 ID:{msg_id} 到 {connection_count} 个WebSocket连接")
            
        except ImportError as e:
            self.logger.error(f"导入WebSocket管理器失败: {e}")
        except Exception as e:
            self.logger.error(f"广播消息失败: {e}")
    
    def _create_message_compat(self, message_data: Dict):
        """创建兼容的消息对象用于转发"""
        from app.services.duplicate_detector import MessageCompat
        
        temp_message = MessageCompat(message_data)
        temp_message.id = message_data.get('message_id')
        temp_message.source_channel = message_data.get('source_channel')
        temp_message.content = message_data.get('content')
        temp_message.filtered_content = message_data.get('filtered_content')
        temp_message.media_type = message_data.get('media_type')
        temp_message.media_url = message_data.get('media_url')
        temp_message.is_ad = message_data.get('is_ad')
        temp_message.status = message_data.get('status')
        
        return temp_message
    
    def _prepare_broadcast_data(self, message_data: Dict) -> Dict:
        """准备WebSocket广播数据"""
        return {
            "id": message_data.get('message_id'),
            "message_id": message_data.get('message_id'),
            "source_channel": message_data.get('source_channel'),
            "content": message_data.get('content'),
            "filtered_content": message_data.get('filtered_content'),
            "media_type": message_data.get('media_type'),
            "media_url": message_data.get('media_url'),
            "is_ad": message_data.get('is_ad'),
            "status": message_data.get('status'),
            "created_at": message_data.get('created_at'),
            "is_combined": message_data.get('is_combined'),
            "media_group": message_data.get('media_group') if message_data.get('is_combined') else None,
            "combined_messages": message_data.get('combined_messages') if message_data.get('is_combined') else None
        }


class ReviewForwarder(MessageProcessor):
    """审核转发处理器 - 专门处理审核群转发逻辑"""
    
    def __init__(self):
        super().__init__("ReviewForwarder")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理审核群转发
        - 检查转发条件
        - 执行转发操作
        """
        try:
            # 检查是否应该转发
            if not await self._should_forward(context):
                return ProcessorResult(True, context)
            
            # 执行转发
            await self._execute_forward(context)
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            return await self._handle_error(context, e)
    
    async def _should_forward(self, context: MessageContext) -> bool:
        """检查是否应该转发"""
        # 没有保存数据则不转发
        if not context.save_data:
            return False
        
        # 检查用户设置
        if not context.should_forward:
            return False
        
        # 检查系统配置
        try:
            from app.services.config_manager import config_manager
            
            enable_review = await config_manager.get_config('review.enable_forward_to_group')
            if enable_review is False:
                return False
            
            # 历史消息特殊处理
            if context.is_history:
                forward_history = await config_manager.get_config('review.forward_history_messages')
                return forward_history if forward_history is not None else False
            
            return True
            
        except Exception as e:
            self.logger.error(f"检查转发配置失败: {e}")
            return not context.is_history  # 默认策略
    
    async def _execute_forward(self, context: MessageContext):
        """执行转发操作"""
        try:
            from app.telegram.message_forwarder import message_forwarder
            from app.telegram.bot import telegram_bot
            
            if not telegram_bot or not telegram_bot.client:
                self.logger.warning("Telegram客户端未连接，无法转发")
                return
            
            # 创建消息对象
            from app.services.duplicate_detector import MessageCompat
            temp_message = MessageCompat(context.save_data)
            temp_message.id = context.save_data.get('message_id')
            temp_message.source_channel = context.save_data.get('source_channel')
            temp_message.content = context.save_data.get('content')
            temp_message.filtered_content = context.save_data.get('filtered_content')
            temp_message.media_type = context.save_data.get('media_type')
            temp_message.media_url = context.save_data.get('media_url')
            temp_message.is_ad = context.save_data.get('is_ad')
            temp_message.status = context.save_data.get('status')
            
            # 执行转发
            await message_forwarder.forward_to_review(telegram_bot.client, temp_message)
            self.logger.info(f"消息已转发到审核群: #{context.telegram_message.id}")
            
        except Exception as e:
            self.logger.error(f"执行转发失败: {e}")


class WebSocketBroadcaster(MessageProcessor):
    """WebSocket广播处理器 - 专门处理WebSocket消息广播"""
    
    def __init__(self):
        super().__init__("WebSocketBroadcaster")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理WebSocket广播
        - 准备广播数据
        - 执行广播操作
        """
        try:
            # 检查是否启用广播
            if not context.broadcast_enabled or not context.save_data:
                return ProcessorResult(True, context)
            
            # 执行广播
            await self._execute_broadcast(context)
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            return await self._handle_error(context, e)
    
    async def _execute_broadcast(self, context: MessageContext):
        """执行WebSocket广播"""
        try:
            from app.api.websocket import websocket_manager
            
            # 准备广播数据
            broadcast_data = {
                "id": context.save_data.get('message_id'),
                "message_id": context.save_data.get('message_id'),
                "source_channel": context.save_data.get('source_channel'),
                "content": context.save_data.get('content'),
                "filtered_content": context.save_data.get('filtered_content'),
                "media_type": context.save_data.get('media_type'),
                "media_url": context.save_data.get('media_url'),
                "is_ad": context.save_data.get('is_ad'),
                "status": context.save_data.get('status'),
                "created_at": context.save_data.get('created_at'),
                "is_combined": context.save_data.get('is_combined'),
                "media_group": context.save_data.get('media_group') if context.save_data.get('is_combined') else None,
                "combined_messages": context.save_data.get('combined_messages') if context.save_data.get('is_combined') else None
            }
            
            # 执行广播
            await websocket_manager.broadcast_new_message(broadcast_data)
            
            msg_id = context.save_data.get('message_id', 'N/A')
            connection_count = len(websocket_manager.active_connections)
            self.logger.info(f"成功广播新消息 ID:{msg_id} 到 {connection_count} 个WebSocket连接")
            
        except ImportError as e:
            self.logger.error(f"导入WebSocket管理器失败: {e}")
        except Exception as e:
            self.logger.error(f"执行广播失败: {e}")