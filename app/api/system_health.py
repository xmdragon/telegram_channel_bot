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



@router.get(ROUTES.system.health)
async def health_check() -> Dict[str, Any]:
    """健康检查"""
    try:
        current_status = await system_monitor.get_current_status()
        
        # 检查存储连接
        storage_status = "unknown"
        try:
            redis_store = redis_manager
            redis_manager.client.ping()  # 测试Redis连接
            
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
