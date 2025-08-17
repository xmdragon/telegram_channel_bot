"""
系统监控API
负责历史消息采集进度监控和实时状态跟踪
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
from datetime import datetime, timedelta
from app.services.history_collector import history_collector
from app.storage.redis_store import get_redis_message_store
from app.core.routes import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["system-monitor"])

@router.get(ROUTES.system.history_progress)
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

@router.post(ROUTES.system.history_start)
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

@router.post(ROUTES.system.history_stop)
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

@router.get(ROUTES.system.logs_realtime)  
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