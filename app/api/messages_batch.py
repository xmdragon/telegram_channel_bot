"""
消息批量操作API模块
处理消息的批量批准、拒绝、删除等操作
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.utils.timezone import get_current_time, format_for_api
import logging
import asyncio

from app.storage.redis_store import get_redis_message_store
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.core.api_paths import api_paths
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

def check_permission(permission_name: str):
    """检查权限装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 这里可以添加具体的权限检查逻辑
            return await func(*args, **kwargs)
        return wrapper
    return decorator

async def parse_and_collect_messages(message_ids: List[str], status_filter: str = 'pending'):
    """
    解析消息ID并收集相关的组合消息
    避免重复处理组合消息
    """
    redis_store = get_redis_message_store()
    message_tuples = []
    valid_messages = []
    processed_group_ids = set()
    
    for msg_id in message_ids:
        try:
            if ':' in str(msg_id):
                # 新格式: "channel_id:message_id"
                channel_id, message_id = str(msg_id).split(':', 1)
                message_tuples.append((channel_id, int(message_id)))
            else:
                # 老格式: 纯数字ID（需要从其他地方获取channel_id）
                logger.warning(f"无法解析消息ID格式: {msg_id}")
                continue
                
            # 检查消息是否存在且为指定状态
            msg_data = redis_store.get_message(channel_id, int(message_id))
            if msg_data and msg_data.get('status') == status_filter:
                # 检查是否为组合消息，如果是，需要同时处理整个组
                if msg_data.get('is_combined') and msg_data.get('grouped_id'):
                    grouped_id = msg_data.get('grouped_id')
                    if grouped_id not in processed_group_ids:
                        processed_group_ids.add(grouped_id)
                        # 查找同组的所有单独消息，一起处理
                        group_messages = redis_store.get_messages_by_channel(channel_id, limit=100)
                        for group_msg in group_messages:
                            if (group_msg.get('grouped_id') == grouped_id and 
                                group_msg.get('status') == status_filter and
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

@router.post(ROUTES.messages.batch_approve)
@check_permission("messages.approve")
async def batch_approve_messages(
    request: dict,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    批量批准消息
    支持组合消息的完整处理
    """
    message_ids = request.get("message_ids", [])
    if not message_ids:
        return {"success": False, "message": "未提供消息ID列表"}
    
    try:
        reviewer_name = user.get('username', 'Web用户')
        
        # 解析消息ID并收集相关的组合消息
        message_tuples, valid_messages = await parse_and_collect_messages(message_ids, 'pending')
        
        if not valid_messages:
            return {"success": False, "message": "没有找到可批准的消息"}
        
        # 批量更新状态
        update_results = await message_processor.batch_update_status(
            message_tuples, "approved", reviewer_name
        )
        
        approved_count = sum(1 for success in update_results.values() if success)
        
        # 使用任务队列批量转发到目标频道，避免客户端锁冲突
        forwarded_count = 0
        try:
            from app.services.message_forward_queue import forward_queue
            
            # 提交所有转发任务到队列
            task_ids = []
            for msg_data in valid_messages:
                try:
                    msg_key = f"{msg_data.get('source_channel')}:{msg_data.get('message_id')}"
                    task_id = await forward_queue.submit_forward_task(msg_key, "forward_to_target")
                    task_ids.append((msg_key, task_id))
                except Exception as e:
                    logger.error(f"提交转发任务失败 {msg_key}: {e}")
            
            logger.info(f"批量批准：已提交 {len(task_ids)} 个转发任务到队列")
            
            # 等待所有任务完成（短暂等待，不阻塞用户响应）
            await asyncio.sleep(2)  # 给队列处理时间
            
            # 检查已完成的任务
            for msg_key, task_id in task_ids:
                try:
                    result = await forward_queue.get_task_result(msg_key, timeout=1)  # 快速检查
                    if result and result.get('success'):
                        forwarded_count += 1
                except Exception as e:
                    logger.debug(f"检查转发任务结果失败 {msg_key}: {e}")
            
        except ImportError:
            logger.warning("消息转发队列模块不可用，跳过自动转发")
        except Exception as e:
            logger.error(f"批量转发失败: {e}")
        
        return {
            "success": True,
            "message": f"批量操作完成，批准 {approved_count} 条消息，转发 {forwarded_count} 条消息",
            "data": {
                "approved_count": approved_count,
                "forwarded_count": forwarded_count,
                "total_processed": len(valid_messages)
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"批量批准消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量批准消息失败: {str(e)}")

@router.post(ROUTES.messages.batch_reject)
@check_permission("messages.reject")
async def batch_reject_messages(
    request: dict,
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
        except ImportError:
            logger.warning("Telegram bot模块不可用，跳过消息删除")
        except Exception as e:
            logger.error(f"删除审核群消息失败: {e}")
        
        # 批量更新状态为拒绝
        update_results = await message_processor.batch_update_status(
            message_tuples, "rejected", reviewer_name, reason
        )
        
        rejected_count = sum(1 for success in update_results.values() if success)
        
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

@router.post(ROUTES.messages.batch_refetch_media)
@check_permission("messages.refetch")
async def batch_refetch_media(
    request: dict,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    批量重新获取媒体文件
    """
    message_ids = request.get("message_ids", [])
    if not message_ids:
        return {"success": False, "message": "未提供消息ID列表"}
    
    try:
        # 解析消息ID（可以处理任何状态的消息）
        message_tuples, valid_messages = await parse_and_collect_messages(message_ids, None)
        
        if not valid_messages:
            return {"success": False, "message": "没有找到可处理的消息"}
        
        # 批量提交重新获取媒体任务
        success_count = 0
        failed_count = 0
        
        for msg_data in valid_messages:
            try:
                success = await message_processor.refetch_media(
                    msg_data.get('source_channel'),
                    msg_data.get('message_id')
                )
                if success:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"重新获取媒体失败: {e}")
                failed_count += 1
        
        return {
            "success": True,
            "message": f"批量重新获取媒体完成，成功 {success_count} 条，失败 {failed_count} 条",
            "data": {
                "success_count": success_count,
                "failed_count": failed_count,
                "total_processed": len(valid_messages)
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"批量重新获取媒体失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量重新获取媒体失败: {str(e)}")

@router.post(ROUTES.messages.batch_delete)
@check_permission("messages.delete")
async def batch_delete_messages(
    request: dict,
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
        
        # 批量删除消息
        deleted_count = 0
        for msg_data in valid_messages:
            try:
                success = await message_processor.delete_message(
                    f"{msg_data.get('source_channel')}:{msg_data.get('message_id')}",
                    user.get('user_id')
                )
                if success:
                    deleted_count += 1
            except Exception as e:
                logger.error(f"删除消息失败: {e}")
        
        return {
            "success": True,
            "message": f"批量删除完成，删除 {deleted_count} 条消息",
            "data": {
                "deleted_count": deleted_count,
                "total_processed": len(valid_messages)
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"批量删除消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量删除消息失败: {str(e)}")