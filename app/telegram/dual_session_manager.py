"""
双Session管理器 - 优雅解决方案
彻底消除锁需求，实现真正的并发处理
监听Session：长连接，专门用于事件循环
发送Session：按需连接，专门用于API调用
"""
import logging
import asyncio
import time
import os
from typing import Optional, Callable, List, Dict, Any
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, AuthKeyUnregisteredError, SessionRevokedError
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged
from dotenv import load_dotenv

from app.services.config_manager import ConfigManager
from app.services.telegram_config_manager import telegram_config_manager
from app.core.telegram_config import TelegramConfig
from app.utils.error_formatter import TelethonErrorHandler

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)

class TelegramDualSessionManager:
    """双Session管理器 - 消除所有锁需求的核心组件"""
    
    def __init__(self):
        self.listener_client: Optional[TelegramClient] = None
        self.sender_client: Optional[TelegramClient] = None

        self.listener_connected = False
        self.sender_connected = False

        # 添加连接状态缓存，避免频繁网络检查
        self._listener_last_check = 0
        self._sender_last_check = 0
        self._check_interval = 30  # 30秒内不重复检查连接状态

        # 认证信息缓存
        self._auth_info: Dict[str, Any] = {}

        self.config_manager = ConfigManager()

        # 连接回调
        self._listener_callbacks: List[Callable] = []
        self._sender_callbacks: List[Callable] = []
        self._disconnection_callbacks: List[Callable] = []

        # 连接锁 - 防止并发调用创建多余连接
        self._listener_lock: Optional[asyncio.Lock] = None
        self._sender_lock: Optional[asyncio.Lock] = None

        # 获取代理配置
        self._proxy_config = self._get_proxy_config()

        # 错误处理器
        self._error_handler = TelethonErrorHandler(logger)
    
    def _get_proxy_config(self) -> Optional[Dict[str, Any]]:
        """从环境变量获取代理配置"""
        use_proxy = os.getenv('TELEGRAM_USE_PROXY', 'false').lower() == 'true'
        
        if not use_proxy:
            logger.info("Telegram代理未启用")
            return None
        
        proxy_type = os.getenv('TELEGRAM_PROXY_TYPE', 'http')
        proxy_host = os.getenv('TELEGRAM_PROXY_HOST', '127.0.0.1')
        proxy_port = int(os.getenv('TELEGRAM_PROXY_PORT', '10808'))
        
        proxy = {
            'proxy_type': proxy_type,
            'addr': proxy_host,
            'port': proxy_port
        }
        
        # 可选的认证信息
        username = os.getenv('TELEGRAM_PROXY_USERNAME')
        password = os.getenv('TELEGRAM_PROXY_PASSWORD')
        
        if username and password:
            proxy['username'] = username
            proxy['password'] = password
        
        logger.info(f"使用{proxy_type}代理: {proxy_host}:{proxy_port}")
        return proxy
    
    def add_listener_callback(self, callback: Callable):
        """添加监听客户端连接成功回调"""
        self._listener_callbacks.append(callback)
    
    def add_sender_callback(self, callback: Callable):
        """添加发送客户端连接成功回调"""
        self._sender_callbacks.append(callback)
    
    def add_disconnection_callback(self, callback: Callable):
        """添加断开连接回调"""
        self._disconnection_callbacks.append(callback)
    
    def _get_listener_lock(self) -> asyncio.Lock:
        """懒初始化监听客户端连接锁"""
        if self._listener_lock is None:
            self._listener_lock = asyncio.Lock()
        return self._listener_lock

    def _get_sender_lock(self) -> asyncio.Lock:
        """懒初始化发送客户端连接锁"""
        if self._sender_lock is None:
            self._sender_lock = asyncio.Lock()
        return self._sender_lock

    async def get_listener_client(self) -> Optional[TelegramClient]:
        """
        获取监听客户端（长连接）
        专门用于运行事件循环和监听消息
        """
        if not self.listener_connected:
            async with self._get_listener_lock():
                if not self.listener_connected:
                    await self._connect_listener()
        return self.listener_client

    async def get_sender_client(self) -> Optional[TelegramClient]:
        """
        获取发送客户端（按需连接）
        专门用于API调用、消息转发、媒体处理
        """
        if not self.sender_connected or not self.sender_client:
            async with self._get_sender_lock():
                if not self.sender_connected or not self.sender_client:
                    await self._connect_sender()
        return self.sender_client
    
    async def _connect_listener(self) -> bool:
        """连接采集Session - 用于长期监听，增强依赖检查"""
        try:
            # Early stop: 快速检查必要配置
            session = await telegram_config_manager.get_listener_session()
            api_id = await telegram_config_manager.get_api_id()
            api_hash = await telegram_config_manager.get_api_hash()

            if not session or session.strip() == "":
                logger.info("监听Session未配置，跳过连接")
                self.listener_connected = False
                return False

            if not api_id or not api_hash:
                logger.info("API ID或API Hash未配置，跳过连接")
                self.listener_connected = False
                return False

            # 增强配置依赖检查
            config_validation = await self._validate_listener_config()
            if not config_validation["valid"]:
                logger.error(f"采集Session配置验证失败: {config_validation['errors']}")
                
                # 尝试重新加载配置
                logger.info("尝试重新加载配置...")
                if await self._retry_config_load():
                    config_validation = await self._validate_listener_config()
                    if not config_validation["valid"]:
                        logger.error("重新加载配置后验证仍然失败")
                        return False
                else:
                    logger.error("重新加载配置失败")
                    return False
            
            session = config_validation["session"]
            api_id = config_validation["api_id"] 
            api_hash = config_validation["api_hash"]
            
            logger.info(f"连接采集Session，API ID: {api_id}")
            
            # 创建监听客户端（增强连接稳定性）
            self.listener_client = TelegramClient(
                StringSession(session),
                int(api_id),
                api_hash,
                connection=ConnectionTcpAbridged,   # 使用Abridged连接，兼容性更好
                proxy=self._proxy_config,       # 使用代理配置（如果有）
                connection_retries=8,          # 增加重试次数 5->8
                retry_delay=2,                 # 减少重试延迟 3->2
                auto_reconnect=True,
                flood_sleep_threshold=60,      # 60秒flood控制
                request_retries=3,             # API请求重试
                sequential_updates=True        # 顺序更新，提高稳定性
            )
            
            # 启动客户端（带重试机制）
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await self.listener_client.start()
                    break
                except Exception as start_e:
                    if attempt == max_retries - 1:
                        raise start_e
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                    logger.warning(f"监听客户端启动重试 {attempt + 1}/{max_retries}: {start_e}")
            
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
            await telegram_config_manager.update_session("listener", "")
            return False
            
        except Exception as e:
            self._error_handler.handle_error(e, "连接采集Session失败")
            self.listener_client = None
            self.listener_connected = False
            return False
    
    async def _connect_sender(self) -> bool:
        """连接发送Session - 用于API调用，增强依赖检查"""
        try:
            # Early stop: 快速检查必要配置
            session = await telegram_config_manager.get_sender_session()
            api_id = await telegram_config_manager.get_api_id()
            api_hash = await telegram_config_manager.get_api_hash()

            if not session or session.strip() == "":
                logger.info("发送Session未配置，跳过连接")
                self.sender_connected = False
                return False

            if not api_id or not api_hash:
                logger.info("API ID或API Hash未配置，跳过连接")
                self.sender_connected = False
                return False

            # 增强配置依赖检查
            config_validation = await self._validate_sender_config()
            if not config_validation["valid"]:
                logger.error(f"发送Session配置验证失败: {config_validation['errors']}")
                
                # 尝试重新加载配置
                logger.info("尝试重新加载配置...")
                if await self._retry_config_load():
                    config_validation = await self._validate_sender_config()
                    if not config_validation["valid"]:
                        logger.error("重新加载配置后验证仍然失败")
                        return False
                else:
                    logger.error("重新加载配置失败")
                    return False
            
            session = config_validation["session"]
            api_id = config_validation["api_id"]
            api_hash = config_validation["api_hash"]
            
            logger.info(f"连接发送Session，API ID: {api_id}")
            
            # 创建发送客户端（增强连接稳定性）
            self.sender_client = TelegramClient(
                StringSession(session),
                int(api_id),
                api_hash,
                connection=ConnectionTcpAbridged,   # 使用Abridged连接，兼容性更好
                proxy=self._proxy_config,       # 使用代理配置（如果有）
                connection_retries=8,          # 增加重试次数 5->8
                retry_delay=2,                 # 减少重试延迟 3->2
                auto_reconnect=True,
                flood_sleep_threshold=60,      # 60秒flood控制
                request_retries=3,             # API请求重试
                sequential_updates=True        # 顺序更新，提高稳定性
            )
            
            # 启动客户端（带重试机制）
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await self.sender_client.start()
                    break
                except Exception as start_e:
                    if attempt == max_retries - 1:
                        raise start_e
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                    logger.warning(f"发送客户端启动重试 {attempt + 1}/{max_retries}: {start_e}")
            
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
            await telegram_config_manager.update_session("sender", "")
            return False
            
        except Exception as e:
            self._error_handler.handle_error(e, "连接发送Session失败")
            self.sender_client = None
            self.sender_connected = False
            return False
    
    async def is_listener_connected(self) -> bool:
        """检查监听客户端连接状态（带缓存优化）"""
        if not self.listener_client or not self.listener_connected:
            return False
        
        # 使用缓存避免频繁网络检查
        current_time = time.time()
        if current_time - self._listener_last_check < self._check_interval:
            return self.listener_connected
        
        try:
            # 使用简单的连接检查，避免复杂的API调用
            if self.listener_client.is_connected():
                self._listener_last_check = current_time
                return True
            else:
                # 只有在真的断开时才调用get_me确认
                await self.listener_client.get_me()
                self._listener_last_check = current_time
                return True
        except Exception as e:
            # 对于连接检查失败，使用 debug 级别且简化错误信息
            if self._error_handler.is_protocol_error(e):
                logger.debug(f"监听客户端协议错误: {self._error_handler.handle_error(e, '', logging.DEBUG)}")
            else:
                logger.debug(f"监听客户端连接检查失败: {e}")
            self.listener_connected = False
            self._listener_last_check = current_time
            return False
    
    async def is_sender_connected(self) -> bool:
        """检查发送客户端连接状态（带缓存优化）"""
        if not self.sender_client or not self.sender_connected:
            return False
        
        # 使用缓存避免频繁网络检查
        current_time = time.time()
        if current_time - self._sender_last_check < self._check_interval:
            return self.sender_connected
        
        try:
            # 使用简单的连接检查，避免复杂的API调用
            if self.sender_client.is_connected():
                self._sender_last_check = current_time
                return True
            else:
                # 只有在真的断开时才调用get_me确认
                await self.sender_client.get_me()
                self._sender_last_check = current_time
                return True
        except Exception as e:
            # 对于连接检查失败，使用 debug 级别且简化错误信息
            if self._error_handler.is_protocol_error(e):
                logger.debug(f"发送客户端协议错误: {self._error_handler.handle_error(e, '', logging.DEBUG)}")
            else:
                logger.debug(f"发送客户端连接检查失败: {e}")
            self.sender_connected = False
            self._sender_last_check = current_time
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
    
    async def _validate_listener_config(self) -> dict:
        """验证监听客户端配置"""
        errors = []
        session = None
        api_id = None
        api_hash = None
        
        try:
            session = await telegram_config_manager.get_listener_session()
            api_id = await telegram_config_manager.get_api_id()
            api_hash = await telegram_config_manager.get_api_hash()
            
            # 检查配置存在性
            if not session or session.strip() == "":
                errors.append("listener_session配置缺失或为空")
            elif len(session) < 100:
                errors.append("listener_session格式无效（长度不足）")
            elif not session.startswith('1'):
                errors.append("listener_session格式无效（格式错误）")
                
            if not api_id:
                errors.append("api_id配置缺失或为空")
                
            if not api_hash:
                errors.append("api_hash配置缺失或为空")
            elif len(api_hash) != 32:
                errors.append("api_hash格式无效（长度应为32字符）")
                
        except Exception as e:
            errors.append(f"读取配置时发生异常: {e}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "session": session,
            "api_id": api_id,
            "api_hash": api_hash
        }
    
    async def _validate_sender_config(self) -> dict:
        """验证发送客户端配置"""
        errors = []
        session = None
        api_id = None
        api_hash = None
        
        try:
            session = await telegram_config_manager.get_sender_session()
            api_id = await telegram_config_manager.get_api_id()
            api_hash = await telegram_config_manager.get_api_hash()
            
            # 检查配置存在性
            if not session or session.strip() == "":
                errors.append("sender_session配置缺失或为空")
            elif len(session) < 100:
                errors.append("sender_session格式无效（长度不足）")
            elif not session.startswith('1'):
                errors.append("sender_session格式无效（格式错误）")
                
            if not api_id:
                errors.append("api_id配置缺失或为空")
                
            if not api_hash:
                errors.append("api_hash配置缺失或为空")
            elif len(api_hash) != 32:
                errors.append("api_hash格式无效（长度应为32字符）")
                
        except Exception as e:
            errors.append(f"读取配置时发生异常: {e}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "session": session,
            "api_id": api_id,
            "api_hash": api_hash
        }
    
    async def _retry_config_load(self, max_retries: int = 2) -> bool:
        """重试配置加载"""
        try:
            # 尝试重新加载配置管理器
            success = await self.config_manager.force_reload_with_retry(max_retries=max_retries)
            if success:
                logger.info("配置重新加载成功")
                return True
            else:
                logger.error("配置重新加载失败")
                return False
        except Exception as e:
            logger.error(f"重试配置加载时发生异常: {e}")
            return False
    
    async def get_config_diagnostics(self) -> dict:
        """获取配置诊断信息"""
        diagnostics = {
            "listener_config": await self._validate_listener_config(),
            "sender_config": await self._validate_sender_config(),
            "config_manager_healthy": self.config_manager.is_storage_healthy()
        }

        diagnostics["overall_config_valid"] = (
            diagnostics["listener_config"]["valid"] and
            diagnostics["sender_config"]["valid"] and
            diagnostics["config_manager_healthy"]
        )

        return diagnostics

    # ============== 认证相关功能 ==============
    # 用于新的session认证流程

    async def create_auth_client(self, session_type: str) -> Optional[TelegramClient]:
        """创建用于认证的临时客户端"""
        try:
            # 获取API配置
            api_id = await telegram_config_manager.get_api_id()
            api_hash = await telegram_config_manager.get_api_hash()

            if not api_id or not api_hash:
                raise ValueError("请先在「Telegram认证」页面配置 API ID 和 API Hash")

            # 创建临时认证客户端（空session）
            auth_client = TelegramClient(
                StringSession(),  # 使用空的StringSession进行新认证
                int(api_id),
                api_hash,
                proxy=self._proxy_config  # 使用代理配置
            )

            await auth_client.connect()
            logger.info(f"✅ 创建{session_type}认证客户端成功")
            return auth_client

        except Exception as e:
            logger.error(f"❌ 创建{session_type}认证客户端失败: {e}")
            return None

    async def send_auth_code(self, session_type: str, phone: str, client: TelegramClient) -> Dict[str, Any]:
        """发送验证码"""
        try:
            result = await client.send_code_request(phone)
            logger.info(f"✅ {session_type}验证码已发送到 {phone}")
            return {
                "success": True,
                "phone_code_hash": result.phone_code_hash,
                "phone": phone
            }
        except FloodWaitError as e:
            error_msg = f"请求过于频繁，请等待 {e.seconds} 秒后重试"
            logger.warning(f"⚠️ {session_type}发送验证码频率限制: {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"发送验证码失败: {str(e)}"
            logger.error(f"❌ {session_type}发送验证码失败: {e}")
            return {"success": False, "error": error_msg}

    async def verify_auth_code(self, session_type: str, phone: str, code: str,
                               phone_code_hash: str, client: TelegramClient) -> Dict[str, Any]:
        """验证验证码"""
        try:
            from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError

            result = await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)

            # 保存session
            session_string = client.session.save()
            if session_type == "listener":
                await telegram_config_manager.update_session("listener", session_string)
            else:
                await telegram_config_manager.update_session("sender", session_string)

            # 获取用户信息
            me = await client.get_me()

            # 检测Premium状态
            is_premium = getattr(me, 'premium', False)

            # 如果是Sender账号，保存Premium状态到配置
            if session_type == "sender":
                await self.config_manager.set_config('telegram.is_premium', str(is_premium).lower())
                logger.info(f"检测到Sender账号Premium状态: {'是' if is_premium else '否'}")

            user_info = {
                "id": me.id,
                "username": me.username,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "phone": me.phone,
                "is_premium": is_premium
            }

            logger.info(f"✅ {session_type}认证成功: {me.username or me.first_name}")

            return {
                "success": True,
                "user": user_info
            }

        except SessionPasswordNeededError:
            logger.info(f"⚠️ {session_type}需要两步验证密码")
            return {
                "success": False,
                "password_required": True,
                "error": "需要输入两步验证密码"
            }
        except PhoneCodeInvalidError:
            return {"success": False, "error": "验证码无效或已过期"}
        except Exception as e:
            return {"success": False, "error": f"验证失败: {str(e)}"}

    async def verify_auth_password(self, session_type: str, password: str,
                                   client: TelegramClient) -> Dict[str, Any]:
        """验证两步验证密码"""
        try:
            result = await client.sign_in(password=password)

            # 保存session
            session_string = client.session.save()
            if session_type == "listener":
                await telegram_config_manager.update_session("listener", session_string)
            else:
                await telegram_config_manager.update_session("sender", session_string)

            # 获取用户信息
            me = await client.get_me()

            # 检测Premium状态
            is_premium = getattr(me, 'premium', False)

            # 如果是Sender账号，保存Premium状态到配置
            if session_type == "sender":
                await self.config_manager.set_config('telegram.is_premium', str(is_premium).lower())
                logger.info(f"检测到Sender账号Premium状态: {'是' if is_premium else '否'}")

            user_info = {
                "id": me.id,
                "username": me.username,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "phone": me.phone,
                "is_premium": is_premium
            }

            logger.info(f"✅ {session_type}两步验证成功: {me.username or me.first_name}")

            return {
                "success": True,
                "user": user_info
            }
        except Exception as e:
            return {"success": False, "error": f"密码验证失败: {str(e)}"}

    async def clear_session(self, session_type: str) -> Dict[str, Any]:
        """清除指定的session"""
        try:
            if session_type == "listener":
                # 断开连接
                if self.listener_client:
                    await self.listener_client.disconnect()
                    self.listener_client = None
                    self.listener_connected = False

                # 删除配置
                await telegram_config_manager.update_session("listener", "")

            else:  # sender
                # 断开连接
                if self.sender_client:
                    await self.sender_client.disconnect()
                    self.sender_client = None
                    self.sender_connected = False

                # 删除配置
                await telegram_config_manager.update_session("sender", "")

            logger.info(f"✅ {session_type}Session已清除")
            return {"success": True, "message": f"{session_type}Session已清除"}

        except Exception as e:
            error_msg = f"清除Session失败: {str(e)}"
            logger.error(f"❌ 清除{session_type}Session失败: {e}")
            return {"success": False, "error": error_msg}


# 全局双Session管理器实例
dual_session_manager = TelegramDualSessionManager()
