"""
认证和会话管理服务
使用Redis存储会话，JSON存储用户权限
"""
import hashlib
import logging
import secrets
import bcrypt
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import HTTPException

from app.storage.redis_manager import redis_manager
from app.storage.json_store import get_json_admin_store

logger = logging.getLogger(__name__)

class AuthService:
    """认证服务"""
    
    def __init__(self):
        from app.storage.redis_manager import redis_manager
        self.session_store = redis_manager
        self.admin_store = get_json_admin_store()
        self.default_session_expire = 24 * 3600  # 24小时
        # 暴力破解防护配置
        self.max_login_attempts = 5      # 最大尝试次数
        self.lockout_duration = 15 * 60  # 锁定时间（15分钟）
    
    def hash_password(self, password: str) -> str:
        """密码哈希 - 使用bcrypt"""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(self, password: str, hashed_password: str) -> bool:
        """验证密码 - 支持bcrypt和legacy SHA-256"""
        if len(hashed_password) == 64:
            # Legacy SHA-256 hex digest fallback
            return hashlib.sha256(password.encode()).hexdigest() == hashed_password
        try:
            return bcrypt.checkpw(password.encode(), hashed_password.encode())
        except (ValueError, TypeError):
            return False
    
    def generate_token(self) -> str:
        """生成会话token"""
        return secrets.token_urlsafe(32)
    
    async def _is_account_locked(self, identifier: str) -> bool:
        """检查账户是否被锁定 - Redis based"""
        attempts = int(redis_manager.client.get(f"login_attempts:{identifier}") or 0)
        return attempts >= self.max_login_attempts

    async def _record_login_attempt(self, identifier: str, success: bool = False) -> None:
        """记录登录尝试 - Redis based"""
        key = f"login_attempts:{identifier}"
        if success:
            redis_manager.client.delete(key)
            logger.info(f"清除登录失败记录: {identifier}")
            return

        current = redis_manager.client.incr(key)
        redis_manager.client.expire(key, self.lockout_duration)

        logger.warning(f"记录登录失败尝试: {identifier} ({current}/{self.max_login_attempts})")
        if current >= self.max_login_attempts:
            logger.warning(f"账户被锁定: {identifier} (连续{current}次失败尝试，锁定{self.lockout_duration//60}分钟)")

    async def get_lockout_info(self, identifier: str) -> dict:
        """获取账户锁定信息 - Redis based"""
        key = f"login_attempts:{identifier}"
        current_attempts = int(redis_manager.client.get(key) or 0)
        is_locked = current_attempts >= self.max_login_attempts

        lockout_remaining = 0
        if is_locked:
            ttl = redis_manager.client.ttl(key)
            lockout_remaining = max(0, ttl) if ttl > 0 else 0

        return {
            'is_locked': is_locked,
            'lockout_remaining_seconds': lockout_remaining,
            'current_attempts': current_attempts,
            'max_attempts': self.max_login_attempts,
            'remaining_attempts': max(0, self.max_login_attempts - current_attempts)
        }
    
    async def login(self, username: str, password: str, 
                   ip_address: str = None, user_agent: str = None) -> Optional[Dict[str, Any]]:
        """用户登录"""
        try:
            # 使用用户名和IP作为标识符进行暴力破解防护
            identifier = f"{username}:{ip_address or 'unknown'}"
            
            # 检查账户是否被锁定
            if await self._is_account_locked(identifier):
                lockout_info = await self.get_lockout_info(identifier)
                remaining_seconds = lockout_info['lockout_remaining_seconds']
                logger.warning(f"登录被拒绝: 账户已锁定 {username} (剩余{remaining_seconds}秒)")
                raise HTTPException(
                    status_code=429, 
                    detail=f"账户暂时锁定，请{remaining_seconds // 60}分钟后重试"
                )
            
            # 查找用户
            admin = self.admin_store.get_admin_by_username(username)
            if not admin:
                logger.warning(f"登录失败: 用户不存在 {username}")
                logger.info(f"🚀 准备调用 _record_login_attempt: {identifier}")
                await self._record_login_attempt(identifier, success=False)
                logger.info(f"✅ _record_login_attempt 调用完成")
                return None
            
            # 检查用户状态
            if not admin.get('is_active', True):
                logger.warning(f"登录失败: 用户已禁用 {username}")
                await self._record_login_attempt(identifier, success=False)
                return None
            
            # 验证密码
            if not self.verify_password(password, admin['password_hash']):
                logger.warning(f"登录失败: 密码错误 {username}")
                await self._record_login_attempt(identifier, success=False)
                return None
            
            # 生成会话token
            token = self.generate_token()
            
            # 保存admin_id，因为save_admin会删除id字段
            admin_id = admin['id']
            
            # 创建会话数据
            session_data = {
                'admin_id': admin_id,
                'username': admin['username'],
                'ip_address': ip_address,
                'user_agent': user_agent,
                'login_time': datetime.now().isoformat()
            }
            
            # 保存会话到Redis
            if not self.session_store.save_session(token, session_data, self.default_session_expire):
                logger.error(f"保存会话失败: {username}")
                return None
            
            # 更新用户最后登录时间
            admin['last_login'] = datetime.now().isoformat()
            self.admin_store.save_admin(admin)
            
            # 记录登录成功，清除失败记录
            await self._record_login_attempt(identifier, success=True)
            
            logger.info(f"用户登录成功: {username}")
            
            # 返回登录结果
            return {
                'token': token,
                'admin_id': admin_id,
                'username': admin['username'],
                'expires_at': (datetime.now() + timedelta(seconds=self.default_session_expire)).isoformat()
            }
            
        except HTTPException:
            # 重新抛出HTTP异常（如账户锁定）
            raise
        except Exception as e:
            logger.error(f"登录异常 {username}: {e}")
            return None
    
    async def logout(self, token: str) -> bool:
        """用户登出"""
        try:
            # 获取会话信息用于日志
            session_data = self.session_store.get_session(token)
            username = session_data.get('username', 'unknown') if session_data else 'unknown'
            
            # 删除会话
            if self.session_store.delete_session(token):
                logger.info(f"用户登出成功: {username}")
                return True
            else:
                logger.warning(f"登出失败，会话不存在: {token[:8]}...")
                return False
                
        except Exception as e:
            logger.error(f"登出异常: {e}")
            return False
    
    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """获取当前用户信息"""
        try:
            # 从Redis获取会话
            session_data = self.session_store.get_session(token)
            if not session_data:
                return None
            
            admin_id = session_data.get('admin_id')
            if not admin_id:
                return None
            
            # 从JSON存储获取完整用户信息
            admin = self.admin_store.get_admin_by_id(admin_id)
            if not admin or not admin.get('is_active', True):
                # 用户不存在或已禁用，清除会话
                self.session_store.delete_session(token)
                return None
            
            # 合并会话和用户信息
            return {
                'id': admin['id'],
                'username': admin['username'],
                'is_active': admin.get('is_active', True),
                'is_super_admin': admin.get('is_super_admin', admin['id'] == 1),  # ID为1的管理员默认为超级管理员
                'last_login': admin.get('last_login'),
                'created_at': admin.get('created_at'),
                'session_info': {
                    'ip_address': session_data.get('ip_address'),
                    'user_agent': session_data.get('user_agent'),
                    'login_time': session_data.get('login_time')
                }
            }
            
        except Exception as e:
            logger.error(f"获取用户信息异常: {e}")
            return None
    
    
    async def create_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """创建用户"""
        try:
            # 检查用户名是否已存在
            existing_user = self.admin_store.get_admin_by_username(username)
            if existing_user:
                logger.warning(f"创建用户失败: 用户名已存在 {username}")
                return None

            # 创建用户数据
            admin_data = {
                'username': username,
                'password_hash': self.hash_password(password),
                'is_active': True,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # 保存用户
            if self.admin_store.save_admin(admin_data):
                logger.info(f"用户创建成功: {username}")
                
                # 重新获取用户（包含ID）
                return self.admin_store.get_admin_by_username(username)
            else:
                logger.error(f"用户创建失败: {username}")
                return None
                
        except Exception as e:
            logger.error(f"创建用户异常 {username}: {e}")
            return None
    
    async def update_password(self, token: str, old_password: str, 
                            new_password: str) -> bool:
        """更新用户密码"""
        try:
            # 获取当前用户
            user = await self.get_current_user(token)
            if not user:
                return False
            
            # 获取完整用户信息
            admin = self.admin_store.get_admin_by_id(user['id'])
            if not admin:
                return False
            
            # 验证旧密码
            if not self.verify_password(old_password, admin['password_hash']):
                logger.warning(f"修改密码失败: 旧密码错误 {user['username']}")
                return False
            
            # 更新密码
            admin['password_hash'] = self.hash_password(new_password)
            admin['updated_at'] = datetime.now().isoformat()
            
            if self.admin_store.save_admin(admin):
                logger.info(f"密码更新成功: {user['username']}")
                return True
            else:
                logger.error(f"密码更新失败: {user['username']}")
                return False
                
        except Exception as e:
            logger.error(f"更新密码异常: {e}")
            return False
    
    
    async def get_active_sessions(self) -> List[Dict[str, Any]]:
        """获取活跃会话列表"""
        try:
            active_tokens = self.session_store.get_active_sessions()
            sessions = []
            
            for token in active_tokens:
                session_data = self.session_store.get_session(token)
                if session_data:
                    sessions.append({
                        'token': token[:8] + '...',  # 只显示token前8位
                        'username': session_data.get('username'),
                        'ip_address': session_data.get('ip_address'),
                        'login_time': session_data.get('login_time')
                    })
            
            return sessions
            
        except Exception as e:
            logger.error(f"获取活跃会话异常: {e}")
            return []
    
    async def revoke_session(self, token: str) -> bool:
        """撤销指定会话"""
        try:
            return self.session_store.delete_session(token)
        except Exception as e:
            logger.error(f"撤销会话异常: {e}")
            return False
    
    async def cleanup_expired_sessions(self):
        """清理过期会话（由Redis自动TTL处理，这里主要用于日志）"""
        try:
            active_count = len(self.session_store.get_active_sessions())
            logger.debug(f"当前活跃会话数: {active_count}")
        except Exception as e:
            logger.error(f"清理会话异常: {e}")

# 全局实例
auth_service = None

def init_auth_service():
    """初始化认证服务 - 单例模式，避免重复初始化"""
    global auth_service
    
    # 检查是否已经初始化
    if auth_service is not None:
        logger.debug("认证服务已经初始化，跳过重复初始化")
        return True
    
    try:
        auth_service = AuthService()
        logger.info("认证服务初始化成功")
        return True
    except Exception as e:
        logger.error(f"认证服务初始化失败: {e}")
        return False

def get_auth_service() -> AuthService:
    """获取认证服务实例"""
    if auth_service is None:
        raise RuntimeError("认证服务未初始化")
    return auth_service


# FastAPI依赖注入函数
async def verify_sender_auth(authorization: Optional[str] = None) -> Dict[str, Any]:
    """验证发送者认证的FastAPI依赖"""
    from fastapi import HTTPException, Header
    
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少认证令牌")
    
    # 提取Bearer令牌
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization
    
    auth_service = get_auth_service()
    user = await auth_service.get_current_user(token)
    
    if not user:
        raise HTTPException(status_code=401, detail="无效的认证令牌")
    
    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "permissions": user.get("permissions", []),
        "token": token
    }