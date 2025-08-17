"""
管理员历史采集API
包括：启动历史采集、获取采集进度、停止采集
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
import logging

from app.core.route_config import ROUTES

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(ROUTES.admin.collect_history)
async def collect_channel_history(
    channel_id: str,
    limit: int = Query(default=100, description="采集消息数量限制")
):
    """采集频道历史消息"""
    from app.services.history_collector import history_collector
    
    # 启动历史消息采集
    success = await history_collector.start_collection(channel_id, limit)
    
    if success:
        return {
            "success": True,
            "message": f"已启动频道 {channel_id} 的历史消息采集，限制 {limit} 条"
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="启动历史消息采集失败，请检查频道ID或是否已在采集中"
        )

@router.get(ROUTES.admin.collect_history_progress)
async def get_collection_progress():
    """获取所有历史消息采集进度"""
    from app.services.history_collector import history_collector
    
    all_progress = await history_collector.get_all_progress()
    
    # 转换为可序列化的格式
    result = {}
    for channel_id, progress in all_progress.items():
        result[channel_id] = {
            "channel_name": progress.channel_name,
            "total_messages": progress.total_messages,
            "collected_messages": progress.collected_messages,
            "status": progress.status,
            "start_time": progress.start_time.isoformat() if progress.start_time else None,
            "end_time": progress.end_time.isoformat() if progress.end_time else None,
            "error_message": progress.error_message
        }
    
    return result

@router.post(ROUTES.admin.collect_history_stop)
async def stop_collection(channel_id: str):
    """停止频道历史消息采集"""
    from app.services.history_collector import history_collector
    
    success = await history_collector.stop_collection(channel_id)
    
    if success:
        return {
            "success": True,
            "message": f"已停止频道 {channel_id} 的历史消息采集"
        }
    else:
        return {
            "success": False,
            "message": f"频道 {channel_id} 当前没有在采集中"
        }