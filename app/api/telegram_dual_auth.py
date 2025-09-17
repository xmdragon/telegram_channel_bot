"""
双Session认证API - 基于dual_session_manager的统一实现
复用现有的Session连接，避免冲突
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Literal
import logging

# 导入统一的Session管理器
from app.telegram.dual_session_manager import dual_session_manager
from app.core.telegram_config import TelegramConfig

# Python 3.13兼容性：Telethon类型导入必须在模块顶部
from telethon import TelegramClient
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)

router = APIRouter()

# 请求模型定义
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


@router.post("/init-session")
async def init_session_auth(request: SessionInitRequest):
    """初始化Session认证 - 基于现有连接"""
    try:
        session_manager = dual_session_manager

        # 检查对应的Session是否已连接
        if request.session_type == "listener":
            is_connected = await session_manager.is_listener_connected()
            if is_connected:
                return {
                    "success": True,
                    "message": f"{request.session_type}Session已连接",
                    "session_type": request.session_type,
                    "status": {
                        "state": "authorized",
                        "error_message": None,
                        "has_client": True
                    }
                }
        else:  # sender
            is_connected = await session_manager.is_sender_connected()
            if is_connected:
                return {
                    "success": True,
                    "message": f"{request.session_type}Session已连接",
                    "session_type": request.session_type,
                    "status": {
                        "state": "authorized",
                        "error_message": None,
                        "has_client": True
                    }
                }

        # 如果未连接，返回需要认证状态
        return {
            "success": True,
            "message": f"{request.session_type}Session需要认证",
            "session_type": request.session_type,
            "status": {
                "state": "phone_needed",
                "error_message": None,
                "has_client": False
            }
        }

    except Exception as e:
        logger.error(f"初始化{request.session_type}Session失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-code")
async def send_verification_code(request: SendCodeRequest):
    """发送验证码 - 暂不支持，需要通过系统配置页面完成认证"""
    return {
        "success": False,
        "error": "请通过系统配置页面完成Telegram认证，此界面仅显示当前认证状态"
    }

@router.post("/verify-code")
async def verify_verification_code(request: VerifyCodeRequest):
    """验证验证码 - 暂不支持，需要通过系统配置页面完成认证"""
    return {
        "success": False,
        "error": "请通过系统配置页面完成Telegram认证，此界面仅显示当前认证状态"
    }

@router.post("/verify-password")
async def verify_two_step_password(request: VerifyPasswordRequest):
    """验证两步验证密码 - 暂不支持，需要通过系统配置页面完成认证"""
    return {
        "success": False,
        "error": "请通过系统配置页面完成Telegram认证，此界面仅显示当前认证状态"
    }

@router.get("/session-status/{session_type}")
async def get_session_status(session_type: Literal["listener", "sender"]):
    """获取Session状态"""
    try:
        session_manager = dual_session_manager

        if session_type == "listener":
            is_connected = await session_manager.is_listener_connected()
        else:
            is_connected = await session_manager.is_sender_connected()

        if is_connected:
            return {
                "success": True,
                "status": {
                    "session_type": session_type,
                    "state": "authorized",
                    "error_message": None,
                    "has_client": True
                }
            }
        else:
            return {
                "success": True,
                "status": {
                    "session_type": session_type,
                    "state": "idle",
                    "error_message": "未连接或需要重新认证",
                    "has_client": False
                }
            }

    except Exception as e:
        logger.error(f"获取{session_type}Session状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

