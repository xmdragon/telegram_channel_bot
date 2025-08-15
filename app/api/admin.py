"""
管理员API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
import os
import shutil
import tarfile
import tempfile
import asyncio
import logging

from app.storage.json_store import get_json_channel_store
from app.core.config import settings
from app.services.config_manager import config_manager
from app.services.scheduler import MessageScheduler
from app.services.unified_channel_service import unified_channel_service

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
    search: Optional[str] = Query(None, description="搜索关键词，支持名称精准匹配或标题模糊匹配")
):
    """获取频道配置 - 只返回源频道，支持搜索"""
    channel_store = get_json_channel_store()
    all_channels = channel_store.get_all_channels()
    
    # 过滤只返回源频道
    channels = [ch for ch in all_channels if ch.get('channel_type') == 'source']
    
    # 如果有搜索关键词，添加搜索过滤
    if search:
        filtered_channels = []
        for ch in channels:
            channel_name = ch.get('channel_name', '')
            channel_title = ch.get('channel_title', '')
            
            # 名称精准匹配或标题模糊匹配
            if (channel_name == search or 
                search.lower() in channel_title.lower()):
                filtered_channels.append(ch)
        channels = filtered_channels
    
    # 按创建时间倒序排列
    channels = sorted(channels, key=lambda x: x.get('created_at', ''), reverse=True)
    
    return {
        "success": True,
        "channels": [
            {
                "id": ch.get('id', ''),
                "name": ch.get('channel_name', ''),
                "title": ch.get('channel_title', ''),
                "status": "active" if ch.get('is_active', True) else "inactive",
                "channel_id": ch.get('channel_id', ''),
                "channel_type": ch.get('channel_type', ''),
                "config": ch.get('config', {}),
                "created_at": ch.get('created_at', '')
            }
            for ch in channels
        ]
    }

@router.post("/channels")
async def add_channel(
    request: ChannelCreateRequest
):
    """添加频道配置 - 自动解析频道ID和标题"""
    try:
        channel_store = get_json_channel_store()
        
        # 检查频道名称是否已存在
        existing_channels = channel_store.get_all_channels()
        if any(ch.get('channel_name') == request.channel_name for ch in existing_channels):
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
        channel_data = {
            "id": len(existing_channels) + 1,
            "channel_id": resolved_id,
            "channel_name": request.channel_name,
            "channel_title": resolved_title or request.channel_name,
            "channel_type": request.channel_type,
            "config": request.config or {},
            "is_active": True,
            "created_at": datetime.now().isoformat()
        }
        
        if channel_store.add_channel(channel_data):
            return {
                "success": True, 
                "message": "频道添加成功",
                "channel": {
                    "id": channel_data["id"],
                    "channel_id": channel_data["channel_id"],
                    "channel_name": channel_data["channel_name"],
                    "channel_title": channel_data["channel_title"]
                }
            }
        else:
            raise HTTPException(status_code=500, detail="频道添加失败")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加频道失败: {str(e)}")

@router.put("/channels/{channel_name}")
async def update_channel(
    channel_name: str,
    request: ChannelUpdateRequest
):
    """更新频道配置"""
    try:
        channel_store = get_json_channel_store()
        
        # 查找频道
        all_channels = channel_store.get_all_channels()
        channel = None
        for ch in all_channels:
            if ch.get('channel_name') == channel_name:
                channel = ch
                break
        
        if not channel:
            raise HTTPException(status_code=404, detail="频道不存在")
        
        # 更新频道信息
        if request.channel_id is not None:
            channel['channel_id'] = request.channel_id
        if request.channel_title is not None:
            channel['channel_title'] = request.channel_title
        if request.channel_type is not None:
            channel['channel_type'] = request.channel_type
        if request.is_active is not None:
            channel['is_active'] = request.is_active
        if request.config is not None:
            channel['config'] = request.config
        
        # 保存更新
        if channel_store.update_channel(channel):
            return {"success": True, "message": "频道更新成功", "channel_id": channel.get('id')}
        else:
            raise HTTPException(status_code=500, detail="频道更新失败")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新频道失败: {str(e)}")

@router.delete("/channels/{channel_name}")
async def delete_channel(
    channel_name: str
):
    """删除频道配置"""
    try:
        channel_store = get_json_channel_store()
        
        # 查找频道
        all_channels = channel_store.get_all_channels()
        channel_id = None
        for ch in all_channels:
            if ch.get('channel_name') == channel_name:
                channel_id = ch.get('id')
                break
        
        if channel_id is None:
            raise HTTPException(status_code=404, detail="频道不存在")
        
        # 删除频道
        if channel_store.delete_channel(channel_id):
            return {"success": True, "message": "频道删除成功"}
        else:
            raise HTTPException(status_code=500, detail="频道删除失败")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除频道失败: {str(e)}")

@router.post("/channels/refresh-titles")
async def refresh_channel_titles():
    """刷新所有频道的真实标题"""
    try:
        result = await unified_channel_service.refresh_channel_titles()
        return result
    except Exception as e:
        logger.error(f"刷新频道标题失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新频道标题失败: {str(e)}")


@router.get("/search-channels")
async def search_channels(
    query: str = Query(..., description="搜索关键词")
):
    """从JSON存储搜索已存在的频道"""
    try:
        channel_store = get_json_channel_store()
        all_channels = channel_store.get_all_channels()
        
        # 搜索频道名称或标题包含关键词的频道
        query_lower = query.lower()
        matching_channels = []
        
        for channel in all_channels:
            channel_name = channel.get('channel_name', '')
            channel_title = channel.get('channel_title', '')
            
            if (query_lower in channel_name.lower() or 
                query_lower in channel_title.lower()):
                matching_channels.append(channel)
        
        # 转换为返回格式
        channel_list = []
        for channel in matching_channels:
            channel_name = channel.get('channel_name', '')
            channel_list.append({
                'id': channel.get('channel_id', ''),
                'title': channel.get('channel_title') or channel_name,
                'username': channel_name.replace('@', '') if channel_name.startswith('@') else channel_name,
                'channel_type': channel.get('channel_type', ''),
                'is_active': channel.get('is_active', True),
                'description': channel.get('description', '')
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
        # 前端显示用（用户友好格式）
        "target_channel": await config_manager.get_config('channels.target_channel', ''),
        "review_group": await config_manager.get_config('channels.review_group', ''),
        
        # 其他配置
        "auto_forward_enabled": await config_manager.get_config('review.auto_forward_enabled', False),
        "auto_forward_delay": await db_settings.get_auto_forward_delay(),
        "source_channels": await db_settings.get_source_channels(),
        "history_message_limit": await db_settings.get_history_message_limit(),
        "ad_keywords": await db_settings.get_ad_keywords_text(),
        "channel_signature": await config_manager.get_config('channels.signature', '')
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
        # 检查Redis连接
        from app.storage.redis_store import get_redis_store
        redis_store = get_redis_store()
        redis_store.redis.ping()  # 测试Redis连接
        
        # 检查JSON存储
        channel_store = get_json_channel_store()
        channel_store.get_all_channels()  # 测试文件访问
        
        return {
            "status": "healthy",
            "storage": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "2.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "storage": "disconnected",
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
async def update_config_batch(configs: Dict[str, Any]):
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

class ForwardingConfigRequest(BaseModel):
    target_channel: str
    review_group: str
    auto_forward_enabled: bool = False
    auto_forward_delay: int = 1800

@router.post("/config/forwarding")
async def update_forwarding_config(request: ForwardingConfigRequest):
    """更新转发配置并刷新缓存"""
    try:
        # 保存用户输入的用户名/链接格式
        await config_manager.set_config('channels.target_channel', request.target_channel)
        await config_manager.set_config('channels.review_group', request.review_group)
        await config_manager.set_config('review.auto_forward_enabled', request.auto_forward_enabled)
        await config_manager.set_config('review.auto_forward_delay', request.auto_forward_delay)
        
        # 尝试解析并缓存私有链接的ID
        target_resolved_id = None
        review_resolved_id = None
        
        # 处理审核群私有链接
        if request.review_group and ('https://t.me/+' in request.review_group or 't.me/+' in request.review_group):
            try:
                from app.services.telegram_link_resolver import link_resolver
                resolved_id = await link_resolver.resolve_group_id(request.review_group)
                if resolved_id:
                    # 保存解析后的ID到专门的缓存字段
                    await config_manager.set_config('channels.review_group_id_cached', str(resolved_id))
                    review_resolved_id = str(resolved_id)
                    logger.info(f"审核群私有链接已解析: {request.review_group} -> {resolved_id}")
                else:
                    logger.warning(f"审核群私有链接解析失败: {request.review_group}")
            except Exception as e:
                logger.error(f"解析审核群私有链接时出错: {e}")
        
        # 处理目标频道私有链接
        if request.target_channel and ('https://t.me/+' in request.target_channel or 't.me/+' in request.target_channel):
            try:
                from app.services.telegram_link_resolver import link_resolver
                resolved_id = await link_resolver.resolve_group_id(request.target_channel)
                if resolved_id:
                    await config_manager.set_config('channels.target_channel_id_cached', str(resolved_id))
                    target_resolved_id = str(resolved_id)
                    logger.info(f"目标频道私有链接已解析: {request.target_channel} -> {resolved_id}")
                else:
                    logger.warning(f"目标频道私有链接解析失败: {request.target_channel}")
            except Exception as e:
                logger.error(f"解析目标频道私有链接时出错: {e}")
        
        # 刷新Redis缓存并获取解析结果
        from app.services.channel_cache import channel_cache
        target_result = await channel_cache.refresh_target_channel_cache()
        review_result = await channel_cache.refresh_review_group_cache()
        
        # 构建详细的返回消息
        messages = ["转发配置已保存"]
        
        if target_resolved_id:
            messages.append(f"目标频道私有链接已解析: {target_resolved_id}")
        elif target_result:
            messages.append(f"目标频道解析成功: {target_result}")
        else:
            messages.append("目标频道暂未解析（需要Telegram连接）")
            
        if review_resolved_id:
            messages.append(f"审核群私有链接已解析: {review_resolved_id}")
        elif review_result:
            messages.append(f"审核群解析成功: {review_result}")
        else:
            messages.append("审核群暂未解析（需要Telegram连接）")
        
        return {
            "success": True,
            "message": "，".join(messages),
            "target_resolved": target_result or target_resolved_id,
            "review_resolved": review_result or review_resolved_id,
            "private_links_resolved": {
                "target_channel": target_resolved_id,
                "review_group": review_resolved_id
            }
        }
        
    except Exception as e:
        logger.error(f"更新转发配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新转发配置失败: {str(e)}")

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