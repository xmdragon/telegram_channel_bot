"""
配置管理API
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from pydantic import BaseModel
import logging

from app.services.config_manager import config_manager

router = APIRouter()
logger = logging.getLogger(__name__)

class ConfigItem(BaseModel):
    key: str
    value: Any
    description: str = ""
    config_type: str = "string"

class ConfigUpdate(BaseModel):
    value: Any
    description: str = ""

@router.get("/")
async def get_all_configs():
    """获取所有配置项"""
    try:
        configs = await config_manager.get_all_configs()
        return {
            "success": True,
            "configs": configs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")

@router.get("/{config_key}")
async def get_config(config_key: str):
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

@router.post("/")
async def create_config(config: ConfigItem):
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

@router.put("/{config_key}")
async def update_config(config_key: str, config_update: ConfigUpdate):
    """更新配置项"""
    try:
        # 先检查配置是否存在
        existing_value = await config_manager.get_config(config_key)
        if existing_value is None:
            raise HTTPException(status_code=404, detail="配置项不存在")
        
        # 获取现有配置信息以保持类型
        all_configs = await config_manager.get_all_configs()
        existing_config = all_configs.get(config_key, {})
        config_type = existing_config.get('config_type', 'string')
        
        success = await config_manager.set_config(
            key=config_key,
            value=config_update.value,
            description=config_update.description,
            config_type=config_type
        )
        
        if success:
            # 重新加载应用配置缓存
            from app.core.config import settings
            await settings.load_db_configs()
            
            return {"success": True, "message": "配置更新成功"}
        else:
            raise HTTPException(status_code=500, detail="配置更新失败")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")

@router.delete("/{config_key}")
async def delete_config(config_key: str):
    """删除配置项"""
    try:
        success = await config_manager.delete_config(config_key)
        
        if success:
            return {"success": True, "message": "配置删除成功"}
        else:
            raise HTTPException(status_code=404, detail="配置项不存在")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除配置失败: {str(e)}")

@router.post("/reload")
async def reload_configs():
    """重新加载配置缓存"""
    try:
        await config_manager.reload_cache()
        
        # 重新加载应用配置缓存
        from app.core.config import settings
        await settings.load_db_configs()
        
        return {"success": True, "message": "配置缓存重新加载成功"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新加载配置失败: {str(e)}")

@router.get("/resolve-group-id")
async def resolve_group_id(group_link: str):
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

@router.post("/resolve-target-channel")
async def resolve_target_channel(request: dict):
    """解析目标频道ID"""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        target_channel = request.get("target_channel", "").strip()
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

@router.get("/categories/telegram")
async def get_telegram_configs():
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

@router.get("/categories/channels")
async def get_channel_configs():
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

@router.get("/categories/filter")
async def get_filter_configs():
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

@router.get("/categories/accounts")
async def get_accounts_configs():
    """获取账号采集相关配置"""
    try:
        all_configs = await config_manager.get_all_configs()
        accounts_configs = {
            key: value for key, value in all_configs.items()
            if key.startswith('accounts.')
        }
        
        return {
            "success": True,
            "configs": accounts_configs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取账号采集配置失败: {str(e)}")

@router.get("/categories/review")
async def get_review_configs():
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

@router.post("/batch-update")
async def batch_update_configs(configs: List[ConfigItem]):
    """批量更新配置"""
    try:
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
        
        # 重新加载应用配置缓存
        from app.core.config import settings
        await settings.load_db_configs()
        
        return {
            "success": True,
            "message": f"成功更新 {success_count} 个配置",
            "success_count": success_count,
            "errors": errors
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量更新配置失败: {str(e)}")

@router.post("/reset-defaults")
async def reset_default_configs():
    """重置为默认配置"""
    try:
        from app.services.config_manager import DEFAULT_CONFIGS
        
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
        
        # 重新加载应用配置缓存
        from app.core.config import settings
        await settings.load_db_configs()
        
        return {
            "success": True,
            "message": f"成功重置 {success_count} 个配置为默认值",
            "success_count": success_count,
            "errors": errors
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置默认配置失败: {str(e)}")

# 频道管理相关API
class ChannelAddRequest(BaseModel):
    channel_id: str
    channel_name: str = ""
    channel_title: str = ""
    description: str = ""

@router.post("/channels/add")
async def add_channel(request: ChannelAddRequest):
    """添加监听频道"""
    try:
        from app.services.channel_manager import channel_manager
        
        success = await channel_manager.add_channel(
            channel_id=request.channel_id,
            channel_name=request.channel_name,
            description=request.description,
            channel_type="source"
        )
        
        if success:
            return {"success": True, "message": f"频道 {request.channel_id} 添加成功"}
        else:
            raise HTTPException(status_code=400, detail="频道已存在或添加失败")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加频道失败: {str(e)}")

@router.delete("/channels/{channel_id}")
async def remove_channel(channel_id: str):
    """移除监听频道"""
    try:
        from app.services.channel_manager import channel_manager
        
        success = await channel_manager.delete_channel(channel_id)
        
        if success:
            return {"success": True, "message": f"频道 {channel_id} 移除成功"}
        else:
            raise HTTPException(status_code=404, detail="频道不存在")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"移除频道失败: {str(e)}")

class ChannelStatusRequest(BaseModel):
    enabled: bool

@router.put("/channels/{channel_id}/status")
async def update_channel_status(channel_id: str, request: ChannelStatusRequest):
    """更新频道监听状态"""
    try:
        from app.services.channel_manager import channel_manager
        
        success = await channel_manager.update_channel(
            channel_id, 
            is_active=request.enabled
        )
        
        if success:
            return {"success": True, "message": f"频道 {channel_id} 状态更新成功"}
        else:
            raise HTTPException(status_code=404, detail="频道不存在")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新频道状态失败: {str(e)}")

@router.get("/channels/")
async def get_channels():
    """获取所有频道"""
    try:
        from app.services.channel_manager import channel_manager
        
        channels = await channel_manager.get_source_channels()
        
        return {
            "success": True,
            "channels": channels
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取频道列表失败: {str(e)}")

class ChannelBatchAddRequest(BaseModel):
    channels: str  # 多行文本，每行一个频道

@router.post("/channels/batch-add")
async def batch_add_channels(request: ChannelBatchAddRequest):
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

@router.get("/channels/{channel_id}")
async def get_channel(channel_id: str):
    """获取单个频道信息"""
    try:
        from app.services.channel_manager import channel_manager
        
        channel = await channel_manager.get_channel_by_id(channel_id)
        
        if channel:
            return {
                "success": True,
                "channel": channel
            }
        else:
            raise HTTPException(status_code=404, detail="频道不存在")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取频道信息失败: {str(e)}")


# 账号管理相关API
class AccountAddRequest(BaseModel):
    account: str

@router.post("/accounts/blacklist/add")
async def add_account_to_blacklist(request: AccountAddRequest):
    """添加账号到黑名单"""
    try:
        blacklist = await config_manager.get_config("accounts.account_blacklist", [])
        if request.account not in blacklist:
            blacklist.append(request.account)
            await config_manager.set_config("accounts.account_blacklist", blacklist, "账号黑名单", "list")
        
        return {"success": True, "message": f"账号 '{request.account}' 已添加到黑名单"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加账号到黑名单失败: {str(e)}")

@router.delete("/accounts/blacklist/{account}")
async def remove_account_from_blacklist(account: str):
    """从黑名单移除账号"""
    try:
        blacklist = await config_manager.get_config("accounts.account_blacklist", [])
        if account in blacklist:
            blacklist.remove(account)
            await config_manager.set_config("accounts.account_blacklist", blacklist, "账号黑名单", "list")
        
        return {"success": True, "message": f"账号 '{account}' 已从黑名单移除"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"从黑名单移除账号失败: {str(e)}")

@router.post("/accounts/whitelist/add")
async def add_account_to_whitelist(request: AccountAddRequest):
    """添加账号到白名单"""
    try:
        whitelist = await config_manager.get_config("accounts.account_whitelist", [])
        if request.account not in whitelist:
            whitelist.append(request.account)
            await config_manager.set_config("accounts.account_whitelist", whitelist, "账号白名单", "list")
        
        return {"success": True, "message": f"账号 '{request.account}' 已添加到白名单"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加账号到白名单失败: {str(e)}")

@router.delete("/accounts/whitelist/{account}")
async def remove_account_from_whitelist(account: str):
    """从白名单移除账号"""
    try:
        whitelist = await config_manager.get_config("accounts.account_whitelist", [])
        if account in whitelist:
            whitelist.remove(account)
            await config_manager.set_config("accounts.account_whitelist", whitelist, "账号白名单", "list")
        
        return {"success": True, "message": f"账号 '{account}' 已从白名单移除"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"从白名单移除账号失败: {str(e)}")