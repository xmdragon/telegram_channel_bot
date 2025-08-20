"""
消息基础CRUD API模块
处理消息的基本增删改查操作
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
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
from app.core.route_config import ROUTES

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
        import functools
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 这里可以添加具体的权限检查逻辑
            return await func(*args, **kwargs)
        return wrapper
    return decorator

@router.get(ROUTES.messages.list)
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
        
        # 🚀 性能优化：精确数据获取，避免过量数据拉取
        if source_channel:
            # 从指定频道获取消息 - 适度冗余以应对去重过滤
            fetch_limit = page_size * 2 if status else page_size
            fetch_offset = offset
            
            all_messages = redis_store.get_messages_by_channel(
                source_channel, 
                limit=fetch_limit,
                offset=fetch_offset
            )
        else:
            # 根据状态获取消息 - 直接获取所需数量，减少内存占用
            fetch_limit = page_size * 2 if page > 1 else page_size + 10
            
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
        
        # 🚀 性能优化：单次遍历完成去重和过滤
        combined_group_ids = set()
        grouped_messages = {}  # grouped_id -> combined_message
        filtered_messages = []
        
        # 第一次遍历：收集组合消息和应用基础过滤
        for msg in all_messages:
            # 状态过滤（提前过滤减少后续处理）
            if status and msg.get('status') != status:
                continue
            
            # 搜索过滤（提前过滤）
            if search:
                content = msg.get('content', '')
                filtered_content = msg.get('filtered_content', '')
                if (search.lower() not in content.lower() and 
                    search.lower() not in filtered_content.lower()):
                    continue
            
            # 组合消息处理
            if msg.get('is_combined') and msg.get('grouped_id'):
                grouped_id = msg.get('grouped_id')
                combined_group_ids.add(grouped_id)
                grouped_messages[grouped_id] = msg
                filtered_messages.append(msg)
            elif msg.get('grouped_id') and msg.get('grouped_id') not in combined_group_ids:
                # 单独消息，但还没有对应的组合版本，先添加
                filtered_messages.append(msg)
        
        # 第二次遍历：移除已有组合版本的单独消息
        final_messages = []
        for msg in filtered_messages:
            if (not msg.get('is_combined') and 
                msg.get('grouped_id') and 
                msg.get('grouped_id') in combined_group_ids):
                # 跳过单独消息，使用组合版本
                continue
            final_messages.append(msg)
        
        filtered_messages = final_messages
        
        # 分页处理
        total_messages = len(filtered_messages)
        if not source_channel:
            # 对于非频道筛选，取前page_size条
            filtered_messages = filtered_messages[:page_size]
        
        # 计算总页数
        total_pages = (total_messages + page_size - 1) // page_size if total_messages > 0 else 1
        
        # 🚀 性能优化：批量获取重复消息的原始数据
        duplicate_original_ids = []
        for message in filtered_messages:
            if message.get('duplicate_original_id'):
                duplicate_original_ids.append(message['duplicate_original_id'])
        
        # 批量查询重复消息的原始数据（如果有的话）
        duplicate_data_cache = {}
        if duplicate_original_ids:
            try:
                # 批量获取原始消息数据
                for original_id in duplicate_original_ids:
                    original_message = redis_store.get_message_by_id(original_id)
                    if original_message:
                        duplicate_data_cache[original_id] = original_message
            except Exception as e:
                logger.warning(f"批量获取重复消息原始数据失败: {e}")
        
        # 🚀 性能优化：预编译正则表达式
        import re
        media_desc_pattern = re.compile(r'\s*\[📎 媒体组:[^]]*\]\s*')
        
        # 处理媒体显示URL和重复消息信息
        for message in filtered_messages:
            # 为前端添加统一的id字段（用于API调用）
            if 'source_channel' in message and 'message_id' in message:
                message['id'] = f"{message['source_channel']}:{message['message_id']}"
            
            # 确保消息有链接前缀
            if not message.get('source_channel_link_prefix') and message.get('source_channel'):
                from app.services.processors.message_storage_processor import MessageStorageProcessor
                processor = MessageStorageProcessor()
                message['source_channel_link_prefix'] = processor._generate_channel_link_prefix(message['source_channel'])
            
            # 处理单个媒体显示URL（支持多种字段名）
            media_path = message.get('media_path') or message.get('media_url')
            if media_path:
                message['media_display_url'] = api_paths.get_temp_media_url(
                    os.path.basename(media_path)
                )
                # 统一字段名，确保前端能找到
                message['media_path'] = media_path
            
            # 处理组合消息媒体 - 转换数据格式
            if message.get('media_group'):
                # 转换media_group为media_group_display格式
                media_group_display = []
                for media in message['media_group']:
                    media_item = {
                        'media_type': media.get('media_type'),
                        'media_path': media.get('file_path'),  # Redis中是file_path，前端需要media_path
                        'message_id': media.get('message_id'),
                        'file_size': media.get('file_size'),
                        'mime_type': media.get('mime_type'),
                        'download_failed': media.get('download_failed', False),
                        'error': media.get('error')
                    }
                    # 添加显示URL
                    if media_item.get('media_path'):
                        media_item['display_url'] = api_paths.get_temp_media_url(
                            os.path.basename(media_item['media_path'])
                        )
                    media_group_display.append(media_item)
                
                message['media_group_display'] = media_group_display
                
                # 为组合消息设置media_type（如果没有的话）
                if not message.get('media_type') and media_group_display:
                    # 使用第一个媒体的类型作为整体类型
                    message['media_type'] = media_group_display[0].get('media_type')
                
                # 清理内容中的媒体文本描述（使用预编译的正则表达式）
                if message.get('content'):
                    original_content = message['content']
                    cleaned_content = media_desc_pattern.sub('', original_content).strip()
                    if cleaned_content != original_content:
                        message['content'] = cleaned_content
                if message.get('filtered_content'):
                    original_filtered = message['filtered_content']
                    cleaned_filtered = media_desc_pattern.sub('', original_filtered).strip()
                    if cleaned_filtered != original_filtered:
                        message['filtered_content'] = cleaned_filtered
            
            # 兼容处理：如果已有media_group_display，更新其display_url
            elif message.get('media_group_display'):
                for media in message['media_group_display']:
                    if media.get('media_path'):
                        media['display_url'] = api_paths.get_temp_media_url(
                            os.path.basename(media['media_path'])
                        )
            
            # 🚀 性能优化：使用缓存的重复消息数据
            if message.get('duplicate_original_id'):
                try:
                    # 从缓存中获取原始消息数据，避免重复查询
                    original_message = duplicate_data_cache.get(message['duplicate_original_id'])
                    if original_message:
                        # 处理原始消息的单个媒体URL（支持多种字段名）
                        original_media_path = original_message.get('media_path') or original_message.get('media_url')
                        if original_media_path:
                            original_message['media_display_url'] = api_paths.get_temp_media_url(
                                os.path.basename(original_media_path)
                            )
                            # 统一字段名
                            original_message['media_path'] = original_media_path
                        
                        # 处理原始消息的组合媒体 - 转换数据格式
                        if original_message.get('media_group'):
                            # 转换media_group为media_group_display格式
                            media_group_display = []
                            for media in original_message['media_group']:
                                media_item = {
                                    'media_type': media.get('media_type'),
                                    'media_path': media.get('file_path'),
                                    'message_id': media.get('message_id'),
                                    'file_size': media.get('file_size'),
                                    'mime_type': media.get('mime_type'),
                                    'download_failed': media.get('download_failed', False),
                                    'error': media.get('error')
                                }
                                # 添加显示URL
                                if media_item.get('media_path'):
                                    media_item['display_url'] = api_paths.get_temp_media_url(
                                        os.path.basename(media_item['media_path'])
                                    )
                                media_group_display.append(media_item)
                            
                            original_message['media_group_display'] = media_group_display
                            
                            # 为原始消息的组合消息设置media_type
                            if not original_message.get('media_type') and media_group_display:
                                original_message['media_type'] = media_group_display[0].get('media_type')
                        
                        # 兼容处理：如果已有media_group_display，更新其display_url
                        elif original_message.get('media_group_display'):
                            for media in original_message['media_group_display']:
                                if media.get('media_path'):
                                    media['display_url'] = api_paths.get_temp_media_url(
                                        os.path.basename(media['media_path'])
                                    )
                        
                        # 为原始消息添加id字段
                        if 'source_channel' in original_message and 'message_id' in original_message:
                            original_message['id'] = f"{original_message['source_channel']}:{original_message['message_id']}"
                        
                        # 将原始消息数据填充到duplicate_info字段
                        message['duplicate_info'] = original_message
                        
                except Exception as e:
                    logger.warning(f"获取重复消息原始数据失败 {message.get('duplicate_original_id')}: {e}")
                    # 如果无法获取原始消息，保持原有结构
                    message['duplicate_info'] = None
        
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

@router.get(ROUTES.messages.channel_info)
async def get_channel_info(
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    获取频道信息
    """
    try:
        from app.storage.json_store import get_json_channel_store
        
        # 获取频道配置
        channel_store = get_json_channel_store()
        all_channels = channel_store.get_all_channels()
        
        # 转换为频道信息格式
        channels = []
        for channel in all_channels:
            if isinstance(channel, dict):
                # 从channel_name中提取username（如果有@前缀则去掉）
                channel_name = channel.get('channel_name', '')
                username = channel_name.lstrip('@') if channel_name else ''
                
                channels.append({
                    "channel_id": channel.get('channel_id', ''),
                    "title": channel.get('channel_title', channel.get('title', f'频道 {channel.get("channel_id", "")}')),
                    "username": username,
                    "enabled": channel.get('is_active', channel.get('enabled', True)),
                    "channel_type": channel.get('channel_type', 'source'),
                    # 保留原始字段供前端使用
                    "channel_title": channel.get('channel_title', ''),
                    "channel_name": channel.get('channel_name', '')
                })
        
        return {
            "success": True,
            "data": channels,
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取频道信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取频道信息失败: {str(e)}")

@router.get(ROUTES.messages.detail)
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
        
        # 为前端添加统一的id字段
        if 'source_channel' in message and 'message_id' in message:
            message['id'] = f"{message['source_channel']}:{message['message_id']}"
        
        # 确保消息有链接前缀
        if not message.get('source_channel_link_prefix') and message.get('source_channel'):
            from app.services.processors.message_storage_processor import MessageStorageProcessor
            processor = MessageStorageProcessor()
            message['source_channel_link_prefix'] = processor._generate_channel_link_prefix(message['source_channel'])
        
        # 处理单个媒体显示URL（支持多种字段名）
        media_path = message.get('media_path') or message.get('media_url')
        if media_path:
            message['media_display_url'] = api_paths.get_temp_media_url(
                os.path.basename(media_path)
            )
            # 统一字段名
            message['media_path'] = media_path
        
        # 处理组合消息媒体 - 转换数据格式
        if message.get('media_group'):
            # 转换media_group为media_group_display格式
            media_group_display = []
            for media in message['media_group']:
                media_item = {
                    'media_type': media.get('media_type'),
                    'media_path': media.get('file_path'),
                    'message_id': media.get('message_id'),
                    'file_size': media.get('file_size'),
                    'mime_type': media.get('mime_type'),
                    'download_failed': media.get('download_failed', False),
                    'error': media.get('error')
                }
                # 添加显示URL
                if media_item.get('media_path'):
                    media_item['display_url'] = api_paths.get_temp_media_url(
                        os.path.basename(media_item['media_path'])
                    )
                media_group_display.append(media_item)
            
            message['media_group_display'] = media_group_display
            
            # 为组合消息设置media_type（如果没有的话）
            if not message.get('media_type') and media_group_display:
                message['media_type'] = media_group_display[0].get('media_type')
            
            # 不需要清理单个消息的内容，因为这里是处理单个媒体显示URL
        
        # 兼容处理：如果已有media_group_display，更新其display_url
        elif message.get('media_group_display'):
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

async def _publish_message_to_target(message_id: str, user_id: str = None) -> dict:
    """
    统一的发布消息逻辑 - 批准并转发到目标频道
    供 approve_message、publish_message、resend_message 复用
    """
    redis_store = get_redis_message_store()
    message = redis_store.get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    # 转发消息到目标频道
    message_processor = get_message_processor()
    try:
        await message_processor.forward_message(message_id)
        
        # 转发成功后更新状态为已发布
        redis_store.update_message_status(message_id, "published", user_id)
    except Exception as e:
        logger.error(f"消息发布失败: {message_id}, 错误: {e}")
        return {
            "success": False,
            "message": f"消息发布失败: {str(e)}",
            "timestamp": format_for_api(get_current_time())
        }
    
    return {
        "success": True,
        "message": "消息已发布到目标频道",
        "timestamp": format_for_api(get_current_time())
    }

@router.post(ROUTES.messages.approve)
@check_permission("message.approve")
async def approve_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    发布单个消息到目标频道
    """
    try:
        return await _publish_message_to_target(message_id, user.get('user_id'))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发布消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"发布消息失败: {str(e)}")

@router.post(ROUTES.messages.reject)
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
        
        # 处理广告媒体保存（单个消息拒绝时）
        await _handle_single_reject_media_training(message, reason)
        
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

@router.delete(ROUTES.messages.delete)
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

@router.put(ROUTES.messages.update)
@check_permission("message.update")
async def update_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    request: dict = Body({})
):
    """
    更新消息内容
    """
    try:
        redis_store = get_redis_message_store()
        message = redis_store.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 更新消息内容
        update_data = {}
        if "content" in request:
            update_data["content"] = request["content"]
        if "filtered_content" in request:
            update_data["filtered_content"] = request["filtered_content"]
        
        # 添加更新时间和操作者
        update_data["updated_at"] = get_current_time().isoformat()
        update_data["updated_by"] = user.get('user_id')
        
        # 解析message_id获取channel_id
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
            msg_id = int(msg_id)
        else:
            # 尝试从消息数据中获取channel_id
            channel_id = message.get('source_channel')
            msg_id = int(message_id)
        
        if not channel_id:
            raise HTTPException(status_code=400, detail="无法确定消息的频道ID")
        
        # 执行更新
        success = await redis_store.update_message(channel_id, msg_id, update_data)
        if not success:
            raise HTTPException(status_code=500, detail="更新消息失败")
        
        return {
            "success": True,
            "message": "消息已更新",
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新消息失败: {str(e)}")

@router.post(ROUTES.messages.publish)
@check_permission("message.publish")
async def publish_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    发布消息到目标频道
    """
    try:
        return await _publish_message_to_target(message_id, user.get('user_id'))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发布消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"发布消息失败: {str(e)}")

