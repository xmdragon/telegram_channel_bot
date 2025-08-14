"""
认证和会话管理服务
使用Redis存储会话，JSON存储用户权限
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from app.storage.redis_store import get_redis_session_store
from app.storage.json_store import get_json_admin_store

logger = logging.getLogger(__name__)

class AuthService:
    """认证服务"""
    
    def __init__(self):
        self.session_store = get_redis_session_store()
        self.admin_store = get_json_admin_store()
        self.default_session_expire = 24 * 3600  # 24小时
    
    def hash_password(self, password: str) -> str:
        """密码哈希"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.hash_password(password) == hashed_password
    
    def generate_token(self) -> str:
        """生成会话token"""
        return secrets.token_urlsafe(32)
    
    async def login(self, username: str, password: str, 
                   ip_address: str = None, user_agent: str = None) -> Optional[Dict[str, Any]]:
        """用户登录"""
        try:
            # 查找用户
            admin = self.admin_store.get_admin_by_username(username)
            if not admin:
                logger.warning(f"登录失败: 用户不存在 {username}")
                return None
            
            # 检查用户状态
            if not admin.get('is_active', True):
                logger.warning(f"登录失败: 用户已禁用 {username}")
                return None
            
            # 验证密码
            if not self.verify_password(password, admin['password_hash']):
                logger.warning(f"登录失败: 密码错误 {username}")
                return None
            
            # 生成会话token
            token = self.generate_token()
            
            # 保存admin_id，因为save_admin会删除id字段
            admin_id = admin['id']
            
            # 创建会话数据
            session_data = {
                'admin_id': admin_id,
                'username': admin['username'],
                'is_super_admin': admin.get('is_super_admin', False),
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
            
            logger.info(f"用户登录成功: {username}")
            
            # 返回登录结果
            return {
                'token': token,
                'admin_id': admin_id,
                'username': admin['username'],
                'is_super_admin': admin.get('is_super_admin', False),
                'expires_at': (datetime.now() + timedelta(seconds=self.default_session_expire)).isoformat()
            }
            
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
                'is_super_admin': admin.get('is_super_admin', False),
                'is_active': admin.get('is_active', True),
                'last_login': admin.get('last_login'),
                'session_info': {
                    'ip_address': session_data.get('ip_address'),
                    'user_agent': session_data.get('user_agent'),
                    'login_time': session_data.get('login_time')
                }
            }
            
        except Exception as e:
            logger.error(f"获取用户信息异常: {e}")
            return None
    
    async def check_permission(self, token: str, permission_name: str) -> bool:
        """检查用户权限"""
        try:
            # 获取当前用户
            user = await self.get_current_user(token)
            if not user:
                return False
            
            # 超级管理员拥有所有权限
            if user.get('is_super_admin'):
                return True
            
            # 检查具体权限
            return self.admin_store.has_permission(user['id'], permission_name)
            
        except Exception as e:
            logger.error(f"检查权限异常: {e}")
            return False
    
    async def get_user_permissions(self, token: str) -> List[str]:
        """获取用户权限列表"""
        try:
            user = await self.get_current_user(token)
            if not user:
                return []
            
            # 超级管理员返回所有权限
            if user.get('is_super_admin'):
                all_permissions = self.admin_store.get_all_permissions()
                return [perm['name'] for perm in all_permissions]
            
            # 普通用户返回已分配权限
            return self.admin_store.get_admin_permissions(user['id'])
            
        except Exception as e:
            logger.error(f"获取用户权限异常: {e}")
            return []
    
    async def create_user(self, username: str, password: str, 
                         is_super_admin: bool = False) -> Optional[Dict[str, Any]]:
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
                'is_super_admin': is_super_admin,
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
    
    async def set_user_permissions(self, admin_id: int, permission_names: List[str]) -> bool:
        """设置用户权限"""
        try:
            # 检查用户是否存在
            admin = self.admin_store.get_admin_by_id(admin_id)
            if not admin:
                logger.warning(f"设置权限失败: 用户不存在 {admin_id}")
                return False
            
            # 设置权限
            if self.admin_store.set_admin_permissions(admin_id, permission_names):
                logger.info(f"权限设置成功: 用户 {admin_id}, 权限: {permission_names}")
                return True
            else:
                logger.error(f"权限设置失败: 用户 {admin_id}")
                return False
                
        except Exception as e:
            logger.error(f"设置权限异常: {e}")
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
    """初始化认证服务"""
    global auth_service
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