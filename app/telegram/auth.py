"""
Telethon 认证管理器
支持 Web 界面的登录流程
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.tl.functions.auth import ResendCodeRequest

logger = logging.getLogger(__name__)

class TelethonAuthManager:
    """Telethon 认证管理器"""
    
    def __init__(self):
        self.client = None
        self.auth_state = "idle"  # idle, phone_sent, code_sent, password_needed, authorized
        self.auth_data = {}
    
    async def create_client(self, api_id: int, api_hash: str, phone: str) -> bool:
        """创建客户端"""
        try:
            self.client = TelegramClient(
                f'sessions/{phone}',
                api_id,
                api_hash
            )
            
            await self.client.connect()
            
            if await self.client.is_user_authorized():
                self.auth_state = "authorized"
                logger.info("客户端已授权")
                return True
            else:
                self.auth_state = "idle"
                self.auth_data = {
                    "api_id": api_id,
                    "api_hash": api_hash,
                    "phone": phone
                }
                logger.info("需要登录认证")
                return False
                
        except Exception as e:
            logger.error(f"创建客户端失败: {e}")
            return False
    
    async def send_code(self) -> Dict[str, Any]:
        """发送验证码"""
        try:
            if not self.client:
                return {"success": False, "error": "客户端未初始化"}
            
            await self.client.send_code_request(self.auth_data["phone"])
            self.auth_state = "phone_sent"
            
            return {
                "success": True,
                "message": "验证码已发送",
                "state": self.auth_state
            }
            
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def verify_code(self, code: str) -> Dict[str, Any]:
        """验证验证码"""
        try:
            if not self.client or self.auth_state != "phone_sent":
                return {"success": False, "error": "状态错误"}
            
            await self.client.sign_in(self.auth_data["phone"], code)
            self.auth_state = "authorized"
            
            return {
                "success": True,
                "message": "登录成功",
                "state": self.auth_state
            }
            
        except PhoneCodeInvalidError:
            return {"success": False, "error": "验证码错误"}
        except SessionPasswordNeededError:
            self.auth_state = "password_needed"
            return {
                "success": False,
                "error": "需要两步验证密码",
                "state": self.auth_state
            }
        except Exception as e:
            logger.error(f"验证码验证失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def verify_password(self, password: str) -> Dict[str, Any]:
        """验证两步验证密码"""
        try:
            if not self.client or self.auth_state != "password_needed":
                return {"success": False, "error": "状态错误"}
            
            await self.client.sign_in(password=password)
            self.auth_state = "authorized"
            
            return {
                "success": True,
                "message": "两步验证成功",
                "state": self.auth_state
            }
            
        except Exception as e:
            logger.error(f"两步验证失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def resend_code(self) -> Dict[str, Any]:
        """重新发送验证码"""
        try:
            if not self.client or self.auth_state != "phone_sent":
                return {"success": False, "error": "状态错误"}
            
            await self.client(ResendCodeRequest(self.auth_data["phone"]))
            
            return {
                "success": True,
                "message": "验证码已重新发送",
                "state": self.auth_state
            }
            
        except Exception as e:
            logger.error(f"重新发送验证码失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_auth_status(self) -> Dict[str, Any]:
        """获取认证状态"""
        return {
            "state": self.auth_state,
            "authorized": self.auth_state == "authorized",
            "data": self.auth_data if self.auth_state != "authorized" else {}
        }
    
    async def disconnect(self):
        """断开连接"""
        if self.client:
            await self.client.disconnect()
            self.client = None
            self.auth_state = "idle"
            self.auth_data = {}

# 全局认证管理器实例
auth_manager = TelethonAuthManager() 