@router.post(ROUTES.messages.edit_publish)
@check_permission("message.edit_publish")
async def edit_and_publish_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    request: dict = Body({})
):
    """
    编辑消息（仅编辑，不自动发布）
    """
    try:
        # 只更新消息内容，不进行发布
        if "content" in request or "filtered_content" in request:
            return await update_message(message_id, user, request)
        else:
            raise HTTPException(status_code=400, detail="没有提供要更新的内容")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"编辑消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"编辑消息失败: {str(e)}")

@router.post(ROUTES.messages.resend)
@check_permission("message.resend")
async def resend_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    重新发布消息到目标频道
    """
    try:
        # 使用统一的发布逻辑，自动处理状态检查
        result = await _publish_message_to_target(message_id, user.get('user_id'))
        
        # 修改返回消息文本
        if result.get('success') and "已发布到目标频道" in result.get('message', ''):
            result['message'] = "消息已重新发布到目标频道"
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新发布消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新发布消息失败: {str(e)}")

@router.post(ROUTES.messages.refetch_media)
@check_permission("message.refetch_media")
async def refetch_message_media(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    重新获取消息的媒体文件
    """
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 使用消息处理器重新获取媒体
        message_processor = get_message_processor()
        success = await message_processor.refetch_media(channel_id, int(msg_id))
        
        if not success:
            raise HTTPException(status_code=500, detail="重新获取媒体失败")
        
        return {
            "success": True,
            "message": "媒体文件已重新获取",
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新获取媒体失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新获取媒体失败: {str(e)}")

@router.delete(ROUTES.messages.delete_review)
@check_permission("message.delete_review")
async def delete_review_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    删除审核群中的消息
    """
    try:
        redis_store = get_redis_message_store()
        message = redis_store.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        review_message_id = message.get('review_message_id')
        if not review_message_id:
            raise HTTPException(status_code=400, detail="消息没有审核消息ID")
        
        # 删除审核群中的消息
        try:
            from app.telegram.bot import telegram_bot
            if telegram_bot and telegram_bot.client:
                await telegram_bot.delete_review_message(review_message_id)
                logger.info(f"已删除审核群消息: {review_message_id}")
            else:
                raise HTTPException(status_code=503, detail="Telegram bot服务不可用")
        except ImportError:
            raise HTTPException(status_code=503, detail="Telegram bot模块不可用")
        except Exception as e:
            logger.error(f"删除审核消息失败: {e}")
            raise HTTPException(status_code=500, detail=f"删除审核消息失败: {str(e)}")
        
        return {
            "success": True,
            "message": "审核消息已删除",
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除审核消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除审核消息失败: {str(e)}")


async def _handle_single_reject_media_training(message: Dict[str, Any], reason: str):
    """
    处理单个消息拒绝时的广告媒体训练数据保存
    如果拒绝原因包含广告相关内容且有媒体，保存到训练目录
    """
    try:
        # 检查拒绝原因是否包含广告相关内容
        is_ad_rejection = any(keyword in reason.lower() for keyword in [
            '广告', 'ad', '推广', '营销', '宣传', '促销', 'spam', '垃圾'
        ])
        
        # 检查消息是否有媒体
        has_media = message.get('media_type') and message.get('media_path')
        
        if is_ad_rejection and has_media:
            try:
                from app.services.training_media_manager import training_media_manager
                
                # 标记消息为广告（用于训练数据保存）
                message['is_ad'] = 'True'  # 设置广告标记
                
                # 从临时目录保存到训练目录
                temp_media_path = message.get('media_path')
                if temp_media_path:
                    saved_path = await training_media_manager.save_training_media(
                        source_path=temp_media_path,
                        message_id=message.get('message_id'),
                        media_type=message.get('media_type'),
                        channel_id=message.get('source_channel'),
                        is_ad=True
                    )
                    if saved_path:
                        logger.info(f"✅ 单个拒绝时保存广告媒体到训练目录: {saved_path}")
                        logger.info(f"🏷️  拒绝原因: {reason}")
                    else:
                        logger.warning(f"⚠️  单个拒绝时保存广告媒体失败: {temp_media_path}")
                
            except ImportError:
                logger.warning("训练媒体管理器不可用，跳过媒体训练数据保存")
            except Exception as e:
                logger.error(f"❌ 单个拒绝时保存媒体到训练目录失败: {e}")
        else:
            if not is_ad_rejection:
                logger.debug(f"拒绝原因不包含广告关键词，跳过媒体保存: {reason}")
            if not has_media:
                logger.debug(f"消息无媒体，跳过媒体保存")
                
    except Exception as e:
        logger.error(f"处理单个拒绝媒体训练失败: {e}")