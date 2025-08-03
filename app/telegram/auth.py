"""
Telethon 认证管理器
支持 Web 界面的登录流程
"""
import asyncio
import logging
import os
from typing import Optional, Dict, Any
from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.tl.functions.auth import ResendCodeRequest

from app.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class TelethonAuthManager:
    """Telethon 认证管理器"""
    
    def __init__(self):
        self.client = None
        self.auth_state = "idle"  # idle, phone_sent, code_sent, password_needed, authorized
        self.auth_data = {}
        self.config_manager = ConfigManager()
    
    async def load_saved_auth(self) -> bool:
        """从数据库加载已保存的认证信息"""
        try:
            api_id = await self.config_manager.get_config("telegram.api_id")
            api_hash = await self.config_manager.get_config("telegram.api_hash")
            session_name = await self.config_manager.get_config("telegram.session_name")
            
            if api_id and api_hash and session_name:
                logger.info("发现已保存的认证信息，尝试自动连接")
                return await self.create_client(api_id, api_hash, session_name)
            
            return False
            
        except Exception as e:
            logger.error(f"加载已保存认证信息失败: {e}")
            return False
    
    async def create_client(self, api_id: int, api_hash: str, session_name: str) -> bool:
        """创建客户端"""
        try:
            # 确保sessions目录存在
            os.makedirs('sessions', exist_ok=True)
            
            # 处理session文件名（如果已包含.session后缀则不重复添加）
            if session_name.endswith('.session'):
                session_filename = session_name
                base_session_name = session_name[:-8]  # 移除.session后缀
            else:
                session_filename = f'{session_name}.session'
                base_session_name = session_name
            
            session_path = f'sessions/{session_filename}'
            
            self.client = TelegramClient(
                session_path,
                api_id,
                api_hash
            )
            
            await self.client.connect()
            
            if await self.client.is_user_authorized():
                self.auth_state = "authorized"
                logger.info("客户端已授权")
                # 保存认证信息到数据库
                await self._save_auth_config(api_id, api_hash, base_session_name)
                return True
            else:
                self.auth_state = "idle"
                self.auth_data = {
                    "api_id": api_id,
                    "api_hash": api_hash,
                    "session_name": base_session_name
                }
                logger.info("需要登录认证")
                return False
                
        except Exception as e:
            logger.error(f"创建客户端失败: {e}")
            return False
    
    async def _save_auth_config(self, api_id: int, api_hash: str, session_name: str):
        """保存认证配置到数据库"""
        try:
            # 保存api_id
            await self.config_manager.set_config(
                "telegram.api_id", 
                api_id, 
                "Telegram API ID", 
                "integer"
            )
            
            # 保存api_hash
            await self.config_manager.set_config(
                "telegram.api_hash", 
                api_hash, 
                "Telegram API Hash", 
                "string"
            )
            
            # 保存session_name (包含.session后缀)
            await self.config_manager.set_config(
                "telegram.session_name", 
                f"{session_name}.session", 
                "Telegram Session File Name", 
                "string"
            )
            
            logger.info(f"认证配置已保存到数据库: api_id={api_id}, session_name={session_name}")
            
        except Exception as e:
            logger.error(f"保存认证配置失败: {e}")
    
    async def send_code(self, phone: str) -> Dict[str, Any]:
        """发送验证码"""
        try:
            if not self.client:
                return {"success": False, "error": "客户端未初始化"}
            
            self.auth_data["phone"] = phone
            await self.client.send_code_request(phone)
            self.auth_state = "code_sent"
            
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
            if not self.client or self.auth_state != "code_sent":
                return {"success": False, "error": "状态错误"}
            
            await self.client.sign_in(self.auth_data["phone"], code)
            self.auth_state = "authorized"
            
            # 认证成功后保存配置
            await self._save_auth_config(
                self.auth_data["api_id"],
                self.auth_data["api_hash"],
                self.auth_data["session_name"]
            )
            
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
            
            # 认证成功后保存配置
            await self._save_auth_config(
                self.auth_data["api_id"],
                self.auth_data["api_hash"],
                self.auth_data["session_name"]
            )
            
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
            if not self.client or self.auth_state != "code_sent":
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
    
    async def clear_auth_data(self):
        """清除认证数据和session文件"""
        try:
            # 先断开连接
            await self.disconnect()
            
            # 从数据库获取session文件名
            session_name = await self.config_manager.get_config("telegram.session_name")
            
            # 删除session文件
            if session_name:
                session_path = f'sessions/{session_name}'
                if os.path.exists(session_path):
                    os.remove(session_path)
                    logger.info(f"已删除session文件: {session_path}")
            
            # 清除数据库中的认证配置
            await self.config_manager.delete_config("telegram.api_id")
            await self.config_manager.delete_config("telegram.api_hash") 
            await self.config_manager.delete_config("telegram.session_name")
            
            logger.info("认证数据已清除")
            return {"success": True, "message": "认证数据已清除"}
            
        except Exception as e:
            logger.error(f"清除认证数据失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_saved_auth_info(self):
        """获取已保存的认证信息"""
        try:
            api_id = await self.config_manager.get_config("telegram.api_id")
            api_hash = await self.config_manager.get_config("telegram.api_hash")
            session_name = await self.config_manager.get_config("telegram.session_name")
            
            return {
                "has_saved_auth": bool(api_id and api_hash and session_name),
                "api_id": api_id if api_id else "",
                "api_hash": api_hash if api_hash else "",
                "session_name": session_name if session_name else ""
            }
        except Exception as e:
            logger.error(f"获取认证信息失败: {e}")
            return {
                "has_saved_auth": False,
                "api_id": "",
                "api_hash": "", 
                "session_name": ""
            }

# 全局认证管理器实例
auth_manager = TelethonAuthManager() 