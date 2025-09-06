"""
Telegram客户端核心功能 - 重构版本
使用组件化架构，保持向后兼容
"""
import logging
from typing import Optional
from telethon.tl.types import Message as TLMessage

# 组件化模块
from app.telegram.bot_manager import bot_manager
from app.telegram.message_handler import message_handler
from app.telegram.media_processor import media_processor
from app.telegram.event_handler import event_handler
from app.telegram.message_event_handler import message_event_handler
from app.telegram.message_forwarder import message_forwarder
from app.telegram.client_manager import client_manager

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram机器人管理类 - 重构版本，保持向后兼容"""
    
    def __init__(self):
        # 使用组件化架构，保持向后兼容的属性
        self._bot_manager = bot_manager
        self._message_handler = message_handler
        self._media_processor = media_processor
        self._event_handler = event_handler
        
        # 向后兼容属性
        self.message_processor = message_handler.message_processor
        self.content_filter = message_handler.content_filter
        
        # 设置组件间的回调关系
        self._setup_component_callbacks()
    
    def _setup_component_callbacks(self):
        """设置各组件间的回调关系"""
        # 设置事件处理器的消息处理器
        message_event_handler.set_message_processor(self._message_handler.handle_message_from_event)
        message_event_handler.set_callback_processor(self._event_handler.handle_callback)
        
        # 设置历史采集器的消息处理器 - 延迟导入避免循环依赖
        from app.telegram.history_collector import history_collector
        history_collector.set_message_processor(self._message_handler.process_source_message)
    
    async def start(self):
        """启动Telegram客户端和监控"""
        await self._bot_manager.start()
        logger.info("Telegram机器人已启动")
    
    # 向后兼容属性
    @property
    def client(self):
        """获取客户端（向后兼容）"""
        return self._bot_manager.get_client()
    
    @property
    def is_running(self):
        """检查是否运行中（向后兼容）"""
        return self._bot_manager.is_client_running()
    
    # 委托方法到组件
    async def process_source_message(self, message: TLMessage, chat):
        """处理源频道消息 - 委托给消息处理器"""
        return await self._message_handler.process_source_message(message, chat)
    
    async def process_review_message(self, message: TLMessage, chat):
        """处理审核群消息 - 委托给消息处理器"""
        return await self._message_handler.process_review_message(message, chat)
    
    
    async def handle_callback(self, event):
        """处理回调按钮 - 委托给事件处理器"""
        return await self._event_handler.handle_callback(event)
    
    # 保持原有的公开方法接口不变，委托给相应组件
    async def forward_to_review(self, db_message):
        """转发消息到审核群 - 委托给转发器"""
        if self.client:
            await message_forwarder.forward_to_review(self.client, db_message)
        else:
            logger.error("客户端未连接，无法转发消息")
    
    async def forward_to_target(self, message):
        """重新发布到目标频道 - 委托给转发器"""
        if self.client:
            await message_forwarder.forward_to_target(self.client, message)
        else:
            logger.error("客户端未连接，无法转发消息")
    
    async def update_review_message(self, message):
        """更新审核群中的消息内容 - 委托给转发器"""
        if self.client:
            await message_forwarder.update_review_message(self.client, message)
        else:
            logger.error("客户端未连接，无法更新消息")
    
    async def delete_review_message(self, review_message_id: int):
        """删除审核群的消息 - 委托给转发器"""
        if self.client:
            await message_forwarder.delete_review_message(self.client, review_message_id)
        else:
            logger.error("客户端未连接，无法删除消息")
    
    async def approve_message(self, message_id: int, reviewer: str):
        """批准消息 - 委托给事件处理器"""
        return await self._event_handler.approve_message(message_id, reviewer)
    
    async def reject_message(self, message_id: int, reviewer: str):
        """拒绝消息 - 委托给事件处理器"""
        return await self._event_handler.reject_message(message_id, reviewer)
    
    async def edit_message(self, message_id: int):
        """编辑消息 - 委托给事件处理器"""
        return await self._event_handler.edit_message(message_id)
    
    async def show_message_detail(self, message_id: int):
        """显示消息详情 - 委托给事件处理器"""
        return await self._event_handler.show_message_detail(message_id)
    
    async def get_chat_info(self, chat_id: str):
        """获取聊天信息 - 委托给客户端管理器"""
        return await client_manager.get_chat_info(chat_id)
    
    async def stop(self):
        """停止客户端 - 委托给Bot管理器"""
        await self._bot_manager.stop()
        logger.info("Telegram客户端已停止")
    
    # 兼容旧方法 - 这些方法已被重构到组件中
    async def save_processed_message(self, message_data: dict, channel_id: str, is_history: bool = False, original_media_info: dict = None):
        """保存处理后的消息 - 委托给消息处理器"""
        return await self._message_handler.save_processed_message(message_data, channel_id, is_history, original_media_info)
    
    async def cleanup_message_files(self, message):
        """清理消息相关的媒体文件 - 委托给媒体处理器"""
        return await self._media_processor.cleanup_message_files(message)

# 全局bot实例，供其他模块使用
telegram_bot = None

# 创建全局实例的工厂函数
def create_telegram_bot():
    """创建Telegram机器人实例"""
    global telegram_bot
    if telegram_bot is None:
        telegram_bot = TelegramBot()
    return telegram_bot

# 获取全局实例
def get_telegram_bot() -> Optional[TelegramBot]:
    """获取Telegram机器人实例"""
    return telegram_bot