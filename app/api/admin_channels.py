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
    config: Optional[dict] = None

class ChannelUpdateRequest(BaseModel):
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    config: Optional[dict] = None

@router.get(ROUTES.admin.channels)
async def get_channels(
    search: Optional[str] = Query(None, description="搜索关键词，支持名称精准匹配或标题模糊匹配")
):
    """获取频道配置 - 只返回源频道，支持搜索"""
    try:
        channel_store = get_json_channel_store()
        all_channels = channel_store.get_all_channels()
        logger.info(f"API获取到 {len(all_channels)} 个频道")
        
        # 所有频道都是源频道，无需过滤
        channels = all_channels
    except Exception as e:
        logger.error(f"获取频道列表失败: {e}")
        channels = []
    
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
                "status": "active",  # 存在即活跃
                "channel_id": ch.get('channel_id', ''),
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
    """添加频道配置 - 使用统一服务自动解析频道ID和标题"""
    try:
        # 处理频道名称格式
        channel_name = request.channel_name.strip()
        if not channel_name.startswith('@'):
            channel_name = '@' + channel_name
        
        # 使用统一频道服务添加频道
        result = await unified_channel_service.add_channel(
            channel_name=channel_name,
            channel_id=request.channel_id if request.channel_id else "",
            description="",
            resolve_title=True  # 自动解析标题
        )
        
        if result['success']:
            # 成功添加或更新
            return {
                "success": True,
                "message": result['message'],
                "channel": {
                    "id": result['data']['id'],
                    "channel_id": result['data']['channel_id'],
                    "channel_name": result['data']['channel_name'],
                    "channel_title": result['data']['channel_title']
                }
            }
        else:
            # 业务错误（如频道已存在）- 返回200状态码但success为false
            if "已存在" in result['message']:
                # 频道已存在，返回现有频道信息
                return {
                    "success": False,
                    "message": result['message'],
                    "channel": result.get('data')  # 返回已存在的频道信息
                }
            else:
                # 其他错误仍返回400
                raise HTTPException(status_code=400, detail=result['message'])
            
    except HTTPException:
        raise
    except Exception as e:
        # 系统错误
        logger.error(f"添加频道失败: {e}")
        raise HTTPException(status_code=500, detail=f"系统错误: {str(e)}")

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
        
        # 使用双Session系统检查连接状态
        from app.telegram.dual_session_manager import dual_session_manager
        client = await dual_session_manager.get_listener_client()
        
        if not client:
            logger.info("Telegram客户端未连接")
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
        
        # 使用双Session系统检查连接状态
        from app.telegram.dual_session_manager import dual_session_manager
        client = await dual_session_manager.get_listener_client()
        
        if not client:
            logger.info("Telegram客户端未连接")
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