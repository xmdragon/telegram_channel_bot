"""
管理员认证API
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime
from typing import Optional, List
import logging
from pydantic import BaseModel

from app.services.auth_service import get_auth_service, AuthService
from app.storage.json_store import get_json_admin_store
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter()

# HTTP Bearer认证
security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str


class AdminResponse(BaseModel):
    """管理员响应"""
    id: int
    username: str
    last_login: Optional[str]
    created_at: Optional[str]


def get_auth() -> AuthService:
    """获取认证服务实例"""
    return get_auth_service()


async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """获取当前登录的管理员"""
    if not credentials:
        return None
    
    token = credentials.credentials
    auth = get_auth()
    
    # 从认证服务获取用户信息
    user = await auth.get_current_user(token)
    return user


async def require_admin(admin: dict = Depends(get_current_admin)) -> dict:
    """要求管理员登录"""
    if not admin:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return admin




@router.post(ROUTES.admin_auth.login)
async def login(
    request: Request,
    login_req: LoginRequest
) -> dict:
    """管理员登录"""
    auth = get_auth()
    
    # 获取客户端信息
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get('user-agent')
    
    # 尝试登录
    try:
        login_result = await auth.login(
            login_req.username, 
            login_req.password,
            ip_address=ip_address,
            user_agent=user_agent
        )
    except HTTPException:
        # 重新抛出暴力破解防护等HTTPException
        raise
    
    if not login_result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    return {
        "success": True,
        "token": login_result['token'],
        "admin": {
            "id": login_result['admin_id'],
            "username": login_result['username']
        }
    }


@router.post(ROUTES.admin_auth.logout)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """管理员登出"""
    if not credentials:
        raise HTTPException(status_code=401, detail="未登录")
    
    auth = get_auth()
    token = credentials.credentials
    
    # 登出
    success = await auth.logout(token)
    
    return {"success": success, "message": "已成功登出"}


@router.get(ROUTES.admin_auth.current)
async def get_current_admin_info(
    admin: dict = Depends(require_admin),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """获取当前登录管理员信息"""
    auth = get_auth()
    token = credentials.credentials
    
    return {
        "id": admin['id'],
        "username": admin['username'],
        "is_super_admin": admin.get('is_super_admin', admin['id'] == 1),  # ID为1的管理员默认为超级管理员
        "last_login": admin.get('last_login'),
        "created_at": admin.get('created_at')
    }


@router.post(ROUTES.admin_auth.change_password)
async def change_password(
    req: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """修改密码"""
    if not credentials:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 检查新密码
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度至少6位")
    
    auth = get_auth()
    token = credentials.credentials
    
    # 更新密码
    success = await auth.update_password(token, req.old_password, req.new_password)
    
    if not success:
        raise HTTPException(status_code=400, detail="原密码错误或更新失败")
    
    return {"success": True, "message": "密码修改成功，请重新登录"}


@router.get(ROUTES.admin_auth.check_auth)
async def check_auth(admin: Optional[dict] = Depends(get_current_admin)) -> dict:
    """检查认证状态"""
    return {
        "authenticated": admin is not None
    }


# ==================== 管理员管理功能 ====================

class CreateAdminRequest(BaseModel):
    """创建管理员请求"""
    username: str
    password: str
    is_super_admin: bool = False


class UpdateAdminRequest(BaseModel):
    """更新管理员请求"""
    is_active: Optional[bool] = None
    is_super_admin: Optional[bool] = None
    password: Optional[str] = None


@router.get(ROUTES.admin_auth.admins)
async def get_admins(
    admin: dict = Depends(require_admin)
) -> dict:
    """获取所有管理员列表"""
    admin_store = get_json_admin_store()
    
    # 获取所有管理员数据
    admins_data = admin_store._load_json(admin_store.ADMIN_FILE)
    
    admin_list = []
    for admin_id, admin_data in admins_data.items():
        admin_list.append({
            "id": int(admin_id),
            "username": admin_data.get('username'),
            "is_active": admin_data.get('is_active', True),
            "is_super_admin": admin_data.get('is_super_admin', int(admin_id) == 1),  # ID为1的管理员默认为超级管理员
            "last_login": admin_data.get('last_login'),
            "created_at": admin_data.get('created_at')
        })
    
    # 按创建时间倒序排列
    admin_list.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    
    return {"success": True, "admins": admin_list}


@router.post(ROUTES.admin_auth.admins)
async def create_admin(
    req: CreateAdminRequest,
    admin: dict = Depends(require_admin)
) -> dict:
    """创建新管理员"""
    auth = get_auth()
    
    # 创建管理员
    new_admin = await auth.create_user(
        username=req.username,
        password=req.password
    )

    if not new_admin:
        raise HTTPException(status_code=400, detail="用户名已存在或创建失败")

    # 设置是否为超级管理员
    if req.is_super_admin:
        admin_store = get_json_admin_store()
        new_admin_data = admin_store.get_admin_by_id(new_admin['id'])
        if new_admin_data:
            new_admin_data['is_super_admin'] = True
            admin_store.save_admin(new_admin_data)
    
    return {
        "success": True,
        "message": "管理员创建成功",
        "admin": {
            "id": new_admin['id'],
            "username": new_admin['username']
        }
    }


@router.put(ROUTES.admin_auth.admin_by_id)
async def update_admin(
    admin_id: int,
    req: UpdateAdminRequest,
    admin: dict = Depends(require_admin)
) -> dict:
    """更新管理员信息"""
    admin_store = get_json_admin_store()
    auth = get_auth()
    
    # 获取要更新的管理员
    target_admin = admin_store.get_admin_by_id(admin_id)
    if not target_admin:
        raise HTTPException(status_code=404, detail="管理员不存在")
    
    # 更新基本信息
    if req.is_active is not None:
        target_admin['is_active'] = req.is_active

    if req.is_super_admin is not None:
        target_admin['is_super_admin'] = req.is_super_admin

    if req.password:
        if len(req.password) < 6:
            raise HTTPException(status_code=400, detail="密码长度至少6位")
        target_admin['password_hash'] = auth.hash_password(req.password)
    
    target_admin['updated_at'] = datetime.now().isoformat()
    
    # 保存管理员更新
    if not admin_store.save_admin(target_admin):
        raise HTTPException(status_code=500, detail="更新管理员信息失败")
    
    return {"success": True, "message": "管理员信息更新成功"}


@router.delete(ROUTES.admin_auth.admin_by_id)
async def delete_admin(
    admin_id: int,
    admin: dict = Depends(require_admin)
) -> dict:
    """删除管理员"""
    # 不允许删除自己
    if admin_id == admin['id']:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    
    admin_store = get_json_admin_store()
    
    # 获取要删除的管理员
    target_admin = admin_store.get_admin_by_id(admin_id)
    if not target_admin:
        raise HTTPException(status_code=404, detail="管理员不存在")
    
    # 从管理员文件中删除
    admins_data = admin_store._load_json(admin_store.ADMIN_FILE)
    if str(admin_id) in admins_data:
        del admins_data[str(admin_id)]
        admin_store._save_json(admin_store.ADMIN_FILE, admins_data)
    
    
    # TODO: 清理相关会话（需要从Redis中清理）
    
    return {"success": True, "message": "管理员删除成功"}






