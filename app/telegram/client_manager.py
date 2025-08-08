"""
Telegram客户端连接管理器
专门负责客户端的创建、连接、状态监控和认证管理
"""
import logging
import asyncio
from typing import Optional, Callable
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, ChannelPrivateError

from app.services.config_manager import ConfigManager
from app.telegram.process_lock import telegram_lock
from app.services.system_monitor import system_monitor

logger = logging.getLogger(__name__)

class TelegramClientManager:
    """Telegram客户端管理器 - 只负责连接管理"""
    
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.config_manager = ConfigManager()
        self.is_connected = False
        self._connection_callbacks = []
        self._disconnection_callbacks = []
        
    def add_connection_callback(self, callback: Callable):
        """添加连接成功回调"""
        self._connection_callbacks.append(callback)
        
    def add_disconnection_callback(self, callback: Callable):
        """添加断开连接回调"""
        self._disconnection_callbacks.append(callback)
    
    async def connect(self) -> bool:
        """连接到Telegram"""
        try:
            # 获取认证信息
            api_id = await self.config_manager.get_config("telegram.api_id")
            api_hash = await self.config_manager.get_config("telegram.api_hash") 
            session_string = await self.config_manager.get_config("telegram.session")
            
            # 检查认证信息，session_string必须是有效的session，而不仅仅是非空字符串
            if not all([api_id, api_hash]) or not session_string or session_string == "":
                logger.warning("缺少Telegram认证信息，请通过Web界面进行认证")
                return False
            
            # 验证session_string格式（StringSession通常以1开头且长度较长）
            if len(session_string) < 100 or not session_string.startswith('1'):
                logger.warning("Telegram session无效或未认证，请通过Web界面进行认证")
                return False
            
            logger.info(f"准备连接Telegram客户端，API ID: {api_id}")
            
            # 获取进程锁
            if not await telegram_lock.acquire(timeout=30):
                logger.error("无法获取Telegram进程锁，可能有其他进程正在使用")
                return False
            
            try:
                # 创建客户端
                self.client = TelegramClient(
                    StringSession(session_string),
                    int(api_id),
                    api_hash
                )
                
                # 启动客户端
                logger.info("启动Telegram客户端...")
                await self.client.start()
                
                # 验证连接
                me = await self.client.get_me()
                logger.info(f"✅ 客户端已成功连接，登录用户: {me.first_name} (@{me.username})")
                
                # 更新连接状态
                self.is_connected = True
                
                # 更新auth_manager的客户端实例，保持向后兼容
                from app.telegram.auth import auth_manager
                auth_manager.client = self.client
                
                # 执行连接成功回调
                for callback in self._connection_callbacks:
                    try:
                        await callback(self.client)
                    except Exception as e:
                        logger.error(f"连接回调执行失败: {e}")
                
                return True
                
            except Exception as e:
                logger.error(f"启动客户端失败: {e}")
                await telegram_lock.release()
                self.client = None
                self.is_connected = False
                raise
                
        except Exception as e:
            logger.error(f"连接Telegram客户端时出错: {e}")
            return False
    
    async def disconnect(self):
        """断开Telegram连接"""
        if self.client and self.is_connected:
            try:
                # 执行断开连接回调
                for callback in self._disconnection_callbacks:
                    try:
                        await callback()
                    except Exception as e:
                        logger.error(f"断开连接回调执行失败: {e}")
                
                await self.client.disconnect()
                logger.info("Telegram客户端已断开连接")
                
            except Exception as e:
                logger.error(f"断开连接时出错: {e}")
            finally:
                self.client = None
                self.is_connected = False
                await telegram_lock.release()
    
    async def is_client_connected(self) -> bool:
        """检查客户端连接状态"""
        if not self.client:
            return False
        
        try:
            # 尝试获取自己的信息来测试连接
            await self.client.get_me()
            return True
        except Exception:
            self.is_connected = False
            return False
    
    async def get_client(self) -> Optional[TelegramClient]:
        """获取客户端实例（如果已连接）"""
        if self.is_connected and self.client:
            return self.client
        return None
    
    async def ensure_connected(self) -> bool:
        """确保客户端已连接，如果未连接则尝试连接"""
        if await self.is_client_connected():
            return True
        
        logger.info("客户端未连接，尝试重新连接...")
        return await self.connect()
    
    async def get_chat_info(self, chat_id: str):
        """获取聊天信息"""
        if not self.client:
            raise RuntimeError("客户端未连接")
            
        try:
            chat = await self.client.get_entity(int(chat_id))
            return chat
        except Exception as e:
            logger.error(f"获取聊天信息时出错: {e}")
            return None

# 全局客户端管理器实例
client_manager = TelegramClientManager()