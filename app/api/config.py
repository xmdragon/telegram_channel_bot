"""
配置管理API - 路由聚合模块
将分散的配置相关API聚合在一起
"""
from fastapi import APIRouter

# 导入拆分后的子模块
# from .config_basic import router as basic_router  # 已删除 - 功能集成到双Session认证系统
from .config_channels import router as channels_router  
# from .config_batch import router as batch_router  # 已删除 - 功能集成到双Session认证系统

router = APIRouter()

# 聚合所有配置相关路由
# router.include_router(basic_router, tags=["config-basic"])  # 已删除 - 功能集成到双Session认证系统
router.include_router(channels_router, tags=["config-channels"])
# router.include_router(batch_router, tags=["config-batch"])  # 已删除 - 功能集成到双Session认证系统

# 所有功能已拆分到子模块，这些内容被移除以避免代码重复


