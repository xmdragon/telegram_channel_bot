"""目标频道管理API"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
from pydantic import BaseModel
import logging

from app.core.route_config import ROUTES
from app.api.deps import require_auth

router = APIRouter()
logger = logging.getLogger(__name__)

class TargetChannelAddRequest(BaseModel):
    channel_name: str
    signature: str = ""

class TargetChannelUpdateRequest(BaseModel):
    signature: Optional[str] = None
    enabled: Optional[bool] = None

@router.get(ROUTES.target_channels.list)
async def get_target_channels(user: Dict[str, Any] = Depends(require_auth)):
    """获取所有目标频道"""
    try:
        from app.services.target_channel_service import target_channel_service
        targets = target_channel_service.get_all_targets()
        return {"success": True, "targets": targets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.target_channels.add)
async def add_target_channel(request: TargetChannelAddRequest, user: Dict[str, Any] = Depends(require_auth)):
    """添加目标频道"""
    try:
        from app.services.target_channel_service import target_channel_service
        result = await target_channel_service.add_target(
            channel_name=request.channel_name,
            signature=request.signature
        )
        if result["success"]:
            return result
        raise HTTPException(status_code=400, detail=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put(ROUTES.target_channels.update)
async def update_target_channel(id: int, request: TargetChannelUpdateRequest, user: Dict[str, Any] = Depends(require_auth)):
    """更新目标频道"""
    try:
        from app.services.target_channel_service import target_channel_service
        updates = {}
        if request.signature is not None:
            updates["signature"] = request.signature
        if request.enabled is not None:
            updates["enabled"] = request.enabled
        result = await target_channel_service.update_target(id, updates)
        if result["success"]:
            return result
        raise HTTPException(status_code=404, detail=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete(ROUTES.target_channels.delete)
async def delete_target_channel(id: int, user: Dict[str, Any] = Depends(require_auth)):
    """删除目标频道"""
    try:
        from app.services.target_channel_service import target_channel_service
        result = await target_channel_service.remove_target(id)
        if result["success"]:
            return result
        raise HTTPException(status_code=404, detail=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
