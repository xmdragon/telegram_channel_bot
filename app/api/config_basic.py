"""
基础配置管理API
包括：配置CRUD操作、分类配置获取、解析服务
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

class ConfigUpdate(BaseModel):
    value: Any
    description: str = ""

class TargetChannelResolveRequest(BaseModel):
    target_channel: str

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

@router.get(ROUTES.config.base)
async def get_all_configs(user: Dict[str, Any] = Depends(check_config_permission)):
    """获取所有配置项"""
    try:
        configs = await config_manager.get_all_configs()
        return {
            "success": True,
            "configs": configs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")

@router.get(ROUTES.config.by_key)
async def get_config(config_key: str, user: Dict[str, Any] = Depends(check_config_permission)):
    """获取单个配置项"""
    try:
        value = await config_manager.get_config(config_key)
        if value is None:
            raise HTTPException(status_code=404, detail="配置项不存在")
        
        return {
            "success": True,
            "key": config_key,
            "value": value
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")

@router.post(ROUTES.config.base)
async def create_config(config: ConfigItem, user: Dict[str, Any] = Depends(check_config_permission)):
    """创建新配置项"""
    try:
        success = await config_manager.set_config(
            key=config.key,
            value=config.value,
            description=config.description,
            config_type=config.config_type
        )
        
        if success:
            return {"success": True, "message": "配置创建成功"}
        else:
            raise HTTPException(status_code=500, detail="配置创建失败")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建配置失败: {str(e)}")

@router.post(ROUTES.config.by_key)
async def set_config(config_key: str, config_update: ConfigUpdate, user: Dict[str, Any] = Depends(check_config_permission)):
    """设置配置（创建或更新）"""
    try:
        # 获取现有配置信息（如果存在）
        all_configs = await config_manager.get_all_configs()
        existing_config = all_configs.get(config_key)
        
        # 如果配置存在，保持现有的配置类型和描述（如果没有提供新的描述）
        if existing_config:
            config_type = existing_config.get('config_type', 'string')
            description = config_update.description or existing_config.get('description', '')
        else:
            # 新配置，使用默认类型
            config_type = 'string'
            description = config_update.description or ''
        
        success = await config_manager.set_config(
            key=config_key,
            value=config_update.value,
            description=description,
            config_type=config_type
        )
        
        if success:
            # 配置已通过监听器自动更新，无需手动重新加载
            return {"success": True, "message": "配置设置成功"}
        else:
            raise HTTPException(status_code=500, detail="配置设置失败")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"设置配置失败: {str(e)}")

@router.put(ROUTES.config.by_key)
async def update_config(config_key: str, config_update: ConfigUpdate, user: Dict[str, Any] = Depends(check_config_permission)):
    """更新配置项"""
    try:
        # 获取现有配置信息以保持类型和描述
        all_configs = await config_manager.get_all_configs()
        existing_config = all_configs.get(config_key)
        
        if existing_config is None:
            raise HTTPException(status_code=404, detail="配置项不存在")
        
        # 保持现有的配置类型，如果没有提供描述则保持现有描述
        config_type = existing_config.get('config_type', 'string')
        description = config_update.description or existing_config.get('description', '')
        
        success = await config_manager.set_config(
            key=config_key,
            value=config_update.value,
            description=description,
            config_type=config_type
        )
        
        if success:
            # 配置已通过监听器自动更新，无需手动重新加载
            return {"success": True, "message": "配置更新成功"}
        else:
            raise HTTPException(status_code=500, detail="配置更新失败")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")

@router.delete(ROUTES.config.by_key)
async def delete_config(config_key: str, user: Dict[str, Any] = Depends(check_config_permission)):
    """删除配置项"""
    try:
        success = await config_manager.delete_config(config_key)
        
        if success:
            return {"success": True, "message": "配置删除成功"}
        else:
            raise HTTPException(status_code=404, detail="配置项不存在")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除配置失败: {str(e)}")

@router.post(ROUTES.config.reload)
async def reload_configs(user: Dict[str, Any] = Depends(check_config_permission)):
    """重新加载配置缓存"""
    try:
        await config_manager.reload_cache()
        
        # 配置已通过监听器自动更新，无需手动重新加载
        
        return {"success": True, "message": "配置缓存重新加载成功"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新加载配置失败: {str(e)}")

@router.get(ROUTES.config.categories_telegram)
async def get_telegram_configs(user: Dict[str, Any] = Depends(check_config_permission)):
    """获取Telegram相关配置"""
    try:
        all_configs = await config_manager.get_all_configs()
        telegram_configs = {
            key: value for key, value in all_configs.items()
            if key.startswith('telegram.')
        }
        
        return {
            "success": True,
            "configs": telegram_configs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取Telegram配置失败: {str(e)}")

@router.get(ROUTES.config.categories_channels)
async def get_channel_configs(user: Dict[str, Any] = Depends(check_config_permission)):
    """获取频道相关配置"""
    try:
        all_configs = await config_manager.get_all_configs()
        channel_configs = {
            key: value for key, value in all_configs.items()
            if key.startswith('channels.')
        }
        
        return {
            "success": True,
            "configs": channel_configs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取频道配置失败: {str(e)}")

@router.get(ROUTES.config.categories_filter)
async def get_filter_configs(user: Dict[str, Any] = Depends(check_config_permission)):
    """获取过滤相关配置"""
    try:
        all_configs = await config_manager.get_all_configs()
        filter_configs = {
            key: value for key, value in all_configs.items()
            if key.startswith('filter.')
        }
        
        return {
            "success": True,
            "configs": filter_configs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取过滤配置失败: {str(e)}")

@router.get(ROUTES.config.categories_review)
async def get_review_configs(user: Dict[str, Any] = Depends(check_config_permission)):
    """获取审核相关配置"""
    try:
        all_configs = await config_manager.get_all_configs()
        review_configs = {
            key: value for key, value in all_configs.items()
            if key.startswith('review.')
        }
        
        return {
            "success": True,
            "configs": review_configs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取审核配置失败: {str(e)}")

@router.get(ROUTES.config.resolve_group_id)
async def resolve_group_id(group_link: str, user: Dict[str, Any] = Depends(check_config_permission)):
    """解析群组ID"""
    try:
        from app.services.telegram_link_resolver import link_resolver
        
        # 尝试解析群ID
        resolved_id = await link_resolver.resolve_group_id(group_link)
        
        if resolved_id:
            return {
                "success": True,
                "group_id": resolved_id
            }
        else:
            return {
                "success": False,
                "message": "无法解析群ID"
            }
            
    except Exception as e:
        return {
            "success": False,
            "message": f"解析失败: {str(e)}"
        }

@router.post(ROUTES.config.resolve_target_channel)
async def resolve_target_channel(request: TargetChannelResolveRequest, user: Dict[str, Any] = Depends(check_config_permission)):
    """解析目标频道ID"""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        target_channel = request.target_channel.strip()
        if not target_channel:
            return {"success": False, "message": "目标频道不能为空"}
        
        # 获取认证信息
        api_id = await config_manager.get_config('telegram.api_id')
        api_hash = await config_manager.get_config('telegram.api_hash')
        string_session = await config_manager.get_config('telegram.session', '')
        
        if not all([api_id, api_hash, string_session]):
            return {"success": False, "message": "Telegram认证信息不完整"}
        
        # 创建临时客户端
        client = TelegramClient(StringSession(string_session), int(api_id), api_hash)
        await client.connect()
        
        try:
            # 解析频道
            if target_channel.lstrip('-').isdigit():
                # 如果是数字ID，直接返回
                resolved_id = target_channel
            else:
                # 如果是用户名，获取实体
                entity = await client.get_entity(target_channel)
                if hasattr(entity, 'broadcast') and entity.broadcast:
                    resolved_id = f"-100{entity.id}"
                else:
                    resolved_id = str(entity.id)
            
            # 缓存解析的ID
            await config_manager.set_config('channels.target_channel_id_cached', resolved_id, '目标频道解析后的ID', 'string')
            
            return {
                "success": True,
                "resolved_id": resolved_id
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"解析目标频道失败: {str(e)}"
            }
        finally:
            await client.disconnect()
            
    except Exception as e:
        return {
            "success": False,
            "message": f"解析失败: {str(e)}"
        }