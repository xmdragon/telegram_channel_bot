"""
消息批量操作API模块
处理消息的批量批准、拒绝、删除等操作
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.utils.timezone import get_current_time, format_for_api
import logging
import asyncio

from app.storage.redis_manager import redis_manager
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.core.media_paths import media_paths
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)

# 依赖注入辅助函数
def get_message_processor() -> MessageProcessor:
    return MessageProcessor()

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


async def parse_and_collect_messages(message_ids: List[str], status_filter: str = 'pending'):
    """
    解析消息ID并收集相关的组合消息
    避免重复处理组合消息
    """
    redis_store = redis_manager
    message_tuples = []
    valid_messages = []
    processed_group_ids = set()
    
    for msg_id in message_ids:
        try:
            if ':' in str(msg_id):
                # 新格式: "channel_id:message_id"
                # 使用rsplit确保正确处理包含冒号的channel_id
                channel_id, message_id = str(msg_id).rsplit(':', 1)
                message_tuples.append((channel_id, int(message_id)))
            else:
                # 老格式: 纯数字ID（需要从其他地方获取channel_id）
                logger.warning(f"无法解析消息ID格式: {msg_id}")
                continue
                
            # 检查消息是否存在且为指定状态
            msg_data = redis_manager.get_message(channel_id, int(message_id), silent=True)
            # 如果status_filter为None，接受任何状态的消息；否则只接受匹配状态的消息
            status_matches = status_filter is None or msg_data.get('status') == status_filter
            if msg_data and status_matches:
                # 检查是否为组合消息，如果是，需要同时处理整个组
                if msg_data.get('is_combined') and msg_data.get('grouped_id'):
                    grouped_id = msg_data.get('grouped_id')
                    if grouped_id not in processed_group_ids:
                        processed_group_ids.add(grouped_id)
                        # 查找同组的所有单独消息，一起处理
                        group_messages = redis_manager.get_messages_by_channel(channel_id, limit=100)
                        for group_msg in group_messages:
                            group_status_matches = status_filter is None or group_msg.get('status') == status_filter
                            if (group_msg.get('grouped_id') == grouped_id and 
                                group_status_matches and
                                not group_msg.get('is_combined')):  # 只处理单独消息
                                valid_messages.append(group_msg)
                                # 添加到message_tuples用于状态更新
                                group_tuple = (channel_id, group_msg.get('message_id'))
                                if group_tuple not in message_tuples:
                                    message_tuples.append(group_tuple)
                        
                        logger.info(f"检测到组合消息，将同时处理组 {grouped_id} 的所有消息")
                
                # 添加主消息
                valid_messages.append(msg_data)
            
        except (ValueError, IndexError) as e:
            logger.error(f"解析消息ID {msg_id} 失败: {e}")
            continue
    
    return message_tuples, valid_messages


async def process_batch_approve(message_ids: List[str], user_id: str = None) -> Dict:
    """
    批量发布消息的核心逻辑
    可供内部调用（如自动转发）或HTTP API调用
    使用核心发布方法处理每条消息
    """
    try:
        # 判断是否为自动转发
        is_auto = (user_id == 'auto_forward')
        reviewer_name = user_id or 'auto_forward'

        # 解析消息ID并收集相关的组合消息
        message_tuples, valid_messages = await parse_and_collect_messages(message_ids, 'pending')

        if not valid_messages:
            return {
                "success": True,
                "message": "没有找到可批准的消息",
                "approved_count": 0,
                "failed_count": 0
            }

        # 导入核心发布方法
        from app.api.messages_crud import publish_single_message

        approved_count = 0
        failed_count = 0
        ad_count = 0
        length_exceeded_count = 0
        failed_details = []

        logger.info(f"开始批量处理 {len(valid_messages)} 条消息")

        # 使用核心方法逐个发布
        for msg_data in valid_messages:
            msg_id = f"{msg_data.get('source_channel')}:{msg_data.get('message_id')}"

            try:
                # 调用核心发布方法
                result = await publish_single_message(
                    msg_id,
                    reviewer_name,
                    skip_validation=False,
                    is_auto_forward=is_auto
                )

                if result['success']:
                    approved_count += 1
                    logger.debug(f"发布成功: {msg_id}")
                else:
                    failed_count += 1
                    # 统计失败原因
                    if result.get('error') == 'ad_detected':
                        ad_count += 1
                    elif result.get('error') == 'content_too_long':
                        length_exceeded_count += 1

                    # 记录失败详情
                    failed_details.append({
                        'message_id': msg_id,
                        'error': result.get('error'),
                        'message': result.get('message')
                    })

                    logger.debug(f"发布失败: {msg_id}, 原因: {result.get('message')}")

            except Exception as e:
                # 处理意外错误
                failed_count += 1
                logger.error(f"处理消息失败 {msg_id}: {e}")
                failed_details.append({
                    'message_id': msg_id,
                    'error': 'unexpected_error',
                    'message': str(e)
                })

            # 短暂延迟避免过载
            await asyncio.sleep(0.1)

        # 发送统计更新通知
        await _notify_stats_update()

        return {
            "success": True,
            "approved_count": approved_count,
            "forwarded_count": approved_count,  # 发布成功的数量
            "failed_count": failed_count,
            "total": len(valid_messages),
            "message": f"批量发布完成: 成功{approved_count}, 失败{failed_count}"
        }

    except Exception as e:
        logger.error(f"批量发布处理失败: {e}")
        return {
            "success": False,
            "message": str(e),
            "approved_count": 0,
            "failed_count": len(message_ids)
        }


@router.post(ROUTES.messages.batch_approve)
async def batch_approve_messages(
    request: dict = Body({}),
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    批量批准消息 - HTTP API端点
    调用核心批量发送逻辑
    """
    message_ids = request.get("message_ids", [])
    if not message_ids:
        return {"success": False, "message": "未提供消息ID列表"}

    try:
        reviewer_name = user.get('username', 'Web用户')

        # 调用核心批量发送函数
        result = await process_batch_approve(
            message_ids=message_ids,
            user_id=reviewer_name
        )

        # 构建响应
        if result.get('success'):
            approved_count = result.get('approved_count', 0)
            forwarded_count = result.get('forwarded_count', 0)
            failed_count = result.get('failed_count', 0)

            # 构建响应消息
            if forwarded_count > 0:
                if forwarded_count == approved_count:
                    primary_message = f"成功发布 {approved_count} 条消息到目标频道"
                else:
                    primary_message = f"已批准 {approved_count} 条消息，成功转发 {forwarded_count} 条"
            else:
                primary_message = "没有消息需要处理"

            # 构建状态详情
            status_details = []
            if failed_count > 0:
                status_details.append(f"{failed_count} 条转发失败")

            detail_message = f"（{', '.join(status_details)}）" if status_details else ""

            return {
                "success": True,
                "message": f"{primary_message}{detail_message}",
                "data": {
                    "approved_count": approved_count,
                    "forwarded_count": forwarded_count,
                    "failed_count": failed_count,
                    "total_processed": result.get('total', len(message_ids)),
                    "status": "completed"
                },
                "timestamp": format_for_api(get_current_time())
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('message', '批量批准失败'))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量批准消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量批准消息失败: {str(e)}")

