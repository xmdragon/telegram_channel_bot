"""
消息管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.utils.timezone import get_current_time, format_for_api
import os
import logging

from app.storage.redis_store import get_redis_message_store
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.services.channel_manager import ChannelManager

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
    async def permission_checker(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> Dict[str, Any]:
        if not credentials:
            raise HTTPException(status_code=401, detail="未授权访问")
        
        try:
            auth_service = get_auth_service()
            user = await auth_service.get_current_user(credentials.credentials)
            if not user:
                raise HTTPException(status_code=401, detail="未授权访问")
            
            has_permission = await auth_service.check_permission(credentials.credentials, permission_name)
            if not has_permission:
                raise HTTPException(status_code=403, detail=f"缺少权限: {permission_name}")
            
            return user
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"权限检查失败: {e}")
            raise HTTPException(status_code=500, detail="权限检查失败")
    
    return permission_checker

# 导入媒体处理器
from app.services.media_handler import media_handler
from app.telegram.bot import telegram_bot

@router.get("/")
async def get_messages(
    status: Optional[str] = Query(None, description="消息状态过滤"),
    source_channel: Optional[str] = Query(None, description="源频道过滤"),
    is_ad: Optional[bool] = Query(None, description="是否为广告"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: Dict[str, Any] = Depends(check_permission("messages.view")),
    message_processor: MessageProcessor = Depends(get_message_processor),
    channel_manager: ChannelManager = Depends(get_channel_manager)
):
    """获取消息列表"""
    try:
        redis_store = get_redis_message_store()
        
        # 实现完整的消息查询功能
        if source_channel:
            # 从指定频道获取消息
            all_messages = redis_store.get_messages_by_channel(
                source_channel, 
                limit=size * 20  # 获取更多数据用于过滤和分页
            )
        else:
            # 根据状态获取消息
            if status == "pending":
                all_messages = redis_store.get_pending_messages(limit=size * 20)
            elif status == "approved":
                all_messages = redis_store.get_messages_by_status("approved", limit=size * 20)
            elif status == "rejected":
                all_messages = redis_store.get_messages_by_status("rejected", limit=size * 20)
            elif status == "auto_forwarded":
                all_messages = redis_store.get_messages_by_status("auto_forwarded", limit=size * 20)
            else:
                # 无状态过滤或其他状态，获取所有消息
                all_messages = redis_store.get_all_messages(limit=size * 20)
        
        # 应用过滤条件
        filtered_messages = []
        for msg in all_messages:
            # 状态过滤
            if status and msg.get('status') != status:
                continue
            
            # 广告过滤
            if is_ad is not None:
                msg_is_ad = msg.get('is_ad', False)
                if isinstance(msg_is_ad, str):
                    msg_is_ad = msg_is_ad.lower() == 'true'
                if msg_is_ad != is_ad:
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
        start_idx = (page - 1) * size
        end_idx = start_idx + size
        page_messages = filtered_messages[start_idx:end_idx]
        
        # 获取频道信息映射
        channel_info = await channel_manager.get_channel_info_for_display()
        
        # 处理消息列表，检查媒体文件存在性
        processed_messages = []
        for msg in page_messages:
            # 为了保持兼容性，生成假的id（使用channel_id:message_id）
            source_channel = msg.get('source_channel')
            message_id = msg.get('message_id')
            
            # 跳过无效的消息
            if not source_channel or not message_id:
                logger.warning(f"跳过无效消息: source_channel={source_channel}, message_id={message_id}")
                continue
                
            msg_id = f"{source_channel}:{message_id}"
            
            # 检查主媒体文件是否存在
            media_display_url = None
            if msg.get('media_url'):
                media_path = msg['media_url']
                if os.path.exists(media_path):
                    media_display_url = f"/temp_media/{os.path.basename(media_path)}"
                else:
                    media_display_url = None
            
            # 处理组合消息的媒体组
            media_group_display = None
            if msg.get('media_group'):
                media_group_display = []
                for media_item in msg['media_group']:
                    item_copy = dict(media_item)
                    if media_item.get('file_path'):
                        if os.path.exists(media_item['file_path']):
                            item_copy['display_url'] = f"/temp_media/{os.path.basename(media_item['file_path'])}"
                        else:
                            item_copy['display_url'] = None
                    else:
                        item_copy['display_url'] = None
                    media_group_display.append(item_copy)
            
            source_channel_key = msg.get('source_channel', '')
            processed_messages.append({
                "id": msg_id,  # 使用复合ID
                "source_channel": source_channel_key,
                "source_channel_title": channel_info.get(source_channel_key, {}).get('title', '未知频道'),
                "source_channel_link_prefix": channel_info.get(source_channel_key, {}).get('link_prefix', ''),
                "content": msg.get('content', ''),
                "filtered_content": msg.get('filtered_content', ''),
                "message_id": msg.get('message_id'),
                "media_type": msg.get('media_type'),
                "media_url": msg.get('media_url'),
                "media_display_url": media_display_url,
                "grouped_id": msg.get('grouped_id'),
                "is_combined": msg.get('is_combined', False),
                "combined_messages": msg.get('combined_messages'),
                "media_group": msg.get('media_group'),
                "media_group_display": media_group_display,
                "status": msg.get('status', 'pending'),
                "is_ad": msg.get('is_ad', False),
                "created_at": msg.get('created_at'),
                "review_time": msg.get('review_time'),
                "reviewed_by": msg.get('reviewed_by'),
                "filter_reason": msg.get('filter_reason'),
                "removed_hidden_links": msg.get('removed_hidden_links')
            })
        
        return {
            "messages": processed_messages,
            "page": page,
            "size": size,
            "total": len(filtered_messages)
        }
        
    except Exception as e:
        logger.error(f"获取消息列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取消息列表失败")

@router.get("/channel-info")
async def get_channel_info(
    channel_manager: ChannelManager = Depends(get_channel_manager)
):
    """获取频道信息映射"""
    try:
        # 使用新的频道信息获取方法
        channel_info = await channel_manager.get_channel_info_for_display()
        
        return {
            "success": True,
            "data": channel_info
        }
    except Exception as e:
        logger.error(f"获取频道信息失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/batch/approve")
async def batch_approve_messages(
    request: dict,
    user: Dict[str, Any] = Depends(check_permission("messages.approve")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """批量批准消息"""
    message_ids = request.get("message_ids", [])
    if not message_ids:
        return {"success": False, "message": "未提供消息ID列表"}
    
    try:
        redis_store = get_redis_message_store()
        reviewer_name = user.get('username', 'Web用户')
        
        # 解析消息ID（从复合ID中提取channel_id和message_id）
        message_tuples = []
        valid_messages = []
        
        for msg_id in message_ids:
            try:
                if ':' in str(msg_id):
                    # 新格式: "channel_id:message_id"
                    channel_id, message_id = str(msg_id).split(':', 1)
                    message_tuples.append((channel_id, int(message_id)))
                else:
                    # 老格式: 纯数字ID（需要从其他地方获取channel_id）
                    # 这里暂时跳过，实际使用中需要处理
                    logger.warning(f"无法解析消息ID格式: {msg_id}")
                    continue
                    
                # 检查消息是否存在且为待审核状态
                msg_data = redis_store.get_message(channel_id, int(message_id))
                if msg_data and msg_data.get('status') == 'pending':
                    valid_messages.append(msg_data)
                
            except (ValueError, IndexError) as e:
                logger.error(f"解析消息ID {msg_id} 失败: {e}")
                continue
        
        if not valid_messages:
            return {"success": False, "message": "没有找到可批准的消息"}
        
        # 批量更新状态
        update_results = await message_processor.batch_update_status(
            message_tuples, "approved", reviewer_name
        )
        
        approved_count = sum(1 for success in update_results.values() if success)
        
        # 批量转发到目标频道
        forwarded_count = 0
        try:
            from app.telegram.bot import telegram_bot
            if telegram_bot and telegram_bot.client:
                from app.telegram.message_forwarder import message_forwarder
                for msg_data in valid_messages:
                    try:
                        # 这里需要将Redis数据转换为适合message_forwarder的格式
                        await message_forwarder.forward_to_target(telegram_bot.client, msg_data)
                        forwarded_count += 1
                    except Exception as e:
                        msg_key = f"{msg_data.get('source_channel')}:{msg_data.get('message_id')}"
                        logger.error(f"转发消息 {msg_key} 失败: {e}")
                
                # 记录用户反馈用于学习
                try:
                    from app.services.adaptive_learning import adaptive_learning
                    for msg_data in valid_messages:
                        msg_key = f"{msg_data.get('source_channel')}:{msg_data.get('message_id')}"
                        try:
                            await adaptive_learning.learn_from_user_action(msg_key, 'approved', reviewer_name)
                        except Exception as e:
                            logger.debug(f"记录学习反馈失败: {e}")
                except ImportError:
                    logger.debug("自适应学习模块未找到")
                
                logger.info(f"批量批准：{approved_count} 条消息已批准，{forwarded_count} 条已转发")
            else:
                logger.warning(f"批量批准：{approved_count} 条消息已批准但无法转发（Telegram客户端未连接）")
        except Exception as e:
            logger.error(f"批量转发消息失败: {e}")
        
        # 广播批量状态更新到WebSocket客户端
        try:
            from app.api.websocket import websocket_manager
            for msg_data in valid_messages:
                msg_key = f"{msg_data.get('source_channel')}:{msg_data.get('message_id')}"
                await websocket_manager.broadcast_message_status_update(msg_key, "approved")
        except Exception as e:
            logger.debug(f"广播批量状态更新失败: {e}")
        
        return {"success": True, "message": f"已批准 {approved_count} 条消息，{forwarded_count} 条已转发"}
        
    except Exception as e:
        logger.error(f"批量批准消息失败: {e}")
        raise HTTPException(status_code=500, detail="批量批准失败")


@router.post("/batch/reject")
async def batch_reject_messages(
    request: dict,
    user: Dict[str, Any] = Depends(check_permission("messages.reject")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """批量拒绝消息"""
    message_ids = request.get("message_ids", [])
    if not message_ids:
        return {"success": False, "message": "未提供消息ID列表"}
    
    try:
        redis_store = get_redis_message_store()
        reviewer_name = user.get('username', 'Web用户')
        
        # 解析消息ID（从复合ID中提取channel_id和message_id）
        message_tuples = []
        valid_messages = []
        
        for msg_id in message_ids:
            try:
                if ':' in str(msg_id):
                    channel_id, message_id = str(msg_id).split(':', 1)
                    message_tuples.append((channel_id, int(message_id)))
                else:
                    logger.warning(f"无法解析消息ID格式: {msg_id}")
                    continue
                    
                # 检查消息是否存在且为待审核状态
                msg_data = redis_store.get_message(channel_id, int(message_id))
                if msg_data and msg_data.get('status') == 'pending':
                    valid_messages.append(msg_data)
                
            except (ValueError, IndexError) as e:
                logger.error(f"解析消息ID {msg_id} 失败: {e}")
                continue
        
        if not valid_messages:
            return {"success": False, "message": "没有找到可拒绝的消息"}
        
        # 从审核群删除消息和清理媒体文件
        deleted_count = 0
        try:
            from app.telegram.bot import telegram_bot
            if telegram_bot and telegram_bot.client:
                for msg_data in valid_messages:
                    review_message_id = msg_data.get('review_message_id')
                    if review_message_id:
                        try:
                            await telegram_bot.delete_review_message(review_message_id)
                            deleted_count += 1
                        except Exception as e:
                            logger.debug(f"删除审核群消息失败: {e}")
                    
                    # 清理媒体文件
                    try:
                        await telegram_bot._cleanup_message_files(msg_data)
                    except Exception as e:
                        logger.debug(f"清理媒体文件失败: {e}")
        except Exception as e:
            logger.error(f"批量删除审核群消息失败: {e}")
        
        # 批量更新状态
        update_results = await message_processor.batch_update_status(
            message_tuples, "rejected", reviewer_name
        )
        
        rejected_count = sum(1 for success in update_results.values() if success)
        
        # 记录用户反馈用于学习
        try:
            from app.services.adaptive_learning import adaptive_learning
            for msg_data in valid_messages:
                msg_key = f"{msg_data.get('source_channel')}:{msg_data.get('message_id')}"
                try:
                    await adaptive_learning.learn_from_user_action(msg_key, 'rejected', reviewer_name)
                except Exception as e:
                    logger.debug(f"记录学习反馈失败: {e}")
        except ImportError:
            logger.debug("自适应学习模块未找到")
        
        # 广播批量状态更新到WebSocket客户端
        try:
            from app.api.websocket import websocket_manager
            for msg_data in valid_messages:
                msg_key = f"{msg_data.get('source_channel')}:{msg_data.get('message_id')}"
                await websocket_manager.broadcast_message_status_update(msg_key, "rejected")
        except Exception as e:
            logger.debug(f"广播批量状态更新失败: {e}")
        
        logger.info(f"批量拒绝：{rejected_count} 条消息已拒绝，{deleted_count} 条审核群消息已删除")
        
        return {"success": True, "message": f"已拒绝 {rejected_count} 条消息"}
        
    except Exception as e:
        logger.error(f"批量拒绝消息失败: {e}")
        raise HTTPException(status_code=500, detail="批量拒绝失败")


@router.get("/{message_id}")
async def get_message(
    message_id: str,
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """获取单个消息详情"""
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
            msg_data = await message_processor.get_message(channel_id, int(msg_id))
        else:
            # 对于老格式ID，需要更复杂的查找逻辑
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        return {
            "success": True,
            "message": {
                "id": message_id,
                "source_channel": msg_data.get('source_channel'),
                "message_id": msg_data.get('message_id'),
                "content": msg_data.get('content'),
                "filtered_content": msg_data.get('filtered_content'),
                "media_type": msg_data.get('media_type'),
                "media_url": msg_data.get('media_url'),
                "status": msg_data.get('status'),
                "is_ad": msg_data.get('is_ad'),
                "reviewed_by": msg_data.get('reviewed_by'),
                "review_time": msg_data.get('review_time'),
                "forwarded_time": msg_data.get('forwarded_time'),
                "created_at": msg_data.get('created_at'),
                "updated_at": msg_data.get('updated_at')
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取消息失败: {e}")
        raise HTTPException(status_code=500, detail="获取消息失败")

@router.post("/{message_id}/approve")
async def approve_message(
    message_id: str,
    request: dict = None,
    user: Dict[str, Any] = Depends(check_permission("messages.approve")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """批准消息"""
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        if msg_data.get('status') != "pending":
            raise HTTPException(status_code=400, detail="消息状态不允许此操作")
        
        reviewer_name = user.get('username', 'Web用户')
        
        # 更新状态
        success = await message_processor.update_message_status(
            channel_id, int(msg_id), "approved", reviewer_name
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="更新消息状态失败")
        
        # 转发到目标频道
        try:
            logger.info(f"准备转发消息 {message_id} 到目标频道")
            from app.telegram.bot import telegram_bot
            
            if telegram_bot and telegram_bot.client:
                from app.telegram.message_forwarder import message_forwarder
                await message_forwarder.forward_to_target(telegram_bot.client, msg_data)
                
                # 记录用户反馈用于学习
                try:
                    from app.services.adaptive_learning import adaptive_learning
                    await adaptive_learning.learn_from_user_action(message_id, 'approved', reviewer_name)
                except Exception as e:
                    logger.debug(f"记录学习反馈失败: {e}")
                
                logger.info(f"消息 {message_id} 已批准并转发到目标频道")
            else:
                logger.warning(f"消息 {message_id} 已批准但无法转发（Telegram客户端未连接）")
        except Exception as e:
            logger.error(f"转发消息 {message_id} 到目标频道失败: {e}", exc_info=True)
        
        # 广播状态更新到WebSocket客户端
        try:
            from app.api.websocket import websocket_manager
            await websocket_manager.broadcast_message_status_update(message_id, "approved")
        except Exception as e:
            logger.debug(f"广播状态更新失败: {e}")
        
        return {"success": True, "message": "消息已批准"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批准消息失败: {e}")
        raise HTTPException(status_code=500, detail="批准消息失败")

@router.post("/{message_id}/reject")
async def reject_message(
    message_id: str,
    request: dict = None,
    user: Dict[str, Any] = Depends(check_permission("messages.reject")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """拒绝消息"""
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        if msg_data.get('status') != "pending":
            raise HTTPException(status_code=400, detail="消息状态不允许此操作")
        
        reviewer_name = user.get('username', 'Web用户')
        reason = request.get('reason') if request else None
        
        # 从审核群删除消息
        try:
            from app.telegram.bot import telegram_bot
            review_message_id = msg_data.get('review_message_id')
            if telegram_bot and telegram_bot.client and review_message_id:
                await telegram_bot.delete_review_message(review_message_id)
                
                # 清理媒体文件
                await telegram_bot._cleanup_message_files(msg_data)
        except Exception as e:
            logger.debug(f"删除审核群消息失败: {e}")
        
        # 更新状态
        success = await message_processor.update_message_status(
            channel_id, int(msg_id), "rejected", reviewer_name
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="更新消息状态失败")
        
        # 记录用户反馈用于学习
        try:
            from app.services.adaptive_learning import adaptive_learning
            await adaptive_learning.learn_from_user_action(message_id, 'rejected', reviewer_name)
        except Exception as e:
            logger.debug(f"记录学习反馈失败: {e}")
        
        # 广播状态更新到WebSocket客户端
        try:
            from app.api.websocket import websocket_manager
            await websocket_manager.broadcast_message_status_update(message_id, "rejected")
        except Exception as e:
            logger.debug(f"广播状态更新失败: {e}")
        
        return {"success": True, "message": "消息已拒绝"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"拒绝消息失败: {e}")
        raise HTTPException(status_code=500, detail="拒绝消息失败")

@router.post("/{message_id}/publish")
async def publish_message(
    message_id: str,
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """发布消息到目标频道"""
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 直接使用批准接口的功能，该接口已经包含了转发功能
        return await approve_message(message_id, None, {"username": "Web用户"}, message_processor)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发布消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"发布失败: {str(e)}")

@router.post("/{message_id}/edit-publish")
async def edit_and_publish_message(
    message_id: str,
    request: dict,
    user: Dict[str, Any] = Depends(check_permission("messages.edit")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """编辑消息内容"""
    try:
        logger.info(f"编辑消息请求: message_id={message_id}, user={user.get('username', 'unknown')}")
        logger.debug(f"请求内容: {request}")
        
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
            logger.debug(f"解析消息ID: channel_id={channel_id}, msg_id={msg_id}")
        else:
            error_msg = f"不支持的消息ID格式: {message_id}"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        
        # 验证解析后的ID
        if not channel_id or not msg_id or msg_id == 'None':
            error_msg = f"无效的消息ID组件: channel_id='{channel_id}', msg_id='{msg_id}'"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=f"无效的消息ID: {message_id}")
        
        # 转换消息ID为整数
        try:
            msg_id_int = int(msg_id)
            logger.debug(f"消息ID转换成功: {msg_id_int}")
        except ValueError as e:
            error_msg = f"消息ID不是有效数字: '{msg_id}' - {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=f"消息ID必须是数字: {msg_id}")
        
        # 获取消息
        logger.info(f"正在获取消息: {channel_id}:{msg_id_int}")
        msg_data = await message_processor.get_message(channel_id, msg_id_int)
        
        if not msg_data:
            # 尝试直接从Redis再次获取以获得更多信息
            redis_store = get_redis_message_store()
            raw_data = redis_store.redis.hgetall(f"msg:{channel_id}:{msg_id_int}")
            
            if raw_data:
                logger.error(f"消息存在于Redis但get_message返回None: {channel_id}:{msg_id_int}")
                logger.debug(f"Redis原始数据字段: {list(raw_data.keys())}")
                error_msg = f"消息数据损坏，无法编辑: {channel_id}:{msg_id_int}"
            else:
                logger.error(f"消息在Redis中不存在: {channel_id}:{msg_id_int}")
                error_msg = f"消息不存在: {channel_id}:{msg_id_int}"
            
            raise HTTPException(status_code=404, detail=error_msg)
        
        logger.info(f"成功获取消息: {channel_id}:{msg_id_int}, 状态: {msg_data.get('status', 'unknown')}")
        
        # 更新消息内容
        new_content = request.get("content", "").strip()
        logger.debug(f"新内容长度: {len(new_content)}")
        
        # 检查是否有媒体文件
        has_media = bool(msg_data.get('media_type') and msg_data.get('media_url')) or bool(msg_data.get('is_combined') and msg_data.get('media_group'))
        logger.debug(f"是否有媒体: {has_media}")
        
        # 如果没有媒体文件且内容为空，返回错误
        if not new_content and not has_media:
            error_msg = "纯文本消息内容不能为空"
            logger.warning(error_msg)
            return {"success": False, "message": error_msg}
        
        # 更新Redis中的数据
        redis_store = get_redis_message_store()
        msg_key = f"msg:{channel_id}:{msg_id_int}"
        update_data = {
            'filtered_content': new_content,
            'updated_at': get_current_time().isoformat()
        }
        
        try:
            redis_store.redis.hset(msg_key, mapping=update_data)
            logger.info(f"成功更新Redis消息内容: {message_id}")
        except Exception as redis_e:
            logger.error(f"更新Redis失败: {redis_e}")
            raise HTTPException(status_code=500, detail=f"数据库更新失败: {str(redis_e)}")
        
        # 尝试更新审核群消息（如果存在）
        review_message_id = msg_data.get('review_message_id')
        if review_message_id:
            try:
                from app.telegram.bot import telegram_bot
                if telegram_bot and telegram_bot.client:
                    # 更新消息数据后传给update_review_message
                    updated_msg_data = dict(msg_data)
                    updated_msg_data['filtered_content'] = new_content
                    await telegram_bot.update_review_message(updated_msg_data)
                    logger.info(f"已更新审核群消息: {message_id}")
                else:
                    logger.warning("Telegram客户端未连接，跳过审核群消息更新")
            except Exception as e:
                logger.warning(f"更新审核群消息失败，但不影响编辑: {e}")
        
        logger.info(f"消息编辑完成: {message_id}")
        return {"success": True, "message": "消息已编辑", "content": new_content}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"编辑消息 {message_id} 时发生未预期错误: {e}", exc_info=True)
        return {"success": False, "message": f"编辑失败: 系统内部错误"}


@router.get("/stats/overview")
async def get_message_stats(
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """获取消息统计概览"""
    try:
        stats = await message_processor.get_message_stats()
        return stats
    except Exception as e:
        logger.error(f"获取消息统计失败: {e}")
        return {
            "total": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "ads": 0,
            "duplicates": 0,
            "channels": 0,
            "auto_forwarded": 0
        }

@router.delete("/{message_id}/review-message")
async def delete_review_message(
    message_id: str,
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """删除审核群中的消息"""
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        review_message_id = msg_data.get('review_message_id')
        if not review_message_id:
            return {"success": True, "message": "消息没有审核群消息ID"}
        
        try:
            from app.telegram.bot import telegram_bot
            if telegram_bot and telegram_bot.client:
                await telegram_bot.delete_review_message(review_message_id)
                return {"success": True, "message": "审核群消息已删除"}
            else:
                return {"success": False, "message": "Telegram客户端未连接"}
        except Exception as e:
            logger.error(f"删除审核群消息失败: {e}")
            return {"success": False, "message": f"删除失败: {str(e)}"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除审核群消息失败: {e}")
        raise HTTPException(status_code=500, detail="删除审核群消息失败")


@router.post("/{message_id}/refetch-media")
async def refetch_media(
    message_id: str,
    user: Dict[str, Any] = Depends(check_permission("channels.refetch")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    重新抓取消息的媒体文件
    用于补抓缺失或损坏的媒体
    """
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息记录
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 检查是否有媒体
        if not msg_data.get('media_type'):
            return {
                "success": False,
                "message": "该消息没有媒体文件"
            }
        
        # 检查媒体文件是否已存在
        media_url = msg_data.get('media_url')
        if media_url and os.path.exists(media_url):
            file_size = os.path.getsize(media_url)
            if file_size > 0:
                return {
                    "success": True,
                    "message": "媒体文件已存在",
                    "media_url": media_url,
                    "file_size": file_size,
                    "skipped": True
                }
        
        # 检查Telegram客户端
        from app.telegram.client_manager import client_manager
        client = await client_manager.get_client()
        
        if not client or not client.is_connected():
            return {
                "success": False,
                "message": "Telegram客户端未连接"
            }
        
        # 获取原始消息
        try:
            # 尝试从源频道获取消息
            source_entity = await client.get_entity(int(msg_data['source_channel']))
            original_msg = await client.get_messages(
                entity=source_entity,
                ids=int(msg_data['message_id'])
            )
            
            if not original_msg or not original_msg.media:
                return {
                    "success": False,
                    "message": "原始消息不存在或没有媒体"
                }
            
            # 下载媒体文件
            logger.info(f"开始补抓消息 #{message_id} 的媒体文件")
            
            from app.services.media_handler import media_handler
            media_info = await media_handler.download_media(
                client=client,
                message=original_msg,
                message_id=message.id,
                timeout=120.0  # 给更长的超时时间
            )
            
            if media_info and media_info.get("file_path"):
                # 更新Redis记录
                redis_store = get_redis_message_store()
                msg_key = f"msg:{channel_id}:{msg_id}"
                update_data = {
                    'media_url': media_info["file_path"],
                    'media_type': media_info.get("media_type", msg_data.get('media_type')),
                    'media_hash': media_info.get("hash", ''),
                    'visual_hash': json.dumps(media_info.get("visual_hashes", {})) if media_info.get("visual_hashes") else '',
                    'updated_at': get_current_time().isoformat()
                }
                redis_store.redis.hset(msg_key, mapping=update_data)
                
                logger.info(f"成功补抓媒体: {media_info['file_path']} ({media_info['file_size']} bytes)")
                
                # 如果是广告，自动保存到训练数据目录并更新图片索引
                if msg_data.get('is_ad'):
                    try:
                        from app.services.training_media_manager import training_media_manager
                        from app.services.ad_image_detector import ad_image_detector
                        
                        saved_path = await training_media_manager.save_training_media(
                            source_path=media_info["file_path"],
                            message_id=f"{channel_id}:{msg_id}",
                            media_type=media_info["media_type"],
                            channel_id=channel_id,
                            is_ad=True
                        )
                        if saved_path:
                            logger.info(f"广告媒体已保存到训练目录: {saved_path}")
                            
                            # 如果是图片，添加到广告图片索引
                            if media_info["media_type"].startswith("image"):
                                await ad_image_detector.add_ad_image(
                                    saved_path,
                                    metadata={
                                        'message_id': f"{channel_id}:{msg_id}",
                                        'channel_id': channel_id
                                    }
                                )
                                logger.info(f"广告图片已添加到检测索引")
                    except Exception as e:
                        logger.error(f"保存到训练目录失败: {e}")
                
                return {
                    "success": True,
                    "message": "媒体补抓成功",
                    "media_url": media_info["file_path"],
                    "media_type": media_info["media_type"],
                    "file_size": media_info["file_size"],
                    "refetched": True
                }
            else:
                return {
                    "success": False,
                    "message": "媒体下载失败"
                }
                
        except Exception as e:
            logger.error(f"补抓媒体失败: {e}")
            return {
                "success": False,
                "message": f"补抓失败: {str(e)}"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"补抓媒体出错: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/refetch-media")
