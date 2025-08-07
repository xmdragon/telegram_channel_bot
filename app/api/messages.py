"""
消息管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional
from datetime import datetime
import os

from app.core.database import get_db, Message
from app.services.message_processor import MessageProcessor
from app.services.channel_manager import ChannelManager

router = APIRouter()
message_processor = MessageProcessor()
channel_manager = ChannelManager()

@router.get("/")
async def get_messages(
    status: Optional[str] = Query(None, description="消息状态过滤"),
    source_channel: Optional[str] = Query(None, description="源频道过滤"),
    is_ad: Optional[bool] = Query(None, description="是否为广告"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db)
):
    """获取消息列表"""
    
    # 构建查询条件
    conditions = []
    if status:
        conditions.append(Message.status == status)
    if source_channel:
        conditions.append(Message.source_channel == source_channel)
    if is_ad is not None:
        conditions.append(Message.is_ad == is_ad)
    
    # 执行查询
    query = select(Message)
    if conditions:
        query = query.where(and_(*conditions))
    
    query = query.offset((page - 1) * size).limit(size).order_by(Message.created_at.desc())
    
    result = await db.execute(query)
    messages = result.scalars().all()
    
    return {
        "messages": [
            {
                "id": msg.id,
                "source_channel": msg.source_channel,
                "content": msg.content,
                "filtered_content": msg.filtered_content,
                "message_id": msg.message_id,
                "media_type": msg.media_type,
                "media_url": msg.media_url,
                "media_display_url": f"/media/{os.path.basename(msg.media_url)}" if msg.media_url else None,
                "grouped_id": msg.grouped_id,
                "is_combined": msg.is_combined,
                "combined_messages": msg.combined_messages,
                "media_group": msg.media_group,
                "media_group_display": [
                    {
                        **media_item,
                        "display_url": f"/media/{os.path.basename(media_item['file_path'])}" if media_item.get('file_path') else None
                    }
                    for media_item in (msg.media_group or [])
                ] if msg.media_group else None,
                "status": msg.status,
                "is_ad": msg.is_ad,
                "created_at": msg.created_at,
                "review_time": msg.review_time,
                "reviewed_by": msg.reviewed_by
            }
            for msg in messages
        ],
        "page": page,
        "size": size
    }

@router.get("/channel-info")
async def get_channel_info():
    """获取频道信息映射"""
    try:
        # 使用新的频道信息获取方法
        channel_info = await channel_manager.get_channel_info_for_display()
        
        return {
            "success": True,
            "data": channel_info
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/batch/approve")
async def batch_approve_messages(
    request: dict,
    db: AsyncSession = Depends(get_db)
):
    """批量批准消息"""
    message_ids = request.get("message_ids", [])
    if not message_ids:
        return {"success": False, "message": "未提供消息ID列表"}
    
    result = await db.execute(
        select(Message).where(
            and_(
                Message.id.in_(message_ids),
                Message.status == "pending"
            )
        )
    )
    messages = result.scalars().all()
    
    for message in messages:
        message.status = "approved"
        message.reviewed_by = "Web用户"
        message.review_time = datetime.now()
    
    await db.commit()
    
    # 广播批量状态更新到WebSocket客户端
    try:
        from app.api.websocket import websocket_manager
        for message in messages:
            await websocket_manager.broadcast_message_status_update(message.id, "approved")
    except Exception as e:
        print(f"广播批量状态更新失败: {e}")
    
    return {"success": True, "message": f"已批准 {len(messages)} 条消息"}

@router.get("/{message_id}")
async def get_message(
    message_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单个消息详情"""
    result = await db.execute(select(Message).where(Message.id == message_id))
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    return {
        "id": message.id,
        "source_channel": message.source_channel,
        "message_id": message.message_id,
        "content": message.content,
        "filtered_content": message.filtered_content,
        "media_type": message.media_type,
        "media_url": message.media_url,
        "status": message.status,
        "is_ad": message.is_ad,
        "reviewed_by": message.reviewed_by,
        "review_time": message.review_time,
        "forwarded_time": message.forwarded_time,
        "created_at": message.created_at,
        "updated_at": message.updated_at
    }

