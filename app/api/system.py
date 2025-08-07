"""
系统状态API路由
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import psutil
import os
import platform
from datetime import datetime, timedelta
from sqlalchemy import select, func

from app.services.system_monitor import system_monitor
from app.services.history_collector import history_collector
from app.core.database import AsyncSessionLocal, Message, Channel
from app.telegram.auth import auth_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["system"])

# 记录启动时间
START_TIME = datetime.now()

@router.get("/status")
async def get_system_status() -> Dict[str, Any]:
    """获取系统状态"""
    try:
        status_summary = await system_monitor.get_status_summary()
        return {
            "success": True,
            "data": status_summary
        }
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/detailed")
async def get_detailed_status() -> Dict[str, Any]:
    """获取详细系统状态"""
    try:
        # 获取系统信息
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # 计算运行时间
        uptime = datetime.now() - START_TIME
        uptime_str = f"{uptime.days}天 {uptime.seconds // 3600}小时 {(uptime.seconds % 3600) // 60}分钟"
        
        # 获取数据库统计
        async with AsyncSessionLocal() as db:
            # 消息总数
            total_messages = await db.scalar(select(func.count(Message.id)))
            # 今日消息数
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_messages = await db.scalar(
                select(func.count(Message.id)).where(Message.created_at >= today_start)
            )
            # 频道数量
            total_channels = await db.scalar(select(func.count(Channel.id)))
            source_channels = await db.scalar(
                select(func.count(Channel.id)).where(Channel.channel_type == 'source')
            )
            target_channels = await db.scalar(
                select(func.count(Channel.id)).where(Channel.channel_type == 'target')
            )
        
        # 获取Telegram状态
        telegram_status = "未连接"
        telegram_user = None
        if auth_manager and auth_manager.client:
            try:
                me = await auth_manager.client.get_me()
                telegram_status = "已连接"
                telegram_user = f"@{me.username}" if me.username else me.first_name
            except:
                telegram_status = "连接错误"
        
        # 获取监控状态
        current_status = await system_monitor.get_current_status()
        
        return {
            "success": True,
            "data": {
                "system": {
                    "uptime": uptime_str,
                    "cpu_percent": cpu_percent,
                    "memory_used": f"{memory.percent:.1f}%",
                    "memory_mb": f"{memory.used / 1024 / 1024:.0f} MB",
                    "disk_used": f"{disk.percent:.1f}%",
                    "disk_gb": f"{disk.used / 1024 / 1024 / 1024:.1f} GB",
                    "platform": platform.system(),
                    "python_version": platform.python_version()
                },
                "statistics": {
                    "total_messages": total_messages or 0,
                    "today_messages": today_messages or 0,
                    "total_channels": total_channels or 0,
                    "source_channels": source_channels or 0,
                    "target_channels": target_channels or 0
                },
                "telegram": {
                    "status": telegram_status,
                    "user": telegram_user,
                    "auth": current_status.telegram_auth if current_status else False,
                    "connected": current_status.telegram_connected if current_status else False
                },
                "services": {
                    "web_server": "running",
                    "telegram_bot": "running" if telegram_status == "已连接" else "stopped",
                    "database": "running",
                    "message_processor": "running",
                    "system_monitor": "running" if current_status else "stopped"
                },
                "errors": current_status.errors if current_status else [],
                "warnings": current_status.warnings if current_status else [],
                "last_message_time": current_status.last_message_time.isoformat() if current_status and current_status.last_message_time else None
            }
        }
    except Exception as e:
        logger.error(f"获取详细系统状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history-collection/progress")
async def get_collection_progress() -> Dict[str, Any]:
    """获取历史消息采集进度"""
    try:
        all_progress = await history_collector.get_all_progress()
        
        progress_data = {}
        for channel_id, progress in all_progress.items():
            progress_data[channel_id] = {
                "channel_id": progress.channel_id,
                "channel_name": progress.channel_name,
                "total_messages": progress.total_messages,
                "collected_messages": progress.collected_messages,
                "status": progress.status,
                "start_time": progress.start_time.isoformat(),
                "end_time": progress.end_time.isoformat() if progress.end_time else None,
                "error_message": progress.error_message,
                "progress_percent": (
                    int((progress.collected_messages / progress.total_messages) * 100) 
                    if progress.total_messages > 0 else 0
                )
            }
        
        return {
            "success": True,
            "data": progress_data
        }
    except Exception as e:
        logger.error(f"获取历史采集进度失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/history-collection/start/{channel_id}")
async def start_history_collection(channel_id: str, limit: int = 100) -> Dict[str, Any]:
    """开始历史消息采集"""
    try:
        success = await history_collector.start_collection(channel_id, limit)
        
        if success:
            return {
                "success": True,
                "message": f"已开始采集频道 {channel_id} 的历史消息"
            }
        else:
            return {
                "success": False,
                "message": f"启动频道 {channel_id} 历史消息采集失败"
            }
    except Exception as e:
        logger.error(f"启动历史消息采集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/history-collection/stop/{channel_id}")
async def stop_history_collection(channel_id: str) -> Dict[str, Any]:
    """停止历史消息采集"""
    try:
        success = await history_collector.stop_collection(channel_id)
        
        if success:
            return {
                "success": True,
                "message": f"已停止频道 {channel_id} 的历史消息采集"
            }
        else:
            return {
                "success": False,
                "message": f"频道 {channel_id} 没有正在进行的采集任务"
            }
    except Exception as e:
        logger.error(f"停止历史消息采集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查"""
    try:
        current_status = await system_monitor.get_current_status()
        
        if not current_status:
            return {
                "success": True,
                "status": "starting",
                "message": "系统正在启动"
            }
        
        # 判断系统健康状态
        if current_status.errors:
            status = "unhealthy"
            message = f"系统异常: {', '.join(current_status.errors[:2])}"
        elif current_status.warnings:
            status = "warning"
            message = f"系统警告: {', '.join(current_status.warnings[:2])}"
        elif current_status.telegram_auth and current_status.telegram_connected:
            status = "healthy"
            message = "系统运行正常"
        else:
            status = "initializing"
            message = "系统正在初始化"
        
        return {
            "success": True,
            "status": status,
            "message": message,
            "timestamp": current_status.timestamp.isoformat(),
            "uptime": (current_status.timestamp - current_status.timestamp).total_seconds()  # 简化计算
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "success": False,
            "status": "error",
            "message": f"健康检查失败: {str(e)}"
        }