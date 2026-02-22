"""Shared API dependencies - authentication"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.services.auth_service import get_auth_service

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    if not credentials:
        return None
    auth = get_auth_service()
    return await auth.get_current_user(credentials.credentials)


async def require_auth(user: dict = Depends(get_current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


async def require_super_admin(user: dict = Depends(require_auth)) -> dict:
    if not user.get('is_super_admin'):
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return user