@router.post(ROUTES.messages.batch_reject)
async def batch_reject_messages(
    request: dict = Body({}),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    批量拒绝消息
    支持组合消息的完整处理
    """
    message_ids = request.get("message_ids", [])
    reason = request.get("reason", "批量拒绝")
    
    if not message_ids:
        return {"success": False, "message": "未提供消息ID列表"}
    
    try:
        reviewer_name = user.get('username', 'Web用户')
        
        # 解析消息ID并收集相关的组合消息
        message_tuples, valid_messages = await parse_and_collect_messages(message_ids, 'pending')
        
        if not valid_messages:
            return {"success": False, "message": "没有找到可拒绝的消息"}
        
        # 从审核群删除消息和清理媒体文件
        deleted_count = 0
        try:
            from app.telegram.message_forwarder import message_forwarder
            from app.telegram.dual_session_manager import dual_session_manager

            client = await dual_session_manager.get_sender_client()
            if client:
                for msg_data in valid_messages:
                    review_message_id = msg_data.get('review_message_id')
                    if review_message_id:
                        try:
                            await message_forwarder.delete_review_message(client, review_message_id)
                            deleted_count += 1
                        except Exception as e:
                            logger.debug(f"删除审核群消息失败: {e}")

                    # 清理媒体文件
                    from app.services.media_handler import media_handler
                    media_url = msg_data.get('media_url')
                    if media_url:
                        try:
                            await media_handler.cleanup_file(media_url)
                        except Exception as e:
                            logger.debug(f"清理媒体文件失败: {e}")
        except ImportError:
            logger.warning("消息组件模块不可用，跳过消息删除")
        except Exception as e:
            logger.error(f"删除审核群消息失败: {e}")
        
        # 批量更新状态为拒绝
        update_results = await message_processor.batch_update_status(
            message_tuples, "rejected", reviewer_name, reason
        )
        
        rejected_count = sum(1 for success in update_results.values() if success)
        
        # 注意：已移除媒体训练数据移除功能
        
        # 发送统计更新通知
        await _notify_stats_update()
        
        return {
            "success": True,
            "message": f"批量拒绝完成，拒绝 {rejected_count} 条消息，删除 {deleted_count} 条审核消息",
            "data": {
                "rejected_count": rejected_count,
                "deleted_count": deleted_count,
                "total_processed": len(valid_messages)
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"批量拒绝消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量拒绝消息失败: {str(e)}")

@router.post(ROUTES.messages.batch_delete)
async def batch_delete_messages(
    request: dict = Body({}),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    批量删除消息
    """
    message_ids = request.get("message_ids", [])
    if not message_ids:
        return {"success": False, "message": "未提供消息ID列表"}
    
    try:
        # 解析消息ID（可以处理任何状态的消息）
        message_tuples, valid_messages = await parse_and_collect_messages(message_ids, None)
        
        if not valid_messages:
            return {"success": False, "message": "没有找到可删除的消息"}
        
        # 先清理媒体文件，再删除消息数据
        media_cleanup_count = 0
        try:
            from app.telegram.message_forwarder import message_forwarder
            from app.telegram.dual_session_manager import dual_session_manager

            client = await dual_session_manager.get_sender_client()
            if client:
                for msg_data in valid_messages:
                    # 删除审核群消息（如果存在）
                    review_message_id = msg_data.get('review_message_id')
                    if review_message_id:
                        try:
                            await message_forwarder.delete_review_message(client, review_message_id)
                            logger.debug(f"已删除审核群消息: {review_message_id}")
                        except Exception as e:
                            logger.debug(f"删除审核群消息失败: {e}")

                    # 清理媒体文件
                    from app.services.media_handler import media_handler
                    media_url = msg_data.get('media_url')
                    if media_url:
                        try:
                            await media_handler.cleanup_file(media_url)
                            media_cleanup_count += 1
                            logger.debug(f"已清理媒体文件: {msg_data.get('source_channel')}:{msg_data.get('message_id')}")
                        except Exception as e:
                            logger.debug(f"清理媒体文件失败: {e}")
        except ImportError:
            logger.warning("消息组件模块不可用，跳过媒体清理")
        except Exception as e:
            logger.error(f"清理媒体文件失败: {e}")

        # 批量删除消息数据
        deleted_count = 0
        for msg_data in valid_messages:
            try:
                channel_id = msg_data.get('source_channel')
                message_id = msg_data.get('message_id')
                logger.info(f"开始删除消息数据: {channel_id}:{message_id}")
                
                success = await message_processor.delete_message(channel_id, message_id)
                
                logger.info(f"删除消息数据结果: {channel_id}:{message_id} -> {success}")
                if success:
                    deleted_count += 1
            except Exception as e:
                logger.error(f"删除消息数据失败 {channel_id}:{message_id}: {e}")
        
        return {
            "success": True,
            "message": f"批量删除完成，删除 {deleted_count} 条消息，清理 {media_cleanup_count} 个媒体文件",
            "data": {
                "deleted_count": deleted_count,
                "media_cleanup_count": media_cleanup_count,
                "total_processed": len(valid_messages)
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"批量删除消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量删除消息失败: {str(e)}")


# 注意：_handle_approved_media_training 函数已移除（媒体训练功能已废弃）


# 注意：_handle_rejected_media_removal 和 _remove_media_from_training 函数已移除（媒体训练功能已废弃）


@router.post(ROUTES.messages.reset_failed)
async def reset_failed_messages(
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    重置所有发送失败的消息状态
    将 send_failed 状态的消息重置为 approved 状态
    """
    try:
        reset_count = 0
        failed_messages = []

        # 获取所有频道
        from app.storage.json_store import get_json_channel_store
        channel_store = get_json_channel_store()
        all_channels = channel_store.get_all_channels()

        # 遍历所有频道查找发送失败的消息
        for channel in all_channels:
            if isinstance(channel, dict):
                channel_id = channel.get('channel_id', '')
                if channel_id:
                    # 确保频道ID格式统一
                    if not channel_id.startswith('-100'):
                        if channel_id.isdigit():
                            channel_id = f"-100{channel_id}"
                        elif channel_id.startswith('-') and not channel_id.startswith('-100'):
                            channel_id = f"-100{channel_id[1:]}"

                    # 获取该频道的所有消息
                    messages = redis_manager.get_messages_by_channel(channel_id, limit=1000)

                    # 筛选出发送失败的消息
                    from app.core.message_status import MessageStatus
                    for msg in messages:
                        if msg.get('status') == MessageStatus.SEND_FAILED.value:
                            failed_messages.append({
                                'channel_id': channel_id,
                                'message_id': msg.get('message_id')
                            })

        # 批量重置状态
        from app.services.message_processor import MessageProcessor
        message_processor = MessageProcessor()

        for msg_info in failed_messages:
            try:
                # 获取消息数据
                msg_data = redis_manager.get_message(
                    msg_info['channel_id'],
                    msg_info['message_id'],
                    silent=True
                )

                from app.core.message_status import MessageStatus

                if msg_data and msg_data.get('status') == MessageStatus.SEND_FAILED.value:
                    # 重置状态为pending(需要重新审核)
                    msg_data['status'] = MessageStatus.PENDING.value
                    msg_data['send_failed_count'] = 0
                    msg_data['last_send_attempt'] = None
                    msg_data['send_error'] = None

                    # 更新消息
                    redis_manager.update_message(
                        msg_info['channel_id'],
                        msg_info['message_id'],
                        msg_data
                    )

                    reset_count += 1
                    logger.info(f"重置消息 {msg_info['channel_id']}:{msg_info['message_id']} 状态为approved")

            except Exception as e:
                logger.error(f"重置消息 {msg_info['channel_id']}:{msg_info['message_id']} 失败: {e}")

        # 清理所有缓存
        cache_cleanup_stats = {}
        try:
            logger.info("开始清理所有缓存...")
            cache_cleanup_stats = redis_manager.clear_all_caches()
            logger.info(f"缓存清理完成: {cache_cleanup_stats}")
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            # 缓存清理失败不影响主流程

        # 发送统计更新通知
        await _notify_stats_update()

        # 构建返回信息
        message_parts = [f"成功重置 {reset_count} 条发送失败的消息"]
        if cache_cleanup_stats.get('total', 0) > 0:
            message_parts.append(f"清理 {cache_cleanup_stats['total']} 个缓存条目")

        return {
            "success": True,
            "message": "，".join(message_parts),
            "data": {
                "reset_count": reset_count,
                "total_failed": len(failed_messages),
                "cache_cleaned": cache_cleanup_stats.get('total', 0),
                "cache_cleanup_details": cache_cleanup_stats
            },
            "timestamp": format_for_api(get_current_time())
        }

    except Exception as e:
        logger.error(f"重置发送失败消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"重置发送失败消息失败: {str(e)}")


async def _notify_stats_update():
    """发送WebSocket通知更新统计数据"""
    try:
        from app.api.websocket import websocket_manager
        from app.storage.redis_manager import redis_manager
        from datetime import datetime
        import json

        # 获取最新统计数据
        stats = redis_manager.get_statistics()

        # 构造通知数据
        notification_data = {
            "type": "stats_update",
            "timestamp": get_current_time().isoformat(),
            "data": {
                "total_messages": stats.get("total_messages", 0),
                "pending_count": stats.get("pending_messages", 0),
                "approved_count": stats.get("approved_messages", 0),
                "rejected_count": stats.get("rejected_messages", 0)
            }
        }

        # 通过WebSocket广播统计更新
        await websocket_manager.broadcast(json.dumps(notification_data, ensure_ascii=False))

    except Exception as e:
        # 通知失败不应该影响处理流程，只记录错误
        logger.debug(f"发送统计更新通知失败: {e}")