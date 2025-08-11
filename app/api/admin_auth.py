"""
管理员认证API
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timedelta
from typing import Optional, List
import bcrypt
import secrets
import logging
from pydantic import BaseModel

from app.core.database import get_db, Admin, AdminSession, Permission, AdminPermission

logger = logging.getLogger(__name__)
router = APIRouter()

# Token有效期设置
TOKEN_EXPIRE_HOURS = 24
SESSION_EXPIRE_DAYS = 7

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
    is_super_admin: bool
    permissions: List[str]
    last_login: Optional[datetime]
    created_at: datetime


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


async def hash_password(password: str) -> str:
    """密码哈希"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


async def create_session_token(admin_id: int, request: Request, db: AsyncSession) -> str:
    """创建会话token"""
    # 生成随机token
    token = secrets.token_urlsafe(32)
    
    # 创建会话记录
    session = AdminSession(
        admin_id=admin_id,
        token=token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=SESSION_EXPIRE_DAYS),
        is_active=True
    )
    
    db.add(session)
    await db.commit()
    
    return token


async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[Admin]:
    """获取当前登录的管理员"""
    if not credentials:
        return None
    
    token = credentials.credentials
    
    # 查询会话
    result = await db.execute(
        select(AdminSession).where(
            and_(
                AdminSession.token == token,
                AdminSession.is_active == True,
                AdminSession.expires_at > datetime.utcnow()
            )
        )
    )
    session = result.scalars().first()
    
    if not session:
        return None
    
    # 更新最后活动时间
    session.last_activity = datetime.utcnow()
    await db.commit()
    
    # 获取管理员信息
    result = await db.execute(
        select(Admin).where(
            and_(
                Admin.id == session.admin_id,
                Admin.is_active == True
            )
        )
    )
    admin = result.scalars().first()
    
    return admin


async def require_admin(admin: Admin = Depends(get_current_admin)) -> Admin:
    """要求管理员登录"""
    if not admin:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return admin


async def require_super_admin(admin: Admin = Depends(require_admin)) -> Admin:
    """要求超级管理员权限"""
    if not admin.is_super_admin:
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return admin


def check_permission(permission_name: str):
    """检查权限装饰器 - 返回依赖函数"""
    async def permission_checker(
        admin: Admin = Depends(require_admin),
        db: AsyncSession = Depends(get_db)
    ) -> Admin:
        # 超级管理员拥有所有权限
        if admin.is_super_admin:
            return admin
        
        # 检查是否有指定权限
        result = await db.execute(
            select(AdminPermission)
            .join(Permission)
            .where(
                and_(
                    AdminPermission.admin_id == admin.id,
                    Permission.name == permission_name
                )
            )
        )
        
        if not result.scalars().first():
            raise HTTPException(status_code=403, detail=f"缺少权限: {permission_name}")
        
        return admin
    
    return permission_checker


