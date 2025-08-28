"""
API路由模块
"""
from fastapi import APIRouter
# 旧的messages.py已被重构拆分，不再需要导入
from .messages_crud import router as messages_crud_router
from .messages_batch import router as messages_batch_router
from .messages_filter import router as messages_filter_router
from .messages_stats import router as messages_stats_router
from .linus_stats_api import router as linus_stats_router
from .admin import router as admin_router
from .config import router as config_router
from .telegram_auth import router as auth_router
from .telegram_dual_auth import router as dual_auth_router
# 系统模块已重构为多个子模块
from .system_health import router as system_health_router
from .system_monitor import router as system_monitor_router
from .system_logs import router as system_logs_router
from .system_maintenance import router as system_maintenance_router
from .system_admin import router as system_admin_router
from .system_lock import router as system_lock_router
from .admin_auth import router as admin_auth_router
from .ai_control import router as ai_control_router
from .ai_config import router as ai_config_router
from .version import router as version_router
# 使用重构后的训练路由模块
from app.routers.training import router as training_router
# from app.api.channel_resolver import router as channel_resolver_router  # 暂时禁用，包含数据库依赖

api_router = APIRouter()

# 主要消息API路由（确保基础路径正确）
api_router.include_router(messages_crud_router, tags=["messages-crud"])
api_router.include_router(messages_batch_router, tags=["messages-batch"])  
api_router.include_router(messages_filter_router, tags=["messages-filter"])
api_router.include_router(messages_stats_router, tags=["messages-stats"])
api_router.include_router(linus_stats_router, tags=["linus-stats"])

# 保留原有消息路由作为备用
# 旧的messages_router已删除

# 其他API路由
api_router.include_router(admin_router, tags=["admin"])
api_router.include_router(config_router, tags=["config"])
api_router.include_router(auth_router, tags=["telegram-auth"])  # Telegram用户认证（非管理员认证）
api_router.include_router(dual_auth_router, prefix="/dual-auth", tags=["telegram-dual-auth"])  # 双Session认证
api_router.include_router(admin_auth_router, tags=["admin-auth"])  # 管理员认证，使用不同路径
# 注册重构后的系统模块路由
api_router.include_router(system_health_router, tags=["system-health"])
api_router.include_router(system_monitor_router, tags=["system-monitor"])
api_router.include_router(system_logs_router, tags=["system-logs"])
api_router.include_router(system_maintenance_router, tags=["system-maintenance"])
api_router.include_router(system_admin_router, tags=["system-admin"])
api_router.include_router(system_lock_router, tags=["system-lock"])
api_router.include_router(ai_control_router, tags=["ai-control"])
api_router.include_router(ai_config_router, tags=["ai-config"])
api_router.include_router(version_router, tags=["version"])
# 使用重构后的训练路由
api_router.include_router(training_router, tags=["training"])
# api_router.include_router(channel_resolver_router, prefix="/channel-resolver", tags=["channel-resolver"])  # 暂时禁用