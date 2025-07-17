"""
消息管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db, Message
from app.services.message_processor import MessageProcessor

router = APIRouter()
message_processor = MessageProcessor()

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
                "content": msg.content[:200] + "..." if len(msg.content or "") > 200 else msg.content,
                "media_type": msg.media_type,
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
    message.review_time = datetime.utcnow()
    
    await db.commit()
    
    return {"message": "消息已批准"}

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
    
    message.status = "rejected"
    message.reviewed_by = reviewer
    message.review_time = datetime.utcnow()
    
    await db.commit()
    
    return {"message": "消息已拒绝"}

@router.post("/batch-approve")
async def batch_approve_messages(
    message_ids: List[int],
    reviewer: str,
    db: AsyncSession = Depends(get_db)
):
    """批量批准消息"""
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
        message.reviewed_by = reviewer
        message.review_time = datetime.utcnow()
    
    await db.commit()
    
    return {"message": f"已批准 {len(messages)} 条消息"}

@router.get("/stats/overview")
async def get_message_stats():
    """获取消息统计概览"""
    stats = await message_processor.get_message_stats()
    return stats