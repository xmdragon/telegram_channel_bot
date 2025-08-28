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
    
    async def is_authorized(self) -> bool:
        """检查是否已认证 - 任意Session可用即可"""
        return (await dual_session_manager.is_listener_connected() or 
                await dual_session_manager.is_sender_connected())
    
    async def get_auth_state(self) -> str:
        """获取认证状态"""
        if await self.is_authorized():
            return "authorized"
        return "idle"
    
    async def get_auth_status(self) -> dict:
        """获取认证状态详情 - 兼容性方法，专注listener认证诊断"""
        from app.services.config_manager import ConfigManager
        
        try:
            config_manager = ConfigManager()
            
            # === 第一层：配置诊断 ===
            listener_session = await config_manager.get_config("telegram.listener_session")
            listener_api_id = await config_manager.get_config("telegram.listener_api_id") 
            listener_api_hash = await config_manager.get_config("telegram.listener_api_hash")
            
            # 构建配置状态报告
            config_issues = []
            if not listener_session:
                config_issues.append("listener_session缺失")
            elif len(listener_session) < 100:
                config_issues.append("listener_session格式无效")
            
            if not listener_api_id:
                config_issues.append("listener_api_id缺失")
            if not listener_api_hash:
                config_issues.append("listener_api_hash缺失")
            
            # === 第二层：连接诊断 ===
            connection_status = await dual_session_manager.get_connection_status()
            listener_connected = connection_status.get("listener_connected", False)
            
            # 判断认证状态
            config_ok = len(config_issues) == 0
            listener_authorized = config_ok  # 有配置就视为已认证，无需实时连接
            
            # === 第三层：诊断报告生成 ===
            if config_ok:
                config_status = "✅ Listener配置完整"
                solution = "配置正常，如连接失败请检查网络或Session有效性"
            else:
                config_status = f"❌ 配置问题: {', '.join(config_issues)}"
                solution = "访问 http://localhost:8080/static/telegram-auth.html 完成Telegram认证"
            
            connection_detail = "✅ 已连接" if listener_connected else "❌ 未连接"
            
            return {
                "success": True,
                "authorized": listener_authorized,  # collector检查的关键字段
                "authenticated": listener_authorized,  # 向后兼容
                "listener_connected": listener_connected,
                "sender_connected": connection_status.get("sender_connected", False),
                "status": "authorized" if listener_authorized else "idle",
                # 诊断信息
                "config_status": config_status,
                "connection_status": f"Listener连接: {connection_detail}",
                "config_issues": config_issues,
                "solution": solution,
                "session_length": len(listener_session) if listener_session else 0,
                "api_configured": bool(listener_api_id and listener_api_hash)
            }
            
        except Exception as e:
            logger.error(f"获取认证状态失败: {e}")
            return {
                "success": False,
                "authorized": False,
                "authenticated": False,
                "listener_connected": False,
                "sender_connected": False,
                "status": "error",
                "config_status": "❌ 诊断失败",
                "connection_status": "❌ 检查失败", 
                "error_detail": str(e),
                "solution": "检查系统配置和存储服务状态"
            }

# 兼容性实例
auth_manager = AuthManagerCompat()