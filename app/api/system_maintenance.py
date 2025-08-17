"""
系统维护API
负责系统重置、重启和数据清理等维护操作
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import psutil
import shutil
from pathlib import Path
from app.core.path_config import PathConfig
from app.storage.redis_store import get_redis_message_store
from app.storage.json_store import get_json_channel_store
from app.services.system_monitor import system_monitor
from app.telegram.auth import auth_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["system-maintenance"])

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

@router.post("/reset")
async def reset_system() -> Dict[str, Any]:
    """重置消息系统 - 清空所有消息数据和媒体文件"""
    try:
        logger.warning("🚨 执行系统重置操作 - 这将清空所有消息数据")
        
        # 1. 停止采集服务（通过配置）
        from app.services.config_manager import config_manager
        await config_manager.set_config('collection.enabled', False, "系统重置时自动禁用采集")
        logger.info("已通过配置禁用采集服务")
        
        stopped_processes = []
        
        # 2. 清空Redis中的消息数据
        redis_store = get_redis_message_store()
        if redis_store and redis_store.redis:
            # 删除所有消息键
            message_keys = redis_store.redis.keys("msg:*")
            if message_keys:
                redis_store.redis.delete(*message_keys)
                logger.info(f"清空了 {len(message_keys)} 条Redis消息")
            
            # 删除其他消息相关的键
            pending_keys = redis_store.redis.keys("pending_messages")
            if pending_keys:
                redis_store.redis.delete(*pending_keys)
            
            # 清空WebSocket连接信息
            ws_keys = redis_store.redis.keys("websocket:*")
            if ws_keys:
                redis_store.redis.delete(*ws_keys)
        
        # 3. 清空temp_media目录
        temp_media_dir = Path(PathConfig.TEMP_MEDIA_DIR)
        if temp_media_dir.exists():
            # 删除目录内容但保留目录
            for item in temp_media_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except Exception as e:
                    logger.warning(f"删除媒体文件失败 {item}: {e}")
            logger.info(f"清空临时媒体目录: {temp_media_dir}")
        
        # 4. 重置所有频道的last_message_id
        channel_store = get_json_channel_store()
        all_channels = channel_store.get_all_channels()
        reset_count = 0
        
        for channel in all_channels:
            if channel.get('channel_type') == 'source':
                old_id = channel.get('last_message_id', 0)
                channel['last_message_id'] = 0
                channel_store.update_channel(channel)
                reset_count += 1
                logger.info(f"重置频道 {channel.get('title', channel['channel_id'])} 采集点: {old_id} -> 0")
        
        return {
            "success": True,
            "message": "系统重置完成，采集服务已停止",
            "details": {
                "collection_disabled": True,
                "cleared_messages": len(message_keys) if 'message_keys' in locals() else 0,
                "reset_channels": reset_count,
                "temp_media_cleared": True,
                "restart_instructions": "使用服务控制API或配置页面重新启用采集"
            }
        }
        
    except Exception as e:
        logger.error(f"系统重置失败: {e}")
        return {
            "success": False,
            "message": f"系统重置失败: {str(e)}"
        }