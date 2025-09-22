"""
双Session认证API - 基于dual_session_manager的统一实现
复用现有的Session连接，避免冲突
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Literal
import logging

# 导入路由常量
from app.core.route_config import ROUTES

# 导入统一的Session管理器（已集成认证功能）
from app.telegram.dual_session_manager import dual_session_manager
from app.core.telegram_config import TelegramConfig

# Python 3.13兼容性：Telethon类型导入必须在模块顶部
from telethon import TelegramClient
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)

router = APIRouter()  # 前缀已在app/api/__init__.py中配置

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


@router.post(ROUTES.dual_auth.init_session)
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

@router.post(ROUTES.dual_auth.send_code)
async def send_verification_code(request: SendCodeRequest):
    """发送验证码"""
    try:
        # 创建临时认证客户端
        auth_client = await dual_session_manager.create_auth_client(request.session_type)
        if not auth_client:
            raise HTTPException(status_code=500, detail="无法初始化认证客户端")

        # 发送验证码
        result = await dual_session_manager.send_auth_code(
            request.session_type,
            request.phone,
            auth_client
        )

        if result["success"]:
            # 保存认证信息供后续步骤使用
            dual_session_manager._auth_info[request.session_type] = {
                "client": auth_client,
                "phone": request.phone,
                "phone_code_hash": result["phone_code_hash"]
            }
            return result
        else:
            raise HTTPException(status_code=400, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发送{request.session_type}Session验证码失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.dual_auth.verify_code)
async def verify_verification_code(request: VerifyCodeRequest):
    """验证验证码"""
    try:
        # 从session管理器获取认证信息
        auth_info = dual_session_manager._auth_info.get(request.session_type)
        if not auth_info or not auth_info.get("client"):
            raise HTTPException(status_code=400, detail="请先发送验证码")

        # 验证验证码
        result = await dual_session_manager.verify_auth_code(
            request.session_type,
            auth_info["phone"],
            request.code,
            auth_info["phone_code_hash"],
            auth_info["client"]
        )

        if result["success"]:
            # 认证成功，清理临时信息
            if request.session_type in dual_session_manager._auth_info:
                del dual_session_manager._auth_info[request.session_type]
            return result
        elif result.get("password_required"):
            # 需要两步验证密码，保持client等信息
            return {
                "success": True,
                "next_step": "password",
                "message": "需要输入两步验证密码"
            }
        else:
            raise HTTPException(status_code=400, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证{request.session_type}Session验证码失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.dual_auth.verify_password)
async def verify_two_step_password(request: VerifyPasswordRequest):
    """验证两步验证密码"""
    try:
        # 从session管理器获取认证信息
        auth_info = dual_session_manager._auth_info.get(request.session_type)
        if not auth_info or not auth_info.get("client"):
            raise HTTPException(status_code=400, detail="请先发送验证码")

        # 验证密码（只传3个参数）
        result = await dual_session_manager.verify_auth_password(
            request.session_type,
            request.password,
            auth_info["client"]
        )

        if result["success"]:
            # 认证成功，清理临时信息
            if request.session_type in dual_session_manager._auth_info:
                del dual_session_manager._auth_info[request.session_type]
            return result
        else:
            raise HTTPException(status_code=400, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证{request.session_type}Session密码失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


