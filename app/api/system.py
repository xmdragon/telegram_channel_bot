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
from app.services.system_monitor import system_monitor
from app.services.history_collector import history_collector
from app.storage.redis_store import get_redis_message_store
from app.storage.json_store import get_json_channel_store
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
        
        # 从 Redis 获取统计数据
        redis_store = get_redis_message_store()
        channel_store = get_json_channel_store()
        
        # 获取消息统计
        pending_messages = len(redis_store.get_pending_messages(limit=10000))
        all_messages_keys = redis_store.redis.keys("msg:*")
        total_messages = len(all_messages_keys)
        
        # 简单统计转发消息数
        forwarded_count = 0
        for key in all_messages_keys[:1000]:  # 限制检查数量以提高性能
            try:
                msg_data = redis_store.redis.hgetall(key)
                if msg_data.get(b'status') == b'forwarded':
                    forwarded_count += 1
            except:
                continue
        
        # 获取源频道数量
        all_channels = channel_store.get_all_channels()
        source_channels = len([ch for ch in all_channels if ch.get('channel_type') == 'source'])
        
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
                "source_channels": source_channels,
                "total_messages": total_messages,
                "pending_messages": pending_messages,
                "forwarded_messages": forwarded_count
            },
            "services": {
                "telegram_client": telegram_connected,
                "message_processor": True,  # 始终运行
                "scheduler": True,  # 始终运行
                "redis": True  # Redis 存储服务
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
                "redis": False
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
        
        # 检查是否有新的消息处理（从 Redis 检查）
        try:
            redis_store = get_redis_message_store()
            # 简单统计最近的消息数量
            recent_keys = redis_store.redis.keys("msg:*")
            recent_count = 0
            
            for key in recent_keys[:50]:  # 限制检查数量
                try:
                    msg_data = redis_store.redis.hgetall(key)
                    created_at_str = msg_data.get(b'created_at', b'').decode('utf-8')
                    if created_at_str:
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        if created_at >= since_time:
                            recent_count += 1
                except:
                    continue
            
            if recent_count > 0:
                logs.append({
                    "timestamp": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "level": "INFO", 
                    "source": "message",
                    "message": f"处理了 {recent_count} 条新消息"
                })
        except Exception as e:
            logger.debug(f"检查最近消息失败: {e}")
            
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