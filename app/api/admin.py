"""
管理员API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import os
import shutil
import tarfile
import tempfile
import asyncio
import logging

from app.core.database import get_db, Channel, AsyncSessionLocal
from app.core.config import settings
from app.services.config_manager import config_manager
from app.services.scheduler import MessageScheduler

router = APIRouter()
logger = logging.getLogger(__name__)

class ChannelCreateRequest(BaseModel):
    channel_id: str = ""
    channel_name: str
    channel_title: str = ""
    channel_type: str = "source"
    config: Optional[dict] = None

class ChannelUpdateRequest(BaseModel):
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    channel_type: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[dict] = None

@router.get("/channels")
async def get_channels(
    search: Optional[str] = Query(None, description="搜索关键词，支持名称精准匹配或标题模糊匹配"),
    db: AsyncSession = Depends(get_db)
):
    """获取频道配置 - 只返回源频道，支持搜索"""
    # 基础查询，只查询源频道
    query = select(Channel).where(Channel.channel_type == "source")
    
    # 如果有搜索关键词，添加搜索条件
    if search:
        from sqlalchemy import or_
        # 支持名称精准匹配或标题模糊匹配
        query = query.where(
            or_(
                Channel.channel_name == search,  # 名称精准匹配
                Channel.channel_title.ilike(f"%{search}%")  # 标题模糊匹配（不区分大小写）
            )
        )
    
    result = await db.execute(query)
    channels = result.scalars().all()
    
    # 按创建时间倒序排列，新添加的频道在最上面
    channels = sorted(channels, key=lambda x: x.created_at, reverse=True)
    
    return {
        "success": True,
        "channels": [
            {
                "id": ch.id,
                "name": ch.channel_name,
                "title": ch.channel_title or "",
                "status": "active" if ch.is_active else "inactive",
                "channel_id": ch.channel_id,
                "channel_type": ch.channel_type,
                "config": ch.config,
                "created_at": ch.created_at
            }
            for ch in channels
        ]
    }

@router.post("/channels")
async def add_channel(
    request: ChannelCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """添加频道配置 - 自动解析频道ID和标题"""
    try:
        # 检查频道名称是否已存在
        existing = await db.execute(select(Channel).where(Channel.channel_name == request.channel_name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="频道名称已存在")
        
        # 自动解析频道信息
        from app.services.channel_id_resolver import channel_id_resolver
        from app.telegram.auth import auth_manager
        
        resolved_id = request.channel_id if request.channel_id else None
        resolved_title = request.channel_title if request.channel_title else None
        
        # 如果没有提供ID或标题，尝试自动解析
        if not resolved_id or not resolved_title:
            # 确保Telegram客户端已连接
            if not auth_manager.client:
                await auth_manager.ensure_connected()
            
            if auth_manager.client:
                try:
                    # 获取频道详细信息
                    channel_info = await channel_id_resolver.get_channel_info(request.channel_name)
                    if channel_info:
                        # 如果没有提供ID，使用解析的ID
                        if not resolved_id:
                            resolved_id = channel_info['id']
                            # 确保ID格式正确（频道ID应该以-100开头）
                            if not resolved_id.startswith('-100'):
                                resolved_id = f"-100{resolved_id}" if not resolved_id.startswith('-') else resolved_id
                        
                        # 如果没有提供标题，使用解析的标题
                        if not resolved_title:
                            resolved_title = channel_info['title']
                        
                        logger.info(f"自动解析频道信息: {request.channel_name} -> ID: {resolved_id}, 标题: {resolved_title}")
                except Exception as e:
                    logger.warning(f"自动解析频道信息失败: {e}")
                    # 继续执行，使用用户提供的或空值
        
        # 创建频道记录
        channel = Channel(
            channel_id=resolved_id,
            channel_name=request.channel_name,
            channel_title=resolved_title or request.channel_name,  # 如果没有标题，使用频道名称
            channel_type=request.channel_type,
            config=request.config or {}
        )
        
        db.add(channel)
        await db.commit()
        await db.refresh(channel)
        
        return {
            "success": True, 
            "message": "频道添加成功",
            "channel": {
                "id": channel.id,
                "channel_id": channel.channel_id,
                "channel_name": channel.channel_name,
                "channel_title": channel.channel_title
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"添加频道失败: {str(e)}")

@router.put("/channels/{channel_name}")
async def update_channel(
    channel_name: str,
    request: ChannelUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """更新频道配置"""
    try:
        result = await db.execute(select(Channel).where(Channel.channel_name == channel_name))
        channel = result.scalar_one_or_none()
        
        if not channel:
            raise HTTPException(status_code=404, detail="频道不存在")
        
        if request.channel_id is not None:
            channel.channel_id = request.channel_id
        if request.channel_title is not None:
            channel.channel_title = request.channel_title
        if request.channel_type is not None:
            channel.channel_type = request.channel_type
        if request.is_active is not None:
            channel.is_active = request.is_active
        if request.config is not None:
            channel.config = request.config
        
        await db.commit()
        await db.refresh(channel)
        
        return {"success": True, "message": "频道更新成功", "channel_id": channel.id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"更新频道失败: {str(e)}")

@router.delete("/channels/{channel_name}")
async def delete_channel(
    channel_name: str,
    db: AsyncSession = Depends(get_db)
):
    """删除频道配置"""
    try:
        result = await db.execute(select(Channel).where(Channel.channel_name == channel_name))
        channel = result.scalar_one_or_none()
        
        if not channel:
            raise HTTPException(status_code=404, detail="频道不存在")
        
        await db.delete(channel)
        await db.commit()
        
        return {"success": True, "message": "频道删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除频道失败: {str(e)}")

@router.post("/cleanup/temp-media")
async def cleanup_temp_media():
    """立即执行临时媒体文件清理"""
    try:
        # 创建调度器实例并执行清理
        scheduler = MessageScheduler()
        await scheduler.cleanup_temp_media()
        
        # 获取目录状态
        from pathlib import Path
        temp_media_dir = Path("temp_media")
        
        if temp_media_dir.exists():
            files = list(temp_media_dir.iterdir())
            file_count = len([f for f in files if f.is_file()])
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            
            # 转换文件大小为可读格式
            if total_size > 1024 * 1024 * 1024:  # GB
                size_str = f"{total_size / (1024 * 1024 * 1024):.2f} GB"
            elif total_size > 1024 * 1024:  # MB
                size_str = f"{total_size / (1024 * 1024):.2f} MB"
            elif total_size > 1024:  # KB
                size_str = f"{total_size / 1024:.2f} KB"
            else:
                size_str = f"{total_size} bytes"
            
            return {
                "status": "success",
                "message": "临时媒体文件清理完成",
                "remaining_files": file_count,
                "remaining_size": size_str
            }
        else:
            return {
                "status": "success",
                "message": "temp_media目录不存在",
                "remaining_files": 0,
                "remaining_size": "0 bytes"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")

@router.get("/cleanup/temp-media/status")
async def get_temp_media_status():
    """获取临时媒体文件目录状态"""
    try:
        from pathlib import Path
        import time
        
        temp_media_dir = Path("temp_media")
        
        if not temp_media_dir.exists():
            return {
                "exists": False,
                "total_files": 0,
                "total_size": "0 bytes",
                "old_files": 0,
                "old_files_size": "0 bytes"
            }
        
        current_time = time.time()
        one_day_ago = current_time - 86400
        
        total_files = 0
        total_size = 0
        old_files = 0
        old_files_size = 0
        
        for file_path in temp_media_dir.iterdir():
            if file_path.is_file():
                file_size = file_path.stat().st_size
                file_mtime = file_path.stat().st_mtime
                
                total_files += 1
                total_size += file_size
                
                if file_mtime < one_day_ago:
                    old_files += 1
                    old_files_size += file_size
        
        # 格式化大小
        def format_size(size):
            if size > 1024 * 1024 * 1024:  # GB
                return f"{size / (1024 * 1024 * 1024):.2f} GB"
            elif size > 1024 * 1024:  # MB
                return f"{size / (1024 * 1024):.2f} MB"
            elif size > 1024:  # KB
                return f"{size / 1024:.2f} KB"
            else:
                return f"{size} bytes"
        
        return {
            "exists": True,
            "total_files": total_files,
            "total_size": format_size(total_size),
            "old_files": old_files,
            "old_files_size": format_size(old_files_size),
            "message": f"共 {total_files} 个文件，其中 {old_files} 个超过1天未使用"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

@router.get("/search-channels")
async def search_channels(
    query: str = Query(..., description="搜索关键词"),
    db: AsyncSession = Depends(get_db)
):
    """从数据库搜索已存在的频道"""
    try:
        from sqlalchemy import or_
        from app.core.database import Channel
        
        # 搜索频道名称或标题包含关键词的频道
        search_pattern = f"%{query}%"
        result = await db.execute(
            select(Channel).where(
                or_(
                    Channel.channel_name.ilike(search_pattern),
                    Channel.channel_title.ilike(search_pattern)
                )
            )
        )
        channels = result.scalars().all()
        
        # 转换为返回格式
        channel_list = []
        for channel in channels:
            channel_list.append({
                'id': channel.channel_id,
                'title': channel.channel_title or channel.channel_name,
                'username': channel.channel_name.replace('@', '') if channel.channel_name and channel.channel_name.startswith('@') else channel.channel_name,
                'channel_type': channel.channel_type,
                'is_active': channel.is_active,
                'description': channel.description
            })
        
        return {
            "success": True,
            "channels": channel_list,
            "count": len(channel_list),
            "message": f"找到 {len(channel_list)} 个匹配的频道"
        }
            
    except Exception as e:
        logger.error(f"搜索频道失败: {e}")
        return {
            "success": False,
            "message": f"搜索失败: {str(e)}",
            "channels": []
        }

@router.post("/collect-history/{channel_id}")
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

@router.get("/collect-history/progress")
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

@router.post("/collect-history/{channel_id}/stop")
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

@router.get("/config")
async def get_system_config():
    """获取系统配置"""
    from app.core.config import db_settings
    
    return {
        "auto_forward_delay": await db_settings.get_auto_forward_delay(),
        "source_channels": await db_settings.get_source_channels(),
        "review_group_id": await db_settings.get_review_group_id(),
        "review_group_id_cached": await config_manager.get_config('channels.review_group_id_cached', ''),
        "target_channel_id": await db_settings.get_target_channel_id(),
        "target_channel_id_cached": await config_manager.get_config('channels.target_channel_id_cached', ''),
        "history_message_limit": await db_settings.get_history_message_limit(),
        "ad_keywords": await db_settings.get_ad_keywords_text(),
        "channel_replacements": await db_settings.get_channel_replacements(),
        "channels.signature": await config_manager.get_config('channels.signature', '')
    }

@router.post("/restart")
async def restart_system():
    """重启系统"""
    try:
        # 这里可以实现系统重启逻辑
        # 在实际部署中，可能需要通过进程管理工具重启
        return {"success": True, "message": "系统重启命令已发送"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"系统重启失败: {str(e)}")

@router.post("/backup")
async def backup_data():
    """备份数据"""
    try:
        # 创建备份目录
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{backup_dir}/backup_{timestamp}.tar.gz"
        
        # 创建备份文件
        with tarfile.open(backup_file, "w:gz") as tar:
            # 备份PostgreSQL数据（需要使用pg_dump，这里只备份配置说明）
            # 注意：PostgreSQL数据库备份应该使用pg_dump命令
            backup_info = "PostgreSQL数据库备份需要使用pg_dump命令\n"
            backup_info += "示例：pg_dump -h postgres -U postgres telegram_system > backup.sql\n"
            info_file = f"{backup_dir}/database_backup_info.txt"
            with open(info_file, "w") as f:
                f.write(backup_info)
            tar.add(info_file, arcname="database/backup_info.txt")
            os.remove(info_file)
            
            # 备份会话文件
            if os.path.exists("sessions"):
                tar.add("sessions", arcname="sessions")
            
            # 备份数据目录
            if os.path.exists("data"):
                tar.add("data", arcname="data")
            
            # 备份日志目录
            if os.path.exists("logs"):
                tar.add("logs", arcname="logs")
        
        return {"success": True, "message": f"数据备份成功: {backup_file}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据备份失败: {str(e)}")

@router.post("/clear-cache")
async def clear_cache():
    """清理缓存"""
    try:
        # 清理配置缓存
        await config_manager.clear_cache()
        
        # 清理其他缓存（如果有的话）
        # 这里可以添加其他缓存清理逻辑
        
        return {"success": True, "message": "缓存清理成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"缓存清理失败: {str(e)}")

@router.post("/export-logs")
async def export_logs():
    """导出日志"""
    try:
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "system_logs.txt")
            
            # 收集日志信息
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("=== 系统日志导出 ===\n")
                f.write(f"导出时间: {datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                
                # 系统信息
                f.write("系统信息:\n")
                f.write(f"- Python版本: {os.sys.version}\n")
                f.write(f"- 工作目录: {os.getcwd()}\n")
                f.write(f"- 当前时间: {datetime.now().isoformat()}\n\n")
                
                # 配置文件信息
                f.write("配置文件:\n")
                try:
                    all_configs = await config_manager.get_all_configs()
                    for key, config in all_configs.items():
                        f.write(f"- {key}: {config['value']}\n")
                except Exception as e:
                    f.write(f"- 配置读取失败: {str(e)}\n")
                
                f.write("\n" + "=" * 50 + "\n")
            
            # 创建下载文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            download_file = f"logs/system_logs_{timestamp}.txt"
            os.makedirs("logs", exist_ok=True)
            shutil.copy2(log_file, download_file)
            
            return {"success": True, "message": f"日志导出成功: {download_file}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"日志导出失败: {str(e)}")

@router.get("/health")
async def health_check():
    """系统健康检查"""
    try:
        # 检查数据库连接
        async with AsyncSessionLocal() as db:
            await db.execute("SELECT 1")
        
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

class ConfigUpdateRequest(BaseModel):
    key: str
    value: str
    config_type: str = "string"

@router.post("/config")
async def update_config(request: ConfigUpdateRequest):
    """更新单个配置项"""
    try:
        success = await config_manager.set_config(
            key=request.key,
            value=request.value,
            config_type=request.config_type
        )
        
        if success:
            return {"success": True, "message": f"配置 {request.key} 更新成功"}
        else:
            raise HTTPException(status_code=500, detail="配置更新失败")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")

@router.post("/config/batch")
async def update_config_batch(configs: dict):
    """批量更新配置项"""
    try:
        success_count = 0
        errors = []
        
        for key, value in configs.items():
            try:
                # 自动推断配置类型
                config_type = "string"
                if isinstance(value, bool):
                    config_type = "boolean"
                elif isinstance(value, int):
                    config_type = "integer"
                elif isinstance(value, (list, dict)):
                    config_type = "json"
                
                success = await config_manager.set_config(
                    key=key,
                    value=value,
                    config_type=config_type
                )
                
                if success:
                    success_count += 1
                else:
                    errors.append(f"配置 {key} 更新失败")
                    
            except Exception as e:
                errors.append(f"配置 {key} 更新失败: {str(e)}")
        
        return {
            "success": len(errors) == 0,
            "message": f"成功更新 {success_count} 个配置项",
            "errors": errors if errors else None
        }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量更新配置失败: {str(e)}")

class ReviewGroupResolveRequest(BaseModel):
    review_group_config: str

@router.post("/resolve-review-group")
async def resolve_review_group(request: ReviewGroupResolveRequest):
    """解析审核群链接并缓存ID"""
    try:
        from app.services.telegram_link_resolver import link_resolver
        
        resolved_id = await link_resolver.resolve_and_cache_group_id(request.review_group_config)
        
        if resolved_id:
            return {
                "success": True,
                "original_config": request.review_group_config,
                "resolved_id": resolved_id,
                "message": f"审核群链接解析成功，ID: {resolved_id}"
            }
        else:
            return {
                "success": False,
                "message": "无法解析审核群链接，请检查链接是否正确或机器人是否已加入该群"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析审核群链接失败: {str(e)}")

@router.get("/review-group-status")
async def get_review_group_status():
    """获取审核群状态信息"""
    try:
        from app.services.telegram_link_resolver import link_resolver
        
        # 获取配置的审核群
        review_group_config = await config_manager.get_config('channels.review_group_id', '')
        cached_id = await link_resolver.get_cached_group_id()
        effective_id = await link_resolver.get_effective_group_id()
        
        return {
            "review_group_config": review_group_config,
            "cached_id": cached_id,
            "effective_id": effective_id,
            "is_link": link_resolver.is_telegram_link(review_group_config) if review_group_config else False
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取审核群状态失败: {str(e)}")

@router.post("/resolve-channel-ids")
async def resolve_channel_ids():
    """解析所有缺失的频道ID"""
    try:
        from app.services.channel_manager import channel_manager
        from app.telegram.auth import auth_manager
        
        # 先检查Telegram客户端连接状态
        if not auth_manager.client:
            logger.info("Telegram客户端未连接，尝试重新连接...")
            try:
                await auth_manager.ensure_connected()
            except Exception as e:
                logger.error(f"重新连接Telegram失败: {e}")
                return {
                    "success": False,
                    "resolved_count": 0,
                    "message": "Telegram客户端未连接，请先完成Telegram认证"
                }
        
        resolved_count = await channel_manager.resolve_missing_channel_ids()
        
        return {
            "success": True,
            "resolved_count": resolved_count,
            "message": f"成功解析 {resolved_count} 个频道ID"
        }
        
    except Exception as e:
        logger.error(f"批量解析频道ID时出错: {e}")
        raise HTTPException(status_code=500, detail=f"解析频道ID失败: {str(e)}")

class ChannelResolveRequest(BaseModel):
    channel_name: str

@router.post("/resolve-channel-id")
async def resolve_single_channel_id(request: ChannelResolveRequest):
    """解析单个频道的ID"""
    try:
        from app.services.channel_id_resolver import channel_id_resolver
        from app.telegram.auth import auth_manager
        
        # 先检查Telegram客户端连接状态
        if not auth_manager.client:
            # 尝试重新连接
            logger.info("Telegram客户端未连接，尝试重新连接...")
            try:
                await auth_manager.ensure_connected()
            except Exception as e:
                logger.error(f"重新连接Telegram失败: {e}")
                return {
                    "success": False,
                    "message": "Telegram客户端未连接，请先完成Telegram认证"
                }
        
        # 尝试解析频道ID（最多重试3次）
        resolved_id = None
        for attempt in range(3):
            resolved_id = await channel_id_resolver.resolve_and_update_channel(request.channel_name)
            if resolved_id:
                break
            
            if attempt < 2:
                logger.info(f"第{attempt + 1}次解析失败，等待1秒后重试...")
                await asyncio.sleep(1)
        
        if resolved_id:
            return {
                "success": True,
                "channel_name": request.channel_name,
                "resolved_id": resolved_id,
                "message": f"频道 {request.channel_name} ID解析成功: {resolved_id}"
            }
        else:
            return {
                "success": False,
                "message": f"无法解析频道 {request.channel_name} 的ID，请检查频道名称是否正确"
            }
            
    except Exception as e:
        logger.error(f"解析频道ID时出错: {e}")
        raise HTTPException(status_code=500, detail=f"解析频道ID失败: {str(e)}")