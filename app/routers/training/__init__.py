"""
训练数据管理路由模块 - 统一路由注册和导出
"""
from fastapi import APIRouter

# 导入所有子模块的路由
from .basic import router as basic_router
from .tail_filter import router as tail_filter_router
from .media import router as media_router
from .ad_samples import router as ad_samples_router
from .ocr import router as ocr_router
from .admin import router as admin_router
from .thresholds import router as thresholds_router
from .promo_training import router as promo_training_router

# 创建主路由器（不设置prefix，由主API路由器设置）
router = APIRouter(tags=["training"])

# 注册所有子路由
def register_training_routes():
    """注册所有训练数据管理路由"""
    
    # 基础训练数据管理
    router.include_router(basic_router, tags=["training-basic"])
    
    # 尾部过滤管理
    router.include_router(tail_filter_router, tags=["training-tail-filter"])
    
    # 媒体文件管理
    router.include_router(media_router, tags=["training-media"])
    
    # 广告样本管理
    router.include_router(ad_samples_router, tags=["training-ad-samples"])
    
    # OCR样本管理
    router.include_router(ocr_router, tags=["training-ocr"])
    
    # 系统管理
    router.include_router(admin_router, tags=["training-admin"])
    
    # 阈值管理
    router.include_router(thresholds_router, tags=["training-thresholds"])
    
    # 推广链接训练
    router.include_router(promo_training_router, tags=["training-promo"])

# 执行路由注册
register_training_routes()

# 导出主路由器
__all__ = ["router"]