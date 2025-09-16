"""
双Session认证管理器 - 支持并行认证流程
独立管理两个Session的认证状态和流程
避免状态混乱，实现真正的并行认证
"""
import logging
from typing import Optional, Dict, Any
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneCodeInvalidError, SessionPasswordNeededError, 
    AuthKeyUnregisteredError, SessionRevokedError, FloodWaitError
)

from app.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class SessionAuthState:
    """单个Session的认证状态"""
    
    def __init__(self, session_type: str):
        self.session_type = session_type  # 'listener' 或 'sender'
        self.state = "idle"  # idle, phone_sent, code_sent, password_needed, authorized
        self.client: Optional[TelegramClient] = None
        self.auth_data: Dict[str, Any] = {}
        self.error_message: Optional[str] = None
        
    def reset(self):
        """重置认证状态"""
        self.state = "idle"
        self.client = None
        self.auth_data = {}
        self.error_message = None

class DualSessionAuthManager:
    """双Session认证管理器 - 清晰分离"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        
        # 独立的Session认证状态
        self.listener_auth = SessionAuthState("listener")
        self.sender_auth = SessionAuthState("sender")
        
        # 共享的API凭据
        self.shared_api_id: Optional[int] = None
        self.shared_api_hash: Optional[str] = None
    
    def get_session_auth(self, session_type: str) -> SessionAuthState:
        """获取指定Session的认证状态"""
        if session_type == "listener":
            return self.listener_auth
        elif session_type == "sender":
            return self.sender_auth
        else:
            raise ValueError(f"无效的Session类型: {session_type}")
    
    async def load_api_config_from_system(self):
        """从系统配置加载API配置"""
        try:
            api_id_str = await self.config_manager.get_config("telegram.api_id")
            api_hash = await self.config_manager.get_config("telegram.api_hash")
            
            if api_id_str and api_hash:
                self.shared_api_id = int(api_id_str)
                self.shared_api_hash = api_hash
                logger.info(f"✅ 从系统配置加载API配置，API ID: {self.shared_api_id}")
                return True
            else:
                logger.warning("⚠️ 系统配置中未找到完整的API配置")
                return False
        except Exception as e:
            logger.error(f"❌ 从系统配置加载API配置失败: {e}")
            return False
    
    async def set_shared_api_config(self, api_id: int, api_hash: str):
        """设置共享的API配置（兼容性方法，建议使用系统配置）"""
        self.shared_api_id = api_id
        self.shared_api_hash = api_hash
        logger.info(f"✅ 已设置共享API配置，API ID: {api_id}")
        
        # 同时保存到系统配置
        await self.config_manager.set_config("telegram.api_id", str(api_id))
        await self.config_manager.set_config("telegram.api_hash", api_hash)
    
    async def create_session_client(self, session_type: str) -> bool:
        """为指定Session创建客户端"""
        # 如果没有API配置，尝试从系统配置加载
        if not self.shared_api_id or not self.shared_api_hash:
            await self.load_api_config_from_system()
            
        if not self.shared_api_id or not self.shared_api_hash:
            raise ValueError("请先在系统配置中设置API ID和API Hash")
        
        session_auth = self.get_session_auth(session_type)
        
        try:
            # 检查是否已有保存的Session
            session_key = f"telegram.{session_type}_session"
            saved_session = await self.config_manager.get_config(session_key)
            
            if saved_session and len(saved_session) > 100:
                logger.info(f"发现已保存的{session_type}Session，尝试使用")
                # 使用已保存的Session
                session_auth.client = TelegramClient(
                    StringSession(saved_session),
                    self.shared_api_id,
                    self.shared_api_hash,
                    connection_retries=5,
                    retry_delay=3
                )
                
                await session_auth.client.start()
                
                # 检查授权状态
                if await session_auth.client.is_user_authorized():
                    session_auth.state = "authorized"
                    logger.info(f"✅ {session_type}Session已授权")
                    return True
                else:
                    logger.info(f"{session_type}Session需要重新认证")
                    await session_auth.client.disconnect()
                    session_auth.client = None
            
            # 创建新的Session客户端
            session_auth.client = TelegramClient(
                StringSession(),  # 空Session，需要认证
                self.shared_api_id,
                self.shared_api_hash,
                connection_retries=5,
                retry_delay=3
            )
            
            await session_auth.client.connect()
            session_auth.state = "phone_needed"
            session_auth.auth_data = {
                "api_id": self.shared_api_id,
                "api_hash": self.shared_api_hash
            }
            
            logger.info(f"✅ {session_type}Session客户端已创建，等待手机号")
            return True
            
        except Exception as e:
            logger.error(f"创建{session_type}Session客户端失败: {e}")
            session_auth.state = "error"
            session_auth.error_message = str(e)
            return False
    
    async def send_code(self, session_type: str, phone: str) -> Dict[str, Any]:
        """发送验证码"""
        session_auth = self.get_session_auth(session_type)
        
        if not session_auth.client:
            return {"success": False, "error": "客户端未初始化"}
        
        try:
            logger.info(f"为{session_type}Session发送验证码到: {phone}")
            
            # 发送验证码
            result = await session_auth.client.send_code_request(phone)
            session_auth.state = "code_sent"
            session_auth.auth_data["phone"] = phone
            session_auth.auth_data["phone_code_hash"] = result.phone_code_hash
            
            logger.info(f"✅ {session_type}Session验证码已发送")
            
            return {
                "success": True,
                "message": f"{session_type}Session验证码已发送",
                "session_type": session_type
            }
            
        except FloodWaitError as e:
            error_msg = f"发送验证码过于频繁，请等待 {e.seconds} 秒"
            logger.warning(f"{session_type}Session: {error_msg}")
            session_auth.error_message = error_msg
            return {"success": False, "error": error_msg}
            
        except Exception as e:
            error_msg = f"发送验证码失败: {str(e)}"
            logger.error(f"{session_type}Session: {error_msg}")
            session_auth.state = "error"
            session_auth.error_message = error_msg
            return {"success": False, "error": error_msg}
    
    async def verify_code(self, session_type: str, code: str) -> Dict[str, Any]:
        """验证验证码"""
        session_auth = self.get_session_auth(session_type)
        
        if session_auth.state != "code_sent":
            return {"success": False, "error": "状态错误，请重新发送验证码"}
        
        try:
            logger.info(f"验证{session_type}Session验证码")
            
            # 验证验证码
            await session_auth.client.sign_in(
                session_auth.auth_data["phone"], 
                code,
                phone_code_hash=session_auth.auth_data.get("phone_code_hash")
            )
            
            # 检查是否需要两步验证
            if not await session_auth.client.is_user_authorized():
                session_auth.state = "password_needed"
                logger.info(f"{session_type}Session需要两步验证密码")
                return {
                    "success": True,
                    "message": "需要两步验证密码",
                    "session_type": session_type,
                    "next_step": "password"
                }
            else:
                # 认证成功
                return await self._complete_auth(session_type)
                
        except PhoneCodeInvalidError:
            error_msg = "验证码无效，请检查后重试"
            logger.warning(f"{session_type}Session: {error_msg}")
            session_auth.error_message = error_msg
            return {"success": False, "error": error_msg}
            
        except SessionPasswordNeededError:
            session_auth.state = "password_needed"
            logger.info(f"{session_type}Session需要两步验证密码")
            return {
                "success": True,
                "message": "需要两步验证密码",
                "session_type": session_type,
                "next_step": "password"
            }
            
        except Exception as e:
            error_msg = f"验证码验证失败: {str(e)}"
            logger.error(f"{session_type}Session: {error_msg}")
            session_auth.state = "error"
            session_auth.error_message = error_msg
            return {"success": False, "error": error_msg}
    
    async def verify_password(self, session_type: str, password: str) -> Dict[str, Any]:
        """验证两步验证密码"""
        session_auth = self.get_session_auth(session_type)
        
        if session_auth.state != "password_needed":
            return {"success": False, "error": "状态错误"}
        
        try:
            logger.info(f"验证{session_type}Session两步验证密码")
            
            # 验证密码
            await session_auth.client.sign_in(password=password)
            
            # 完成认证
            return await self._complete_auth(session_type)
            
        except Exception as e:
            error_msg = f"密码验证失败: {str(e)}"
            logger.error(f"{session_type}Session: {error_msg}")
            session_auth.error_message = error_msg
            return {"success": False, "error": error_msg}
    
    async def _complete_auth(self, session_type: str) -> Dict[str, Any]:
        """完成认证流程"""
        session_auth = self.get_session_auth(session_type)
        
        try:
            # 获取用户信息
            me = await session_auth.client.get_me()
            logger.info(f"✅ {session_type}Session认证成功: {me.first_name} (@{me.username})")
            
            # 保存Session
            session_string = session_auth.client.session.save()
            await self._save_session_config(session_type, session_string)
            
            session_auth.state = "authorized"
            
            return {
                "success": True,
                "message": f"{session_type}Session认证成功",
                "session_type": session_type,
                "user_info": {
                    "first_name": me.first_name,
                    "username": me.username,
                    "phone": me.phone
                }
            }
            
        except Exception as e:
            error_msg = f"完成认证时出错: {str(e)}"
            logger.error(f"{session_type}Session: {error_msg}")
            session_auth.state = "error"
            session_auth.error_message = error_msg
            return {"success": False, "error": error_msg}
    
    async def _save_session_config(self, session_type: str, session_string: str):
        """保存Session配置"""
        session_key = f"telegram.{session_type}_session"
        
        await self.config_manager.set_config(
            session_key, session_string,
            f"Telegram {session_type.title()} Session", "string"
        )
        
        logger.info(f"✅ {session_type}Session配置已保存")
    
    async def get_session_status(self, session_type: str) -> Dict[str, Any]:
        """获取Session状态"""
        session_auth = self.get_session_auth(session_type)
        
        return {
            "session_type": session_type,
            "state": session_auth.state,
            "error_message": session_auth.error_message,
            "has_client": session_auth.client is not None
        }
    
    async def clear_session(self, session_type: str):
        """清除Session"""
        session_auth = self.get_session_auth(session_type)
        
        # 断开客户端连接
        if session_auth.client:
            try:
                await session_auth.client.disconnect()
            except Exception:
                pass
        
        # 重置状态
        session_auth.reset()
        
        # 清除保存的配置
        session_key = f"telegram.{session_type}_session"
        
        await self.config_manager.delete_config(session_key)
        
        logger.info(f"✅ {session_type}Session已清除")
    
    async def disconnect_all(self):
        """断开所有客户端连接"""
        for session_auth in [self.listener_auth, self.sender_auth]:
            if session_auth.client:
                try:
                    await session_auth.client.disconnect()
                except Exception:
                    pass
                session_auth.client = None

# 全局双Session认证管理器实例
dual_auth_manager = DualSessionAuthManager()