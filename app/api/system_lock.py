"""
系统锁状态监控API模块
提供Telegram锁状态查询和管理接口
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import logging
import subprocess
import sys
import os

from app.services.auth_service import get_auth_service
from app.core.route_config import ROUTES
from app.utils.timezone import get_current_time, format_for_api

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)

# 认证中间件
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """获取当前用户"""
    if not credentials:
        return None
    
    try:
        auth_service = get_auth_service()
        return await auth_service.get_current_user(credentials.credentials)
    except Exception as e:
        logger.error(f"获取当前用户失败: {e}")
        return None

async def require_auth(user: Optional[Dict[str, Any]] = Depends(get_current_user)) -> Dict[str, Any]:
    """要求用户认证"""
    if not user:
        raise HTTPException(status_code=401, detail="未授权访问")
    return user

@router.get("/system/lock-status")
async def get_lock_status(user: Dict[str, Any] = Depends(require_auth)):
    """
    获取Telegram锁状态
    """
    try:
        # 系统现在使用Redis分布式锁，无需文件锁检查
        from app.storage.lock_manager import RedisLockManager
        
        lock_status = {
            "has_lock": False,
            "lock_owner": None,
            "heartbeat_age": None,
            "is_expired": False,
            "status": "normal",
            "message": "系统使用Redis分布式锁，状态正常"
        }
        
        return {
            "success": True,
            "data": lock_status,
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取锁状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取锁状态失败: {str(e)}")

@router.post("/system/clear-lock")
async def clear_lock(
    request: Dict[str, Any] = {},
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    清理Telegram锁（仅限管理员）
    """
    try:
        # 检查管理员权限
        if not user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="需要管理员权限")
        
        force = request.get("force", False)
        
        # 系统现在使用Redis分布式锁，无需文件锁清理
        # 直接返回成功状态
        
        return {
            "success": True,
            "message": "Redis分布式锁系统，无需手动清理",
            "cleared": False,
            "force_requested": force,
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"清理锁失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理锁失败: {str(e)}")

@router.post("/system/auto-clear-lock")  
async def auto_clear_lock(user: Dict[str, Any] = Depends(require_auth)):
    """
    智能清理过期锁
    """
    try:
        # 系统现在使用Redis分布式锁，自动管理过期锁
        # 无需手动清理，直接返回正常状态
        
        return {
            "success": True,
            "message": "Redis分布式锁系统自动管理过期锁",
            "action": "none",
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"自动锁清理失败: {e}")
        raise HTTPException(status_code=500, detail=f"自动锁清理失败: {str(e)}")