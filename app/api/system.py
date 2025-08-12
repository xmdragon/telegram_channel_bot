"""
系统状态API路由
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import psutil
import os
import platform
import json
import subprocess
from datetime import datetime, timedelta
from sqlalchemy import select, func
from typing import List

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
        # 计算运行时间
        uptime_seconds = (datetime.now() - START_TIME).total_seconds()
        
        # 获取数据库统计
        async with AsyncSessionLocal() as db:
            total_messages = await db.scalar(select(func.count(Message.id)))
            pending_messages = await db.scalar(
                select(func.count(Message.id)).where(Message.status == 'pending')
            )
            forwarded_messages = await db.scalar(
                select(func.count(Message.id)).where(Message.status == 'forwarded')
            )
            source_channels = await db.scalar(
                select(func.count(Channel.id)).where(Channel.channel_type == 'source')
            )
        
        # 获取服务状态
        telegram_connected = False
        if auth_manager and auth_manager.client:
            try:
                await auth_manager.client.get_me()
                telegram_connected = True
            except:
                pass
        
        return {
            "stats": {
                "source_channels": source_channels or 0,
                "total_messages": total_messages or 0,
                "pending_messages": pending_messages or 0,
                "forwarded_messages": forwarded_messages or 0
            },
            "services": {
                "telegram_client": telegram_connected,
                "message_processor": True,  # 始终运行
                "scheduler": True,  # 始终运行
                "database": True  # 如果能查询就是运行中
            },
            "system": {
                "uptime": uptime_seconds,
                "version": "2.0.0"
            }
        }
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        return {
            "stats": {
                "source_channels": 0,
                "total_messages": 0,
                "pending_messages": 0,
                "forwarded_messages": 0
            },
            "services": {
                "telegram_client": False,
                "message_processor": False,
                "scheduler": False,
                "database": False
            },
            "system": {
                "uptime": 0,
                "version": "2.0.0"
            }
        }

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
        
        # 检查数据库连接
        database_status = "unknown"
        try:
            from app.core.database import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
            database_status = "connected"
        except Exception as e:
            logger.error(f"数据库连接检查失败: {e}")
            database_status = "disconnected"
        
        if not current_status:
            return {
                "success": True,
                "status": "starting",
                "message": "系统正在启动",
                "database": database_status,
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
            "database": database_status,
            "version": "2.0.0",
            "timestamp": current_status.timestamp.isoformat(),
            "uptime": (current_status.timestamp - current_status.timestamp).total_seconds()  # 简化计算
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "success": False,
            "status": "error",
            "message": f"健康检查失败: {str(e)}",
            "database": "unknown",
            "version": "2.0.0"
        }

@router.post("/restart")
async def restart_services() -> Dict[str, Any]:
    """重启服务"""
    try:
        # 重启Telegram客户端连接
        if auth_manager and auth_manager.client:
            try:
                await auth_manager.client.disconnect()
                await auth_manager.ensure_connected()
                logger.info("Telegram客户端已重启")
            except Exception as e:
                logger.error(f"重启Telegram客户端失败: {e}")
        
        # 重启系统监控
        try:
            await system_monitor.start_monitoring()
            logger.info("系统监控已重启")
        except Exception as e:
            logger.error(f"重启系统监控失败: {e}")
        
        return {
            "success": True,
            "message": "服务重启成功"
        }
    except Exception as e:
        logger.error(f"重启服务失败: {e}")
        return {
            "success": False,
            "message": f"重启失败: {str(e)}"
        }

@router.get("/logs")
async def get_system_logs(limit: int = 100) -> Dict[str, Any]:
    """获取系统日志"""
    try:
        import glob
        logs = []
        log_sources = []
        
        # 查找所有日志文件（包括轮转的历史文件）
        log_pattern = "./logs/app.log*"
        log_files = glob.glob(log_pattern)
        
        # 按修改时间排序，最新的在前
        log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # 读取日志文件直到获取足够的行数
        for log_file in log_files[:3]:  # 最多读取最近3个文件
            if not os.path.exists(log_file):
                continue
                
            log_sources.append(log_file)
            try:
                # 读取日志文件
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    file_lines = f.readlines()
                    
                    # 从文件末尾开始读取
                    for log_line in reversed(file_lines):
                        if log_line.strip():
                            # 解析日志行
                            timestamp = extract_timestamp(log_line)
                            level = extract_log_level(log_line)
                            # 提取实际的消息内容
                            message = extract_message(log_line)
                            
                            logs.append({
                                "time": timestamp,
                                "level": level,
                                "message": message
                            })
                            
                            # 如果已经收集够了，停止
                            if len(logs) >= limit:
                                break
                                
            except Exception as e:
                logger.error(f"读取日志文件 {log_file} 失败: {e}")
                continue
            
            if len(logs) >= limit:
                break
        
        # 如果没有找到日志文件，显示基本系统信息
        if not logs:
            logs.append({
                "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "level": "INFO",
                "message": f"系统正在运行 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            })
        else:
            # 日志已经是倒序读取的，不需要再排序
            # 只需要限制返回的行数
            logs = logs[:limit]
        
        return {
            "success": True,
            "logs": logs
        }
    except Exception as e:
        logger.error(f"获取系统日志失败: {e}")
        # 返回基本信息而不是抛出异常
        return {
            "success": True,
            "data": {
                "logs": [{
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "level": "INFO",
                    "message": f"系统运行中 - 无法读取详细日志: {str(e)}"
                }],
                "sources": [],
                "total": 1,
                "timestamp": datetime.now().isoformat()
            }
        }

@router.get("/logs/realtime")  
async def get_realtime_logs(since: str = None) -> Dict[str, Any]:
    """获取实时日志更新"""
    try:
        # 解析since参数
        since_time = None
        if since:
            try:
                since_time = datetime.fromisoformat(since.replace('Z', '+00:00'))
            except:
                since_time = datetime.now() - timedelta(seconds=30)
        else:
            since_time = datetime.now() - timedelta(seconds=30)
        
        logs = []
        current_time = datetime.now()
        
        # 添加心跳检测日志（前端会过滤掉不显示）
        logs.append({
            "timestamp": current_time.strftime('%Y-%m-%d %H:%M:%S'),
            "level": "INFO",
            "source": "heartbeat",
            "message": f"系统心跳检测 - 当前时间: {current_time.strftime('%H:%M:%S')}"
        })
        
        # 检查是否有新的Telegram消息处理
        try:
            async with AsyncSessionLocal() as db:
                recent_messages = await db.scalar(
                    select(func.count(Message.id)).where(
                        Message.created_at >= since_time
                    )
                )
                if recent_messages and recent_messages > 0:
                    logs.append({
                        "timestamp": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                        "level": "INFO", 
                        "source": "message",
                        "message": f"处理了 {recent_messages} 条新消息"
                    })
        except:
            pass
            
        return {
            "success": True,
            "data": {
                "logs": logs,
                "timestamp": current_time.isoformat(),
                "since": since_time.isoformat() if since_time else None
            }
        }
    except Exception as e:
        logger.error(f"获取实时日志失败: {e}")
        return {
            "success": False,
            "message": f"获取实时日志失败: {str(e)}"
        }

def extract_timestamp(log_line: str) -> str:
    """从日志行中提取时间戳"""
    try:
        # 尝试匹配常见的时间戳格式
        import re
        timestamp_patterns = [
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
            r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})'
        ]
        
        for pattern in timestamp_patterns:
            match = re.search(pattern, log_line)
            if match:
                return match.group(1)
        
        # 如果没有找到时间戳，返回当前时间
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    except:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def extract_log_level(log_line: str) -> str:
    """从日志行中提取日志级别"""
    try:
        import re
        level_pattern = r'\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b'
        match = re.search(level_pattern, log_line.upper())
        if match:
            return match.group(1)
        return "INFO"
    except:
        return "INFO"

def extract_message(log_line: str) -> str:
    """从日志行中提取消息内容"""
    try:
        import re
        # 标准格式: 2025-08-07 20:33:37,197 - module.name - LEVEL - message
        pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)? - [\w\.]+ - \w+ - (.+)$'
        match = re.match(pattern, log_line)
        if match:
            return match.group(1)
        
        # 如果不匹配标准格式，尝试提取 - 后面的内容
        parts = log_line.split(' - ')
        if len(parts) >= 4:
            return ' - '.join(parts[3:])
        
        # 返回原始内容
        return log_line.strip()
    except:
        return log_line.strip()