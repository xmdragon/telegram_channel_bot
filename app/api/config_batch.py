"""
批量配置操作API
包括：批量设置、批量更新、重置默认配置、批量添加频道
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import logging

from app.services.config_manager import config_manager
from app.services.auth_service import get_auth_service
from app.core.route_config import ROUTES

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

class ConfigItem(BaseModel):
    key: str
    value: Any
    description: str = ""
    config_type: str = "string"

# 认证中间件
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """获取当前用户"""
    if not credentials:
        return None
    
    try:
        auth_service = get_auth_service()
        return await auth_service.get_current_user(credentials.credentials)
    except Exception as e:
        logger.error(f"获取当前用户失败: {e}")
        return None

async def require_auth(user: Optional[Dict[str, Any]] = Depends(get_current_user)) -> Dict[str, Any]:
    """要求用户认证"""
    if not user:
        raise HTTPException(status_code=401, detail="未授权访问")
    return user

async def check_config_permission(user: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
    """检查配置管理权限"""
    try:
        # 简化权限检查：超级管理员可以管理配置
        # 在实际项目中，可以根据需要添加更细粒度的权限控制
        if user.get('is_super_admin'):
            return user
        else:
            # 暂时只允许超级管理员访问配置管理
            raise HTTPException(status_code=403, detail="权限不足")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查配置权限失败: {e}")
        raise HTTPException(status_code=500, detail="权限检查失败")

@router.post(ROUTES.config.batch)
async def batch_set_configs(configs: List[ConfigItem], user: Dict[str, Any] = Depends(check_config_permission)):
    """批量设置配置"""
    try:
        # 使用新的批量更新方法
        config_dict = {}
        for config in configs:
            config_dict[config.key] = {
                'value': config.value,
                'description': config.description,
                'config_type': config.config_type
            }
        
        # 批量设置配置
        batch_success = await config_manager.set_multiple_configs(config_dict)
        
        if batch_success:
            return {
                "success": True,
                "message": f"成功批量设置 {len(configs)} 个配置",
                "success_count": len(configs),
                "errors": []
            }
        else:
            # 如果批量更新失败，回退到逐个更新
            success_count = 0
            errors = []
            
            for config in configs:
                try:
                    success = await config_manager.set_config(
                        key=config.key,
                        value=config.value,
                        description=config.description,
                        config_type=config.config_type
                    )
                    if success:
                        success_count += 1
                    else:
                        errors.append(f"设置配置 {config.key} 失败")
                except Exception as e:
                    errors.append(f"设置配置 {config.key} 失败: {str(e)}")
            
            return {
                "success": success_count > 0,
                "message": f"成功设置 {success_count} 个配置" + (f"，{len(errors)} 个失败" if errors else ""),
                "success_count": success_count,
                "errors": errors
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量设置配置失败: {str(e)}")

@router.post(ROUTES.config.batch_update)
async def batch_update_configs(configs: List[ConfigItem], user: Dict[str, Any] = Depends(check_config_permission)):
    """批量更新配置"""
    try:
        # 使用新的批量更新方法
        config_dict = {}
        for config in configs:
            config_dict[config.key] = {
                'value': config.value,
                'description': config.description,
                'config_type': config.config_type
            }
        
        # 批量更新配置
        batch_success = await config_manager.set_multiple_configs(config_dict)
        
        if batch_success:
            return {
                "success": True,
                "message": f"成功批量更新 {len(configs)} 个配置",
                "success_count": len(configs),
                "errors": []
            }
        else:
            # 如果批量更新失败，回退到逐个更新
            success_count = 0
            errors = []
            
            for config in configs:
                try:
                    success = await config_manager.set_config(
                        key=config.key,
                        value=config.value,
                        description=config.description,
                        config_type=config.config_type
                    )
                    if success:
                        success_count += 1
                    else:
                        errors.append(f"更新配置 {config.key} 失败")
                except Exception as e:
                    errors.append(f"更新配置 {config.key} 失败: {str(e)}")
            
            return {
                "success": success_count > 0,
                "message": f"成功更新 {success_count} 个配置" + (f"，{len(errors)} 个失败" if errors else ""),
                "success_count": success_count,
                "errors": errors
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量更新配置失败: {str(e)}")

@router.post(ROUTES.config.reset_defaults)
async def reset_default_configs(user: Dict[str, Any] = Depends(check_config_permission)):
    """重置为默认配置"""
    try:
        from app.services.config_manager import DEFAULT_CONFIGS
        
        # 使用新的批量更新方法
        config_dict = {}
        for key, config_info in DEFAULT_CONFIGS.items():
            config_dict[key] = {
                'value': config_info["value"],
                'description': config_info["description"],
                'config_type': config_info["config_type"]
            }
        
        # 批量重置配置
        batch_success = await config_manager.set_multiple_configs(config_dict)
        
        if batch_success:
            return {
                "success": True,
                "message": f"成功重置 {len(DEFAULT_CONFIGS)} 个配置为默认值",
                "success_count": len(DEFAULT_CONFIGS),
                "errors": []
            }
        else:
            # 如果批量更新失败，回退到逐个更新
            success_count = 0
            errors = []
            
            for key, config_info in DEFAULT_CONFIGS.items():
                try:
                    success = await config_manager.set_config(
                        key=key,
                        value=config_info["value"],
                        description=config_info["description"],
                        config_type=config_info["config_type"]
                    )
                    if success:
                        success_count += 1
                    else:
                        errors.append(f"重置配置 {key} 失败")
                except Exception as e:
                    errors.append(f"重置配置 {key} 失败: {str(e)}")
            
            return {
                "success": success_count > 0,
                "message": f"成功重置 {success_count} 个配置为默认值" + (f"，{len(errors)} 个失败" if errors else ""),
                "success_count": success_count,
                "errors": errors
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置默认配置失败: {str(e)}")

class ChannelBatchAddRequest(BaseModel):
    channels: str  # 多行文本，每行一个频道

@router.post(ROUTES.config.channels_batch_add)
async def batch_add_channels(request: ChannelBatchAddRequest, user: Dict[str, Any] = Depends(check_config_permission)):
    """批量添加频道"""
    try:
        from app.services.channel_manager import channel_manager
        from app.services.config_manager import config_manager
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.channels import JoinChannelRequest
        import re
        
        # 获取认证信息
        api_id = await config_manager.get_config('telegram.api_id')
        api_hash = await config_manager.get_config('telegram.api_hash')
        string_session = await config_manager.get_config('telegram.session', '')
        
        if not all([api_id, api_hash, string_session]):
            return {"success": False, "message": "Telegram认证信息不完整，请先完成认证"}
        
        # 解析频道列表
        channel_lines = request.channels.strip().split('\n')
        channels_to_add = []
        
        for line in channel_lines:
            line = line.strip()
            if not line:
                continue
                
            # 支持多种格式：@channel_name, https://t.me/channel_name, channel_name
            if line.startswith('https://t.me/'):
                channel_name = line.replace('https://t.me/', '@')
            elif not line.startswith('@'):
                channel_name = '@' + line
            else:
                channel_name = line
                
            # 去除多余的@符号
            channel_name = '@' + channel_name.lstrip('@')
            
            if channel_name not in channels_to_add:
                channels_to_add.append(channel_name)
        
        if not channels_to_add:
            return {"success": False, "message": "没有有效的频道需要添加"}
        
        # 创建Telegram客户端
        client = TelegramClient(StringSession(string_session), int(api_id), api_hash)
        await client.connect()
        
        results = {
            "added": [],
            "existed": [],
            "failed": [],
            "subscribed": []
        }
        
        try:
            for channel_name in channels_to_add:
                try:
                    # 检查频道是否已存在（通过channel_name检查）
                    existing_channel = await channel_manager.get_channel_by_name(channel_name)
                    if existing_channel:
                        results["existed"].append(channel_name)
                        continue
                    
                    # 获取频道实体
                    try:
                        entity = await client.get_entity(channel_name)
                        
                        # 获取频道信息
                        channel_id = None
                        channel_title = channel_name
                        
                        if hasattr(entity, 'id'):
                            if hasattr(entity, 'broadcast') and entity.broadcast:
                                channel_id = f"-100{entity.id}"
                            else:
                                channel_id = str(entity.id)
                        
                        if hasattr(entity, 'title'):
                            channel_title = entity.title
                        
                        # 检查是否需要订阅
                        if hasattr(entity, 'left') and entity.left:
                            # 频道未订阅，尝试订阅
                            try:
                                await client(JoinChannelRequest(entity))
                                results["subscribed"].append(channel_name)
                            except Exception as join_error:
                                logger.warning(f"订阅频道 {channel_name} 失败: {join_error}")
                        
                        # 添加频道到数据库
                        success = await channel_manager.add_channel(
                            channel_id=channel_id,
                            channel_name=channel_name,
                            channel_title=channel_title,
                            channel_type="source",
                            description=f"批量添加的频道: {channel_title}"
                        )
                        
                        if success:
                            results["added"].append({
                                "channel_name": channel_name,
                                "channel_title": channel_title,
                                "channel_id": channel_id
                            })
                        else:
                            results["failed"].append({
                                "channel_name": channel_name,
                                "reason": "添加到数据库失败"
                            })
                            
                    except Exception as e:
                        results["failed"].append({
                            "channel_name": channel_name,
                            "reason": str(e)
                        })
                        
                except Exception as e:
                    results["failed"].append({
                        "channel_name": channel_name,
                        "reason": str(e)
                    })
            
            # 构建响应消息
            message_parts = []
            if results["added"]:
                message_parts.append(f"成功添加 {len(results['added'])} 个频道")
            if results["existed"]:
                message_parts.append(f"{len(results['existed'])} 个频道已存在")
            if results["subscribed"]:
                message_parts.append(f"自动订阅了 {len(results['subscribed'])} 个频道")
            if results["failed"]:
                message_parts.append(f"{len(results['failed'])} 个频道添加失败")
            
            return {
                "success": len(results["added"]) > 0 or len(results["existed"]) > 0,
                "message": "，".join(message_parts) if message_parts else "没有频道被添加",
                "results": results
            }
            
        finally:
            await client.disconnect()
            
    except Exception as e:
        return {
            "success": False,
            "message": f"批量添加频道失败: {str(e)}"
        }