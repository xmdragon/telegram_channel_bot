"""
系统维护API
负责系统重置、重启和数据清理等维护操作
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import psutil
import shutil
import subprocess
from pathlib import Path
from app.core.path_config import PathConfig
from app.storage.redis_manager import redis_manager
from app.storage.json_store import get_json_channel_store
from app.services.system_monitor import system_monitor
from app.core.route_config import ROUTES
from app.api.websocket import websocket_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system-maintenance"])

@router.post(ROUTES.system.reset)
async def reset_system() -> Dict[str, Any]:
    """重置消息系统 - 清空所有消息数据和媒体文件，通过WebSocket实时推送进度"""
    operation = "system_reset"

    # 清理步骤状态追踪
    cleanup_status = {
        "redis_messages": {"success": False, "error": None, "count": 0},
        "redis_pending": {"success": False, "error": None, "count": 0},
        "redis_websocket": {"success": False, "error": None, "count": 0},
        "redis_checkpoints": {"success": False, "error": None, "count": 0},
        "temp_media": {"success": False, "error": None, "count": 0},
        "channel_reset": {"success": False, "error": None, "count": 0}
    }
    
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
        channel_store = get_json_channel_store()
        
        # 步骤4：清空消息数据 (45%)
        await websocket_manager.broadcast_progress(operation, 45, "清空消息数据...")

        # 清空消息和缓存数据（SQLite）
        try:
            result = redis_manager.reset_all_message_data()
            cache_result = redis_manager.clear_all_caches()
            deleted_total = result.get("messages_deleted", 0)
            deleted_total += cache_result.get("total", 0)
            cleanup_status["redis_messages"] = {
                "success": "error" not in result,
                "error": result.get("error"),
                "count": deleted_total,
            }
            logger.info(f"清空了 {deleted_total} 条消息和缓存数据")
        except Exception as message_error:
            cleanup_status["redis_messages"] = {
                "success": False,
                "error": str(message_error),
                "count": 0,
            }
            logger.error(f"清理消息数据失败: {message_error}")

        # 旧pending_messages键在SQLite中不存在，标记为成功
        cleanup_status["redis_pending"] = {
            "success": True, "error": None, "count": 0
        }

        # WebSocket连接信息在内存中管理，无需清理存储
        cleanup_status["redis_websocket"] = {
            "success": True, "error": None, "count": 0
        }

        # 频道采集点（checkpoint）通过频道重置处理
        cleanup_status["redis_checkpoints"] = {
            "success": True, "error": None, "count": 0
        }

        # 清空采集进度记录（断点续传位置）
        try:
            redis_manager.cache_delete("collector:current_channel_index")
            logger.info("清除采集进度记录，下次采集将从头开始")
        except Exception as progress_error:
            logger.error(f"清理采集进度记录失败: {progress_error}")

        # 步骤4：清空临时媒体目录 (60%)
        await websocket_manager.broadcast_progress(operation, 60, "清空临时媒体目录...")
        try:
            temp_media_dir = Path(PathConfig.TEMP_MEDIA_DIR)
            if temp_media_dir.exists():
                # 删除目录内容但保留目录
                items = list(temp_media_dir.iterdir())
                deleted_count = 0
                failed_count = 0
                
                for i, item in enumerate(items):
                    try:
                        if item.is_file():
                            item.unlink()
                            deleted_count += 1
                        elif item.is_dir():
                            shutil.rmtree(item)
                            deleted_count += 1
                        
                        # 更新进度
                        if i % 10 == 0 or i == len(items) - 1:
                            progress = 65 + (10 * (i + 1) / len(items))
                            await websocket_manager.broadcast_progress(
                                operation, 
                                int(progress), 
                                f"清理媒体文件 {i + 1}/{len(items)}..."
                            )
                    except Exception as e:
                        failed_count += 1
                        logger.warning(f"删除媒体文件失败 {item}: {e}")
                
                cleanup_status["temp_media"] = {
                    "success": failed_count == 0,
                    "error": f"删除失败 {failed_count} 个文件" if failed_count > 0 else None,
                    "count": deleted_count
                }
                
                if failed_count == 0:
                    logger.info(f"✅ 成功清空临时媒体目录: {temp_media_dir} (删除 {deleted_count} 个文件/文件夹)")
                else:
                    logger.warning(f"⚠️ 临时媒体目录清理完成: 成功删除 {deleted_count} 个，失败 {failed_count} 个")
            else:
                cleanup_status["temp_media"] = {
                    "success": True,
                    "error": None,
                    "count": 0
                }
                logger.info(f"ℹ️ 临时媒体目录不存在: {temp_media_dir}")
        except Exception as media_error:
            cleanup_status["temp_media"] = {
                "success": False,
                "error": str(media_error),
                "count": 0
            }
            logger.error(f"❌ 清理临时媒体目录失败: {media_error}")
        
        # 步骤5：重置频道采集点 (75%)
        await websocket_manager.broadcast_progress(operation, 75, "重置频道采集点...")
        try:
            all_channels = channel_store.get_all_channels()
            source_channels = [ch for ch in all_channels if ch.get('channel_type') == 'source']
            reset_count = 0
            failed_count = 0
            
            for i, channel in enumerate(source_channels):
                try:
                    old_id = channel.get('last_message_id', 0)
                    channel['last_message_id'] = 0
                    channel_store.update_channel(channel)
                    reset_count += 1
                    
                    # 更新进度
                    progress = 75 + (20 * (i + 1) / len(source_channels))
                    channel_name = channel.get('channel_title', channel.get('channel_name', channel['channel_id']))
                    await websocket_manager.broadcast_progress(
                        operation, 
                        int(progress), 
                        f"重置频道 {channel_name} ({i + 1}/{len(source_channels)})"
                    )
                    logger.info(f"重置频道 {channel.get('channel_id')} 采集点: {old_id} -> 0")
                except Exception as channel_error:
                    failed_count += 1
                    logger.error(f"重置频道 {channel.get('channel_id', 'unknown')} 采集点失败: {channel_error}")
            
            cleanup_status["channel_reset"] = {
                "success": failed_count == 0,
                "error": f"重置失败 {failed_count} 个频道" if failed_count > 0 else None,
                "count": reset_count
            }
            
            if failed_count == 0:
                logger.info(f"✅ 成功重置 {reset_count} 个源频道的采集点")
            else:
                logger.warning(f"⚠️ 频道采集点重置完成: 成功重置 {reset_count} 个，失败 {failed_count} 个")
        except Exception as channel_reset_error:
            cleanup_status["channel_reset"] = {
                "success": False,
                "error": str(channel_reset_error),
                "count": 0
            }
            logger.error(f"❌ 重置频道采集点失败: {channel_reset_error}")
        
        # 步骤7：完成 (100%)
        await websocket_manager.broadcast_progress(operation, 100, "系统重置完成")
        
        # 计算总体成功状态
        overall_success = all(status["success"] for status in cleanup_status.values())
        failed_operations = [k for k, v in cleanup_status.items() if not v["success"]]
        
        result = {
            "success": overall_success,
            "message": "系统重置完成，请手动启用采集开关" if overall_success else f"系统重置部分失败，失败操作: {', '.join(failed_operations)}",
            "details": {
                "collection_restored": False,
                "cleared_messages": cleanup_status["redis_messages"]["count"],
                "reset_channels": cleanup_status["channel_reset"]["count"],
                "temp_media_cleared": cleanup_status["temp_media"]["success"],
                "cleanup_status": cleanup_status
            }
        }
        
        logger.info("✅ 系统重置操作完成，采集开关需手动启用")
        return result
        
    except Exception as e:
        logger.error(f"系统重置失败: {e}")
        await websocket_manager.broadcast_progress(operation, 100, f"重置失败: {str(e)}")
        return {
            "success": False,
            "message": f"系统重置失败: {str(e)}",
            "details": {
                "cleanup_status": cleanup_status if 'cleanup_status' in locals() else {
                    "redis_messages": {"success": False, "error": "未执行", "count": 0},
                    "redis_pending": {"success": False, "error": "未执行", "count": 0},
                    "redis_websocket": {"success": False, "error": "未执行", "count": 0},
                    "redis_checkpoints": {"success": False, "error": "未执行", "count": 0},
                    "temp_media": {"success": False, "error": "未执行", "count": 0},
                    "channel_reset": {"success": False, "error": "未执行", "count": 0}
                }
            }
        }