async def batch_refetch_media(
    request: dict,
    user: Dict[str, Any] = Depends(check_permission("channels.refetch")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    批量补抓媒体文件
    """
    message_ids = request.get("message_ids", [])
    results = {
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "details": []
    }
    
    for msg_id in message_ids:
        try:
            # 调用单个补抓接口
            result = await refetch_media(str(msg_id), user, message_processor)
            if result["success"]:
                if result.get("skipped"):
                    results["skipped"] += 1
                else:
                    results["success"] += 1
            else:
                results["failed"] += 1
            
            results["details"].append({
                "message_id": msg_id,
                **result
            })
        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "message_id": msg_id,
                "success": False,
                "message": str(e)
            })
    
    return results

@router.post("/{message_id}/filter-tail")
async def filter_message_tail(
    message_id: str,
    user: Dict[str, Any] = Depends(check_permission("filter.execute")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    对单条消息执行尾部过滤
    """
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 获取原始内容（如果没有原始内容，使用当前内容）
        original_content = msg_data.get('content') or msg_data.get('filtered_content')
        
        if not original_content:
            return {
                "success": False,
                "message": "消息没有内容可以过滤"
            }
        
        # 执行尾部过滤 - 使用新的FilterPipeline架构
        from app.services.filters.tail_filter import TailFilter
        from app.services.filters.base import FilterContext
        from datetime import datetime
        
        # 创建过滤器上下文
        context = FilterContext(
            message_id=int(msg_id),
            channel_id=int(channel_id),
            timestamp=datetime.now().timestamp(),
            message_type=msg_data.get('media_type', 'text')
        )
        
        # 添加元数据
        context.add_metadata('is_history', False)
        context.add_metadata('message_obj', msg_data)
        
        # 初始化尾部过滤器
        tail_filter = TailFilter({
            'intelligent_threshold': 0.6,
            'semantic_threshold': 0.45,  # 稍微降低阈值以提高检测敏感度
            'enable_intelligent': True,
            'enable_semantic': True
        })
        
        # 执行过滤
        filter_result = await tail_filter.filter(original_content, context)
        
        # 提取结果
        filtered_content = filter_result.filtered_content
        has_tail = not filter_result.passed or len(filtered_content) < len(original_content)
        removed_tail = filter_result.details.get('removed_tail', '')
        
        # 如果没有移除内容，计算移除的部分
        if not removed_tail and has_tail:
            removed_tail = original_content[len(filtered_content):].strip()
        
        # 更新过滤后的内容
        if has_tail:
            redis_store = get_redis_message_store()
            msg_key = f"msg:{channel_id}:{msg_id}"
            update_data = {
                'filtered_content': filtered_content,
                'updated_at': get_current_time().isoformat()
            }
            redis_store.redis.hset(msg_key, mapping=update_data)
            
            # 保存尾部训练数据到文件
            if removed_tail:
                import json
                from datetime import datetime
                from app.core.path_config import PathConfig
                
                # 加载现有数据
                tail_file = str(PathConfig.TAIL_FILTER_SAMPLES_FILE)
                try:
                    with open(tail_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        samples = data.get('samples', [])
                except:
                    samples = []
                
                # 简化的样本结构 - 只保留尾部
                new_sample = {
                    "id": len(samples) + 1,
                    "tail_part": removed_tail,  # 只保留尾部内容
                    "created_at": datetime.now().isoformat()
                }
                samples.append(new_sample)
                
                # 保存更新后的数据
                with open(tail_file, 'w', encoding='utf-8') as f:
                    json.dump({"samples": samples}, f, ensure_ascii=False, indent=2)
                
                # 自动学习已禁用，只保存样本到文件，不触发智能学习
                # 智能学习仅通过用户手动训练触发
                logger.info(f"已保存尾部训练数据（自动学习已禁用）")
            
            # 广播消息更新到WebSocket客户端
            try:
                from app.api.websocket import websocket_manager
                # 构建更新的消息数据
                message_data = {
                    "id": message_id,
                    "filtered_content": filtered_content,
                    "updated_at": get_current_time().isoformat()
                }
                await websocket_manager.broadcast_message_update(message_id, message_data)
                logger.info(f"已广播消息 {message_id} 的更新到WebSocket客户端")
            except Exception as e:
                logger.debug(f"广播消息更新失败: {e}")
            
            # 获取过滤器详细信息
            filter_method = filter_result.details.get('filter_method', 'unknown')
            confidence = filter_result.confidence
            processing_time = filter_result.processing_time_ms
            
            logger.info(f"消息 {message_id} 尾部过滤成功，方法: {filter_method}, 置信度: {confidence:.3f}, "
                       f"移除了 {len(removed_tail)} 个字符, 处理时间: {processing_time:.1f}ms")
            
            return {
                "success": True,
                "message": f"尾部过滤成功 ({filter_method})",
                "original_length": len(original_content),
                "filtered_length": len(filtered_content),
                "removed_length": len(removed_tail) if removed_tail else 0,
                "filtered_content": filtered_content,
                "removed_tail": removed_tail,
                "filter_method": filter_method,
                "confidence": confidence,
                "processing_time_ms": processing_time,
                "filter_details": filter_result.details
            }
        else:
            # 获取过滤器详细信息（即使没有过滤）
            filter_method = filter_result.details.get('filter_method', 'none')
            confidence = filter_result.confidence
            processing_time = filter_result.processing_time_ms
            
            logger.info(f"消息 {message_id} 未检测到尾部内容，方法: {filter_method}, "
                       f"置信度: {confidence:.3f}, 处理时间: {processing_time:.1f}ms")
            
            return {
                "success": True,
                "message": f"未检测到需要过滤的尾部内容 ({filter_method})",
                "original_length": len(original_content),
                "filtered_length": len(original_content),
                "removed_length": 0,
                "filtered_content": original_content,
                "removed_tail": "",
                "filter_method": filter_method,
                "confidence": confidence,
                "processing_time_ms": processing_time,
                "filter_details": filter_result.details
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"尾部过滤失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{message_id}/feedback")
async def record_filter_feedback(
    message_id: str,
    feedback_data: Dict[str, Any],
    user: Dict[str, Any] = Depends(check_permission("filter.feedback")),
):
    """
    记录过滤器反馈
    
    Request body:
    {
        "filter_name": "tail_filter",
        "metric_name": "intelligent", 
        "action": "approve|reject|correct",
        "predicted_score": 0.65,
        "actual_result": "positive|negative",
        "threshold_used": 0.6,
        "comments": "用户备注"
    }
    """
    try:
        # 验证必需参数
        required_fields = ['filter_name', 'metric_name', 'action', 'predicted_score', 'actual_result']
        for field in required_fields:
            if field not in feedback_data:
                raise HTTPException(status_code=400, detail=f"缺少必需字段: {field}")
        
        # 导入阈值管理器
        from app.core.threshold_manager import threshold_manager
        
        filter_name = feedback_data['filter_name']
        metric_name = feedback_data['metric_name']
        predicted_score = float(feedback_data['predicted_score'])
        actual_result = feedback_data['actual_result']
        threshold_used = feedback_data.get('threshold_used')
        action = feedback_data['action']
        comments = feedback_data.get('comments', '')
        
        # 验证数值范围
        if not 0.0 <= predicted_score <= 1.0:
            raise HTTPException(status_code=400, detail="predicted_score必须在0.0-1.0之间")
        
        if actual_result not in ['positive', 'negative']:
            raise HTTPException(status_code=400, detail="actual_result必须是'positive'或'negative'")
        
        if action not in ['approve', 'reject', 'correct']:
            raise HTTPException(status_code=400, detail="action必须是'approve'、'reject'或'correct'")
        
        # 记录反馈
        threshold_manager.record_feedback(
            filter_name=filter_name,
            metric_name=metric_name,
            predicted_score=predicted_score,
            actual_result=actual_result,
            threshold_used=threshold_used
        )
        
        # 记录审核日志
        logger.info(f"📝 过滤器反馈 - 用户: {user.get('name', 'unknown')}, "
                   f"过滤器: {filter_name}.{metric_name}, 动作: {action}, "
                   f"分数: {predicted_score:.3f}, 结果: {actual_result}")
        
        # 获取更新后的统计
        stats = threshold_manager.get_all_stats()
        current_config = stats.get(filter_name, {}).get(metric_name, {})
        
        return {
            "success": True,
            "message": "反馈记录成功",
            "data": {
                "message_id": message_id,
                "feedback_recorded": True,
                "current_threshold": current_config.get('current_threshold', 0.5),
                "feedback_count": current_config.get('feedback_count', 0),
                "accuracy": current_config.get('accuracy', 0.0),
                "f1_score": current_config.get('f1_score', 0.0)
            }
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"参数格式错误: {str(e)}")
    except Exception as e:
        logger.error(f"❌ 记录反馈失败: {e}")
        raise HTTPException(status_code=500, detail=f"记录反馈失败: {str(e)}")


@router.get("/thresholds/stats")
async def get_threshold_stats(
    user: Dict[str, Any] = Depends(check_permission("filter.view"))
):
    """获取所有阈值统计信息"""
    try:
        from app.core.threshold_manager import threshold_manager
        
        stats = threshold_manager.get_all_stats()
        
        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ 获取阈值统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


@router.post("/thresholds/optimize")
async def optimize_thresholds(
    user: Dict[str, Any] = Depends(check_permission("filter.admin"))
):
    """手动触发阈值优化"""
    try:
        from app.core.threshold_manager import threshold_manager
        
        # 执行批量优化
        threshold_manager.batch_optimize()
        
        # 获取优化后的统计
        stats = threshold_manager.get_all_stats()
        
        logger.info(f"🎯 阈值优化完成 - 用户: {user.get('name', 'unknown')}")
        
        return {
            "success": True,
            "message": "阈值优化完成",
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ 阈值优化失败: {e}")
        raise HTTPException(status_code=500, detail=f"优化失败: {str(e)}")


@router.post("/thresholds/{filter_name}/{metric_name}/reset")
async def reset_threshold(
    filter_name: str,
    metric_name: str,
    user: Dict[str, Any] = Depends(check_permission("filter.admin"))
):
    """重置特定阈值"""
    try:
        from app.core.threshold_manager import threshold_manager
        
        # 重置阈值
        threshold_manager.reset_threshold(filter_name, metric_name)
        
        # 获取重置后的配置
        config = threshold_manager.get_threshold_config(filter_name, metric_name)
        
        logger.info(f"🔄 重置阈值 - 用户: {user.get('name', 'unknown')}, "
                   f"过滤器: {filter_name}.{metric_name}")
        
        return {
            "success": True,
            "message": f"阈值 {filter_name}.{metric_name} 已重置",
            "data": {
                "filter_name": filter_name,
                "metric_name": metric_name,
                "new_threshold": config.get('current', 0.5),
                "reset_at": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"❌ 重置阈值失败: {e}")
        raise HTTPException(status_code=500, detail=f"重置失败: {str(e)}")

@router.post("/test-broadcast")
async def test_broadcast(
    message_data: dict,
    user: Dict[str, Any] = Depends(require_auth)
):
    """测试WebSocket广播功能"""
    try:
        from app.api.websocket import websocket_manager
        
        # 添加必要的字段
        message_data["id"] = message_data.get("id", 99999)
        message_data["message_id"] = message_data.get("message_id", 99999)
        
        # 广播消息
        await websocket_manager.broadcast_new_message(message_data)
        
        num_connections = len(websocket_manager.active_connections)
        logger.info(f"测试广播已发送到 {num_connections} 个连接")
        
        return {
            "success": True,
            "message": f"消息已广播到 {num_connections} 个WebSocket连接",
            "connections": num_connections
        }
    except Exception as e:
        logger.error(f"测试广播失败: {e}")
        raise HTTPException(status_code=500, detail="测试广播失败")


@router.post("/{message_id}/refilter")
async def refilter_message(
    message_id: str,
    user: Dict[str, Any] = Depends(check_permission("messages.edit")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """重新过滤消息内容（使用最新的训练数据）"""
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        original_content = msg_data.get('content')
        if not original_content:
            return {"success": False, "message": "消息内容为空"}
        
        try:
            # 使用内容过滤器重新过滤
            from app.services.content_filter import content_filter
            
            # 应用完整的过滤流程
            filtered_content = content_filter.filter_promotional_content(
                original_content,
                channel_id=channel_id
            )
            
            # 记录过滤效果
            original_len = len(original_content)
            filtered_len = len(filtered_content)
            
            # 更新Redis中的数据
            redis_store = get_redis_message_store()
            msg_key = f"msg:{channel_id}:{msg_id}"
            update_data = {
                'filtered_content': filtered_content,
                'updated_at': get_current_time().isoformat()
            }
            redis_store.redis.hset(msg_key, mapping=update_data)
            
            logger.info(f"消息 {message_id} 重新过滤完成: {original_len} -> {filtered_len} 字符")
            
            # 如果有审核群消息ID，尝试更新审核群中的消息
            review_message_id = msg_data.get('review_message_id')
            if review_message_id:
                try:
                    from app.telegram.bot import telegram_bot
                    if telegram_bot and telegram_bot.client:
                        # 更新msg_data中的过滤内容然后传递给update_review_message
                        updated_msg_data = dict(msg_data)
                        updated_msg_data['filtered_content'] = filtered_content
                        await telegram_bot.update_review_message(updated_msg_data)
                        logger.info(f"审核群消息 {review_message_id} 已更新")
                except Exception as e:
                    logger.error(f"更新审核群消息失败: {e}")
            
            return {
                "success": True,
                "message": f"消息已重新过滤",
                "original_length": original_len,
                "filtered_length": filtered_len,
                "reduction": original_len - filtered_len
            }
            
        except Exception as e:
            logger.error(f"重新过滤消息 {message_id} 失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新过滤消息失败: {e}")
        raise HTTPException(status_code=500, detail="重新过滤消息失败")

@router.post("/reset")
async def reset_message(
    request: Request,
    user: Dict[str, Any] = Depends(check_permission("messages.edit")),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """重置消息状态为待审核，用于误判恢复"""
    try:
        data = await request.json()
        source_channel = data.get('source_channel')
        message_id = data.get('message_id')
        is_ad = data.get('is_ad', False)
        
        if not source_channel or not message_id:
            raise HTTPException(status_code=400, detail="缺少必要参数: source_channel 或 message_id")
        
        # 获取消息数据
        msg_data = await message_processor.get_message(source_channel, int(message_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        logger.info(f"重置消息: {source_channel}:{message_id}, is_ad: {is_ad}")
        
        # 如果是广告消息，需要从训练样本中移除
        if is_ad:
            try:
                # 尝试从广告训练数据中移除此消息
                import json
                from pathlib import Path
                from app.utils.safe_file_ops import SafeFileOperation
                
                # 读取广告训练数据
                ad_data_file = Path("data/ad_training_data.json")
                if ad_data_file.exists():
                    safe_file_op = SafeFileOperation()
                    ad_data = safe_file_op.read_json(ad_data_file)
                    
                    # 构造要查找的样本ID
                    sample_id = f"{source_channel}:{message_id}"
                    
                    # 从samples中移除
                    original_count = len(ad_data.get('samples', []))
                    ad_data['samples'] = [
                        sample for sample in ad_data.get('samples', []) 
                        if sample.get('id') != sample_id
                    ]
                    new_count = len(ad_data.get('samples', []))
                    
                    # 如果有移除，保存文件
                    if original_count > new_count:
                        safe_file_op.write_json(ad_data_file, ad_data)
                        logger.info(f"已从广告训练样本中移除消息 {source_channel}:{message_id}")
                    else:
                        logger.info(f"消息 {source_channel}:{message_id} 未在训练样本中找到")
                        
            except Exception as e:
                logger.warning(f"从训练样本中移除消息失败，但继续重置操作: {e}")
        
        # 重置消息状态为pending
        success = await message_processor.update_message_status(
            source_channel, 
            int(message_id), 
            "pending", 
            reviewed_by=user.get('username', 'system')
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="重置消息状态失败")
        
        # 重置广告标记
        redis_store = get_redis_message_store()
        await redis_store.update_message_field(source_channel, int(message_id), 'is_ad', False)
        
        # 添加重置记录
        await redis_store.update_message_field(
            source_channel, 
            int(message_id), 
            'reset_time', 
            get_current_time().isoformat()
        )
        await redis_store.update_message_field(
            source_channel, 
            int(message_id), 
            'reset_by', 
            user.get('username', 'system')
        )
        
        logger.info(f"消息 {source_channel}:{message_id} 已重置为待审核状态")
        
        return {
            "success": True, 
            "message": "消息已重置为待审核状态" + ("，并从广告训练样本中移除" if is_ad else "")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置消息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重置消息失败: {str(e)}")