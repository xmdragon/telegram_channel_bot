"""
管理员API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime

from app.core.database import get_db, Channel, FilterRule, AsyncSessionLocal
from app.core.config import settings

router = APIRouter()

@router.get("/channels")
async def get_channels(db: AsyncSession = Depends(get_db)):
    """获取频道配置"""
    result = await db.execute(select(Channel))
    channels = result.scalars().all()
    
    return {
        "channels": [
            {
                "id": ch.id,
                "channel_id": ch.channel_id,
                "channel_name": ch.channel_name,
                "channel_type": ch.channel_type,
                "is_active": ch.is_active,
                "config": ch.config,
                "created_at": ch.created_at
            }
            for ch in channels
        ]
    }

@router.post("/channels")
async def add_channel(
    channel_id: str,
    channel_name: str,
    channel_type: str,
    config: dict = None,
    db: AsyncSession = Depends(get_db)
):
    """添加频道配置"""
    channel = Channel(
        channel_id=channel_id,
        channel_name=channel_name,
        channel_type=channel_type,
        config=config or {}
    )
    
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    
    return {"message": "频道添加成功", "channel_id": channel.id}

@router.get("/filter-rules")
async def get_filter_rules(db: AsyncSession = Depends(get_db)):
    """获取过滤规则"""
    result = await db.execute(select(FilterRule))
    rules = result.scalars().all()
    
    return {
        "rules": [
            {
                "id": rule.id,
                "rule_type": rule.rule_type,
                "pattern": rule.pattern,
                "action": rule.action,
                "is_active": rule.is_active,
                "created_at": rule.created_at
            }
            for rule in rules
        ]
    }

@router.post("/filter-rules")
async def add_filter_rule(
    rule_type: str,
    pattern: str,
    action: str,
    db: AsyncSession = Depends(get_db)
):
    """添加过滤规则"""
    rule = FilterRule(
        rule_type=rule_type,
        pattern=pattern,
        action=action
    )
    
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    
    return {"message": "过滤规则添加成功", "rule_id": rule.id}

@router.get("/config")
async def get_system_config():
    """获取系统配置"""
    return {
        "auto_forward_delay": settings.AUTO_FORWARD_DELAY,
        "source_channels": settings.SOURCE_CHANNELS,
        "review_group_id": settings.REVIEW_GROUP_ID,
        "target_channel_id": settings.TARGET_CHANNEL_ID,
        "ad_keywords": settings.AD_KEYWORDS,
        "channel_replacements": settings.CHANNEL_REPLACEMENTS
    }

@router.get("/health")
async def health_check():
    """系统健康检查"""
    try:
        # 检查数据库连接
        async with AsyncSessionLocal() as db:
            await db.execute("SELECT 1")
        
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }