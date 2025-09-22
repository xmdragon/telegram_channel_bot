"""
API路由模块
"""
from fastapi import APIRouter
from .messages_crud import router as messages_crud_router
from .messages_batch import router as messages_batch_router
from .messages_filter import router as messages_filter_router
from .messages_stats import router as messages_stats_router
from .admin import router as admin_router
from .channels import router as channels_router
from .telegram_dual_auth import router as dual_auth_router
from .system_health import router as system_health_router
from .system_maintenance import router as system_maintenance_router
from .admin_auth import router as admin_auth_router
from .training import router as training_router
from .telegram_tools import router as telegram_tools_router

api_router = APIRouter()

# 主要消息API路由（确保基础路径正确）
api_router.include_router(messages_crud_router, tags=["messages-crud"])
api_router.include_router(messages_batch_router, tags=["messages-batch"])
api_router.include_router(messages_filter_router, tags=["messages-filter"])
api_router.include_router(messages_stats_router, tags=["messages-stats"])

# 其他API路由
api_router.include_router(admin_router, tags=["admin"])
api_router.include_router(channels_router, prefix="/channels", tags=["channels"])  # 统一的频道管理
api_router.include_router(dual_auth_router, prefix="/dual-auth", tags=["telegram-dual-auth"])  # 双Session认证
api_router.include_router(admin_auth_router, tags=["admin-auth"])  # 管理员认证，使用不同路径
# 注册重构后的系统模块路由
api_router.include_router(system_health_router, tags=["system-health"])
api_router.include_router(system_maintenance_router, tags=["system-maintenance"])
# 使用重构后的训练路由
api_router.include_router(training_router, tags=["training"])
# Telegram工具路由
api_router.include_router(telegram_tools_router, tags=["telegram-tools"])

# 服务管理路由（Supervisor集成）
from .services import router as services_router
api_router.include_router(services_router, tags=["services"])