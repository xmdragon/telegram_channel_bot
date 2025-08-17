"""
系统API模块入口点
整合所有系统相关的API路由模块
"""
from fastapi import APIRouter
from app.api.system_health import router as health_router
from app.api.system_monitor import router as monitor_router
from app.api.system_logs import router as logs_router
from app.api.system_maintenance import router as maintenance_router
from app.api.system_admin import router as admin_router

# 创建主系统路由器
system_router = APIRouter()

# 包含所有子模块的路由
system_router.include_router(health_router)
system_router.include_router(monitor_router)
system_router.include_router(logs_router)
system_router.include_router(maintenance_router)
system_router.include_router(admin_router)

# 为了向后兼容，也导出为 router
router = system_router