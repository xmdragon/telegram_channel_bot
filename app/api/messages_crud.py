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
import os

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
    source_channel: Optional[str] = Query(None, description="频道筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    获取消息列表
    支持分页、筛选、搜索和排序
    """
    try:
        redis_store = get_redis_message_store()
        
        # 计算分页参数
        offset = (page - 1) * page_size
        
        # 根据筛选条件获取消息
        if source_channel:
            # 从指定频道获取消息
            fetch_limit = page_size * 3 if status else page_size
            fetch_offset = offset * 2 if status else offset
            
            all_messages = redis_store.get_messages_by_channel(
                source_channel, 
                limit=fetch_limit,
                offset=fetch_offset
            )
        else:
            # 根据状态获取消息
            fetch_limit = page_size * 5
            
            if status == "pending":
                all_messages = redis_store.get_pending_messages(limit=fetch_limit, offset=offset)
            elif status == "approved":
                all_messages = redis_store.get_messages_by_status("approved", limit=fetch_limit, offset=offset)
            elif status == "rejected":
                all_messages = redis_store.get_messages_by_status("rejected", limit=fetch_limit, offset=offset)
            elif status == "auto_forwarded":
                all_messages = redis_store.get_messages_by_status("auto_forwarded", limit=fetch_limit, offset=offset)
            else:
                # 获取所有消息
                all_messages = redis_store.get_all_messages(limit=fetch_limit, offset=offset)
        
        # 收集已组合的grouped_id
        combined_group_ids = set()
        for msg in all_messages:
            if msg.get('is_combined') and msg.get('grouped_id'):
                combined_group_ids.add(msg['grouped_id'])
        
        # 应用过滤条件
        filtered_messages = []
        for msg in all_messages:
            # 组消息去重
            if (not msg.get('is_combined') and 
                msg.get('grouped_id') and 
                msg.get('grouped_id') in combined_group_ids):
                continue
            
            # 状态过滤
            if status and msg.get('status') != status:
                continue
            
            # 搜索过滤
            if search:
                content = msg.get('content', '')
                filtered_content = msg.get('filtered_content', '')
                if (search.lower() not in content.lower() and 
                    search.lower() not in filtered_content.lower()):
                    continue
            
            filtered_messages.append(msg)
        
        # 分页处理
        total_messages = len(filtered_messages)
        if not source_channel:
            # 对于非频道筛选，取前page_size条
            filtered_messages = filtered_messages[:page_size]
        
        # 计算总页数
        total_pages = (total_messages + page_size - 1) // page_size if total_messages > 0 else 1
        
        # 处理媒体显示URL
        for message in filtered_messages:
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
        
        # 构建返回结果
        result = {
            "messages": filtered_messages,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_messages,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }
        
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
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    获取单个消息详情
    """
    try:
        redis_store = get_redis_message_store()
        message = redis_store.get_message_by_id(message_id)
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
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    批准单个消息
    """
    try:
        redis_store = get_redis_message_store()
        message = redis_store.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 更新消息状态为已批准
        success = redis_store.update_message_status(message_id, "approved", user.get('user_id'))
        if not success:
            raise HTTPException(status_code=500, detail="批准消息失败")
        
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
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    拒绝单个消息
    """
    try:
        redis_store = get_redis_message_store()
        message = redis_store.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 更新消息状态为已拒绝
        success = redis_store.update_message_status(message_id, "rejected", user.get('user_id'), reason)
        if not success:
            raise HTTPException(status_code=500, detail="拒绝消息失败")
        
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
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    删除消息
    """
    try:
        redis_store = get_redis_message_store()
        message = redis_store.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 删除消息
        success = redis_store.delete_message(message_id)
        if not success:
            raise HTTPException(status_code=500, detail="删除消息失败")
        
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
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    获取频道信息
    """
    try:
        from app.services.config_manager import ConfigManager
        config_manager = ConfigManager()
        
        # 获取频道配置
        channels_config = await config_manager.get_config('channels', {})
        
        # 转换为频道信息格式
        channels = []
        for channel_id, channel_data in channels_config.items():
            if isinstance(channel_data, dict):
                channels.append({
                    "channel_id": channel_id,
                    "title": channel_data.get('title', f'频道 {channel_id}'),
                    "username": channel_data.get('username', ''),
                    "enabled": channel_data.get('enabled', True)
                })
        
        return {
            "success": True,
            "data": channels,
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取频道信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取频道信息失败: {str(e)}")