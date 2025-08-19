"""
AI功能控制API
提供运行时开启/关闭AI功能的接口
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
import logging

from app.services.auth_service import get_auth_service
from app.core.ai_config import get_ai_config
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter()

async def require_admin():
    """要求管理员权限"""
    # 简化版权限检查，实际项目应有完整的权限系统
    return True

@router.get(ROUTES.ai.status)
async def get_ai_status():
    """获取AI功能状态"""
    try:
        ai_config = get_ai_config()
        return {
            "success": True,
            "data": ai_config.get_config()
        }
    except Exception as e:
        logger.error(f"获取AI状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.ai.enable)
async def enable_ai(admin: bool = Depends(require_admin)):
    """启用AI功能"""
    try:
        ai_config = get_ai_config()
        success = ai_config.set_ai_enabled(True)
        
        if success:
            return {
                "success": True,
                "message": "AI功能已启用",
                "data": ai_config.get_config()
            }
        else:
            raise HTTPException(status_code=500, detail="启用AI功能失败")
            
    except Exception as e:
        logger.error(f"启用AI功能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.ai.disable)
async def disable_ai(admin: bool = Depends(require_admin)):
    """禁用AI功能"""
    try:
        ai_config = get_ai_config()
        success = ai_config.set_ai_enabled(False)
        
        if success:
            return {
                "success": True,
                "message": "AI功能已禁用，重启后生效",
                "data": ai_config.get_config()
            }
        else:
            raise HTTPException(status_code=500, detail="禁用AI功能失败")
            
    except Exception as e:
        logger.error(f"禁用AI功能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(ROUTES.ai.cache_info)
async def get_cache_info():
    """获取模型缓存信息"""
    try:
        from app.services.model_cache_manager import get_model_cache_manager
        cache_manager = get_model_cache_manager()
        
        return {
            "success": True,
            "data": cache_manager.get_cache_info()
        }
    except Exception as e:
        logger.error(f"获取缓存信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.ai.cache_preload)
async def preload_models(admin: bool = Depends(require_admin)):
    """预加载AI模型"""
    try:
        from app.services.model_cache_manager import get_model_cache_manager
        cache_manager = get_model_cache_manager()
        
        success = cache_manager.preload_models()
        
        return {
            "success": success,
            "message": "模型预加载已启动" if success else "模型预加载失败"
        }
    except Exception as e:
        logger.error(f"预加载模型失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete(ROUTES.ai.cache_clear)
async def clear_cache(admin: bool = Depends(require_admin)):
    """清理模型缓存"""
    try:
        from app.services.model_cache_manager import get_model_cache_manager
        cache_manager = get_model_cache_manager()
        
        success = cache_manager.clear_cache()
        
        return {
            "success": success,
            "message": "缓存已清理" if success else "清理缓存失败"
        }
    except Exception as e:
        logger.error(f"清理缓存失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))