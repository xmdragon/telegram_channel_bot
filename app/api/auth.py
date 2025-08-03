"""
Telethon 认证 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from app.telegram.auth import auth_manager

router = APIRouter()

class AuthRequest(BaseModel):
    api_id: int
    api_hash: str
    phone: str

class CodeRequest(BaseModel):
    code: str

class PasswordRequest(BaseModel):
    password: str

@router.post("/init")
async def init_auth(request: AuthRequest):
    """初始化认证"""
    try:
        success = await auth_manager.create_client(
            request.api_id,
            request.api_hash,
            request.phone
        )
        
        if success:
            return {
                "success": True,
                "message": "客户端已授权",
                "state": "authorized"
            }
        else:
            return {
                "success": True,
                "message": "需要发送验证码",
                "state": "idle"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化失败: {str(e)}")

@router.post("/send-code")
async def send_code():
    """发送验证码"""
    try:
        result = await auth_manager.send_code()
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送验证码失败: {str(e)}")

@router.post("/verify-code")
async def verify_code(request: CodeRequest):
    """验证验证码"""
    try:
        result = await auth_manager.verify_code(request.code)
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"验证码验证失败: {str(e)}")

@router.post("/verify-password")
async def verify_password(request: PasswordRequest):
    """验证两步验证密码"""
    try:
        result = await auth_manager.verify_password(request.password)
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"两步验证失败: {str(e)}")

@router.post("/resend-code")
async def resend_code():
    """重新发送验证码"""
    try:
        result = await auth_manager.resend_code()
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新发送验证码失败: {str(e)}")

@router.get("/status")
async def get_auth_status():
    """获取认证状态"""
    try:
        result = await auth_manager.get_auth_status()
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

@router.post("/disconnect")
async def disconnect():
    """断开连接"""
    try:
        await auth_manager.disconnect()
        return {
            "success": True,
            "message": "已断开连接"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"断开连接失败: {str(e)}") 