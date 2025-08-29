"""
双Session管理器 - Linus式优雅解决方案
彻底消除锁需求，实现真正的并发处理
监听Session：长连接，专门用于事件循环
发送Session：按需连接，专门用于API调用
"""
import logging
import asyncio
from typing import Optional, Callable, List
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, AuthKeyUnregisteredError, SessionRevokedError

from app.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class TelegramDualSessionManager:
    """双Session管理器 - 消除所有锁需求的核心组件"""
    
    def __init__(self):
        self.listener_client: Optional[TelegramClient] = None
        self.sender_client: Optional[TelegramClient] = None
        
        self.listener_connected = False
        self.sender_connected = False
        
        self.config_manager = ConfigManager()
        
        # 连接回调
        self._listener_callbacks: List[Callable] = []
        self._sender_callbacks: List[Callable] = []
        self._disconnection_callbacks: List[Callable] = []
    
    def add_listener_callback(self, callback: Callable):
        """添加监听客户端连接成功回调"""
        self._listener_callbacks.append(callback)
    
    def add_sender_callback(self, callback: Callable):
        """添加发送客户端连接成功回调"""
        self._sender_callbacks.append(callback)
    
    def add_disconnection_callback(self, callback: Callable):
        """添加断开连接回调"""
        self._disconnection_callbacks.append(callback)
    
    async def get_listener_client(self) -> Optional[TelegramClient]:
        """
        获取监听客户端（长连接）
        专门用于运行事件循环和监听消息
        """
        if not self.listener_connected:
            await self._connect_listener()
        return self.listener_client
    
    async def get_sender_client(self) -> Optional[TelegramClient]:
        """
        获取发送客户端（按需连接）
        专门用于API调用、消息转发、媒体处理
        """
        if not self.sender_connected or not self.sender_client:
            await self._connect_sender()
        return self.sender_client
    
    async def _connect_listener(self) -> bool:
        """连接采集Session - 用于长期监听"""
        try:
            session = await self.config_manager.get_config("telegram.listener_session")
            api_id = await self.config_manager.get_config("telegram.api_id")
            api_hash = await self.config_manager.get_config("telegram.api_hash")
            
            if not all([session, api_id, api_hash]):
                logger.warning("采集Session配置不完整，无法连接监听客户端")
                return False
            
            # 验证Session格式
            if len(session) < 100 or not session.startswith('1'):
                logger.warning("采集Session格式无效")
                return False
            
            logger.info(f"连接采集Session，API ID: {api_id}")
            
            # 创建监听客户端
            self.listener_client = TelegramClient(
                StringSession(session),
                int(api_id),
                api_hash,
                connection_retries=5,
                retry_delay=3,
                auto_reconnect=True
            )
            
            # 启动客户端
            await self.listener_client.start()
            
            # 验证连接
            me = await self.listener_client.get_me()
            logger.info(f"✅ 采集客户端连接成功，用户: {me.first_name} (@{me.username})")
            
            self.listener_connected = True
            
            # 执行连接回调
            for callback in self._listener_callbacks:
                try:
                    await callback(self.listener_client)
                except Exception as e:
                    logger.error(f"监听客户端连接回调失败: {e}")
            
            return True
            
        except (AuthKeyUnregisteredError, SessionRevokedError) as e:
            logger.error(f"采集Session已失效: {e}")
            # 清除失效的Session
            await self.config_manager.set_config("telegram.listener_session", "")
            return False
            
        except Exception as e:
            logger.error(f"连接采集Session失败: {e}")
            self.listener_client = None
            self.listener_connected = False
            return False
    
    async def _connect_sender(self) -> bool:
        """连接发送Session - 用于API调用"""
        try:
            session = await self.config_manager.get_config("telegram.sender_session")
            api_id = await self.config_manager.get_config("telegram.api_id")
            api_hash = await self.config_manager.get_config("telegram.api_hash")
            
            if not all([session, api_id, api_hash]):
                logger.warning("发送Session配置不完整，无法连接发送客户端")
                return False
            
            # 验证Session格式
            if len(session) < 100 or not session.startswith('1'):
                logger.warning("发送Session格式无效")
                return False
            
            logger.info(f"连接发送Session，API ID: {api_id}")
            
            # 创建发送客户端
            self.sender_client = TelegramClient(
                StringSession(session),
                int(api_id),
                api_hash,
                connection_retries=5,
                retry_delay=3,
                auto_reconnect=True
            )
            
            # 启动客户端
            await self.sender_client.start()
            
            # 验证连接
            me = await self.sender_client.get_me()
            logger.info(f"✅ 发送客户端连接成功，用户: {me.first_name} (@{me.username})")
            
            self.sender_connected = True
            
            # 执行连接回调
            for callback in self._sender_callbacks:
                try:
                    await callback(self.sender_client)
                except Exception as e:
                    logger.error(f"发送客户端连接回调失败: {e}")
            
            return True
            
        except (AuthKeyUnregisteredError, SessionRevokedError) as e:
            logger.error(f"发送Session已失效: {e}")
            # 清除失效的Session
            await self.config_manager.set_config("telegram.sender_session", "")
            return False
            
        except Exception as e:
            logger.error(f"连接发送Session失败: {e}")
            self.sender_client = None
            self.sender_connected = False
            return False
    
    async def is_listener_connected(self) -> bool:
        """检查监听客户端连接状态"""
        if not self.listener_client or not self.listener_connected:
            return False
        
        try:
            await self.listener_client.get_me()
            return True
        except Exception:
            self.listener_connected = False
            return False
    
    async def is_sender_connected(self) -> bool:
        """检查发送客户端连接状态"""
        if not self.sender_client or not self.sender_connected:
            return False
        
        try:
            await self.sender_client.get_me()
            return True
        except Exception:
            self.sender_connected = False
            return False
    
    async def ensure_listener_connected(self) -> bool:
        """确保监听客户端已连接"""
        if await self.is_listener_connected():
            return True
        
        logger.info("监听客户端未连接，尝试重新连接...")
        return await self._connect_listener()
    
    async def ensure_sender_connected(self) -> bool:
        """确保发送客户端已连接"""
        if await self.is_sender_connected():
            return True
        
        logger.info("发送客户端未连接，尝试重新连接...")
        return await self._connect_sender()
    
    async def disconnect_all(self):
        """断开所有连接"""
        disconnection_tasks = []
        
        # 执行断开连接回调
        for callback in self._disconnection_callbacks:
            try:
                await callback()
            except Exception as e:
                logger.error(f"断开连接回调失败: {e}")
        
        # 断开监听客户端
        if self.listener_client and self.listener_connected:
            try:
                await self.listener_client.disconnect()
                logger.info("监听客户端已断开连接")
            except Exception as e:
                logger.error(f"断开监听客户端连接时出错: {e}")
            finally:
                self.listener_client = None
                self.listener_connected = False
        
        # 断开发送客户端
        if self.sender_client and self.sender_connected:
            try:
                await self.sender_client.disconnect()
                logger.info("发送客户端已断开连接")
            except Exception as e:
                logger.error(f"断开发送客户端连接时出错: {e}")
            finally:
                self.sender_client = None
                self.sender_connected = False
    
    async def get_connection_status(self) -> dict:
        """获取连接状态"""
        return {
            "listener_connected": self.listener_connected,
            "sender_connected": self.sender_connected,
            "listener_client_available": self.listener_client is not None,
            "sender_client_available": self.sender_client is not None,
            "listener_status": "已连接" if self.listener_connected else "未连接",
            "sender_status": "按需连接" if not self.sender_connected else "已连接",
            "system_operational": self.listener_connected  # 只要Listener连接就可运行
        }
    

# 全局双Session管理器实例
dual_session_manager = TelegramDualSessionManager()