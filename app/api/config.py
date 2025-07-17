"""
配置管理API
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from pydantic import BaseModel

from app.services.config_manager import config_manager

router = APIRouter()

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