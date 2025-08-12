"""
Telethon 认证 API - 支持 WebSocket 交互式认证
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, Any
import json
import asyncio

from app.telegram.auth import auth_manager

router = APIRouter()

class AuthRequest(BaseModel):
    api_id: int
    api_hash: str

class CodeRequest(BaseModel):
    code: str

class PasswordRequest(BaseModel):
    password: str

class PhoneRequest(BaseModel):
    phone: str

# WebSocket 连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

manager = ConnectionManager()

@router.websocket("/ws/auth")
async def websocket_auth(websocket: WebSocket):
    """WebSocket 认证端点"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            action = message.get("action")
            
            if action == "init_auth":
                # 初始化认证
                api_id = message.get("api_id")
                api_hash = message.get("api_hash")
                
                try:
                    # 首先尝试使用保存的StringSession
                    from app.services.config_manager import config_manager
                    saved_session = await config_manager.get_config("telegram.session")
                    
                    if saved_session:
                        # 尝试使用StringSession
                        success = await auth_manager.create_client_from_string(
                            api_id, api_hash, saved_session
                        )
                    else:
                        # 创建新的认证会话
                        success = await auth_manager.create_client(
                            api_id, api_hash
                        )
                    
                    if success:
                        # 根据实际的认证状态判断
                        if auth_manager.auth_state == "authorized":
                            await manager.send_personal_message(
                                json.dumps({
                                    "type": "auth_status",
                                    "state": "authorized",
                                    "message": "客户端已授权"
                                }), websocket
                            )
                        else:
                            await manager.send_personal_message(
                                json.dumps({
                                    "type": "auth_status",
                                    "state": "phone_needed",
                                    "message": "请输入手机号码"
                                }), websocket
                            )
                    else:
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "auth_status",
                                "state": "phone_needed",
                                "message": "请输入手机号码"
                            }), websocket
                        )
                except Exception as e:
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "error",
                            "message": f"初始化失败: {str(e)}"
                        }), websocket
                    )
            
            elif action == "send_phone":
                # 发送手机号码
                phone = message.get("phone")
                
                try:
                    result = await auth_manager.send_code(phone)
                    if result.get("success"):
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "auth_status",
                                "state": result.get("state", "code_sent"),
                                "message": result.get("message", "验证码已发送")
                            }), websocket
                        )
                    else:
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "error",
                                "message": result.get("error", "发送验证码失败")
                            }), websocket
                        )
                except Exception as e:
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "error",
                            "message": f"发送验证码失败: {str(e)}"
                        }), websocket
                    )
            
            elif action == "verify_code":
                # 验证验证码
                code = message.get("code")
                
                try:
                    result = await auth_manager.verify_code(code)
                    
                    if result.get("success"):
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "auth_status",
                                "state": "authorized",
                                "message": "认证成功"
                            }), websocket
                        )
                    else:
                        if result.get("state") == "password_needed":
                            await manager.send_personal_message(
                                json.dumps({
                                    "type": "auth_status",
                                    "state": "password_needed",
                                    "message": "需要两步验证密码"
                                }), websocket
                            )
                        else:
                            await manager.send_personal_message(
                                json.dumps({
                                    "type": "error",
                                    "message": result.get("error", "验证失败")
                                }), websocket
                            )
                except Exception as e:
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "error",
                            "message": f"验证码验证失败: {str(e)}"
                        }), websocket
                    )
            
            elif action == "verify_password":
                # 验证两步验证密码
                password = message.get("password")
                
                try:
                    result = await auth_manager.verify_password(password)
                    
                    if result.get("success"):
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "auth_status",
                                "state": "authorized",
                                "message": "认证成功"
                            }), websocket
                        )
                    else:
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "error",
                                "message": result.get("error", "两步验证失败")
                            }), websocket
                        )
                except Exception as e:
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "error",
                            "message": f"两步验证失败: {str(e)}"
                        }), websocket
                    )
            
            elif action == "disconnect":
                # 断开连接
                try:
                    await auth_manager.disconnect()
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "auth_status",
                            "state": "disconnected",
                            "message": "已断开连接"
                        }), websocket
                    )
                except Exception as e:
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "error",
                            "message": f"断开连接失败: {str(e)}"
                        }), websocket
                    )
            
            elif action == "clear_auth":
                # 清除认证数据
                try:
                    result = await auth_manager.clear_auth_data()
                    if result.get("success"):
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "auth_cleared",
                                "message": result.get("message", "认证数据已清除")
                            }), websocket
                        )
                    else:
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "error",
                                "message": result.get("error", "清除认证数据失败")
                            }), websocket
                        )
                except Exception as e:
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "error",
                            "message": f"清除认证数据失败: {str(e)}"
                        }), websocket
                    )
            
            elif action == "get_auth_info":
                # 获取认证信息
                try:
                    result = await auth_manager.get_saved_auth_info()
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "auth_info",
                            "data": result
                        }), websocket
                    )
                except Exception as e:
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "error",
                            "message": f"获取认证信息失败: {str(e)}"
                        }), websocket
                    )
            
            else:
                await manager.send_personal_message(
                    json.dumps({
                        "type": "error",
                        "message": "未知操作"
                    }), websocket
                )
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 保留原有的 REST API 端点用于兼容性
@router.post("/init")
async def init_auth(request: AuthRequest):
    """初始化认证"""
    try:
        success = await auth_manager.create_client(
            request.api_id,
            request.api_hash
        )
        
        if success:
            # 已授权（虽然新StringSession不太可能出现这种情况）
            return {
                "success": True,
                "message": "客户端已授权",
                "state": "authorized"
            }
        else:
            # 需要继续认证流程
            return {
                "success": True,
                "message": "请输入手机号码",
                "state": "idle"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化失败: {str(e)}")

@router.post("/send-code")
async def send_code(request: PhoneRequest):
    """发送验证码"""
    try:
        result = await auth_manager.send_code(request.phone)
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

@router.post("/clear")
async def clear_auth():
    """清除认证数据"""
    try:
        result = await auth_manager.clear_auth_data()
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清除认证数据失败: {str(e)}")

@router.get("/info")
async def get_auth_info():
    """获取认证信息"""
    try:
        result = await auth_manager.get_saved_auth_info()
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取认证信息失败: {str(e)}") 