@router.post("/{message_id}/approve")
async def approve_message(
    message_id: int,
    reviewer: str,
    db: AsyncSession = Depends(get_db)
):
    """批准消息"""
    result = await db.execute(select(Message).where(Message.id == message_id))
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    if message.status != "pending":
        raise HTTPException(status_code=400, detail="消息状态不允许此操作")
    
    message.status = "approved"
    message.reviewed_by = reviewer
    message.review_time = datetime.now()
    
    await db.commit()
    
    # 广播状态更新到WebSocket客户端
    try:
        from app.api.websocket import websocket_manager
        await websocket_manager.broadcast_message_status_update(message_id, "approved")
    except Exception as e:
        print(f"广播状态更新失败: {e}")
    
    return {"success": True, "message": "消息已批准"}

@router.post("/{message_id}/reject")
async def reject_message(
    message_id: int,
    reviewer: str,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """拒绝消息"""
    result = await db.execute(select(Message).where(Message.id == message_id))
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    if message.status != "pending":
        raise HTTPException(status_code=400, detail="消息状态不允许此操作")
    
    # 从审核群删除消息
    try:
        from app.telegram.bot import telegram_bot
        if telegram_bot and telegram_bot.client and message.review_message_id:
            await telegram_bot.delete_review_message(message.review_message_id)
            
            # 清理媒体文件
            await telegram_bot._cleanup_message_files(message)
    except Exception as e:
        print(f"删除审核群消息失败: {e}")
    
    message.status = "rejected"
    message.reviewed_by = reviewer
    message.review_time = datetime.now()
    
    await db.commit()
    
    # 广播状态更新到WebSocket客户端
    try:
        from app.api.websocket import websocket_manager
        await websocket_manager.broadcast_message_status_update(message_id, "rejected")
    except Exception as e:
        print(f"广播状态更新失败: {e}")
    
    return {"success": True, "message": "消息已拒绝"}

@router.post("/{message_id}/publish")
async def publish_message(
    message_id: int,
    db: AsyncSession = Depends(get_db)
):
    """发布消息到目标频道"""
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    # 转发到目标频道
    try:
        # 使用独立的客户端连接
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from app.services.config_manager import config_manager
        
        # 获取认证信息
        api_id = await config_manager.get_config('telegram.api_id')
        api_hash = await config_manager.get_config('telegram.api_hash')
        string_session = await config_manager.get_config('telegram.session', '')
        
        if not all([api_id, api_hash, string_session]):
            return {"success": False, "message": "Telegram认证信息不完整"}
        
        # 创建临时客户端
        client = TelegramClient(StringSession(string_session), int(api_id), api_hash)
        await client.connect()
        
        try:
            # 更新状态
            message.status = "approved"
            message.reviewed_by = "Web用户"
            message.review_time = datetime.now()
            
            # 获取目标频道配置
            target_channel_config = await config_manager.get_config('channels.target_channel_id')
            if not target_channel_config:
                return {"success": False, "message": "未配置目标频道"}
            
            # 获取缓存的ID或解析频道
            target_channel_id_cached = await config_manager.get_config('channels.target_channel_id_cached', '')
            
            # 如果有缓存的ID，直接使用
            if target_channel_id_cached and target_channel_id_cached.lstrip('-').isdigit():
                target_entity = int(target_channel_id_cached)
            else:
                # 解析频道用户名或ID
                try:
                    if target_channel_config.lstrip('-').isdigit():
                        # 如果是数字ID
                        target_entity = int(target_channel_config)
                    else:
                        # 如果是用户名，获取实体
                        target_entity = await client.get_entity(target_channel_config)
                        # 缓存解析的ID
                        if hasattr(target_entity, 'id'):
                            resolved_id = f"-100{target_entity.id}" if hasattr(target_entity, 'broadcast') and target_entity.broadcast else str(target_entity.id)
                            await config_manager.set_config('channels.target_channel_id_cached', resolved_id, '目标频道解析后的ID', 'string')
                except Exception as e:
                    return {"success": False, "message": f"解析目标频道失败: {str(e)}"}
            
            # 发送消息
            if message.media_type and message.media_url and os.path.exists(message.media_url):
                # 发送带媒体的消息
                sent_message = await client.send_file(
                    entity=target_entity,
                    file=message.media_url,
                    caption=message.filtered_content or message.content
                )
            else:
                # 发送纯文本消息
                sent_message = await client.send_message(
                    entity=target_entity,
                    message=message.filtered_content or message.content
                )
            
            if sent_message:
                message.target_message_id = sent_message.id
                message.forwarded_time = datetime.now()
            
            await db.commit()
            
            # 更新审核群中的消息状态（标记为已发布）
            if message.review_message_id:
                try:
                    # 获取审核群ID
                    review_group_id = await config_manager.get_config('channels.review_group_id_cached', '')
                    if not review_group_id:
                        review_group_id = await config_manager.get_config('channels.review_group_id', '')
                    
                    if review_group_id:
                        # 编辑审核群消息，添加已发布标记
                        original_text = message.filtered_content or message.content
                        updated_text = f"✅ [已发布]\n\n{original_text}"
                        
                        await client.edit_message(
                            entity=int(review_group_id) if review_group_id.lstrip('-').isdigit() else review_group_id,
                            message=message.review_message_id,
                            text=updated_text
                        )
                except Exception as e:
                    # 更新审核群消息失败不影响主流程
                    print(f"更新审核群消息失败: {e}")
            
            # 清理媒体文件
            if message.media_url and os.path.exists(message.media_url):
                try:
                    os.remove(message.media_url)
                except:
                    pass
            
            return {"success": True, "message": "消息已发布到目标频道"}
            
        finally:
            await client.disconnect()
            
    except Exception as e:
        await db.rollback()
        return {"success": False, "message": f"发布失败: {str(e)}"}

@router.post("/{message_id}/edit-publish")
async def edit_and_publish_message(
    message_id: int,
    request: dict,
    db: AsyncSession = Depends(get_db)
):
    """编辑消息内容"""
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    # 更新消息内容
    new_content = request.get("content", "").strip()
    if not new_content:
        return {"success": False, "message": "消息内容不能为空"}
    
    # 自动添加频道落款（如果还没有的话）
    from app.services.content_filter import ContentFilter
    content_filter = ContentFilter()
    new_content_with_signature = await content_filter.add_channel_signature(new_content)
    
    message.filtered_content = new_content_with_signature
    
    # 如果消息已经在审核群，更新审核群的消息
    try:
        from app.telegram.bot import telegram_bot
        if telegram_bot and hasattr(telegram_bot, 'client') and telegram_bot.client and \
           hasattr(telegram_bot, 'update_review_message') and message.review_message_id:
            await telegram_bot.update_review_message(message)
        
        await db.commit()
        return {"success": True, "message": "消息已编辑"}
    except Exception as e:
        await db.rollback()
        return {"success": False, "message": f"编辑失败: {str(e)}"}


@router.get("/stats/overview")
async def get_message_stats():
    """获取消息统计概览"""
    stats = await message_processor.get_message_stats()
    return stats

@router.delete("/{message_id}/review-message")
async def delete_review_message(
    message_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除审核群中的消息"""
    result = await db.execute(select(Message).where(Message.id == message_id))
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    if not message.review_message_id:
        return {"success": True, "message": "消息没有审核群消息ID"}
    
    try:
        from app.telegram.bot import telegram_bot
        if telegram_bot and telegram_bot.client:
            await telegram_bot.delete_review_message(message)
            return {"success": True, "message": "审核群消息已删除"}
        else:
            return {"success": False, "message": "Telegram客户端未连接"}
    except Exception as e:
        return {"success": False, "message": f"删除失败: {str(e)}"}