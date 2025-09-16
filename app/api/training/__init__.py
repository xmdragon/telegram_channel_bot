"""
训练数据管理路由模块 - 统一路由注册和导出
"""
from fastapi import APIRouter

# 导入所有子模块的路由
from .basic import router as basic_router
from .tail_filter import router as tail_filter_router
# 注意：ad_vector模块已移除
# OCR功能已移除
from .keyword_management import router as keyword_router
from .separator_test import router as separator_test_router

# 创建主路由器（不设置prefix，由主API路由器设置）
router = APIRouter(tags=["training"])

# 注册所有子路由
def register_training_routes():
    """注册所有训练数据管理路由"""
    
    # 基础训练数据管理
    router.include_router(basic_router, tags=["training-basic"])
    
    # 尾部过滤管理
    router.include_router(tail_filter_router, tags=["training-tail-filter"])
    
    # 注意：广告向量管理已移除


    # 关键词管理
    router.include_router(keyword_router, tags=["training-keywords"])

    # 分隔符测试
    router.include_router(separator_test_router, tags=["training-separator-test"])

# 执行路由注册
register_training_routes()

# 导出主路由器
__all__ = ["router"]