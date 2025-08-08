"""
Telegram消息事件处理器
专门负责事件注册、消息接收和初步处理
"""
import logging
from typing import Optional, Callable
from telethon import events
from telethon.tl.types import Message as TLMessage

from app.core.config import db_settings
from app.services.telegram_link_resolver import link_resolver

logger = logging.getLogger(__name__)

class MessageEventHandler:
    """消息事件处理器 - 只负责事件处理和消息分发"""
    
    def __init__(self):
        self._message_processor: Optional[Callable] = None
        self._callback_processor: Optional[Callable] = None
        
    def set_message_processor(self, processor: Callable):
        """设置消息处理器回调"""
        self._message_processor = processor
        
    def set_callback_processor(self, processor: Callable):
        """设置回调处理器回调"""
        self._callback_processor = processor
    
    async def register_event_handlers(self, client):
        """注册事件处理器到客户端"""
        logger.info("注册事件处理器...")
        
        # 获取需要监听的频道ID列表
        source_channels = await db_settings.get_source_channels()
        review_group_id = await link_resolver.get_effective_group_id()
        
        # 构建监听列表（转换为整数格式）
        chats_to_monitor = []
        for channel_id in source_channels:
            try:
                chats_to_monitor.append(int(channel_id))
            except (ValueError, TypeError):
                logger.warning(f"无法转换频道ID: {channel_id}")
        
        # 添加审核群
        if review_group_id:
            try:
                chats_to_monitor.append(int(review_group_id))
            except (ValueError, TypeError):
                logger.warning(f"无法转换审核群ID: {review_group_id}")
        
        logger.info(f"将监听以下频道/群组: {chats_to_monitor}")
        
        # 新消息事件处理器 - 只监听指定的频道
        @client.on(events.NewMessage(chats=chats_to_monitor if chats_to_monitor else None))
        async def handle_new_message(event):
            """处理新消息事件"""
            logger.info("[事件触发] 收到新消息！")
            try:
                await self._handle_new_message(event)
            except Exception as e:
                logger.error(f"处理消息失败: {e}")
        
        # 回调查询事件处理器
        @client.on(events.CallbackQuery)
        async def handle_callback(event):
            """处理回调查询"""
            try:
                await self._handle_callback_query(event)
            except Exception as e:
                logger.error(f"处理回调时出错: {e}")
        
        # 验证事件处理器已注册
        handlers = client.list_event_handlers()
        logger.info(f"✅ 事件处理器注册完成，共 {len(handlers)} 个处理器")
    
    async def _handle_new_message(self, event):
        """处理新消息事件"""
        try:
            message = event.message
            if not message:
                return
            
            # 获取聊天信息
            chat = await event.get_chat()
            chat_info = await self._parse_chat_info(chat)
            
            # 记录消息处理
            logger.info(f"处理消息 - 频道: {chat_info['title']} (原始ID: {chat_info['raw_id']}, 格式化ID: {chat_info['formatted_id']})")
            
            # 判断消息来源类型
            message_type = await self._determine_message_type(chat_info['formatted_id'])
            
            # 分发到相应的处理器
            if self._message_processor:
                await self._message_processor(message, chat, chat_info, message_type)
            else:
                logger.warning("未设置消息处理器，忽略消息")
                
        except Exception as e:
            logger.error(f"处理新消息时出错: {e}")
    
    async def _handle_callback_query(self, event):
        """处理回调查询事件"""
        if self._callback_processor:
            await self._callback_processor(event)
        else:
            logger.warning("未设置回调处理器，忽略回调")
    
    async def _parse_chat_info(self, chat) -> dict:
        """解析聊天信息，统一ID格式"""
        raw_chat_id = chat.id
        chat_title = getattr(chat, 'title', 'Unknown')
        
        # 统一频道ID格式
        # Telegram频道ID可能以不同格式出现：
        # - 正数ID (如 2829999238)
        # - 负数ID (如 -1002829999238)
        # 统一转换为带-100前缀的格式用于匹配
        if raw_chat_id > 0:
            # 如果是正数，加上-100前缀
            formatted_id = f"-100{raw_chat_id}"
        else:
            # 如果是负数，直接转为字符串
            formatted_id = str(raw_chat_id)
        
        return {
            'raw_id': raw_chat_id,
            'formatted_id': formatted_id,
            'title': chat_title,
            'chat': chat
        }
    
    async def _determine_message_type(self, chat_id: str) -> str:
        """判断消息来源类型"""
        # 获取配置
        source_channels = await db_settings.get_source_channels()
        review_group_id = await link_resolver.get_effective_group_id()
        
        # 检查是否来自源频道
        if chat_id in source_channels:
            return "source_channel"
        
        # 检查是否来自审核群
        elif review_group_id and chat_id == review_group_id:
            return "review_group"
        
        # 其他类型
        else:
            return "other"

# 全局事件处理器实例
message_event_handler = MessageEventHandler()