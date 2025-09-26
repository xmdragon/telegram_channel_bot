"""
消息基础CRUD API模块
处理消息的基本增删改查操作
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from datetime import datetime
from app.utils.timezone import get_current_time, format_for_api
import logging
import os
import json

from app.storage.redis_manager import redis_manager
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.services.channel_manager import ChannelManager
from app.core.media_paths import media_paths
from app.core.route_config import ROUTES
from telethon.errors import FloodWaitError
import re

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)

# 依赖注入辅助函数
def get_message_processor() -> MessageProcessor:
    return MessageProcessor()

def get_channel_manager() -> ChannelManager:
    return ChannelManager()

def extract_message_id_from_target_link(target_link: str) -> Optional[int]:
    """
    从目标消息链接中提取消息ID
    支持格式:
    - https://t.me/channel_name/123 -> 123
    - https://t.me/c/1234567890/123 -> 123
    """
    if not target_link:
        return None

    try:
        # 匹配最后一个数字作为消息ID
        match = re.search(r'/(\d+)$', target_link)
        if match:
            return int(match.group(1))
    except (ValueError, AttributeError) as e:
        logger.warning(f"解析目标消息链接失败: {target_link}, 错误: {e}")

    return None

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
        redis_store = redis_manager

        # 计算分页参数
        offset = (page - 1) * page_size

        # 如果有搜索关键词，使用全量搜索
        if search and search.strip():
            # 使用新的全量搜索方法
            filtered_messages, total_messages = redis_manager.search_messages(
                query=search,
                limit=page_size,
                offset=offset,
                status=status  # 搜索时也支持状态过滤
            )

            # 计算总页数
            total_pages = (total_messages + page_size - 1) // page_size if total_messages > 0 else 1

        else:
            # 无搜索关键词时，使用原有逻辑
            # 🚀 性能优化：根据查询类型选择最优方法
            reverse_order = (sort_order == "desc")  # desc=新到旧(逆序), asc=旧到新(正序)

            if source_channel:
                # 从指定频道获取消息，支持状态筛选
                all_messages = redis_manager.get_messages_by_channel(
                    source_channel,
                    limit=page_size,
                    offset=offset,
                    status=status,
                    reverse=reverse_order
                )
            else:
                # 🚀 统一逻辑：消除特殊情况
                if status in ["pending", "approved", "rejected", "send_failed"]:
                    all_messages = redis_manager.get_messages_by_status(status, limit=page_size, offset=offset, reverse=reverse_order)
                else:
                    # 无状态筛选时，默认显示待审核消息
                    all_messages = redis_manager.get_messages_by_status("pending", limit=page_size, offset=offset, reverse=reverse_order)

            # 直接使用获取到的消息
            filtered_messages = all_messages

            # 计算总数和页数
            total_messages = len(filtered_messages)
            total_pages = (total_messages + page_size - 1) // page_size if total_messages > 0 else 1
        
        # 🗑️ 不再需要处理媒体组标记 - 现在单独存储
        
        # 处理媒体显示URL和重复消息信息
        for message in filtered_messages:
            # 为前端添加统一的id字段（用于API调用）
            if 'source_channel' in message and 'message_id' in message:
                source_channel = message['source_channel']
                # 确保source_channel包含-100前缀
                if not source_channel.startswith('-100') and source_channel.isdigit():
                    source_channel = f"-100{source_channel}"
                message['id'] = f"{source_channel}:{message['message_id']}"
            
            # 确保消息有链接前缀
            if not message.get('source_channel_link_prefix') and message.get('source_channel'):
                from app.services.processors.message_storage_processor import MessageStorageProcessor
                processor = MessageStorageProcessor()
                # 优先使用已有的频道用户名
                channel_username = message.get('source_channel_username')
                message['source_channel_link_prefix'] = processor._generate_channel_link_prefix(
                    message['source_channel'], 
                    channel_username
                )
            
            # 处理单个媒体显示URL（支持多种字段名）
            media_path = message.get('media_path') or message.get('media_url')
            if media_path:
                # 修复路径处理：正确处理temp_media/前缀
                if media_path.startswith('temp_media/'):
                    # 如果路径已经包含temp_media/，直接加前导斜杠
                    message['media_display_url'] = '/' + media_path
                else:
                    # 否则使用原有逻辑
                    message['media_display_url'] = media_paths.get_temp_media_url(
                        os.path.basename(media_path)
                    )
                # 统一字段名，确保前端能找到
                message['media_path'] = media_path

            # 处理视频缩略图URL
            if message.get('media_type') == 'video' and message.get('thumbnail_url'):
                # 确保缩略图路径也正确处理
                thumbnail_path = message.get('thumbnail_url')
                if thumbnail_path:
                    if not thumbnail_path.startswith('/'):
                        message['thumbnail_display_url'] = '/' + thumbnail_path
                    else:
                        message['thumbnail_display_url'] = thumbnail_path
            
            # 处理组合消息媒体 - 转换数据格式
            if message.get('media_group'):
                # 🔍 修复双重序列化问题：如果media_group是字符串，先解析它
                media_group_data = message['media_group']
                if isinstance(media_group_data, str):
                    try:
                        media_group_data = json.loads(media_group_data)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"媒体组JSON解析失败: {e}")
                        media_group_data = []
                
                # 转换media_group为media_group_display格式
                media_group_display = []
                for media in media_group_data:
                    media_item = {
                        'media_type': media.get('media_type'),
                        'media_path': media.get('file_path'),  # Redis中是file_path，前端需要media_path
                        'message_id': media.get('message_id'),
                        'file_size': media.get('file_size'),
                        'mime_type': media.get('mime_type'),
                        'download_failed': media.get('download_failed', False),
                        'error': media.get('error'),
                        'thumbnail_url': media.get('thumbnail_url')  # 添加缩略图URL
                    }
                    # 添加显示URL
                    if media_item.get('media_path'):
                        # 修复路径处理：正确处理temp_media/前缀
                        if media_item['media_path'].startswith('temp_media/'):
                            media_item['display_url'] = '/' + media_item['media_path']
                        else:
                            media_item['display_url'] = media_paths.get_temp_media_url(
                                os.path.basename(media_item['media_path'])
                            )

                    # 处理视频缩略图URL
                    if media_item.get('media_type') == 'video' and media_item.get('thumbnail_url'):
                        thumbnail_url = media_item['thumbnail_url']
                        if not thumbnail_url.startswith('/'):
                            media_item['thumbnail_display_url'] = '/' + thumbnail_url
                        else:
                            media_item['thumbnail_display_url'] = thumbnail_url
                    media_group_display.append(media_item)
                
                message['media_group_display'] = media_group_display
                
                # 为组合消息设置media_type（如果没有的话）
                if not message.get('media_type') and media_group_display:
                    # 使用第一个媒体的类型作为整体类型
                    message['media_type'] = media_group_display[0].get('media_type')
            
            # 兼容处理：如果已有media_group_display，更新其display_url和thumbnail_url
            elif message.get('media_group_display'):
                for media in message['media_group_display']:
                    if media.get('media_path'):
                        # 修复路径处理：正确处理temp_media/前缀
                        if media['media_path'].startswith('temp_media/'):
                            media['display_url'] = '/' + media['media_path']
                        else:
                            media['display_url'] = media_paths.get_temp_media_url(
                                os.path.basename(media['media_path'])
                            )

                    # 处理视频缩略图URL - 保持与上面media_group转换相同的逻辑
                    if media.get('media_type') == 'video' and media.get('thumbnail_url'):
                        thumbnail_url = media['thumbnail_url']
                        if not thumbnail_url.startswith('/'):
                            media['thumbnail_display_url'] = '/' + thumbnail_url
                        else:
                            media['thumbnail_display_url'] = thumbnail_url
            
            # 🚀 性能优化：单独消息已清理，重复消息处理大幅简化
            if message.get('duplicate_original_id'):
                try:
                    # 直接查询原始消息（不再需要缓存，因为数据量大幅减少）
                    original_message = redis_manager.get_message_by_id(message['duplicate_original_id'])
                    if original_message:
                        # 处理原始消息的单个媒体URL（支持多种字段名）
                        original_media_path = original_message.get('media_path') or original_message.get('media_url')
                        if original_media_path:
                            # 修复路径处理：正确处理temp_media/前缀
                            if original_media_path.startswith('temp_media/'):
                                original_message['media_display_url'] = '/' + original_media_path
                            else:
                                original_message['media_display_url'] = media_paths.get_temp_media_url(
                                    os.path.basename(original_media_path)
                                )
                            original_message['media_path'] = original_media_path
                        
                        # 处理原始消息的组合媒体
                        if original_message.get('media_group'):
                            # 🔍 修复双重序列化问题：如果media_group是字符串，先解析它
                            original_media_group_data = original_message['media_group']
                            if isinstance(original_media_group_data, str):
                                try:
                                    original_media_group_data = json.loads(original_media_group_data)
                                except (json.JSONDecodeError, TypeError) as e:
                                    logger.warning(f"原始消息媒体组JSON解析失败: {e}")
                                    original_media_group_data = []
                            
                            media_group_display = []
                            for media in original_media_group_data:
                                media_item = {
                                    'media_type': media.get('media_type'),
                                    'media_path': media.get('file_path'),
                                    'message_id': media.get('message_id'),
                                    'file_size': media.get('file_size'),
                                    'mime_type': media.get('mime_type'),
                                    'download_failed': media.get('download_failed', False),
                                    'error': media.get('error')
                                }
                                if media_item.get('media_path'):
                                    # 修复路径处理：正确处理temp_media/前缀
                                    if media_item['media_path'].startswith('temp_media/'):
                                        media_item['display_url'] = '/' + media_item['media_path']
                                    else:
                                        media_item['display_url'] = media_paths.get_temp_media_url(
                                            os.path.basename(media_item['media_path'])
                                        )
                                media_group_display.append(media_item)
                            
                            original_message['media_group_display'] = media_group_display
                            if not original_message.get('media_type') and media_group_display:
                                original_message['media_type'] = media_group_display[0].get('media_type')
                        
                        # 兼容处理：如果已有media_group_display，更新其display_url和thumbnail_url
                        elif original_message.get('media_group_display'):
                            for media in original_message['media_group_display']:
                                if media.get('media_path'):
                                    # 修复路径处理：正确处理temp_media/前缀
                                    if media['media_path'].startswith('temp_media/'):
                                        media['display_url'] = '/' + media['media_path']
                                    else:
                                        media['display_url'] = media_paths.get_temp_media_url(
                                            os.path.basename(media['media_path'])
                                        )

                                # 处理视频缩略图URL - 保持与上面media_group转换相同的逻辑
                                if media.get('media_type') == 'video' and media.get('thumbnail_url'):
                                    thumbnail_url = media['thumbnail_url']
                                    if not thumbnail_url.startswith('/'):
                                        media['thumbnail_display_url'] = '/' + thumbnail_url
                                    else:
                                        media['thumbnail_display_url'] = thumbnail_url
                        
                        # 为原始消息添加id字段
                        if 'source_channel' in original_message and 'message_id' in original_message:
                            original_message['id'] = f"{original_message['source_channel']}:{original_message['message_id']}"
                        
                        message['duplicate_info'] = original_message
                        
                except Exception as e:
                    logger.warning(f"获取重复消息原始数据失败 {message.get('duplicate_original_id')}: {e}")
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
                
                # 确保频道 ID 格式统一（添加 -100 前缀）
                channel_id = channel.get('channel_id', '')
                if channel_id and not channel_id.startswith('-100'):
                    # 如果是纯数字且没有 -100 前缀，添加前缀
                    if channel_id.isdigit() or (channel_id.startswith('-') and channel_id[1:].isdigit()):
                        if not channel_id.startswith('-'):
                            channel_id = f"-100{channel_id}"
                        elif not channel_id.startswith('-100'):
                            channel_id = f"-100{channel_id[1:]}"

                channels.append({
                    "channel_id": channel_id,  # 使用统一格式的 ID
                    "title": channel.get('channel_title', channel.get('title', f'频道 {channel_id}')),
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

def _normalize_message_id(message_id: str) -> str:
    """
    消息ID标准化 - 统一处理所有格式变体
    自动检测并补全缺少的-100前缀
    """
    if ':' not in message_id:
        return message_id
        
    channel_part, msg_part = message_id.split(':', 1)
    
    # 如果频道ID不以-100开头，自动补全
    if channel_part.isdigit():
        channel_part = f"-100{channel_part}"
    elif channel_part.startswith('-') and not channel_part.startswith('-100'):
        channel_part = f"-100{channel_part[1:]}"
    
    return f"{channel_part}:{msg_part}"


@router.get(ROUTES.messages.detail)
async def get_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    获取单个消息详情
    """
    try:
        redis_store = redis_manager
        
        # 🚀 智能ID处理 - 消除格式特殊情况
        normalized_id = _normalize_message_id(message_id)
        
        message = redis_manager.get_message_by_id(normalized_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 为前端添加统一的id字段
        if 'source_channel' in message and 'message_id' in message:
            message['id'] = f"{message['source_channel']}:{message['message_id']}"
        
        # 确保消息有链接前缀
        if not message.get('source_channel_link_prefix') and message.get('source_channel'):
            from app.services.processors.message_storage_processor import MessageStorageProcessor
            processor = MessageStorageProcessor()
            # 优先使用已有的频道用户名
            channel_username = message.get('source_channel_username')
            message['source_channel_link_prefix'] = processor._generate_channel_link_prefix(
                message['source_channel'], 
                channel_username
            )
        
        # 处理单个媒体显示URL（支持多种字段名）
        media_path = message.get('media_path') or message.get('media_url')
        if media_path:
            # 修复路径处理：正确处理temp_media/前缀
            if media_path.startswith('temp_media/'):
                # 如果路径已经包含temp_media/，直接加前导斜杠
                message['media_display_url'] = '/' + media_path
            else:
                # 否则使用原有逻辑
                message['media_display_url'] = media_paths.get_temp_media_url(
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
                    # 修复路径处理：正确处理temp_media/前缀
                    if media_item['media_path'].startswith('temp_media/'):
                        media_item['display_url'] = '/' + media_item['media_path']
                    else:
                        media_item['display_url'] = media_paths.get_temp_media_url(
                            os.path.basename(media_item['media_path'])
                        )
                media_group_display.append(media_item)
            
            message['media_group_display'] = media_group_display
            
            # 为组合消息设置media_type（如果没有的话）
            if not message.get('media_type') and media_group_display:
                message['media_type'] = media_group_display[0].get('media_type')
            
            # 不需要清理单个消息的内容，因为这里是处理单个媒体显示URL
        
        # 兼容处理：如果已有media_group_display，更新其display_url和thumbnail_url
        elif message.get('media_group_display'):
            for media in message['media_group_display']:
                if media.get('media_path'):
                    # 修复路径处理：正确处理temp_media/前缀
                    if media['media_path'].startswith('temp_media/'):
                        media['display_url'] = '/' + media['media_path']
                    else:
                        media['display_url'] = media_paths.get_temp_media_url(
                            os.path.basename(media['media_path'])
                        )

                # 处理视频缩略图URL - 保持与上面media_group转换相同的逻辑
                if media.get('media_type') == 'video' and media.get('thumbnail_url'):
                    thumbnail_url = media['thumbnail_url']
                    if not thumbnail_url.startswith('/'):
                        media['thumbnail_display_url'] = '/' + thumbnail_url
                    else:
                        media['thumbnail_display_url'] = thumbnail_url
        
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


@router.post(ROUTES.messages.approve)
async def approve_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    发布单个消息到目标频道
    """
    try:
        # 获取消息数据
        message = redis_manager.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")

        # 判断消息类型并选择处理方式
        has_media = message.get('media_type') or message.get('is_combined') == 'True'

        if not has_media:
            # 文本消息：直接调用核心发布方法
            result = await publish_single_message(message_id, user.get('user_id'), is_auto_forward=False)
            return result
        else:
            # 媒体消息：异步处理with WebSocket通知
            import asyncio
            asyncio.create_task(_async_publish_with_notify(message_id, user.get('user_id')))

            return {
                "success": True,
                "mode": "async",
                "message": "媒体消息正在后台处理",
                "timestamp": format_for_api(get_current_time())
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发布消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"发布消息失败: {str(e)}")

@router.post(ROUTES.messages.reject)
async def reject_message(
    message_id: str,
    reason: str = Query(..., description="拒绝原因"),
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    拒绝单个消息
    """
    try:
        redis_store = redis_manager
        message = redis_manager.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 根据拒绝原因设置不同的拒绝状态
        from app.core.message_status import MessageStatus

        # 根据原因判断拒绝类型
        if reason:
            reason_lower = reason.lower()
            if "广告" in reason or "ad" in reason_lower:
                new_status = MessageStatus.AD_REJECTED.value
            elif "重复" in reason or "dup" in reason_lower:
                new_status = MessageStatus.DUP_REJECTED.value
            else:
                new_status = MessageStatus.MANUAL_REJECTED.value
        else:
            new_status = MessageStatus.MANUAL_REJECTED.value

        # 更新消息状态
        success = redis_manager.update_message_status(message_id, new_status, user.get('user_id'))
        if not success:
            raise HTTPException(status_code=500, detail="拒绝消息失败")

        # 保存拒绝原因
        if reason:
            # 解析消息ID获取channel_id和msg_id
            if ':' in message_id:
                channel_id, msg_id = message_id.rsplit(':', 1)
                redis_manager.update_message(channel_id, int(msg_id), {"rejection_reason": reason})
        
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

@router.post(ROUTES.messages.restore)
async def restore_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    恢复被拒绝的消息到未审核状态
    """
    try:
        redis_store = redis_manager
        message = redis_manager.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 检查消息当前状态
        current_status = message.get("status", "pending")
        if current_status not in ["rejected", "approved"]:
            raise HTTPException(status_code=400, detail=f"只能恢复已拒绝或已发送的消息，当前状态: {current_status}")
        
        # 恢复消息状态为未审核
        success = redis_manager.update_message_status(message_id, "pending", user.get('user_id'))
        if not success:
            logger.error(f"恢复消息状态失败: message_id={message_id}, current_status={current_status}, user={user.get('user_id')}")
            raise HTTPException(status_code=500, detail="恢复消息状态失败，请检查消息ID格式或数据库连接")
        
        logger.info(f"✅ 消息恢复成功: {message_id} ({current_status} -> pending), 操作者: {user.get('user_id')}")
        
        return {
            "success": True,
            "message": "消息已恢复到未审核状态",
            "message_id": message_id,
            "previous_status": current_status,
            "new_status": "pending",
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"恢复消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"恢复消息失败: {str(e)}")


@router.put(ROUTES.messages.update)
async def update_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    request: dict = Body({})
):
    """
    更新消息内容
    """
    try:
        redis_store = redis_manager
        message = redis_manager.get_message_by_id(message_id)
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

        # 编辑后清除自动转发失败标记，允许重新尝试自动转发
        # 删除auto_forwarder_status和auto_forward_error字段
        if message.get('auto_forwarder_status') is not None:
            logger.info(f"清除消息 {message_id} 的自动转发失败标记")
            # 通过设置为None来删除字段
            update_data["auto_forwarder_status"] = None
            update_data["auto_forward_error"] = None

            # 同时清理可能添加的提示文字
            if "filtered_content" in update_data:
                content = update_data["filtered_content"]
                # 移除可能添加的提示前缀
                prefixes_to_remove = [
                    "⚠️ 消息内容超过1024字符，请手动编辑消息后发送\n\n",
                    "疑似广告，请审核\n\n"
                ]
                for prefix in prefixes_to_remove:
                    if content.startswith(prefix):
                        content = content[len(prefix):]
                update_data["filtered_content"] = content
        
        # 解析message_id获取channel_id  
        try:
            if ':' in message_id:
                channel_id, msg_id = message_id.split(':', 1)
                msg_id = int(msg_id)
                logger.debug(f"从message_id解析: channel_id={channel_id}, msg_id={msg_id}")
            else:
                # 尝试从消息数据中获取channel_id
                channel_id = message.get('source_channel')
                msg_id = int(message_id)
                logger.debug(f"从消息数据解析: channel_id={channel_id}, msg_id={msg_id}")
        except (ValueError, TypeError) as e:
            logger.error(f"消息ID解析失败: {message_id}, 错误: {e}")
            raise HTTPException(status_code=400, detail=f"消息ID格式错误: {message_id}")
        
        if not channel_id:
            logger.error(f"无法确定频道ID: message_id={message_id}, message_data={message}")
            raise HTTPException(status_code=400, detail="无法确定消息的频道ID")
        
        # 执行更新
        success = redis_manager.update_message(channel_id, msg_id, update_data)
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




@router.delete(ROUTES.messages.delete)
async def delete_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    删除消息及其相关的媒体文件
    如果是已发布消息，同时删除目标频道中的消息
    """
    try:
        # 获取消息
        message = redis_manager.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")

        # 🚀 新增：如果是已发布消息，尝试删除目标频道中的消息
        target_delete_result = None
        if message.get('status') == 'approved' and message.get('target_message_link'):
            try:
                from app.telegram.dual_session_manager import dual_session_manager
                from app.services.config_manager import config_manager

                # 🚀 优先使用新字段target_message_ids（支持媒体组批量删除）
                target_msg_ids = message.get('target_message_ids')
                if target_msg_ids and isinstance(target_msg_ids, list):
                    # 新格式：使用批量删除
                    msg_ids_to_delete = target_msg_ids
                    logger.info(f"使用批量删除模式，目标消息IDs: {msg_ids_to_delete}")
                else:
                    # 兼容模式：从target_message_link解析单个ID
                    target_link = message.get('target_message_link')
                    target_msg_id = extract_message_id_from_target_link(target_link)

                    if not target_msg_id:
                        logger.warning(f"无法从目标消息链接解析消息ID: {target_link}")
                        target_delete_result = "无法解析目标消息ID，仅删除本地消息"
                        msg_ids_to_delete = None
                    else:
                        msg_ids_to_delete = [target_msg_id]
                        logger.info(f"使用兼容删除模式，目标消息ID: {target_msg_id}")

                if msg_ids_to_delete:
                    # 获取目标频道ID
                    target_channel_id = await config_manager.get_config('target.channel_id')
                    if target_channel_id:
                        # 获取发送端客户端
                        client = await dual_session_manager.get_sender_client()
                        if client:
                            logger.info(f"准备删除目标频道消息: {target_channel_id}:{msg_ids_to_delete}")

                            # 转换频道ID为整数格式（Telegram API要求）
                            channel_id_int = int(target_channel_id)

                            # 获取频道实体（确保API能找到频道）
                            try:
                                channel_entity = await client.get_entity(channel_id_int)
                                logger.info(f"成功获取频道实体: {channel_entity.title}")

                                # 🚀 批量删除目标频道中的消息
                                await client.delete_messages(channel_entity, msg_ids_to_delete)
                                msg_count = len(msg_ids_to_delete)
                                target_delete_result = f"已删除目标频道{msg_count}条消息"
                                logger.info(f"成功删除目标频道消息: {target_channel_id}:{msg_ids_to_delete}")

                            except Exception as entity_error:
                                logger.warning(f"获取频道实体失败，尝试直接使用频道ID: {entity_error}")
                                # 备用方案：直接使用整数频道ID
                                await client.delete_messages(channel_id_int, msg_ids_to_delete)
                                msg_count = len(msg_ids_to_delete)
                                target_delete_result = f"已删除目标频道{msg_count}条消息"
                                logger.info(f"成功删除目标频道消息: {target_channel_id}:{msg_ids_to_delete}")
                        else:
                            logger.warning("Telegram客户端未连接，无法删除目标频道消息")
                            target_delete_result = "Telegram客户端未连接，仅删除本地消息"
                    else:
                        logger.warning("未配置目标频道ID，无法删除目标频道消息")
                        target_delete_result = "未配置目标频道ID，仅删除本地消息"

            except Exception as e:
                logger.error(f"删除目标频道消息失败: {e}")
                target_delete_result = f"删除目标频道消息失败: {str(e)}"

        # 删除媒体文件和缩略图
        if message.get('media_path'):
            try:
                media_file = message.get('media_path')
                if media_file and os.path.exists(media_file):
                    os.remove(media_file)
                    logger.info(f"已删除媒体文件: {media_file}")
            except Exception as e:
                logger.error(f"删除媒体文件失败: {e}")

        # 删除缩略图
        if message.get('thumb_path'):
            try:
                thumb_file = message.get('thumb_path')
                if thumb_file and os.path.exists(thumb_file):
                    os.remove(thumb_file)
                    logger.info(f"已删除缩略图文件: {thumb_file}")
            except Exception as e:
                logger.error(f"删除缩略图文件失败: {e}")

        # 如果是组合消息，删除相关的组合消息
        if message.get('is_combined') and message.get('combined_message_ids'):
            for combined_id in message.get('combined_message_ids', []):
                try:
                    combined_msg = redis_manager.get_message_by_id(combined_id)
                    if combined_msg:
                        # 删除组合消息的媒体文件
                        if combined_msg.get('media_path'):
                            media_file = combined_msg.get('media_path')
                            if media_file and os.path.exists(media_file):
                                os.remove(media_file)
                        if combined_msg.get('thumb_path'):
                            thumb_file = combined_msg.get('thumb_path')
                            if thumb_file and os.path.exists(thumb_file):
                                os.remove(thumb_file)
                        # 删除组合消息记录
                        redis_manager.delete_message(combined_id)
                        logger.info(f"已删除组合消息: {combined_id}")
                except Exception as e:
                    logger.error(f"删除组合消息失败 {combined_id}: {e}")

        # 从Redis删除消息
        redis_manager.delete_message(message_id)
        logger.info(f"已删除本地消息: {message_id}")

        # 构建返回消息
        result_message = "消息及相关文件已删除"
        if target_delete_result:
            result_message += f"，{target_delete_result}"

        return {
            "success": True,
            "message": result_message,
            "target_delete_result": target_delete_result,
            "timestamp": format_for_api(get_current_time())
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除消息失败: {str(e)}")

@router.delete(ROUTES.messages.delete_review)
async def delete_review_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    删除审核群中的消息
    """
    try:
        redis_store = redis_manager
        message = redis_manager.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")

        review_message_id = message.get('review_message_id')
        if not review_message_id:
            raise HTTPException(status_code=400, detail="消息没有审核消息ID")

        # 删除审核群中的消息
        try:
            from app.telegram.message_forwarder import message_forwarder
            from app.telegram.dual_session_manager import dual_session_manager

            client = await dual_session_manager.get_sender_client()
            if client:
                await message_forwarder.delete_review_message(client, review_message_id)
                logger.info(f"已删除审核群消息: {review_message_id}")
            else:
                raise HTTPException(status_code=503, detail="Telegram客户端未连接")
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





# ========== 新增：核心发布方法与直接发布API ==========

async def publish_single_message(
    message_id: str,
    user_id: str = None,
    skip_validation: bool = False,
    is_auto_forward: bool = False
) -> dict:
    """
    核心单消息发布方法
    所有发布操作的统一入口

    Args:
        message_id: 消息ID (格式: "channel_id:message_id")
        user_id: 操作用户ID，用于记录
        skip_validation: 是否跳过验证（仅限特殊场景）
        is_auto_forward: 是否为自动转发调用（影响错误处理方式）

    Returns:
        dict: 包含 success, message, error 等字段的结果
    """
    try:
        # 1. 获取消息
        message = redis_manager.get_message_by_id(message_id)
        if not message:
            return {
                "success": False,
                "error": "not_found",
                "message": "消息不存在",
                "message_id": message_id
            }

        channel_id = message.get('source_channel')
        msg_id = message.get('message_id')

        # 2. 验证消息（除非明确跳过）
        if not skip_validation:
            # 2.1 检查是否为广告
            is_ad = message.get('is_ad', False)
            if isinstance(is_ad, str):
                is_ad = is_ad.lower() == 'true'

            if is_ad:
                ad_weight = message.get('ad_weight', 0)
                hit_keywords = message.get('hit_keywords', [])
                keyword_names = [k.get('keyword', '') for k in hit_keywords[:3]] if hit_keywords else []
                error_msg = f"广告消息（权重:{ad_weight:.1f}, 关键词:{','.join(keyword_names)}）"

                if is_auto_forward:
                    # 自动转发：在消息头部添加提示，并更新到Redis
                    original_content = message.get('filtered_content') or message.get('content', '')
                    updated_content = f"🚫 疑似广告，请人工审核\n{error_msg}\n\n{original_content}"

                    redis_manager.update_message(channel_id, msg_id, {
                        'filtered_content': updated_content,
                        'auto_forwarder_status': False,
                        'auto_forward_error': error_msg
                    })

                    logger.info(f"自动转发检测到广告消息，已标记: {message_id}")
                    return {
                        "success": False,
                        "error": "ad_detected",
                        "message": error_msg,
                        "message_id": message_id
                    }
                else:
                    # 手动发布：直接返回错误
                    return {
                        "success": False,
                        "error": "ad_detected",
                        "message": f"广告消息不能发布，{error_msg}",
                        "message_id": message_id
                    }

            # 2.2 检查内容长度（包含频道落款）
            content = message.get('filtered_content') or message.get('content', '')

            # 获取字符限制配置（支持会员等级）
            from app.services.config_manager import config_manager

            # 检查是否为Premium账号
            is_premium = await config_manager.get_config('telegram.is_premium', False)

            # 根据Premium状态选择字符限制
            if is_premium:
                max_message_length = await config_manager.get_config('telegram.max_message_length_vip', 2048)
                logger.debug(f"使用Premium字符限制: {max_message_length}字")
            else:
                max_message_length = await config_manager.get_config('telegram.max_message_length', 1024)
                logger.debug(f"使用普通用户字符限制: {max_message_length}字")

            # 计算落款长度（不实际添加footer，避免重复日志）
            footer_config = await config_manager.get_config("target.signature", "")
            footer_length = 0
            if footer_config:
                # 计算落款长度：\n\n + 处理换行符后的落款
                footer_text = "\n\n" + footer_config.replace("\\n", "\n")
                footer_length = len(footer_text)

            # 检查加上落款后的总长度
            final_length = len(content) + footer_length
            if final_length > max_message_length:
                max_content_length = max_message_length - footer_length

                error_msg = f"超过{max_message_length}字符限制（内容{len(content)}字+落款{footer_length}字={final_length}字）"
                detail_msg = f"请将内容缩减至{max_content_length}字以内"

                if is_auto_forward:
                    # 自动转发：不截断文本，保持原始内容让用户编辑
                    updated_content = f"⚠️ 消息内容超长，请手动编辑\n{error_msg}\n{detail_msg}\n\n{content}"

                    redis_manager.update_message(channel_id, msg_id, {
                        'filtered_content': updated_content,
                        'auto_forwarder_status': False,
                        'auto_forward_error': f"{error_msg}，{detail_msg}"
                    })

                    logger.info(f"自动转发检测到超长消息，已标记: {message_id}")
                    return {
                        "success": False,
                        "error": "content_too_long",
                        "message": error_msg,
                        "detail": detail_msg,
                        "message_id": message_id,
                        "content_length": len(content),
                        "footer_length": footer_length,
                        "total_length": final_length,
                        "max_allowed": max_content_length,
                        "limit": max_message_length
                    }
                else:
                    # 手动发布：返回详细错误
                    return {
                        "success": False,
                        "error": "content_too_long",
                        "message": f"消息{error_msg}",
                        "detail": detail_msg,
                        "message_id": message_id,
                        "content_length": len(content),
                        "footer_length": footer_length,
                        "total_length": final_length,
                        "max_allowed": max_content_length,
                        "limit": max_message_length
                    }

            # 2.3 检查内容是否为空（文本和媒体都为空）
            media_url = message.get('media_url')
            media_type = message.get('media_type')
            is_combined = message.get('is_combined', False)

            # 判断消息是否完全为空
            has_content = content.strip() if content else False
            has_media = media_url or media_type or is_combined

            if not has_content and not has_media:
                error_msg = "消息内容为空（无文本无媒体）"

                if is_auto_forward:
                    # 自动转发：直接标记为已处理，避免重试
                    redis_manager.update_message_atomic(message_id, {
                        'auto_forward_processed': True,
                        'auto_forward_process_reason': 'empty_content',
                        'auto_forward_processed_at': datetime.now().isoformat(),
                        'status': 'rejected',
                        'reject_reason': error_msg
                    })
                    logger.info(f"自动转发检测到空消息，已拒绝: {message_id}")

                return {
                    "success": False,
                    "error": "empty_content",
                    "message": f"{error_msg}，无法发布",
                    "message_id": message_id
                }

        # 3. 执行实际转发
        from app.telegram.message_forwarder import message_forwarder
        target_info = await message_forwarder.forward_to_target_with_sender_session(message)

        # 提取返回的信息
        target_link = target_info.get('link') if isinstance(target_info, dict) else target_info
        target_message_id = target_info.get('target_message_id') if isinstance(target_info, dict) else None
        target_message_ids = target_info.get('target_message_ids', []) if isinstance(target_info, dict) else []

        # 4. 更新状态为已发布（区分自动/手动）
        from app.core.message_status import MessageStatus
        new_status = MessageStatus.AUTO_APPROVED.value if is_auto_forward else MessageStatus.MANUAL_APPROVED.value
        redis_manager.update_message_status(message_id, new_status, user_id or "system")

        # 4.5. 如果成功获取到目标消息链接，追加到消息内容并保存完整的目标消息ID信息
        if target_link:
            original_content = message.get('filtered_content') or message.get('content', '')
            updated_content = f"{original_content}\n\n✅ 目标消息链接: {target_link}"

            # 更新消息内容，保存带链接的版本和目标消息ID
            update_data = {
                'filtered_content': updated_content,
                'target_message_link': target_link
            }

            # 保存目标消息ID信息（用于批量删除）
            if target_message_id:
                update_data['target_message_id'] = str(target_message_id)
            if target_message_ids:
                update_data['target_message_ids'] = target_message_ids

            redis_manager.update_message(channel_id, msg_id, update_data)

        # 5. 如果是自动转发成功，清除错误标记
        if is_auto_forward:
            redis_manager.update_message(channel_id, msg_id, {
                'auto_forwarder_status': True,
                'auto_forward_error': None
            })

        # 删除消息发布成功的确认日志
        return {
            "success": True,
            "message": "消息已成功发布到目标频道",
            "message_id": message_id,
            "link": target_link or "",
            "rate_limit_time": getattr(message_forwarder, '_last_wait_time', 0),
            "timestamp": format_for_api(get_current_time())
        }

    except FloodWaitError as e:
        # FloodWait异常特殊处理 - 让上层能够处理重试
        logger.warning(f"发布消息触发FloodWait: {message_id}, 等待时间: {e.seconds}秒")

        if is_auto_forward:
            # 自动转发：标记需要重试，不是永久失败
            try:
                redis_manager.update_message(channel_id, msg_id, {
                    'auto_forwarder_status': False,
                    'auto_forward_error': f"限流等待{e.seconds}秒",
                    'needs_retry': True,
                    'flood_wait_seconds': e.seconds
                })
            except:
                pass

        # 重新抛出异常，让上层处理重试逻辑
        raise

    except ValueError as ve:
        # 处理转发过程中的特定错误
        error_msg = str(ve)

        if is_auto_forward:
            # 自动转发：更新错误信息到消息
            try:
                original_content = message.get('filtered_content') or message.get('content', '')
                updated_content = f"❌ 转发失败\n{error_msg}\n\n{original_content}"

                redis_manager.update_message(channel_id, msg_id, {
                    'filtered_content': updated_content,
                    'auto_forwarder_status': False,
                    'auto_forward_error': error_msg
                })
            except:
                pass

        return {
            "success": False,
            "error": "forward_error",
            "message": error_msg,
            "message_id": message_id
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"发布消息失败: {message_id}, 错误: {error_msg}")

        # 判断是否为系统级错误
        is_system_error = any(keyword in error_msg.lower() for keyword in [
            'session', '连接', 'connect', 'telethon', '网络',
            'network', '认证', 'auth', 'client', '无法连接',
            '客户端', 'runtime', '配置验证失败', '格式无效'
        ])

        if is_auto_forward and not is_system_error:
            # 自动转发且非系统错误：写入错误信息
            try:
                redis_manager.update_message(channel_id, msg_id, {
                    'auto_forwarder_status': False,
                    'auto_forward_error': f"转发错误: {error_msg}"
                })
            except:
                pass
        elif is_auto_forward and is_system_error:
            # 系统错误：不写入消息，让auto_forwarder重试
            logger.info(f"自动转发遇到系统错误，不写入消息: {message_id}")

        return {
            "success": False,
            "error": "system_error" if is_system_error else "unknown_error",
            "message": error_msg,
            "message_id": message_id
        }

async def _async_publish_with_notify(message_id: str, user_id: str = None):
    """
    异步发布消息并发送WebSocket通知
    """
    try:
        # 通知开始处理
        await _redis_websocket_notify("publish_started", message_id,
                                    "开始处理媒体消息发布...")

        # 调用核心发布方法
        result = await publish_single_message(message_id, user_id, is_auto_forward=False)

        if result['success']:
            # 通知成功
            await _redis_websocket_notify("publish_success", message_id,
                                        result.get('message', "媒体消息发布成功"))
            logger.info(f"异步发布成功: {message_id}")
        else:
            # 通知失败，包含详细错误信息
            error_msg = result.get('message', '发布失败')
            if result.get('detail'):
                error_msg += f" - {result['detail']}"
            await _redis_websocket_notify("publish_failed", message_id,
                                        error_msg, is_final=True)

            # 将消息状态设置为发送失败
            try:
                from app.core.message_status import MessageStatus
                redis_manager.update_message_status(message_id, MessageStatus.SEND_FAILED.value, user_id)
                redis_manager.update_message_field(
                    message_id.split(':')[0], int(message_id.split(':')[1]),
                    'forward_failure_reason', error_msg
                )
            except Exception as status_error:
                logger.error(f"回退消息状态失败: {status_error}")

    except Exception as e:
        logger.error(f"异步发布失败: {message_id}, 错误: {e}")
        # 通知失败
        await _redis_websocket_notify("publish_failed", message_id,
                                    str(e), is_final=True)

async def _redis_websocket_notify(event_type: str, message_id: str, message: str, is_final: bool = False):
    """
    通过Redis Pub/Sub发送WebSocket通知（跨进程通信）
    """
    try:
        import json
        from datetime import datetime
        
        # 构造通知数据（格式与现有通知保持一致）
        notification_data = {
            "type": event_type,
            "message_id": message_id,
            "message": message,
            "timestamp": get_current_time().isoformat(),
            "is_final": is_final
        }
        
        # 构造完整的WebSocket消息格式
        websocket_message = {
            "type": event_type,
            "data": notification_data,
            "timestamp": get_current_time().isoformat()
        }
        
        # 发布到Redis频道（跨进程通信）
        redis_client = redis_manager.client
        if redis_client:
            message_json = json.dumps(websocket_message, ensure_ascii=False)
            redis_client.publish("websocket:broadcast", message_json)
            logger.info(f"📡 已发布直接转发通知到Redis频道: {message_id} - {event_type}")
        else:
            logger.error("Redis客户端不可用，无法发送WebSocket通知")
            
    except Exception as e:
        logger.error(f"发送Redis WebSocket通知失败: {e}")


# ================================
