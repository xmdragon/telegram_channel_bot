"""
消息基础CRUD API模块
处理消息的基本增删改查操作
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.utils.timezone import get_current_time, format_for_api
import logging

from app.storage.redis_store import get_redis_message_store
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.services.channel_manager import ChannelManager
from app.core.api_paths import api_paths

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)

# 依赖注入辅助函数
def get_message_processor() -> MessageProcessor:
    return MessageProcessor()

def get_channel_manager() -> ChannelManager:
    return ChannelManager()

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

def check_permission(permission_name: str):
    """检查权限装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 这里可以添加具体的权限检查逻辑
            return await func(*args, **kwargs)
        return wrapper
    return decorator

@router.get("/")
async def get_messages(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选"),
    channel: Optional[str] = Query(None, description="频道筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    获取消息列表
    支持分页、筛选、搜索和排序
    """
    try:
        # 构建查询条件
        filters = {}
        if status:
            filters['status'] = status
        if channel:
            filters['source_channel'] = channel
        if search:
            filters['search'] = search
        
        # 获取消息列表
        result = await message_processor.get_messages_paginated(
            page=page,
            page_size=page_size,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # 处理媒体显示URL
        for message in result.get('messages', []):
            if message.get('media_path'):
                message['media_display_url'] = api_paths.get_temp_media_url(
                    os.path.basename(message['media_path'])
                )
            
            # 处理组合消息媒体
            if message.get('media_group_display'):
                for media in message['media_group_display']:
                    if media.get('media_path'):
                        media['display_url'] = api_paths.get_temp_media_url(
                            os.path.basename(media['media_path'])
                        )
        
        return {
            "success": True,
            "data": result,
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取消息列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取消息列表失败: {str(e)}")

@router.get("/{message_id}")
async def get_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    获取单个消息详情
    """
    try:
        message = await message_processor.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 处理媒体显示URL
        if message.get('media_path'):
            message['media_display_url'] = api_paths.get_temp_media_url(
                os.path.basename(message['media_path'])
            )
        
        # 处理组合消息媒体
        if message.get('media_group_display'):
            for media in message['media_group_display']:
                if media.get('media_path'):
                    media['display_url'] = api_paths.get_temp_media_url(
                        os.path.basename(media['media_path'])
                    )
        
        return {
            "success": True,
            "data": message,
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取消息详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取消息详情失败: {str(e)}")

@router.post("/{message_id}/approve")
@check_permission("message.approve")
async def approve_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    批准单个消息
    """
    try:
        success = await message_processor.approve_message(message_id, user.get('user_id'))
        if not success:
            raise HTTPException(status_code=404, detail="消息不存在或状态不正确")
        
        return {
            "success": True,
            "message": "消息已批准",
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批准消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"批准消息失败: {str(e)}")

@router.post("/{message_id}/reject")
@check_permission("message.reject")
async def reject_message(
    message_id: str,
    reason: str = Query(..., description="拒绝原因"),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    拒绝单个消息
    """
    try:
        success = await message_processor.reject_message(
            message_id, 
            reason, 
            user.get('user_id')
        )
        if not success:
            raise HTTPException(status_code=404, detail="消息不存在或状态不正确")
        
        return {
            "success": True,
            "message": "消息已拒绝",
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"拒绝消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"拒绝消息失败: {str(e)}")

@router.delete("/{message_id}")
@check_permission("message.delete")
async def delete_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    删除消息
    """
    try:
        success = await message_processor.delete_message(message_id, user.get('user_id'))
        if not success:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        return {
            "success": True,
            "message": "消息已删除",
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除消息失败: {str(e)}")

@router.get("/channel-info")
async def get_channel_info(
    user: Dict[str, Any] = Depends(require_auth),
    channel_manager: ChannelManager = Depends(get_channel_manager)
):
    """
    获取频道信息
    """
    try:
        channels = await channel_manager.get_all_channels()
        return {
            "success": True,
            "data": channels,
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取频道信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取频道信息失败: {str(e)}")