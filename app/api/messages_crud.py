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

from app.storage.redis_manager import redis_manager
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.services.channel_manager import ChannelManager
from app.core.media_paths import media_paths
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
    """检查权限装饰器 - 真正的权限验证"""
    def decorator(func):
        import functools
        
        # 获取函数签名，找到用户参数
        import inspect
        sig = inspect.signature(func)
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取用户参数
            user = None
            
            # 首先尝试从kwargs获取
            if 'user' in kwargs:
                user = kwargs.get('user')
            
            # 如果kwargs中没有，尝试从args中根据参数位置获取
            if not user and args:
                # 获取所有参数名的列表
                param_names = list(sig.parameters.keys())
                # 查找user参数的位置
                if 'user' in param_names:
                    user_index = param_names.index('user')
                    # 如果args有足够的参数
                    if len(args) > user_index:
                        user = args[user_index]
            
            if not user:
                # 添加调试信息
                logger.error(f"权限检查失败: 无法获取用户信息. 函数: {func.__name__}, args数量: {len(args)}, kwargs: {kwargs.keys()}")
                raise HTTPException(status_code=401, detail="用户认证信息缺失")
            
            try:
                auth_service = get_auth_service()
                # 超级管理员拥有所有权限
                if user.get('is_super_admin'):
                    return await func(*args, **kwargs)
                
                # 检查具体权限
                has_permission = await auth_service.check_permission(
                    user.get('token', ''), permission_name
                )
                
                if not has_permission:
                    logger.warning(f"用户 {user.get('username')} 缺少权限: {permission_name}")
                    raise HTTPException(
                        status_code=403, 
                        detail=f"缺少必要权限: {permission_name}"
                    )
                
                return await func(*args, **kwargs)
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"权限检查失败: {e}")
                raise HTTPException(status_code=500, detail="权限检查系统错误")
        
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
        redis_store = redis_manager
        
        # 计算分页参数
        offset = (page - 1) * page_size
        
        # 🚀 Linus式性能优化：根据查询类型选择最优方法
        if source_channel:
            # 从指定频道获取消息
            all_messages = redis_manager.get_messages_by_channel(
                source_channel, 
                limit=page_size,
                offset=offset
            )
        else:
            # 🚀 Linus式统一逻辑：消除特殊情况
            if status in ["pending", "approved", "rejected"]:
                all_messages = redis_manager.get_messages_by_status(status, limit=page_size, offset=offset)
            else:
                # 无状态筛选时，默认显示待审核消息
                all_messages = redis_manager.get_messages_by_status("pending", limit=page_size, offset=offset)
        
        # 🚀 性能优化：简化过滤逻辑（单独消息已清理，无需去重）
        filtered_messages = []
        
        # 单次遍历：应用基础过滤条件
        for msg in all_messages:
            # Linus式防护：确保msg是字典类型，避免字符串.get()错误
            if not isinstance(msg, dict):
                logger.warning(f"跳过非字典类型消息数据: {type(msg)} - {str(msg)[:100]}...")
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
        
        # 🗑️ 不再需要处理媒体组标记 - 现在单独存储
        
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
                message['media_display_url'] = media_paths.get_temp_media_url(
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
                        media_item['display_url'] = media_paths.get_temp_media_url(
                            os.path.basename(media_item['media_path'])
                        )
                    media_group_display.append(media_item)
                
                message['media_group_display'] = media_group_display
                
                # 为组合消息设置media_type（如果没有的话）
                if not message.get('media_type') and media_group_display:
                    # 使用第一个媒体的类型作为整体类型
                    message['media_type'] = media_group_display[0].get('media_type')
            
            # 兼容处理：如果已有media_group_display，更新其display_url
            elif message.get('media_group_display'):
                for media in message['media_group_display']:
                    if media.get('media_path'):
                        media['display_url'] = media_paths.get_temp_media_url(
                            os.path.basename(media['media_path'])
                        )
            
            # 🚀 性能优化：单独消息已清理，重复消息处理大幅简化
            if message.get('duplicate_original_id'):
                try:
                    # 直接查询原始消息（不再需要缓存，因为数据量大幅减少）
                    original_message = redis_manager.get_message_by_id(message['duplicate_original_id'])
                    if original_message:
                        # 处理原始消息的单个媒体URL（支持多种字段名）
                        original_media_path = original_message.get('media_path') or original_message.get('media_url')
                        if original_media_path:
                            original_message['media_display_url'] = media_paths.get_temp_media_url(
                                os.path.basename(original_media_path)
                            )
                            original_message['media_path'] = original_media_path
                        
                        # 处理原始消息的组合媒体
                        if original_message.get('media_group'):
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
                                if media_item.get('media_path'):
                                    media_item['display_url'] = media_paths.get_temp_media_url(
                                        os.path.basename(media_item['media_path'])
                                    )
                                media_group_display.append(media_item)
                            
                            original_message['media_group_display'] = media_group_display
                            if not original_message.get('media_type') and media_group_display:
                                original_message['media_type'] = media_group_display[0].get('media_type')
                        
                        # 兼容处理：如果已有media_group_display，更新其display_url
                        elif original_message.get('media_group_display'):
                            for media in original_message['media_group_display']:
                                if media.get('media_path'):
                                    media['display_url'] = media_paths.get_temp_media_url(
                                        os.path.basename(media['media_path'])
                                    )
                        
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
        redis_store = redis_manager
        message = redis_manager.get_message_by_id(message_id)
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
                    media_item['display_url'] = media_paths.get_temp_media_url(
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
                    media['display_url'] = media_paths.get_temp_media_url(
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
    redis_store = redis_manager
    message = redis_manager.get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    # 通过队列异步转发消息到目标频道
    try:
        from app.services.message_forward_queue import forward_queue
        import asyncio
        
        # 提交转发任务到队列
        task_id = await forward_queue.submit_forward_task(message_id, "forward_to_target")
        logger.info(f"发布任务已提交到队列: {message_id}, 任务ID: {task_id}")
        
        # 等待任务结果（短超时，避免阻塞用户响应）
        task_result = await forward_queue.get_task_result(message_id, timeout=5)
        
        if task_result:
            if task_result.get("success"):
                # 任务成功，更新状态为已发布
                redis_manager.update_message_status(message_id, "approved", user_id)
                logger.info(f"消息发布成功: {message_id}")
            else:
                # 任务失败
                error_msg = task_result.get("error_message", "未知错误")
                logger.error(f"消息发布失败: {message_id}, 错误: {error_msg}")
                return {
                    "success": False,
                    "message": f"消息发布失败: {error_msg}",
                    "timestamp": format_for_api(get_current_time())
                }
        else:
            # 任务还在处理中或超时，先更新为处理中状态
            redis_manager.update_message_status(message_id, "processing", user_id)
            logger.info(f"消息发布任务处理中: {message_id}")
            
    except Exception as e:
        logger.error(f"提交发布任务失败: {message_id}, 错误: {e}")
        return {
            "success": False,
            "message": f"提交发布任务失败: {str(e)}",
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
        redis_store = redis_manager
        message = redis_manager.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 更新消息状态为已拒绝
        success = redis_manager.update_message_status(message_id, "rejected", user.get('user_id'))
        if not success:
            raise HTTPException(status_code=500, detail="拒绝消息失败")
        
        # 如果有拒绝原因，单独更新
        if reason:
            # 解析消息ID获取channel_id和msg_id
            if ':' in message_id:
                channel_id, msg_id = message_id.rsplit(':', 1)
                redis_manager.update_message(channel_id, int(msg_id), {"rejection_reason": reason})
        
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

@router.post(ROUTES.messages.restore)
@check_permission("message.restore")
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
        redis_store = redis_manager
        message = redis_manager.get_message_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 删除消息
        success = redis_manager.delete_message(message_id)
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
        logger.info(f"开始编辑消息: {message_id}, 请求数据: {request}")
        
        # 验证请求数据
        if not request:
            raise HTTPException(status_code=400, detail="请求数据为空")
            
        if "content" not in request and "filtered_content" not in request:
            raise HTTPException(status_code=400, detail="没有提供要更新的内容")
        
        # 验证消息ID格式
        if not message_id or ':' not in message_id:
            logger.error(f"消息ID格式错误: {message_id}")
            raise HTTPException(status_code=400, detail="消息ID格式错误，应为 'channel:message_id'")
        
        # 调用更新方法
        result = await update_message(message_id, user, request)
        logger.info(f"消息编辑成功: {message_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"编辑消息失败: {message_id}, 错误: {e}")
        import traceback
        logger.error(f"编辑消息异常堆栈: {traceback.format_exc()}")
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
    重新获取消息的媒体文件（通过队列异步处理）
    """
    try:
        # 验证消息ID格式
        if ':' not in message_id:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 使用媒体补抓服务提交任务到队列
        from app.services.media_refetch_service import media_refetch_service
        task_id = media_refetch_service.submit_task(message_id)
        
        logger.info(f"媒体补抓任务已提交: {task_id} for message {message_id}")
        
        return {
            "success": True,
            "message": "媒体补抓任务已提交到队列",
            "task_id": task_id,
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交媒体补抓任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"提交媒体补抓任务失败: {str(e)}")

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
        redis_store = redis_manager
        message = redis_manager.get_message_by_id(message_id)
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