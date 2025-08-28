"""
兼容性适配器 - 将旧auth_manager调用适配到新的双Session系统
避免大范围代码修改，保持系统稳定运行
"""
import logging
from typing import Optional
from app.telegram.dual_session_manager import dual_session_manager

logger = logging.getLogger(__name__)

class AuthManagerCompat:
    """兼容性适配器 - 模拟旧auth_manager接口"""
    
    def __init__(self):
        pass
    
    async def initialize(self) -> bool:
        """初始化认证管理器 - 兼容性方法"""
        # 双Session管理器无需显式初始化
        return True
        
    async def get_client(self):
        """获取客户端 - 优先返回监听Session"""
        client = await dual_session_manager.get_listener_client()
        if not client:
            # 如果监听Session不可用，尝试发送Session
            client = await dual_session_manager.get_sender_client()
        return client
    
    async def ensure_connected(self) -> bool:
        """确保连接 - 检查任意一个Session可用"""
        return (await dual_session_manager.ensure_listener_connected() or 
                await dual_session_manager.ensure_sender_connected())
    
    def is_authorized(self) -> bool:
        """检查是否已认证 - 任意Session可用即可"""
        return (dual_session_manager.is_listener_authorized() or 
                dual_session_manager.is_sender_authorized())
    
    def get_auth_state(self) -> str:
        """获取认证状态"""
        if self.is_authorized():
            return "authorized"
        return "idle"

# 兼容性实例
auth_manager = AuthManagerCompat()