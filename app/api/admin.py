"""
管理员API - 路由聚合模块
将分散的管理员相关API聚合在一起
"""
from fastapi import APIRouter

# 导入拆分后的子模块
from .admin_config import router as config_router

router = APIRouter()

# 聚合所有管理员相关路由
router.include_router(config_router, tags=["admin-config"])