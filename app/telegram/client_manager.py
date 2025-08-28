"""
兼容性适配器 - 将旧client_manager调用适配到新的双Session系统
避免大范围代码修改，保持系统稳定运行
"""
import logging
from typing import Optional
from telethon import TelegramClient
from app.telegram.dual_session_manager import dual_session_manager

logger = logging.getLogger(__name__)

class ClientManagerCompat:
    """兼容性适配器 - 模拟旧client_manager接口"""
    
    def __init__(self):
        self.client = None
        self.is_connected = False
    
    async def connect(self) -> bool:
        """连接 - 使用发送Session"""
        return await dual_session_manager.ensure_sender_connected()
    
    async def connect_without_lock(self) -> bool:
        """无锁连接 - 使用监听Session"""
        return await dual_session_manager.ensure_listener_connected()
    
    async def get_client(self) -> Optional[TelegramClient]:
        """获取客户端 - 优先返回监听Session"""
        client = await dual_session_manager.get_listener_client()
        if not client:
            client = await dual_session_manager.get_sender_client()
        return client
    
    async def ensure_connected(self) -> bool:
        """确保连接 - 检查任意Session可用"""
        return (await dual_session_manager.ensure_listener_connected() or 
                await dual_session_manager.ensure_sender_connected())
    
    async def disconnect(self):
        """断开连接"""
        await dual_session_manager.disconnect_all()
    
    async def get_chat_info(self, chat_id):
        """获取聊天信息 - 使用监听Session"""
        client = await dual_session_manager.get_listener_client()
        if client:
            return await client.get_entity(chat_id)
        return None
    
    # 临时客户端相关方法已被双Session替代
    async def create_temp_client_with_lock(self, timeout=5):
        """已废弃：使用发送Session替代临时客户端"""
        logger.warning("create_temp_client_with_lock已废弃，请使用dual_session_manager")
        return await dual_session_manager.get_sender_client()
    
    async def cleanup_temp_client(self, client):
        """已废弃：双Session无需清理临时客户端"""
        logger.debug("cleanup_temp_client已废弃，双Session无需清理")
        pass

# 兼容性实例
client_manager = ClientManagerCompat()