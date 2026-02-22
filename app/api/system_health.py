"""
系统健康检查API
负责系统状态监控、健康检查和性能统计
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import psutil
import platform
import json
import asyncio
from datetime import datetime
from app.services.system_monitor import system_monitor
from app.storage.redis_manager import redis_manager
from app.storage.json_store import get_json_channel_store
from app.core.route_config import ROUTES
from app.api.websocket import websocket_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system-health"])

# 记录启动时间
START_TIME = datetime.now()



@router.get(ROUTES.system.status_detailed)
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
        
        # 从数据库和JSON获取统计数据
        channel_store = get_json_channel_store()

        # 消息统计 - 使用SQLite
        stats = redis_manager.get_statistics()
        total_messages = stats.get("total_messages", 0)
        today_messages = redis_manager.get_today_message_count()
        
        # 频道数量
        all_channels = channel_store.get_all_channels()
        total_channels = len(all_channels)
        source_channels = len([ch for ch in all_channels if ch.get('channel_type') == 'source'])
        target_channels = len([ch for ch in all_channels if ch.get('channel_type') == 'target'])
        
        # 获取Telegram状态
        telegram_status = "未连接"
        telegram_user = None
        try:
            # 使用双Session管理器获取状态
            from app.telegram.dual_session_manager import dual_session_manager
            client = await dual_session_manager.get_listener_client()
            
            if client:
                me = await client.get_me()
                telegram_status = "已连接"
                telegram_user = f"@{me.username}" if me.username else me.first_name
        except Exception:
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
                    "total_messages": total_messages,
                    "today_messages": today_messages,
                    "total_channels": total_channels,
                    "source_channels": source_channels,
                    "target_channels": target_channels
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
                    "storage": "running",
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

@router.get(ROUTES.system.health)
async def health_check() -> Dict[str, Any]:
    """健康检查"""
    try:
        current_status = await system_monitor.get_current_status()
        
        # 检查存储连接
        storage_status = "unknown"
        try:
            if not redis_manager.is_healthy():
                raise RuntimeError("数据库连接不健康")

            channel_store = get_json_channel_store()
            channel_store.get_all_channels()  # 测试JSON文件访问

            storage_status = "connected"
        except Exception as e:
            logger.error(f"存储连接检查失败: {e}")
            storage_status = "disconnected"
        
        if not current_status:
            return {
                "success": True,
                "status": "starting",
                "message": "系统正在启动",
                "storage": storage_status,
                "version": "2.0.0"
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
            "storage": storage_status,
            "version": "2.0.0",
            "timestamp": current_status.timestamp.isoformat(),
            "uptime": (datetime.now() - START_TIME).total_seconds()
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "success": False,
            "status": "error",
            "message": f"健康检查失败: {str(e)}",
            "storage": "unknown",
            "version": "2.0.0"
        }

@router.get(ROUTES.system.health_service)
async def service_health_check(service_name: str) -> Dict[str, Any]:
    """获取指定服务的健康状态"""
    from app.services.health_monitor import HealthCheckService
    health = await HealthCheckService.get_service_health(service_name)
    if health:
        return health.to_dict()
    else:
        raise HTTPException(status_code=404, detail="服务未找到")
