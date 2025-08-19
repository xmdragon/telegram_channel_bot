"""
版本号API模块
提供前端版本号查询和管理接口
"""
from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any
import logging

from app.core.version_manager import get_frontend_version, get_version_manager
from app.utils.timezone import get_current_time, format_for_api

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/version")
async def get_version():
    """
    获取前端资源版本号
    """
    try:
        version_manager = get_version_manager()
        version = version_manager.get_current_version()
        
        # 获取详细信息
        config_manager = version_manager._get_config_manager()
        manual_version = None
        auto_version = None
        
        if config_manager:
            manual_version = config_manager.get_config('system.version')
            auto_version = config_manager.get_config('system.auto_version')
        
        return {
            "success": True,
            "data": {
                "version": version,
                "manual_version": manual_version,
                "auto_version": auto_version,
                "type": "frontend_assets",
                "source": "manual" if manual_version and manual_version.strip() else "auto"
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取版本号失败: {e}")
        return {
            "success": False,
            "message": f"获取版本号失败: {str(e)}",
            "data": {"version": "unknown"},
            "timestamp": format_for_api(get_current_time())
        }

@router.post("/version/refresh")
async def refresh_version():
    """
    刷新版本号（管理员功能）
    生成新的版本号并更新HTML文件
    """
    try:
        version_manager = get_version_manager()
        
        # 生成新版本号
        new_version = version_manager.refresh_version()
        
        # 更新HTML文件
        updated_count = version_manager.update_html_files()
        
        logger.info(f"手动刷新版本号: {new_version}, 更新了 {updated_count} 个文件")
        
        return {
            "success": True,
            "data": {
                "version": new_version,
                "updated_files": updated_count,
                "source": "auto"
            },
            "message": f"版本号已刷新为 {new_version}，更新了 {updated_count} 个HTML文件",
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"刷新版本号失败: {e}")
        return {
            "success": False,
            "message": f"刷新版本号失败: {str(e)}",
            "timestamp": format_for_api(get_current_time())
        }

@router.post("/version/set")
async def set_version(request: Dict[str, Any] = Body(...)):
    """
    设置手动版本号（管理员功能）
    """
    try:
        version = request.get("version", "").strip()
        if not version:
            raise HTTPException(status_code=400, detail="版本号不能为空")
        
        version_manager = get_version_manager()
        
        # 设置手动版本号
        success = version_manager.set_manual_version(version)
        if not success:
            raise HTTPException(status_code=500, detail="设置手动版本号失败")
        
        # 更新HTML文件
        updated_count = version_manager.update_html_files()
        
        logger.info(f"设置手动版本号: {version}, 更新了 {updated_count} 个文件")
        
        return {
            "success": True,
            "data": {
                "version": version,
                "updated_files": updated_count,
                "source": "manual"
            },
            "message": f"手动版本号已设置为 {version}，更新了 {updated_count} 个HTML文件",
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置手动版本号失败: {e}")
        return {
            "success": False,
            "message": f"设置手动版本号失败: {str(e)}",
            "timestamp": format_for_api(get_current_time())
        }

@router.delete("/version/manual")
async def clear_manual_version():
    """
    清除手动版本号设置（管理员功能）
    清除后将使用自动生成的版本号
    """
    try:
        version_manager = get_version_manager()
        
        # 清除手动版本号
        success = version_manager.clear_manual_version()
        if not success:
            raise HTTPException(status_code=500, detail="清除手动版本号失败")
        
        # 获取当前生效的版本号
        current_version = version_manager.get_current_version()
        
        # 更新HTML文件
        updated_count = version_manager.update_html_files()
        
        logger.info(f"清除手动版本号，当前版本: {current_version}, 更新了 {updated_count} 个文件")
        
        return {
            "success": True,
            "data": {
                "version": current_version,
                "updated_files": updated_count,
                "source": "auto"
            },
            "message": f"手动版本号已清除，当前使用自动版本号 {current_version}，更新了 {updated_count} 个HTML文件",
            "timestamp": format_for_api(get_current_time())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清除手动版本号失败: {e}")
        return {
            "success": False,
            "message": f"清除手动版本号失败: {str(e)}",
            "timestamp": format_for_api(get_current_time())
        }