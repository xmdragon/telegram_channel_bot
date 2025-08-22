"""
系统维护API
负责系统重置、重启和数据清理等维护操作
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import psutil
import shutil
import asyncio
import subprocess
from pathlib import Path
from app.core.path_config import PathConfig
from app.storage.redis_store import get_redis_message_store
from app.storage.json_store import get_json_channel_store
from app.services.system_monitor import system_monitor
from app.telegram.auth import auth_manager
from app.core.routes import ROUTES
from app.api.websocket import websocket_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system-maintenance"])

@router.post(ROUTES.system.restart)
async def restart_services() -> Dict[str, Any]:
    """重启服务"""
    try:
        # 重启Telegram采集器进程
        try:
            # 先停止telegram_collector.py进程
            collector_stopped = False
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and any('telegram_collector.py' in str(arg) for arg in cmdline):
                        logger.info(f"停止Telegram采集器进程 PID: {proc.info['pid']}")
                        proc.terminate()
                        proc.wait(timeout=5)  # 等待进程优雅退出
                        collector_stopped = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    continue
            
            # 重新启动telegram_collector.py
            if collector_stopped:
                # 使用nohup在后台启动
                result = subprocess.Popen(
                    ['nohup', 'python3', 'telegram_collector.py'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                logger.info(f"重启Telegram采集器进程: PID {result.pid}")
            
            # 同时重启内部客户端连接（兼容性）
            if auth_manager and auth_manager.client:
                await auth_manager.client.disconnect()
                await auth_manager.ensure_connected()
                logger.info("Telegram内部客户端连接已重启")
                
        except Exception as e:
            logger.error(f"重启Telegram服务失败: {e}")
        
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

@router.post(ROUTES.system.reset)
async def reset_system() -> Dict[str, Any]:
    """重置消息系统 - 清空所有消息数据和媒体文件，通过WebSocket实时推送进度"""
    operation = "system_reset"
    message_keys = []
    
    try:
        # 步骤1：开始重置 (5%)
        await websocket_manager.broadcast_progress(operation, 5, "开始系统重置...")
        logger.warning("🚨 执行系统重置操作 - 这将清空所有消息数据")
        
        # 步骤2：停止采集服务 (15%)
        await websocket_manager.broadcast_progress(operation, 15, "停止采集服务...")
        from app.services.config_manager import config_manager
        await config_manager.set_boolean('collection.enabled', False, "系统重置时自动禁用采集")
        logger.info("已通过配置禁用采集服务")
        
        # 步骤3：连接存储层 (25%)
        await websocket_manager.broadcast_progress(operation, 25, "连接存储层...")
        redis_store = get_redis_message_store()
        channel_store = get_json_channel_store()
        
        # 步骤4：清空Redis消息数据 (45%)
        await websocket_manager.broadcast_progress(operation, 45, "清空Redis消息数据...")
        if redis_store and redis_store.redis:
            # 删除所有消息键
            message_keys = redis_store.redis.keys("msg:*")
            if message_keys:
                # 分批删除，避免阻塞
                batch_size = 1000
                for i in range(0, len(message_keys), batch_size):
                    batch = message_keys[i:i + batch_size]
                    redis_store.redis.delete(*batch)
                    progress = 45 + (10 * (i + len(batch)) / len(message_keys))
                    await websocket_manager.broadcast_progress(
                        operation, 
                        int(progress), 
                        f"删除消息 {i + len(batch)}/{len(message_keys)}..."
                    )
                logger.info(f"清空了 {len(message_keys)} 条Redis消息")
            
            # 删除其他消息相关的键
            pending_keys = redis_store.redis.keys("pending_messages")
            if pending_keys:
                redis_store.redis.delete(*pending_keys)
            
            # 清空WebSocket连接信息
            ws_keys = redis_store.redis.keys("websocket:*")
            if ws_keys:
                redis_store.redis.delete(*ws_keys)
            
            # 清空频道采集点（checkpoint）- 修复采集问题
            checkpoint_keys = redis_store.redis.keys("channel:checkpoint*")
            if checkpoint_keys:
                redis_store.redis.delete(*checkpoint_keys)
                logger.info(f"清空了 {len(checkpoint_keys)} 个频道采集点")
        
        # 步骤5：清空临时媒体目录 (65%)
        await websocket_manager.broadcast_progress(operation, 65, "清空临时媒体目录...")
        temp_media_dir = Path(PathConfig.TEMP_MEDIA_DIR)
        if temp_media_dir.exists():
            # 删除目录内容但保留目录
            items = list(temp_media_dir.iterdir())
            for i, item in enumerate(items):
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                    
                    # 更新进度
                    if i % 10 == 0 or i == len(items) - 1:
                        progress = 65 + (10 * (i + 1) / len(items))
                        await websocket_manager.broadcast_progress(
                            operation, 
                            int(progress), 
                            f"清理媒体文件 {i + 1}/{len(items)}..."
                        )
                except Exception as e:
                    logger.warning(f"删除媒体文件失败 {item}: {e}")
            logger.info(f"清空临时媒体目录: {temp_media_dir}")
        
        # 步骤6：重置频道采集点 (85%)
        await websocket_manager.broadcast_progress(operation, 85, "重置频道采集点...")
        all_channels = channel_store.get_all_channels()
        source_channels = [ch for ch in all_channels if ch.get('channel_type') == 'source']
        reset_count = 0
        
        for i, channel in enumerate(source_channels):
            old_id = channel.get('last_message_id', 0)
            channel['last_message_id'] = 0
            channel_store.update_channel(channel)
            reset_count += 1
            
            # 更新进度
            progress = 85 + (10 * (i + 1) / len(source_channels))
            channel_name = channel.get('channel_title', channel.get('channel_name', channel['channel_id']))
            await websocket_manager.broadcast_progress(
                operation, 
                int(progress), 
                f"重置频道 {channel_name} ({i + 1}/{len(source_channels)})"
            )
            logger.info(f"重置频道 {channel.get('channel_id')} 采集点: {old_id} -> 0")
        
        # 步骤7：完成 (100%)
        await websocket_manager.broadcast_progress(operation, 100, "系统重置完成")
        
        result = {
            "success": True,
            "message": "系统重置完成，采集服务已停止",
            "details": {
                "collection_disabled": True,
                "cleared_messages": len(message_keys),
                "reset_channels": reset_count,
                "temp_media_cleared": True,
                "restart_instructions": "使用服务控制API或配置页面重新启用采集"
            }
        }
        
        logger.info("✅ 系统重置操作完成")
        return result
        
    except Exception as e:
        logger.error(f"系统重置失败: {e}")
        await websocket_manager.broadcast_progress(operation, 100, f"重置失败: {str(e)}")
        return {
            "success": False,
            "message": f"系统重置失败: {str(e)}"
        }