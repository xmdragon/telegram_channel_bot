"""
Telegram配置API - 独立管理telegram.json
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

from app.services.telegram_config_manager import telegram_config_manager
from app.services.auth_service import get_auth_service
from app.core.route_config import ROUTES

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

class TelegramConfigUpdate(BaseModel):
    """Telegram配置更新模型"""
    api_id: Optional[str] = None
    api_hash: Optional[str] = None

@router.get(ROUTES.telegram_config.get)
async def get_telegram_config(user: Dict[str, Any] = Depends(require_auth)):
    """获取Telegram配置"""
    try:
        config = telegram_config_manager.get_all()
        # 添加session状态（从system.json读取）
        config["sender_session"] = await telegram_config_manager.get_sender_session() or ""
        config["listener_session"] = await telegram_config_manager.get_listener_session() or ""

        # 验证状态
        validation = telegram_config_manager.validate_config()

        return {
            "success": True,
            "config": config,
            "validation": validation
        }
    except Exception as e:
        logger.error(f"获取Telegram配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.telegram_config.update)
async def update_telegram_config(data: TelegramConfigUpdate, user: Dict[str, Any] = Depends(require_auth)):
    """更新Telegram API配置"""
    try:
        updates = {}
        if data.api_id is not None:
            updates["api_id"] = data.api_id
        if data.api_hash is not None:
            updates["api_hash"] = data.api_hash

        if not updates:
            raise HTTPException(status_code=400, detail="没有提供要更新的配置")

        success = telegram_config_manager.update(updates)

        if success:
            return {
                "success": True,
                "message": "Telegram配置已更新",
                "updated": list(updates.keys())
            }
        else:
            raise HTTPException(status_code=500, detail="更新配置失败")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新Telegram配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))