"""
管理员配置管理API
包括：配置更新、转发配置、审核群解析
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pydantic import BaseModel
import logging

from app.core.route_config import ROUTES
from app.services.config_manager import config_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# === 配置读取方法 === 
@router.get(ROUTES.admin.config)
async def get_system_config():
    """获取系统配置"""
    from app.core.config import db_settings
    
    return {
        # 前端显示用（用户友好格式）
        "target_channel": await config_manager.get_config('target.channel_link', ''),
        "review_group": await config_manager.get_config('review.group_link', ''),
        
        # 其他配置
        "auto_forward_enabled": await config_manager.get_config('review.auto_forward_enabled', False),
        "auto_forward_delay": await db_settings.get_auto_forward_delay(),
        "source_channels": await db_settings.get_source_channels(),
        "history_message_limit": await db_settings.get_history_message_limit(),
        "target.signature": await config_manager.get_config('target.signature', ''),
        "collection.enabled": await config_manager.get_config('collection.enabled', True)
    }

# === 配置更新方法 ===

class ConfigUpdateRequest(BaseModel):
    key: str
    value: str
    config_type: str = "string"

@router.post(ROUTES.admin.config)
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

@router.post(ROUTES.admin.config_batch)
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

@router.post(ROUTES.admin.config_forwarding)
async def update_forwarding_config(request: ForwardingConfigRequest):
    """更新转发配置并刷新缓存"""
    try:
        # 保存用户输入的用户名/链接格式
        await config_manager.set_config('target.channel_link', request.target_channel)
        await config_manager.set_config('review.group_link', request.review_group)
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

@router.post(ROUTES.admin.resolve_review_group)
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

@router.get(ROUTES.admin.review_group_status)
async def get_review_group_status():
    """获取审核群状态信息"""
    try:
        from app.services.telegram_link_resolver import link_resolver
        
        # 获取配置的审核群
        review_group_config = await config_manager.get_config('review.group_id', '')
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