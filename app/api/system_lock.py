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
        # 构建清理脚本路径
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "tools", "maintenance", "clear_telegram_lock.py"
        )
        
        # 执行锁状态检查
        result = subprocess.run([
            sys.executable, script_path, "--check"
        ], capture_output=True, text=True, timeout=10)
        
        lock_status = {
            "has_lock": False,
            "lock_owner": None,
            "heartbeat_age": None,
            "is_expired": False,
            "status": "normal",
            "message": "系统正常，没有锁"
        }
        
        if result.returncode == 0:
            output = result.stdout
            if "没有锁" in output:
                lock_status["status"] = "normal"
                lock_status["message"] = "系统正常，没有锁"
            elif "锁状态:" in output:
                lock_status["has_lock"] = True
                
                # 解析输出中的锁信息
                lines = output.strip().split('\n')
                for line in lines:
                    if "持有者:" in line:
                        lock_status["lock_owner"] = line.split("持有者:")[-1].strip()
                    elif "心跳年龄:" in line:
                        age_text = line.split("心跳年龄:")[-1].strip()
                        if "秒" in age_text:
                            try:
                                lock_status["heartbeat_age"] = float(age_text.replace("秒", ""))
                            except:
                                pass
                    elif "状态:" in line:
                        status_text = line.split("状态:")[-1].strip()
                        lock_status["is_expired"] = "过期" in status_text
                        
                if lock_status["is_expired"]:
                    lock_status["status"] = "expired"
                    lock_status["message"] = f"检测到死锁，心跳年龄: {lock_status.get('heartbeat_age', '未知')}秒"
                else:
                    lock_status["status"] = "active"
                    lock_status["message"] = f"锁正在使用中，持有者: {lock_status.get('lock_owner', '未知')}"
        else:
            lock_status["status"] = "error"
            lock_status["message"] = f"锁状态检查失败: {result.stderr}"
        
        return {
            "success": True,
            "data": lock_status,
            "timestamp": format_for_api(get_current_time())
        }
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="锁状态检查超时")
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
        
        # 构建清理脚本路径
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "tools", "maintenance", "clear_telegram_lock.py"
        )
        
        # 执行锁清理
        if force:
            result = subprocess.run([
                sys.executable, script_path, "--force"
            ], capture_output=True, text=True, timeout=15)
        else:
            result = subprocess.run([
                sys.executable, script_path, "--clear"
            ], capture_output=True, text=True, timeout=15)
        
        if result.returncode == 0:
            output = result.stdout
            if "没有发现锁" in output or "没有锁" in output:
                return {
                    "success": True,
                    "message": "没有需要清理的锁",
                    "cleared": False,
                    "timestamp": format_for_api(get_current_time())
                }
            elif "锁清理完成" in output:
                return {
                    "success": True,
                    "message": "锁清理成功",
                    "cleared": True,
                    "timestamp": format_for_api(get_current_time())
                }
            else:
                return {
                    "success": False,
                    "message": "锁清理状态未知",
                    "cleared": False,
                    "output": output,
                    "timestamp": format_for_api(get_current_time())
                }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"锁清理失败: {result.stderr}"
            )
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="锁清理操作超时")
    except Exception as e:
        logger.error(f"清理锁失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理锁失败: {str(e)}")

@router.post("/system/auto-clear-lock")  
async def auto_clear_lock(user: Dict[str, Any] = Depends(require_auth)):
    """
    智能清理过期锁
    """
    try:
        # 构建清理脚本路径
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "tools", "maintenance", "clear_telegram_lock.py"
        )
        
        # 执行自动清理
        result = subprocess.run([
            sys.executable, script_path, "--auto"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            output = result.stdout
            if "系统正常" in output or "没有锁" in output:
                return {
                    "success": True,
                    "message": "系统正常，没有死锁",
                    "action": "none",
                    "timestamp": format_for_api(get_current_time())
                }
            elif "自动清理" in output or "锁清理完成" in output:
                return {
                    "success": True,
                    "message": "检测到死锁并已自动清理",
                    "action": "cleared",
                    "timestamp": format_for_api(get_current_time())
                }
            else:
                return {
                    "success": True,
                    "message": "锁存在但未过期，系统正常运行中",
                    "action": "none",
                    "timestamp": format_for_api(get_current_time())
                }
        else:
            return {
                "success": False,
                "message": f"自动锁清理异常: {result.stderr}",
                "action": "error",
                "timestamp": format_for_api(get_current_time())
            }
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="自动锁清理超时")
    except Exception as e:
        logger.error(f"自动锁清理失败: {e}")
        raise HTTPException(status_code=500, detail=f"自动锁清理失败: {str(e)}")