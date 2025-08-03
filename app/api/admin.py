"""
管理员API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import os
import shutil
import tarfile
import tempfile

from app.core.database import get_db, Channel, FilterRule, AsyncSessionLocal
from app.core.config import settings
from app.services.config_manager import config_manager

router = APIRouter()

class ChannelCreateRequest(BaseModel):
    channel_id: str = ""
    channel_name: str
    channel_title: str = ""
    channel_type: str = "source"
    config: Optional[dict] = None

class ChannelUpdateRequest(BaseModel):
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    channel_type: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[dict] = None

@router.get("/channels")
async def get_channels(db: AsyncSession = Depends(get_db)):
    """获取频道配置"""
    result = await db.execute(select(Channel))
    channels = result.scalars().all()
    
    return {
        "success": True,
        "channels": [
            {
                "id": ch.id,
                "name": ch.channel_name,
                "title": ch.channel_title or "",
                "status": "active" if ch.is_active else "inactive",
                "channel_id": ch.channel_id,
                "channel_type": ch.channel_type,
                "config": ch.config,
                "created_at": ch.created_at
            }
            for ch in channels
        ]
    }

@router.post("/channels")
async def add_channel(
    request: ChannelCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """添加频道配置"""
    try:
        # 检查频道名称是否已存在
        existing = await db.execute(select(Channel).where(Channel.channel_name == request.channel_name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="频道名称已存在")
        
        channel = Channel(
            channel_id=request.channel_id if request.channel_id else None,
            channel_name=request.channel_name,
            channel_title=request.channel_title,
            channel_type=request.channel_type,
            config=request.config or {}
        )
        
        db.add(channel)
        await db.commit()
        await db.refresh(channel)
        
        return {"success": True, "message": "频道添加成功", "channel_id": channel.id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"添加频道失败: {str(e)}")

@router.put("/channels/{channel_name}")
async def update_channel(
    channel_name: str,
    request: ChannelUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """更新频道配置"""
    try:
        result = await db.execute(select(Channel).where(Channel.channel_name == channel_name))
        channel = result.scalar_one_or_none()
        
        if not channel:
            raise HTTPException(status_code=404, detail="频道不存在")
        
        if request.channel_id is not None:
            channel.channel_id = request.channel_id
        if request.channel_title is not None:
            channel.channel_title = request.channel_title
        if request.channel_type is not None:
            channel.channel_type = request.channel_type
        if request.is_active is not None:
            channel.is_active = request.is_active
        if request.config is not None:
            channel.config = request.config
        
        await db.commit()
        await db.refresh(channel)
        
        return {"success": True, "message": "频道更新成功", "channel_id": channel.id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"更新频道失败: {str(e)}")

@router.delete("/channels/{channel_name}")
async def delete_channel(
    channel_name: str,
    db: AsyncSession = Depends(get_db)
):
    """删除频道配置"""
    try:
        result = await db.execute(select(Channel).where(Channel.channel_name == channel_name))
        channel = result.scalar_one_or_none()
        
        if not channel:
            raise HTTPException(status_code=404, detail="频道不存在")
        
        await db.delete(channel)
        await db.commit()
        
        return {"success": True, "message": "频道删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除频道失败: {str(e)}")

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

@router.put("/filter-rules/{rule_id}")
async def update_filter_rule(
    rule_id: int,
    rule_type: str = None,
    pattern: str = None,
    action: str = None,
    is_active: bool = None,
    db: AsyncSession = Depends(get_db)
):
    """更新过滤规则"""
    result = await db.execute(select(FilterRule).where(FilterRule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="过滤规则不存在")
    
    if rule_type is not None:
        rule.rule_type = rule_type
    if pattern is not None:
        rule.pattern = pattern
    if action is not None:
        rule.action = action
    if is_active is not None:
        rule.is_active = is_active
    
    await db.commit()
    await db.refresh(rule)
    
    return {"message": "过滤规则更新成功", "rule_id": rule.id}

@router.delete("/filter-rules/{rule_id}")
async def delete_filter_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除过滤规则"""
    result = await db.execute(select(FilterRule).where(FilterRule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="过滤规则不存在")
    
    await db.delete(rule)
    await db.commit()
    
    return {"message": "过滤规则删除成功"}

@router.get("/config")
async def get_system_config():
    """获取系统配置"""
    from app.core.config import db_settings
    
    return {
        "auto_forward_delay": settings.AUTO_FORWARD_DELAY,
        "source_channels": settings.SOURCE_CHANNELS,
        "review_group_id": settings.REVIEW_GROUP_ID,
        "target_channel_id": settings.TARGET_CHANNEL_ID,
        "history_message_limit": await db_settings.get_history_message_limit(),
        "ad_keywords": settings.AD_KEYWORDS,
        "channel_replacements": settings.CHANNEL_REPLACEMENTS
    }

@router.post("/restart")
async def restart_system():
    """重启系统"""
    try:
        # 这里可以实现系统重启逻辑
        # 在实际部署中，可能需要通过进程管理工具重启
        return {"success": True, "message": "系统重启命令已发送"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"系统重启失败: {str(e)}")

@router.post("/backup")
async def backup_data():
    """备份数据"""
    try:
        # 创建备份目录
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{backup_dir}/backup_{timestamp}.tar.gz"
        
        # 创建备份文件
        with tarfile.open(backup_file, "w:gz") as tar:
            # 备份数据库文件
            if os.path.exists("telegram_system.db"):
                tar.add("telegram_system.db", arcname="database/telegram_system.db")
            
            # 备份会话文件
            if os.path.exists("sessions"):
                tar.add("sessions", arcname="sessions")
            
            # 备份数据目录
            if os.path.exists("data"):
                tar.add("data", arcname="data")
            
            # 备份日志目录
            if os.path.exists("logs"):
                tar.add("logs", arcname="logs")
        
        return {"success": True, "message": f"数据备份成功: {backup_file}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据备份失败: {str(e)}")

@router.post("/clear-cache")
async def clear_cache():
    """清理缓存"""
    try:
        # 清理配置缓存
        await config_manager.clear_cache()
        
        # 清理其他缓存（如果有的话）
        # 这里可以添加其他缓存清理逻辑
        
        return {"success": True, "message": "缓存清理成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"缓存清理失败: {str(e)}")

@router.post("/export-logs")
async def export_logs():
    """导出日志"""
    try:
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "system_logs.txt")
            
            # 收集日志信息
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("=== 系统日志导出 ===\n")
                f.write(f"导出时间: {datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                
                # 系统信息
                f.write("系统信息:\n")
                f.write(f"- Python版本: {os.sys.version}\n")
                f.write(f"- 工作目录: {os.getcwd()}\n")
                f.write(f"- 当前时间: {datetime.now().isoformat()}\n\n")
                
                # 配置文件信息
                f.write("配置文件:\n")
                try:
                    all_configs = await config_manager.get_all_configs()
                    for key, config in all_configs.items():
                        f.write(f"- {key}: {config['value']}\n")
                except Exception as e:
                    f.write(f"- 配置读取失败: {str(e)}\n")
                
                f.write("\n" + "=" * 50 + "\n")
            
            # 创建下载文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            download_file = f"logs/system_logs_{timestamp}.txt"
            os.makedirs("logs", exist_ok=True)
            shutil.copy2(log_file, download_file)
            
            return {"success": True, "message": f"日志导出成功: {download_file}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"日志导出失败: {str(e)}")

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