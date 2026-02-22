"""
Telegram消息事件处理器
负责事件注册和消息接收分发
"""
import logging
from typing import Optional, Callable
from telethon import events

from app.core.config import db_settings

logger = logging.getLogger(__name__)

class MessageEventHandler:
    """消息事件处理器 - 处理Telegram事件"""

    def __init__(self):
        self._message_processor: Optional[Callable] = None
        self._callback_processor: Optional[Callable] = None
        
    
    async def register_event_handlers(self, client):
        """注册事件处理器到客户端"""
        logger.info("注册事件处理器...")
        
        # 获取需要监听的频道ID列表
        source_channels = await db_settings.get_source_channels()

        # 构建监听列表（转换为整数格式）
        chats_to_monitor = []
        for channel_data in source_channels:
            try:
                # 检查是否为字典格式（频道对象）
                if isinstance(channel_data, dict):
                    # 提取频道ID
                    channel_id = channel_data.get('channel_id', '')
                    if channel_id:
                        chats_to_monitor.append(int(channel_id))
                        logger.debug(f"添加监听频道: {channel_data.get('channel_name', 'Unknown')} -> {channel_id}")
                    else:
                        logger.warning(f"频道缺少channel_id: {channel_data.get('channel_name', 'Unknown')}")
                else:
                    # 假设是字符串格式的ID
                    chats_to_monitor.append(int(channel_data))
            except (ValueError, TypeError):
                logger.warning(f"无法转换频道ID，跳过异常数据: {channel_data}")
        
        logger.info(f"将监听以下频道/群组: {chats_to_monitor}")

        if not chats_to_monitor:
            logger.warning("监听频道列表为空，跳过事件处理器注册，避免监听所有聊天")
            return

        # 新消息事件处理器 - 只监听指定的频道
        @client.on(events.NewMessage(chats=chats_to_monitor))
        async def handle_new_message(event):
            """处理新消息事件"""
            # 第一时间检查采集开关，避免不必要的处理
            try:
                from app.services.config_manager import config_manager
                collection_enabled = await config_manager.get_config('collection.enabled', False)
                if not collection_enabled:
                    logger.debug("[事件跳过] 采集已禁用，忽略新消息")
                    return
                
                logger.info("[事件触发] 收到新消息！")
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
            # 采集开关已在handle_new_message中检查过，这里无需重复检查
            
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
            # 使用内置的回调处理器
            await self.handle_callback(event)
    
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

        # 检查是否来自源频道
        if chat_id in source_channels:
            return "source_channel"

        # 其他类型
        else:
            return "other"


    async def handle_callback(self, event):
        """处理回调按钮"""
        try:
            data = event.data.decode()
            action, message_id = data.split('_', 1)
            message_id = int(message_id)

            logger.info(f"处理回调: {action} for message {message_id}")

            if action == "approve":
                await self.approve_message(message_id, event.sender.username)
            elif action == "reject":
                await self.reject_message(message_id, event.sender.username)
            else:
                logger.warning(f"未知的回调动作: {action}")

        except Exception as e:
            logger.error(f"处理回调时出错: {e}")


    async def approve_message(self, message_id: int, reviewer: str):
        """批准消息"""
        try:
            logger.info(f"批准消息 {message_id} by {reviewer}")

            from app.storage.redis_manager import redis_manager

            # 获取消息
            message = await redis_manager.get_message(message_id)
            if message:
                # 更新状态为手动批准
                message['status'] = 'manual_approved'
                message['reviewer'] = reviewer
                await redis_manager.update_message(message_id, message)
                logger.info(f"✅ 消息 {message_id} 已批准")
            else:
                logger.error(f"❌ 找不到消息 {message_id}")

        except Exception as e:
            logger.error(f"批准消息失败: {e}")

    async def reject_message(self, message_id: int, reviewer: str):
        """拒绝消息"""
        try:
            logger.info(f"拒绝消息 {message_id} by {reviewer}")

            from app.storage.redis_manager import redis_manager

            # 获取消息
            message = await redis_manager.get_message(message_id)
            if message:
                # 更新状态为手动拒绝
                message['status'] = 'manual_rejected'
                message['reviewer'] = reviewer
                await redis_manager.update_message(message_id, message)
                logger.info(f"✅ 消息 {message_id} 已拒绝")
            else:
                logger.error(f"❌ 找不到消息 {message_id}")

        except Exception as e:
            logger.error(f"拒绝消息失败: {e}")


# 全局事件处理器实例
message_event_handler = MessageEventHandler()