"""
Telethon 认证管理器
支持 Web 界面的登录流程
仅使用 StringSession 方式
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.tl.functions.auth import ResendCodeRequest

from app.services.config_manager import ConfigManager
from app.telegram.process_lock import telegram_lock

logger = logging.getLogger(__name__)

class TelethonAuthManager:
    """Telethon 认证管理器"""
    
    def __init__(self):
        self.client = None
        self.auth_state = "idle"  # idle, phone_sent, code_sent, password_needed, authorized
        self.auth_data = {}
        self.config_manager = ConfigManager()
        self.has_lock = False  # 标记是否持有锁
    
    async def load_saved_auth(self) -> bool:
        """从数据库加载已保存的认证信息（仅支持StringSession）"""
        try:
            api_id = await self.config_manager.get_config("telegram.api_id")
            api_hash = await self.config_manager.get_config("telegram.api_hash")
            session_string = await self.config_manager.get_config("telegram.session")  # 存储StringSession
            
            logger.info(f"从数据库读取的认证信息: api_id={api_id}, api_hash={api_hash[:10] if api_hash else None}..., has_session={bool(session_string)}")
            
            # 仅使用StringSession方式
            if api_id and api_hash and session_string:
                logger.info("发现已保存的StringSession，尝试连接")
                result = await self.create_client_from_string(int(api_id), api_hash, session_string)
                if result:
                    logger.info(f"StringSession连接成功: auth_state={self.auth_state}")
                    return result
                else:
                    logger.warning("StringSession无效或已过期，需要重新认证")
                    # 清除无效的session
                    await self.config_manager.set_config("telegram.session", "", "Telegram Session (StringSession格式)", "string")
            
            logger.info(f"需要进行认证: api_id={bool(api_id)}, api_hash={bool(api_hash)}, has_session={bool(session_string)}")
            return False
            
        except Exception as e:
            logger.error(f"加载认证信息失败: {e}")
            return False
    
    async def create_client(self, api_id: int, api_hash: str) -> bool:
        """创建新的客户端（用于新认证，带进程锁保护）"""
        try:
            # 尝试获取进程锁
            if not await telegram_lock.acquire(timeout=30):
                logger.error("无法获取Telegram进程锁，可能有其他进程正在使用")
                return False
            
            self.has_lock = True
            logger.info("已获取Telegram进程锁")
            
            # 创建新的StringSession客户端
            self.client = TelegramClient(
                StringSession(),  # 使用空的StringSession
                api_id,
                api_hash
            )
            
            # 保存认证信息供后续使用
            self.auth_data = {
                "api_id": api_id,
                "api_hash": api_hash
            }
            
            # 使用start()方法，这是参考实现使用的方式
            logger.info("开始启动Telethon客户端...")
            try:
                # 使用非交互式的start方法
                await self.client.start()
                logger.info("Telethon客户端启动成功")
                
                # 检查授权状态
                is_authorized = await self.client.is_user_authorized()
                logger.info(f"授权状态: {is_authorized}")
                
                if is_authorized:
                    # 不应该发生，因为是新的StringSession
                    self.auth_state = "authorized"
                    logger.warning("新的StringSession已经授权？这不应该发生")
                    return True
                else:
                    self.auth_state = "idle"
                    logger.info("需要登录认证")
                    return False
                    
            except Exception as e:
                logger.error(f"启动客户端失败: {e}")
                return False
                
        except Exception as e:
            logger.error(f"创建客户端失败: {e}")
            # 释放锁
            if self.has_lock:
                await telegram_lock.release()
                self.has_lock = False
            return False
    
    async def create_client_from_string(self, api_id: int, api_hash: str, session_string: str) -> bool:
        """使用StringSession创建客户端（带进程锁保护）"""
        try:
            logger.info("使用StringSession创建客户端...")
            
            # 尝试获取进程锁
            if not await telegram_lock.acquire(timeout=30):
                logger.error("无法获取Telegram进程锁，可能有其他进程正在使用")
                return False
            
            self.has_lock = True
            logger.info("已获取Telegram进程锁")
            
            # 创建StringSession客户端
            self.client = TelegramClient(
                StringSession(session_string),
                api_id,
                api_hash
            )
            
            # 使用start方法完全启动客户端
            await self.client.start()
            logger.info("StringSession客户端启动成功")
            
            # 检查授权状态
            is_authorized = await self.client.is_user_authorized()
            logger.info(f"StringSession授权状态: {is_authorized}")
            
            if is_authorized:
                self.auth_state = "authorized"
                logger.info("StringSession客户端已授权")
                
                # 获取用户信息
                me = await self.client.get_me()
                logger.info(f"登录用户: {me.first_name} (@{me.username})")
                
                # 保存认证信息到数据库
                await self._save_auth_config(api_id, api_hash)
                # 这里已经在 _create_client_with_string_session 方法中保存了
                # 不需要再次保存
                pass
                return True
            else:
                self.auth_state = "idle"
                logger.warning("StringSession未授权")
                await self.client.disconnect()
                self.client = None
                return False
                
        except Exception as e:
            logger.error(f"StringSession创建失败: {e}")
            if self.client:
                await self.client.disconnect()
                self.client = None
            # 释放锁
            if self.has_lock:
                await telegram_lock.release()
                self.has_lock = False
            return False
    
    async def _save_auth_config(self, api_id: int, api_hash: str):
        """保存API认证配置到数据库"""
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
            
            logger.info(f"API配置已保存到数据库: api_id={api_id}")
            
        except Exception as e:
            logger.error(f"保存API配置失败: {e}")
    
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
            
            # 获取StringSession
            session_string = self.client.session.save()
            
            # 保存StringSession到数据库
            await self.config_manager.set_config(
                "telegram.session",
                session_string,
                "Telegram Session (StringSession格式)",
                "string"
            )
            
            # 保存API配置
            await self._save_auth_config(
                self.auth_data["api_id"],
                self.auth_data["api_hash"]
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
            
            # 获取StringSession
            session_string = self.client.session.save()
            
            # 保存StringSession到数据库
            await self.config_manager.set_config(
                "telegram.session",
                session_string,
                "Telegram Session (StringSession格式)",
                "string"
            )
            
            # 保存API配置
            await self._save_auth_config(
                self.auth_data["api_id"],
                self.auth_data["api_hash"]
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
        
        # 释放进程锁
        if self.has_lock:
            await telegram_lock.release()
            self.has_lock = False
            logger.info("已释放Telegram进程锁")
    
    async def clear_auth_data(self):
        """清除认证数据和session文件"""
        try:
            # 先断开连接
            await self.disconnect()
            
            # 从数据库获取session
            session_string = await self.config_manager.get_config("telegram.session")
            
            # 删除session
            if session_string:
                # StringSession不需要删除文件
                logger.info("使用StringSession，无需删除文件")
            
            # 清除数据库中的认证配置
            await self.config_manager.delete_config("telegram.api_id")
            await self.config_manager.delete_config("telegram.api_hash") 
            await self.config_manager.delete_config("telegram.session")
            
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
            session_string = await self.config_manager.get_config("telegram.session")
            
            return {
                "has_saved_auth": bool(api_id and api_hash and session_string),
                "api_id": api_id if api_id else "",
                "api_hash": api_hash if api_hash else "",
                "session": session_string if session_string else ""
            }
        except Exception as e:
            logger.error(f"获取认证信息失败: {e}")
            return {
                "has_saved_auth": False,
                "api_id": "",
                "api_hash": "", 
                "session": ""
            }

# 全局认证管理器实例
auth_manager = TelethonAuthManager() 