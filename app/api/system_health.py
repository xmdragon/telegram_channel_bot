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
from app.storage.redis_store import get_redis_message_store
from app.storage.json_store import get_json_channel_store
from app.core.routes import ROUTES
from app.api.websocket import websocket_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system-health"])

# 记录启动时间
START_TIME = datetime.now()

def check_telegram_collector_process() -> bool:
    """检测telegram_collector.py进程是否运行"""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any('telegram_collector.py' in str(arg) for arg in cmdline):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    except Exception as e:
        logger.error(f"检测telegram_collector进程失败: {e}")
        return False

@router.get(ROUTES.system.status)
async def get_system_status() -> Dict[str, Any]:
    """获取系统状态 - 快速版本，不包含消息统计"""
    try:
        uptime_seconds = (datetime.now() - START_TIME).total_seconds()
        
        # 连接存储层（快速检查）
        redis_store = get_redis_message_store()
        channel_store = get_json_channel_store()
        
        # 获取频道信息（快速）
        all_channels = channel_store.get_all_channels()
        source_channels = len([ch for ch in all_channels if ch.get('channel_type') == 'source'])
        
        # 检查服务状态（快速）
        telegram_connected = False
        web_server_running = True
        scheduler_running = True
        
        # 快速检查健康监控状态
        try:
            import redis
            from app.core.config import settings
            r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2)
            health_data = r.get('service_health:telegram_collector')
            if health_data:
                health_obj = json.loads(health_data)
                telegram_connected = (
                    health_obj.get('status') == 'healthy' and
                    health_obj.get('metadata', {}).get('telegram_authenticated', False)
                )
            
            scheduler_data = r.get('service_health:message_scheduler')
            if scheduler_data:
                scheduler_obj = json.loads(scheduler_data)
                scheduler_running = scheduler_obj.get('status') == 'healthy'
                
        except Exception as e:
            logger.warning(f"健康监控检查失败: {e}")
        
        result = {
            "services": {
                "telegram_client": telegram_connected,
                "message_processor": web_server_running,
                "scheduler": scheduler_running,
                "redis": True
            },
            "system": {
                "uptime": uptime_seconds,
                "version": "2.0.0",
                "source_channels": source_channels
            }
        }
        
        logger.info("✅ 系统状态检查完成（快速版本）")
        return result
        
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        return {
            "services": {
                "telegram_client": False,
                "message_processor": False,
                "scheduler": False,
                "redis": False
            },
            "system": {
                "uptime": 0,
                "version": "2.0.0",
                "source_channels": 0
            }
        }

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
        
        # 从 Redis 和 JSON 获取统计数据
        redis_store = get_redis_message_store()
        channel_store = get_json_channel_store()
        
        # 消息统计
        all_message_keys = redis_store.redis.keys("msg:*")
        total_messages = len(all_message_keys)
        
        # 今日消息数（简化版，从最新消息中算出）
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_messages = 0
        for key in all_message_keys[:500]:  # 限制检查数量
            try:
                msg_data = redis_store.redis.hgetall(key)
                created_at_str = msg_data.get(b'created_at', b'').decode('utf-8')
                if created_at_str:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    if created_at >= today_start:
                        today_messages += 1
            except:
                continue
        
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
                    "telegram_bot": "running" if check_telegram_collector_process() else "stopped",
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
            redis_store = get_redis_message_store()
            redis_store.redis.ping()  # 测试Redis连接
            
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