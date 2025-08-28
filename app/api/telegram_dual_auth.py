"""
双Session认证API - 支持前端双栏认证界面
提供独立的采集Session和发送Session认证接口
实现真正的并行认证流程
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Literal
import logging

from app.telegram.dual_auth_manager import dual_auth_manager
from app.services.session_migrator import session_migrator

logger = logging.getLogger(__name__)

router = APIRouter()

# 请求模型定义
class SharedApiConfigRequest(BaseModel):
    api_id: int
    api_hash: str

class SessionInitRequest(BaseModel):
    session_type: Literal["listener", "sender"]

class SendCodeRequest(BaseModel):
    session_type: Literal["listener", "sender"]
    phone: str

class VerifyCodeRequest(BaseModel):
    session_type: Literal["listener", "sender"]
    code: str

class VerifyPasswordRequest(BaseModel):
    session_type: Literal["listener", "sender"]
    password: str

class ClearSessionRequest(BaseModel):
    session_type: Literal["listener", "sender"]

@router.post("/shared-api-config")
async def set_shared_api_config(request: SharedApiConfigRequest):
    """设置共享的API配置"""
    try:
        await dual_auth_manager.set_shared_api_config(
            request.api_id, 
            request.api_hash
        )
        
        return {
            "success": True,
            "message": "API配置已设置",
            "api_id": request.api_id
        }
        
    except Exception as e:
        logger.error(f"设置API配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/init-session")
async def init_session_auth(request: SessionInitRequest):
    """初始化Session认证"""
    try:
        success = await dual_auth_manager.create_session_client(request.session_type)
        
        if success:
            status = await dual_auth_manager.get_session_status(request.session_type)
            return {
                "success": True,
                "message": f"{request.session_type}Session已初始化",
                "session_type": request.session_type,
                "status": status
            }
        else:
            return {
                "success": False,
                "error": f"初始化{request.session_type}Session失败"
            }
            
    except Exception as e:
        logger.error(f"初始化{request.session_type}Session失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-code")
async def send_verification_code(request: SendCodeRequest):
    """发送验证码"""
    try:
        result = await dual_auth_manager.send_code(
            request.session_type, 
            request.phone
        )
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发送{request.session_type}Session验证码失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify-code")
async def verify_verification_code(request: VerifyCodeRequest):
    """验证验证码"""
    try:
        result = await dual_auth_manager.verify_code(
            request.session_type, 
            request.code
        )
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证{request.session_type}Session验证码失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify-password")
async def verify_two_step_password(request: VerifyPasswordRequest):
    """验证两步验证密码"""
    try:
        result = await dual_auth_manager.verify_password(
            request.session_type,
            request.password
        )
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证{request.session_type}Session密码失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/session-status/{session_type}")
async def get_session_status(session_type: Literal["listener", "sender"]):
    """获取Session状态"""
    try:
        status = await dual_auth_manager.get_session_status(session_type)
        return {
            "success": True,
            "status": status
        }
        
    except Exception as e:
        logger.error(f"获取{session_type}Session状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dual-session-status")
async def get_dual_session_status():
    """获取双Session状态"""
    try:
        listener_status = await dual_auth_manager.get_session_status("listener")
        sender_status = await dual_auth_manager.get_session_status("sender")
        
        # 检查配置状态
        config_status = await session_migrator.check_dual_session_status()
        
        return {
            "success": True,
            "listener": listener_status,
            "sender": sender_status,
            "config": config_status
        }
        
    except Exception as e:
        logger.error(f"获取双Session状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clear-session")
async def clear_session_auth(request: ClearSessionRequest):
    """清除Session认证"""
    try:
        await dual_auth_manager.clear_session(request.session_type)
        
        return {
            "success": True,
            "message": f"{request.session_type}Session已清除"
        }
        
    except Exception as e:
        logger.error(f"清除{request.session_type}Session失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/migrate-config")
async def migrate_legacy_config():
    """迁移旧配置到双Session结构"""
    try:
        result = await session_migrator.migrate_legacy_session()
        
        if result["migrated"]:
            return {
                "success": True,
                "message": "配置迁移成功",
                "details": result
            }
        else:
            return {
                "success": True,
                "message": result["message"],
                "reason": result["reason"]
            }
            
    except Exception as e:
        logger.error(f"配置迁移失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/disconnect-all")
async def disconnect_all_sessions():
    """断开所有Session连接"""
    try:
        await dual_auth_manager.disconnect_all()
        
        return {
            "success": True,
            "message": "所有Session连接已断开"
        }
        
    except Exception as e:
        logger.error(f"断开Session连接失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))