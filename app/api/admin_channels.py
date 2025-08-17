"""
管理员频道管理API
包括：频道CRUD操作、搜索、刷新标题、频道ID解析
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
import asyncio
import logging

from app.storage.json_store import get_json_channel_store
from app.core.route_config import ROUTES
from app.services.config_manager import config_manager
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

@router.get(ROUTES.admin.channels)
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

@router.post(ROUTES.admin.channels)
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

@router.put(ROUTES.admin.channels_by_name)
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

@router.delete(ROUTES.admin.channels_by_name)
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

@router.post(ROUTES.admin.channels_refresh_titles)
async def refresh_channel_titles():
    """刷新所有频道的真实标题"""
    try:
        result = await unified_channel_service.refresh_channel_titles()
        return result
    except Exception as e:
        logger.error(f"刷新频道标题失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新频道标题失败: {str(e)}")

@router.get(ROUTES.admin.search_channels)
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

@router.post(ROUTES.admin.resolve_channel_ids)
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

@router.post(ROUTES.admin.resolve_channel_id)
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