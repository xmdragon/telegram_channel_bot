"""
频道ID解析API
提供手动解析频道ID的接口
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from app.services.config_manager import ConfigManager
from app.services.channel_id_resolver import channel_id_resolver
from app.telegram.auth import auth_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["channel-resolver"])

config_manager = ConfigManager()

class ResolveRequest(BaseModel):
    """解析请求模型"""
    channel_input: str  # 频道用户名、链接或ID
    save_as: Optional[str] = None  # 保存到的配置项名称

@router.post("/resolve")
async def resolve_channel(request: ResolveRequest):
    """
    解析频道ID
    支持解析源频道、目标频道、审核群等任何频道/群组
    """
    try:
        channel_input = request.channel_input.strip()
        if not channel_input:
            return {"success": False, "message": "请输入频道名称或链接"}
        
        # 确保客户端已连接
        if not auth_manager.client:
            await auth_manager.ensure_connected()
        
        if not auth_manager.client:
            return {"success": False, "message": "Telegram客户端未连接，请先完成认证"}
        
        # 解析频道ID
        resolved_id = await channel_id_resolver.resolve_channel_id(channel_input)
        
        if not resolved_id:
            return {
                "success": False,
                "message": f"无法解析 {channel_input}，请检查频道名称或链接是否正确"
            }
        
        # 获取频道详细信息
        channel_info = None
        try:
            entity = await auth_manager.client.get_entity(int(resolved_id))
            channel_info = {
                "id": resolved_id,
                "title": getattr(entity, 'title', '未知'),
                "username": getattr(entity, 'username', None),
                "type": "channel" if getattr(entity, 'broadcast', False) else "group"
            }
        except Exception as e:
            logger.warning(f"获取频道详细信息失败: {e}")
            channel_info = {"id": resolved_id}
        
        # 如果指定了保存位置，保存到配置
        saved_to = None
        if request.save_as:
            await config_manager.set_config(request.save_as, resolved_id)
            saved_to = request.save_as
            logger.info(f"已将解析的ID {resolved_id} 保存到配置 {request.save_as}")
        
        return {
            "success": True,
            "input": channel_input,
            "resolved_id": resolved_id,
            "channel_info": channel_info,
            "saved_to": saved_to,
            "message": f"成功解析为 {resolved_id}"
        }
        
    except Exception as e:
        logger.error(f"解析频道失败: {e}")
        return {
            "success": False,
            "message": f"解析失败: {str(e)}"
        }

@router.post("/resolve-all")
async def resolve_all_channels():
    """
    解析所有未解析的频道ID
    包括源频道、目标频道、审核群
    """
    try:
        # 确保客户端已连接
        if not auth_manager.client:
            await auth_manager.ensure_connected()
        
        if not auth_manager.client:
            return {"success": False, "message": "Telegram客户端未连接，请先完成认证"}
        
        from app.services.startup_checker import startup_checker
        
        # 执行完整的频道检查和解析
        results = await startup_checker.check_and_resolve_all_channels(auth_manager.client)
        
        return {
            "success": results['success'],
            "source_channels": results['source_channels'],
            "target_channel": results['target_channel'],
            "review_group": results['review_group'],
            "resolved": results['resolved'],
            "errors": results['errors'],
            "warnings": results['warnings']
        }
        
    except Exception as e:
        logger.error(f"批量解析频道失败: {e}")
        return {
            "success": False,
            "message": f"批量解析失败: {str(e)}"
        }

@router.post("/resolve-target")
async def resolve_target_channel():
    """
    专门解析目标频道
    """
    try:
        # 获取当前目标频道配置
        target_channel = await config_manager.get_config('channels.target_channel_id')
        
        if not target_channel:
            return {"success": False, "message": "未配置目标频道"}
        
        # 检查是否需要解析
        if target_channel.startswith('-100'):
            return {
                "success": True,
                "message": "目标频道已经是ID格式",
                "resolved_id": target_channel
            }
        
        # 确保客户端已连接
        if not auth_manager.client:
            await auth_manager.ensure_connected()
        
        if not auth_manager.client:
            return {"success": False, "message": "Telegram客户端未连接，请先完成认证"}
        
        # 解析频道ID
        resolved_id = await channel_id_resolver.resolve_channel_id(target_channel)
        
        if not resolved_id:
            return {
                "success": False,
                "message": f"无法解析目标频道 {target_channel}"
            }
        
        # 保存解析的ID
        await config_manager.set_config('channels.target_channel_id', resolved_id)
        
        # 如果原来是用户名，保存到target_channel_name
        if target_channel.startswith('@'):
            await config_manager.set_config('channels.target_channel_name', target_channel)
        
        # 获取频道信息
        channel_info = None
        try:
            entity = await auth_manager.client.get_entity(int(resolved_id))
            channel_info = {
                "title": getattr(entity, 'title', '未知'),
                "username": getattr(entity, 'username', None)
            }
        except:
            pass
        
        return {
            "success": True,
            "original": target_channel,
            "resolved_id": resolved_id,
            "channel_info": channel_info,
            "message": f"目标频道已解析: {target_channel} -> {resolved_id}"
        }
        
    except Exception as e:
        logger.error(f"解析目标频道失败: {e}")
        return {
            "success": False,
            "message": f"解析失败: {str(e)}"
        }

@router.post("/resolve-review")
async def resolve_review_group():
    """
    专门解析审核群
    """
    try:
        # 获取当前审核群配置
        review_group = await config_manager.get_config('channels.review_group_id')
        
        if not review_group:
            return {"success": False, "message": "未配置审核群"}
        
        # 检查是否需要解析
        if review_group.startswith('-100'):
            return {
                "success": True,
                "message": "审核群已经是ID格式",
                "resolved_id": review_group
            }
        
        # 确保客户端已连接
        if not auth_manager.client:
            await auth_manager.ensure_connected()
        
        if not auth_manager.client:
            return {"success": False, "message": "Telegram客户端未连接，请先完成认证"}
        
        # 解析群组ID
        resolved_id = await channel_id_resolver.resolve_channel_id(review_group)
        
        if not resolved_id:
            return {
                "success": False,
                "message": f"无法解析审核群 {review_group}"
            }
        
        # 保存解析的ID
        await config_manager.set_config('channels.review_group_id', resolved_id)
        
        # 如果原来是用户名或链接，保存到review_group_name
        if review_group.startswith('@') or review_group.startswith('http'):
            await config_manager.set_config('channels.review_group_name', review_group)
        
        # 获取群组信息
        group_info = None
        try:
            entity = await auth_manager.client.get_entity(int(resolved_id))
            group_info = {
                "title": getattr(entity, 'title', '未知'),
                "username": getattr(entity, 'username', None)
            }
        except:
            pass
        
        return {
            "success": True,
            "original": review_group,
            "resolved_id": resolved_id,
            "group_info": group_info,
            "message": f"审核群已解析: {review_group} -> {resolved_id}"
        }
        
    except Exception as e:
        logger.error(f"解析审核群失败: {e}")
        return {
            "success": False,
            "message": f"解析失败: {str(e)}"
        }