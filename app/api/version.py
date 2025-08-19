"""
版本号API模块
提供前端版本号查询接口
"""
from fastapi import APIRouter
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
        version = get_frontend_version()
        
        return {
            "success": True,
            "data": {
                "version": version,
                "type": "frontend_assets"
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
                "updated_files": updated_count
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