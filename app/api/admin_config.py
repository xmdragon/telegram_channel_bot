"""
管理员配置管理API
包括：配置更新、转发配置、审核群解析
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel
import logging

from app.core.route_config import ROUTES
from app.services.config_manager import config_manager
from app.services.telegram_config_manager import telegram_config_manager
from app.core.telegram_config import TelegramConfig
from app.services.auth_service import get_auth_service

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

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

def mask_session_string(session_value: str) -> str:
    """脱敏Session字符串，保护敏感信息"""
    if not session_value or session_value.strip() == "":
        return "未配置"
    # 只显示前4位和后4位，中间用*代替
    if len(session_value) <= 8:
        return "****已配置"
    return f"{session_value[:4]}****{session_value[-4:]}"

async def resolve_telegram_entity(entity_link: str, entity_type: str = "entity") -> Tuple[Optional[str], str]:
    """
    通用的Telegram实体（频道/群组）解析方法

    Args:
        entity_link: Telegram链接或用户名
        entity_type: 实体类型（用于日志记录）："channel"/"group"/"entity"

    Returns:
        (resolved_id, link_type) - 解析后的ID和链接类型
    """
    try:
        from app.services.telegram_resolver import telegram_resolver

        # 使用统一解析器
        resolved_id = await telegram_resolver.resolve(entity_link)

        if resolved_id:
            logger.info(f"{entity_type}已解析: {entity_link} -> {resolved_id}")
        else:
            logger.warning(f"{entity_type}解析失败: {entity_link}")

        # 不再区分链接类型，统一返回
        return resolved_id, "链接" if resolved_id else ""

    except Exception as e:
        logger.error(f"解析{entity_type}时出错: {e}")
        return None, ""

# 已删除未使用的_trigger_history_collection函数
# 历史消息采集已由message_collector.py统一处理

# === 配置读取方法 ===
@router.get(ROUTES.admin.config)
async def get_system_config(user: Dict[str, Any] = Depends(require_auth)):
    """获取系统配置 - 字段名与前端完全一致"""
    from app.core.config import db_settings
    
    return {
        # Telegram API配置（从telegram.json读取）
        TelegramConfig.API_ID: await telegram_config_manager.get_api_id() or '',
        TelegramConfig.API_HASH: await telegram_config_manager.get_api_hash() or '',

        # 采集配置
        "collection.enabled": await config_manager.get_config('collection.enabled', True),
        "collection.max_media_size_mb": await config_manager.get_config('collection.max_media_size_mb', 200),
        "collection.max_messages_per_batch": await config_manager.get_config('collection.max_messages_per_batch', 10),
        "source.history_limit": await config_manager.get_config('source.history_limit', 50),

        # 去重检测配置
        "duplicate_detection.enabled": await config_manager.get_config('duplicate_detection.enabled', True),
        "duplicate_detection.content_threshold": await config_manager.get_config('duplicate_detection.content_threshold', 0.86),
        "duplicate_detection.suspected_threshold": await config_manager.get_config('duplicate_detection.suspected_threshold', 0.82),
        "duplicate_detection.confirmed_threshold": await config_manager.get_config('duplicate_detection.confirmed_threshold', 0.95),
        "duplicate_detection.simhash_threshold": await config_manager.get_config('duplicate_detection.simhash_threshold', 4),
        "duplicate_detection.media_threshold": await config_manager.get_config('duplicate_detection.media_threshold', 0.90),
        "duplicate_detection.retention_days": await config_manager.get_config('duplicate_detection.retention_days', 30),
        "duplicate_detection.auto_adjust": await config_manager.get_config('duplicate_detection.auto_adjust', True),
        "duplicate_detection.ttl_hours": await config_manager.get_config('duplicate_detection.ttl_hours', 24),

        # 过滤配置
        "filter.enabled": await config_manager.get_config('filter.enabled', True),
        "filter.tail_filter": await config_manager.get_config('filter.tail_filter', True),
        "filter.separator": await config_manager.get_config('filter.separator', True),
        "filter.markdown": await config_manager.get_config('filter.markdown', True),
        "filter.ad_detector": await config_manager.get_config('filter.ad_detector', True),

        # 目标频道配置
        "target.require_approval": await config_manager.get_config('target.require_approval', True),
        "target.auto_reject_ads": await config_manager.get_config('target.auto_reject_ads', False),
        "target.auto_forward_enabled": await config_manager.get_config('target.auto_forward_enabled', False),
        "target.auto_forward_delay": await config_manager.get_config('target.auto_forward_delay', 300),
        "target.channel_link": await config_manager.get_config('target.channel_link', ''),
        "target.channel_id": await config_manager.get_config('target.channel_id', ''),
        "target.signature": await config_manager.get_config('target.signature', ''),

        # 调度器配置
        "scheduler.enabled": await config_manager.get_config('scheduler.enabled', True),
        "scheduler.data_cleanup_interval_hours": await config_manager.get_config('scheduler.data_cleanup_interval_hours', 24),

        # 存储配置
        "storage.delete_single_messages": await config_manager.get_config('storage.delete_single_messages', True),

        # 系统配置
        "system.log_level": await config_manager.get_config('system.log_level', 'INFO'),

        # 性能优化配置
        "telegram.rate_limit_text_interval": await config_manager.get_config('telegram.rate_limit_text_interval', 5.0),
        "telegram.rate_limit_media_interval": await config_manager.get_config('telegram.rate_limit_media_interval', 12.0),
        "telegram.rate_limit_safety_factor": await config_manager.get_config('telegram.rate_limit_safety_factor', 1.5),
        "telegram.max_retry_attempts": await config_manager.get_config('telegram.max_retry_attempts', 3),
        "telegram.flood_wait_buffer_min": await config_manager.get_config('telegram.flood_wait_buffer_min', 1),
        "telegram.flood_wait_buffer_max": await config_manager.get_config('telegram.flood_wait_buffer_max', 5),
        "telegram.max_message_length": await config_manager.get_config('telegram.max_message_length', 1000),
        "telegram.max_message_length_vip": await config_manager.get_config('telegram.max_message_length_vip', 2000),
        "processor.timeout_seconds": await config_manager.get_config('processor.timeout_seconds', 120),
        "processor.send_message_timeout": await config_manager.get_config('processor.send_message_timeout', 120),

        # Telegram Session配置（脱敏显示）
        TelegramConfig.LISTENER_SESSION: mask_session_string(await telegram_config_manager.get_listener_session() or ''),
        TelegramConfig.SENDER_SESSION: mask_session_string(await telegram_config_manager.get_sender_session() or '')
    }

# === 配置更新方法 ===

class ConfigUpdateRequest(BaseModel):
    key: str
    value: str
    config_type: str = "string"

@router.post(ROUTES.admin.config)
async def update_config(request: ConfigUpdateRequest, user: Dict[str, Any] = Depends(require_auth)):
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
async def update_config_batch(configs: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    """批量更新配置项"""
    try:
        success_count = 0
        errors = []
        
        # 检查采集开关变化以触发历史采集
        collection_changed = False
        old_collection_enabled = None
        new_collection_enabled = None
        
        if 'collection.enabled' in configs:
            # 获取旧值
            old_collection_enabled = await config_manager.get_config('collection.enabled', False)
            new_collection_enabled = configs['collection.enabled']
            
            # 检查是否从关闭变为开启
            if not old_collection_enabled and new_collection_enabled:
                collection_changed = True
                logger.info("检测到采集开关从关闭变为开启，将触发历史采集")
        
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
        
        # 如果采集开关被开启，记录日志（collector服务会自动检测并触发）
        if collection_changed and len(errors) == 0:
            # 不再直接调用历史采集，避免API超时
            # collector服务会在10秒内自动检测配置变化并启动历史采集
            logger.info("采集开关已启用，collector服务将自动检测并启动历史采集")
        
        # 构建返回消息
        message = f"成功更新 {success_count} 个配置项"
        if collection_changed and len(errors) == 0:
            message += "，历史采集将在后台自动启动"
        
        return {
            "success": len(errors) == 0,
            "message": message,
            "errors": errors if errors else None
        }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量更新配置失败: {str(e)}")

class ForwardingConfigRequest(BaseModel):
    target_channel: str
    target_channel_id: str = ""  # 前端可以传入或清空ID
    auto_forward_enabled: bool = False
    auto_forward_delay: int = 1800
    auto_reject_ads: bool = False
    require_approval: bool = True

@router.post(ROUTES.admin.config_forwarding)
async def update_forwarding_config(request: ForwardingConfigRequest, user: Dict[str, Any] = Depends(require_auth)):
    """更新转发配置"""
    try:
        # 保存配置（使用新的target.*命名）
        await config_manager.set_config('target.channel_link', request.target_channel, config_type="string")
        await config_manager.set_config('target.auto_forward_enabled', request.auto_forward_enabled, config_type="boolean")
        await config_manager.set_config('target.auto_forward_delay', request.auto_forward_delay, config_type="integer")
        await config_manager.set_config('target.auto_reject_ads', request.auto_reject_ads, config_type="boolean")
        await config_manager.set_config('target.require_approval', request.require_approval, config_type="boolean")

        target_resolved_id = None

        # 如果前端传入了ID，直接保存；如果没有ID或ID被清空，则需要解析
        if request.target_channel_id:
            # 前端传入了ID，直接使用
            await config_manager.set_config('target.channel_id', request.target_channel_id)
            target_resolved_id = request.target_channel_id
        elif request.target_channel:
            # ID为空但有链接，需要解析
            resolved_id, _ = await resolve_telegram_entity(request.target_channel, "目标频道")
            if resolved_id:
                await config_manager.set_config('target.channel_id', str(resolved_id))
                target_resolved_id = str(resolved_id)

        logger.info("配置已保存并立即生效")

        # 构建返回消息
        messages = ["转发配置已保存"]
        if target_resolved_id:
            messages.append(f"目标频道已解析: {target_resolved_id}")
        else:
            messages.append("目标频道暂未解析（需要Telegram连接）")

        return {
            "success": True,
            "message": "，".join(messages),
            "target_channel_id": target_resolved_id  # 返回解析后的目标频道ID
        }
        
    except Exception as e:
        logger.error(f"更新转发配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新转发配置失败: {str(e)}")