@router.post("/login")
async def login(
    request: Request,
    login_req: LoginRequest,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """管理员登录"""
    # 查找管理员
    result = await db.execute(
        select(Admin).where(Admin.username == login_req.username)
    )
    admin = result.scalars().first()
    
    if not admin or not admin.is_active:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # 验证密码
    if not await verify_password(login_req.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # 创建会话
    token = await create_session_token(admin.id, request, db)
    
    # 更新最后登录时间
    admin.last_login = datetime.utcnow()
    await db.commit()
    
    # 获取权限列表
    permissions = []
    if admin.is_super_admin:
        # 超级管理员拥有所有权限
        result = await db.execute(select(Permission))
        permissions = [p.name for p in result.scalars().all()]
    else:
        # 普通管理员获取分配的权限
        result = await db.execute(
            select(Permission)
            .join(AdminPermission)
            .where(AdminPermission.admin_id == admin.id)
        )
        permissions = [p.name for p in result.scalars().all()]
    
    return {
        "success": True,
        "token": token,
        "admin": {
            "id": admin.id,
            "username": admin.username,
            "is_super_admin": admin.is_super_admin,
            "permissions": permissions
        }
    }


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """管理员登出"""
    if not credentials:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 查找并禁用会话
    result = await db.execute(
        select(AdminSession).where(AdminSession.token == credentials.credentials)
    )
    session = result.scalars().first()
    
    if session:
        session.is_active = False
        await db.commit()
    
    return {"success": True, "message": "已成功登出"}


@router.get("/current")
async def get_current_admin_info(
    admin: Admin = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """获取当前登录管理员信息"""
    # 获取权限列表
    permissions = []
    if admin.is_super_admin:
        result = await db.execute(select(Permission))
        permissions = [p.name for p in result.scalars().all()]
    else:
        result = await db.execute(
            select(Permission)
            .join(AdminPermission)
            .where(AdminPermission.admin_id == admin.id)
        )
        permissions = [p.name for p in result.scalars().all()]
    
    return {
        "id": admin.id,
        "username": admin.username,
        "is_super_admin": admin.is_super_admin,
        "permissions": permissions,
        "last_login": admin.last_login,
        "created_at": admin.created_at
    }


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    admin: Admin = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """修改密码"""
    # 验证旧密码
    if not await verify_password(req.old_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    
    # 检查新密码
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度至少6位")
    
    # 更新密码
    admin.password_hash = await hash_password(req.new_password)
    admin.updated_at = datetime.utcnow()
    
    # 可选：使其他会话失效
    await db.execute(
        select(AdminSession)
        .where(
            and_(
                AdminSession.admin_id == admin.id,
                AdminSession.is_active == True
            )
        )
        .execution_options(synchronize_session="fetch")
    )
    
    await db.commit()
    
    return {"success": True, "message": "密码修改成功，请重新登录"}


@router.get("/check-auth")
async def check_auth(admin: Optional[Admin] = Depends(get_current_admin)) -> dict:
    """检查认证状态"""
    return {
        "authenticated": admin is not None,
        "is_super_admin": admin.is_super_admin if admin else False
    }


# ==================== 管理员管理功能 ====================

class CreateAdminRequest(BaseModel):
    """创建管理员请求"""
    username: str
    password: str
    is_super_admin: bool = False
    permissions: List[str] = []


class UpdateAdminRequest(BaseModel):
    """更新管理员请求"""
    is_active: Optional[bool] = None
    is_super_admin: Optional[bool] = None
    permissions: Optional[List[str]] = None
    password: Optional[str] = None


@router.get("/admins")
async def get_admins(
    admin: Admin = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """获取所有管理员列表"""
    result = await db.execute(select(Admin).order_by(Admin.created_at.desc()))
    admins = result.scalars().all()
    
    admin_list = []
    for a in admins:
        # 获取权限列表
        permissions = []
        if not a.is_super_admin:
            result = await db.execute(
                select(Permission)
                .join(AdminPermission)
                .where(AdminPermission.admin_id == a.id)
            )
            permissions = [p.name for p in result.scalars().all()]
        
        admin_list.append({
            "id": a.id,
            "username": a.username,
            "is_active": a.is_active,
            "is_super_admin": a.is_super_admin,
            "permissions": permissions,
            "last_login": a.last_login,
            "created_at": a.created_at
        })
    
    return {"success": True, "admins": admin_list}


@router.post("/admins")
async def create_admin(
    req: CreateAdminRequest,
    admin: Admin = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """创建新管理员"""
    # 检查用户名是否已存在
    result = await db.execute(
        select(Admin).where(Admin.username == req.username)
    )
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 创建管理员
    new_admin = Admin(
        username=req.username,
        password_hash=await hash_password(req.password),
        is_super_admin=req.is_super_admin,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_admin)
    await db.flush()
    
    # 分配权限（仅非超级管理员）
    if not req.is_super_admin and req.permissions:
        # 获取权限对象
        result = await db.execute(
            select(Permission).where(Permission.name.in_(req.permissions))
        )
        permissions = result.scalars().all()
        
        for perm in permissions:
            admin_perm = AdminPermission(
                admin_id=new_admin.id,
                permission_id=perm.id,
                granted_by=admin.id,  # 记录授权人
                granted_at=datetime.utcnow()
            )
            db.add(admin_perm)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "管理员创建成功",
        "admin": {
            "id": new_admin.id,
            "username": new_admin.username,
            "is_super_admin": new_admin.is_super_admin
        }
    }


@router.put("/admins/{admin_id}")
async def update_admin(
    admin_id: int,
    req: UpdateAdminRequest,
    admin: Admin = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """更新管理员信息"""
    # 获取要更新的管理员
    result = await db.execute(
        select(Admin).where(Admin.id == admin_id)
    )
    target_admin = result.scalars().first()
    
    if not target_admin:
        raise HTTPException(status_code=404, detail="管理员不存在")
    
    # 不允许修改自己的超级管理员权限
    if admin_id == admin.id and req.is_super_admin is False:
        raise HTTPException(status_code=400, detail="不能取消自己的超级管理员权限")
    
    # 更新基本信息
    if req.is_active is not None:
        target_admin.is_active = req.is_active
    
    if req.is_super_admin is not None:
        target_admin.is_super_admin = req.is_super_admin
    
    if req.password:
        if len(req.password) < 6:
            raise HTTPException(status_code=400, detail="密码长度至少6位")
        target_admin.password_hash = await hash_password(req.password)
    
    target_admin.updated_at = datetime.utcnow()
    
    # 更新权限（仅非超级管理员）
    if req.permissions is not None and not target_admin.is_super_admin:
        # 删除现有权限
        result = await db.execute(
            select(AdminPermission)
            .where(AdminPermission.admin_id == admin_id)
        )
        old_permissions = result.scalars().all()
        for perm in old_permissions:
            await db.delete(perm)
        
        # 分配新权限
        if req.permissions:
            result = await db.execute(
                select(Permission).where(Permission.name.in_(req.permissions))
            )
            permissions = result.scalars().all()
            
            for perm in permissions:
                admin_perm = AdminPermission(
                    admin_id=admin_id,
                    permission_id=perm.id,
                    granted_by=admin.id,  # 记录授权人
                    granted_at=datetime.utcnow()
                )
                db.add(admin_perm)
    
    await db.commit()
    
    return {"success": True, "message": "管理员信息更新成功"}


@router.delete("/admins/{admin_id}")
async def delete_admin(
    admin_id: int,
    admin: Admin = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """删除管理员"""
    # 不允许删除自己
    if admin_id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    
    # 获取要删除的管理员
    result = await db.execute(
        select(Admin).where(Admin.id == admin_id)
    )
    target_admin = result.scalars().first()
    
    if not target_admin:
        raise HTTPException(status_code=404, detail="管理员不存在")
    
    # 删除相关会话
    result = await db.execute(
        select(AdminSession)
        .where(AdminSession.admin_id == admin_id)
    )
    sessions = result.scalars().all()
    for session in sessions:
        await db.delete(session)
    
    # 删除管理员（权限关联会自动删除）
    await db.delete(target_admin)
    await db.commit()
    
    return {"success": True, "message": "管理员删除成功"}


@router.get("/permissions")
async def get_permissions(
    admin: Admin = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """获取所有可用权限"""
    result = await db.execute(
        select(Permission).order_by(Permission.module, Permission.action)
    )
    permissions = result.scalars().all()
    
    # 按模块分组
    modules = {}
    for perm in permissions:
        if perm.module not in modules:
            modules[perm.module] = []
        modules[perm.module].append({
            "id": perm.id,
            "name": perm.name,
            "action": perm.action,
            "description": perm.description
        })
    
    return {"success": True, "permissions": modules}