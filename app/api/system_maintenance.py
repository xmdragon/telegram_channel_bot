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
from app.storage.redis_manager import redis_manager
from app.storage.json_store import get_json_channel_store
from app.services.system_monitor import system_monitor
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
            
            # 同时重启内部客户端连接（使用双Session系统）
            try:
                from app.telegram.dual_session_manager import dual_session_manager
                # 重置双Session系统连接
                await dual_session_manager.disconnect_all()
                logger.info("Telegram双Session系统已断开连接，需要重新认证")
            except Exception as dual_error:
                logger.error(f"重置双Session系统失败: {dual_error}")
                
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
        redis_store = redis_manager
        channel_store = get_json_channel_store()
        
        # 步骤4：清空Redis消息数据 (45%)
        await websocket_manager.broadcast_progress(operation, 45, "清空Redis消息数据...")
        if redis_store and redis_manager.client:
            # 删除所有消息键
            try:
                message_keys = redis_manager.client.keys("msg:*")
                if message_keys:
                    # 分批删除，避免阻塞
                    batch_size = 1000
                    deleted_total = 0
                    for i in range(0, len(message_keys), batch_size):
                        batch = message_keys[i:i + batch_size]
                        deleted_count = redis_manager.client.delete(*batch)
                        deleted_total += deleted_count
                        progress = 45 + (10 * (i + len(batch)) / len(message_keys))
                        await websocket_manager.broadcast_progress(
                            operation, 
                            int(progress), 
                            f"删除消息 {i + len(batch)}/{len(message_keys)}..."
                        )
                    cleanup_status["redis_messages"] = {
                        "success": True, 
                        "error": None, 
                        "count": deleted_total
                    }
                    logger.info(f"✅ 成功清空了 {len(message_keys)} 条Redis消息 (实际删除: {deleted_total})")
                else:
                    cleanup_status["redis_messages"] = {
                        "success": True, 
                        "error": None, 
                        "count": 0
                    }
                    logger.info("ℹ️ 没有找到消息数据需要清理")
            except Exception as message_error:
                cleanup_status["redis_messages"] = {
                    "success": False, 
                    "error": str(message_error), 
                    "count": 0
                }
                logger.error(f"❌ 清理消息数据失败: {message_error}")
            
            # 删除其他消息相关的键
            try:
                pending_keys = redis_manager.client.keys("pending_messages")
                if pending_keys:
                    deleted_count = redis_manager.client.delete(*pending_keys)
                    cleanup_status["redis_pending"] = {
                        "success": True, 
                        "error": None, 
                        "count": deleted_count
                    }
                    logger.info(f"✅ 清空了 {deleted_count} 个待处理消息键")
                else:
                    cleanup_status["redis_pending"] = {
                        "success": True, 
                        "error": None, 
                        "count": 0
                    }
            except Exception as pending_error:
                cleanup_status["redis_pending"] = {
                    "success": False, 
                    "error": str(pending_error), 
                    "count": 0
                }
                logger.error(f"❌ 清理待处理消息失败: {pending_error}")
            
            # 清空WebSocket连接信息
            try:
                ws_keys = redis_manager.client.keys("websocket:*")
                if ws_keys:
                    deleted_count = redis_manager.client.delete(*ws_keys)
                    cleanup_status["redis_websocket"] = {
                        "success": True, 
                        "error": None, 
                        "count": deleted_count
                    }
                    logger.info(f"✅ 清空了 {deleted_count} 个WebSocket连接键")
                else:
                    cleanup_status["redis_websocket"] = {
                        "success": True, 
                        "error": None, 
                        "count": 0
                    }
            except Exception as ws_error:
                cleanup_status["redis_websocket"] = {
                    "success": False, 
                    "error": str(ws_error), 
                    "count": 0
                }
                logger.error(f"❌ 清理WebSocket连接失败: {ws_error}")
            
            # 清空频道采集点（checkpoint）- 增强版本，包含重试机制
            checkpoint_cleanup_success = False
            max_retries = 3
            for retry in range(max_retries):
                try:
                    checkpoint_keys = redis_manager.client.keys("channel:checkpoint*")
                    if checkpoint_keys:
                        logger.info(f"🔄 第 {retry + 1} 次尝试清理 {len(checkpoint_keys)} 个checkpoint键")
                        deleted_count = redis_manager.client.delete(*checkpoint_keys)
                        
                        # 验证清理结果
                        remaining_keys = redis_manager.client.keys("channel:checkpoint*")
                        if remaining_keys:
                            logger.warning(f"⚠️ 第 {retry + 1} 次清理后仍有 {len(remaining_keys)} 个checkpoint键未清理")
                            if retry < max_retries - 1:
                                logger.info("🔄 将进行重试...")
                                await asyncio.sleep(1)  # 等待1秒后重试
                                continue
                        else:
                            cleanup_status["redis_checkpoints"] = {
                                "success": True, 
                                "error": None, 
                                "count": deleted_count
                            }
                            logger.info(f"✅ checkpoint清理验证通过 (第 {retry + 1} 次尝试成功)")
                            checkpoint_cleanup_success = True
                            break
                    else:
                        cleanup_status["redis_checkpoints"] = {
                            "success": True, 
                            "error": None, 
                            "count": 0
                        }
                        logger.info("ℹ️ 没有找到checkpoint数据需要清理")
                        checkpoint_cleanup_success = True
                        break
                except Exception as checkpoint_error:
                    if retry == max_retries - 1:  # 最后一次重试失败
                        cleanup_status["redis_checkpoints"] = {
                            "success": False, 
                            "error": str(checkpoint_error), 
                            "count": 0
                        }
                        logger.error(f"❌ 清理checkpoint失败（尝试 {max_retries} 次后）: {checkpoint_error}")
                    else:
                        logger.warning(f"⚠️ 第 {retry + 1} 次清理checkpoint失败: {checkpoint_error}，将重试...")
                        await asyncio.sleep(1)  # 等待1秒后重试
        
        # 步骤5：清空临时媒体目录 (65%)
        await websocket_manager.broadcast_progress(operation, 65, "清空临时媒体目录...")
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
        
        # 步骤6：重置频道采集点 (85%)
        await websocket_manager.broadcast_progress(operation, 85, "重置频道采集点...")
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
                    progress = 85 + (10 * (i + 1) / len(source_channels))
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
        
        # 步骤7：重置采集标志 (95%)
        await websocket_manager.broadcast_progress(operation, 95, "重置采集标志...")
        try:
            # 重置bot_manager的采集标志以便重新采集历史消息
            from app.telegram.bot_manager import bot_manager
            if hasattr(bot_manager, 'auto_collection_done'):
                bot_manager.auto_collection_done = False
                logger.info("已重置auto_collection_done标志，下次连接将自动采集历史消息")
            
            logger.info("采集标志已重置，采集开关由用户手动控制")
                
        except Exception as e:
            logger.error(f"重置采集标志失败: {e}")
        
        # 步骤8：完成 (100%)
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
                "auto_collection_ready": True,
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