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
        import functools
        @functools.wraps(func)
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
    redis_store = redis_manager
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

@router.post(ROUTES.messages.batch_approve)
@check_permission("messages.approve")
async def batch_approve_messages(
    request: dict = Body({}),
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
        
        # 处理广告消息的媒体保存（新增逻辑）
        await _handle_approved_media_training(valid_messages)
        
        # 使用任务队列批量转发到目标频道，避免客户端锁冲突
        forwarded_count = 0
        forward_results = []  # 初始化转发结果列表
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
            
            # 检查已完成的任务，收集详细结果
            forward_results = []
            for msg_key, task_id in task_ids:
                try:
                    result = await forward_queue.get_task_result(msg_key, timeout=1)  # 快速检查
                    if result and result.get('success'):
                        forwarded_count += 1
                        forward_results.append({
                            "message_id": msg_key,
                            "status": "success"
                        })
                    elif result and not result.get('success'):
                        error_msg = result.get('error_message', '未知错误')
                        forward_results.append({
                            "message_id": msg_key,
                            "status": "failed", 
                            "error": error_msg
                        })
                        logger.warning(f"消息转发失败 {msg_key}: {error_msg}")
                    else:
                        # 任务还在处理中
                        forward_results.append({
                            "message_id": msg_key,
                            "status": "pending"
                        })
                except Exception as e:
                    logger.debug(f"检查转发任务结果失败 {msg_key}: {e}")
                    forward_results.append({
                        "message_id": msg_key,
                        "status": "error",
                        "error": f"检查任务状态失败: {str(e)}"
                    })
            
        except ImportError:
            logger.warning("消息转发队列模块不可用，跳过自动转发")
        except Exception as e:
            logger.error(f"批量转发失败: {e}")
        
        failed_count = len([r for r in forward_results if r.get('status') == 'failed'])
        pending_count = len([r for r in forward_results if r.get('status') == 'pending'])
        
        # 构建响应消息
        status_parts = [f"批准 {approved_count} 条"]
        if forwarded_count > 0:
            status_parts.append(f"转发成功 {forwarded_count} 条")
        if failed_count > 0:
            status_parts.append(f"转发失败 {failed_count} 条")
        if pending_count > 0:
            status_parts.append(f"处理中 {pending_count} 条")
        
        return {
            "success": True,
            "message": f"批量操作完成，{', '.join(status_parts)}",
            "data": {
                "approved_count": approved_count,
                "forwarded_count": forwarded_count,
                "failed_count": failed_count,
                "pending_count": pending_count,
                "total_processed": len(valid_messages),
                "forward_results": forward_results  # 详细结果供前端显示
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"批量批准消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量批准消息失败: {str(e)}")

@router.post(ROUTES.messages.batch_reject)
@check_permission("messages.reject")
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
        
        # 处理被拒绝消息的媒体移除（新增逻辑）
        await _handle_rejected_media_removal(valid_messages)
        
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
    request: dict = Body({}),
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
            from app.telegram.bot import telegram_bot
            if telegram_bot and telegram_bot.client:
                for msg_data in valid_messages:
                    # 删除审核群消息（如果存在）
                    review_message_id = msg_data.get('review_message_id')
                    if review_message_id:
                        try:
                            await telegram_bot.delete_review_message(review_message_id)
                            logger.debug(f"已删除审核群消息: {review_message_id}")
                        except Exception as e:
                            logger.debug(f"删除审核群消息失败: {e}")
                    
                    # 清理媒体文件
                    try:
                        await telegram_bot._cleanup_message_files(msg_data)
                        media_cleanup_count += 1
                        logger.debug(f"已清理媒体文件: {msg_data.get('source_channel')}:{msg_data.get('message_id')}")
                    except Exception as e:
                        logger.debug(f"清理媒体文件失败: {e}")
        except ImportError:
            logger.warning("Telegram bot模块不可用，跳过媒体清理")
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


async def _handle_approved_media_training(valid_messages: List[Dict[str, Any]]):
    """
    处理批准消息的媒体训练数据保存
    如果消息被标记为广告且有媒体，保存到训练目录
    """
    try:
        from app.services.training_media_manager import training_media_manager
        
        for msg_data in valid_messages:
            # 检查消息是否被标记为广告且有媒体
            is_ad = msg_data.get('is_ad') == 'True'
            has_media = msg_data.get('media_type') and msg_data.get('media_path')
            
            if is_ad and has_media:
                try:
                    # 从临时目录保存到训练目录
                    temp_media_path = msg_data.get('media_path')
                    if temp_media_path:
                        saved_path = await training_media_manager.save_training_media(
                            source_path=temp_media_path,
                            message_id=msg_data.get('message_id'),
                            media_type=msg_data.get('media_type'),
                            channel_id=msg_data.get('source_channel'),
                            is_ad=True
                        )
                        if saved_path:
                            logger.info(f"✅ 批准时保存广告媒体到训练目录: {saved_path}")
                        else:
                            logger.warning(f"⚠️  批准时保存广告媒体失败: {temp_media_path}")
                
                except Exception as e:
                    logger.error(f"❌ 批准时保存媒体到训练目录失败: {e}")
                    
    except ImportError:
        logger.warning("训练媒体管理器不可用，跳过媒体训练数据保存")
    except Exception as e:
        logger.error(f"处理批准媒体训练失败: {e}")


async def _handle_rejected_media_removal(valid_messages: List[Dict[str, Any]]):
    """
    处理拒绝消息的媒体移除
    如果消息之前被误标记为广告，从训练目录移除
    """
    try:
        from app.services.training_media_manager import training_media_manager
        from app.core.path_config import PathConfig
        from pathlib import Path
        import hashlib
        
        for msg_data in valid_messages:
            # 检查是否有媒体需要从训练目录移除
            has_media = msg_data.get('media_type') and msg_data.get('media_path')
            
            if has_media:
                try:
                    # 计算媒体文件hash来查找训练目录中的对应文件
                    temp_media_path = msg_data.get('media_path')
                    if temp_media_path and Path(temp_media_path).exists():
                        # 计算文件hash
                        sha256_hash = hashlib.sha256()
                        with open(temp_media_path, "rb") as f:
                            for byte_block in iter(lambda: f.read(4096), b""):
                                sha256_hash.update(byte_block)
                        file_hash = sha256_hash.hexdigest()
                        
                        # 检查训练目录中是否存在此hash的文件
                        if file_hash in training_media_manager.metadata.get("media_files", {}):
                            # 从训练目录和OCR样本中移除
                            await _remove_media_from_training(file_hash, msg_data)
                            logger.info(f"✅ 拒绝时从训练目录移除媒体: {file_hash[:12]}")
                        
                except Exception as e:
                    logger.error(f"❌ 拒绝时移除训练媒体失败: {e}")
                    
    except ImportError:
        logger.warning("训练媒体管理器不可用，跳过媒体移除")
    except Exception as e:
        logger.error(f"处理拒绝媒体移除失败: {e}")


async def _remove_media_from_training(file_hash: str, msg_data: Dict[str, Any]):
    """移除训练媒体和对应OCR样本"""
    try:
        from app.services.training_media_manager import training_media_manager
        from app.core.path_config import PathConfig
        from app.utils.safe_file_ops import SafeFileOperation
        from pathlib import Path
        import shutil
        
        # 获取文件信息
        file_info = training_media_manager.metadata.get("media_files", {}).get(file_hash)
        if not file_info:
            return
        
        # 删除物理文件
        training_dir = PathConfig.AD_TRAINING_DIR
        file_path = training_dir / file_info["path"]
        if file_path.exists():
            file_path.unlink()
            logger.info(f"删除训练媒体文件: {file_path}")
        
        # 删除缩略图（如果存在）
        if "thumbnail_path" in file_info:
            thumbnail_path = training_dir / file_info["thumbnail_path"]
            if thumbnail_path.exists():
                thumbnail_path.unlink()
                logger.info(f"删除训练媒体缩略图: {thumbnail_path}")
        
        # 从媒体元数据中移除
        del training_media_manager.metadata["media_files"][file_hash]
        training_media_manager.save_metadata()
        
        # 从OCR样本中移除
        ocr_samples_file = PathConfig.OCR_SAMPLES_FILE
        if ocr_samples_file.exists():
            data = SafeFileOperation.read_json_safe(ocr_samples_file)
            if data and "samples" in data:
                # 过滤掉对应hash的样本
                original_count = len(data["samples"])
                data["samples"] = [
                    sample for sample in data["samples"] 
                    if sample.get("image_hash") != file_hash
                ]
                removed_count = original_count - len(data["samples"])
                
                if removed_count > 0:
                    # 更新统计信息
                    samples = data["samples"]
                    data["statistics"] = {
                        "total_samples": len(samples),
                        "ad_samples": len([s for s in samples if s.get("is_ad")]),
                        "non_ad_samples": len([s for s in samples if not s.get("is_ad")]),
                        "auto_rejected_samples": len([s for s in samples if s.get("auto_rejected")]),
                        "high_score_samples": len([s for s in samples if s.get("ad_score", 0) >= 50.0]),
                        "last_updated": msg_data.get("created_at", ""),
                        "created_at": data["statistics"].get("created_at", "")
                    }
                    
                    # 保存更新后的OCR数据
                    SafeFileOperation.write_json_safe(ocr_samples_file, data)
                    logger.info(f"从OCR样本中移除 {removed_count} 个样本")
        
    except Exception as e:
        logger.error(f"移除训练媒体失败: {e}")