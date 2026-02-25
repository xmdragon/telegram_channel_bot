"""目标频道管理API"""
from fastapi import APIRouter, HTTPException, Depends, Query
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


@router.post(ROUTES.target_channels.sync)
async def sync_target_channel(id: int, user: Dict[str, Any] = Depends(require_auth)):
    """触发目标频道同步"""
    try:
        from app.services.channel_sync_service import channel_sync_service
        result = await channel_sync_service.start_sync(id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(ROUTES.target_channels.sync_status)
async def get_sync_status(id: int, task_id: str = Query(...), user: Dict[str, Any] = Depends(require_auth)):
    """查询同步进度"""
    try:
        from app.services.channel_sync_service import channel_sync_service
        status = channel_sync_service.get_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"success": True, **status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
