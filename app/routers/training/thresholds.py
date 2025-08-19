"""
阈值管理模块 - AI训练阈值的统计、优化和管理
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from datetime import datetime
import logging

from .base import handle_api_error
from app.services.auth_service import get_auth_service
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

security = HTTPBearer(auto_error=False)

# 认证中间件 - 从messages_filter.py复制过来
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

def check_permission(permission_name: str):
    """检查权限装饰器"""
    def decorator(func):
        return func  # 简化版本，实际项目中应该实现权限检查
    return decorator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-thresholds"])

@router.get(ROUTES.training.thresholds_stats)
@check_permission("filter.view")
async def get_threshold_stats(
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    获取阈值统计信息
    返回各个过滤器的阈值配置、性能指标等
    """
    try:
        from app.core.threshold_manager import threshold_manager
        
        stats = threshold_manager.get_all_stats()
        
        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取阈值统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


@router.post(ROUTES.training.thresholds_optimize)
@check_permission("filter.admin")
async def optimize_thresholds(
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    优化所有过滤器的阈值
    基于历史反馈数据自动调整阈值以获得最佳性能
    """
    try:
        from app.core.threshold_manager import threshold_manager
        
        logger.info(f"用户 {user.get('user_id')} 开始阈值优化")
        
        # 执行批量优化
        threshold_manager.batch_optimize()
        
        # 获取优化后的统计
        stats = threshold_manager.get_all_stats()
        
        return {
            "success": True,
            "message": "阈值优化完成",
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"阈值优化失败: {e}")
        raise HTTPException(status_code=500, detail=f"优化失败: {str(e)}")


@router.post(ROUTES.training.thresholds_reset)
@check_permission("filter.admin")
async def reset_threshold(
    filter_name: str,
    metric_name: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    重置指定过滤器的指定指标的阈值到默认值
    """
    try:
        from app.core.threshold_manager import threshold_manager
        
        logger.info(f"用户 {user.get('user_id')} 重置阈值: {filter_name}.{metric_name}")
        
        # 重置阈值
        threshold_manager.reset_threshold(filter_name, metric_name)
        
        # 获取新的阈值
        new_threshold = threshold_manager.get_threshold(filter_name, metric_name)
        
        return {
            "success": True,
            "message": f"阈值已重置",
            "filter_name": filter_name,
            "metric_name": metric_name,
            "new_threshold": new_threshold,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置阈值失败: {e}")
        raise HTTPException(status_code=500, detail=f"重置失败: {str(e)}")