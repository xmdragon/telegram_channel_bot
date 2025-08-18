"""
API路由模块
"""
from fastapi import APIRouter
# 旧的messages.py已被重构拆分，不再需要导入
from .messages_crud import router as messages_crud_router
from .messages_batch import router as messages_batch_router
from .messages_filter import router as messages_filter_router
from .messages_stats import router as messages_stats_router
from .admin import router as admin_router
from .config import router as config_router
from .telegram_auth import router as auth_router
# 系统模块已重构为多个子模块
from .system_health import router as system_health_router
from .system_monitor import router as system_monitor_router
from .system_logs import router as system_logs_router
from .system_maintenance import router as system_maintenance_router
from .system_admin import router as system_admin_router
from .lock import router as lock_router
from .admin_auth import router as admin_auth_router
from .ai_control import router as ai_control_router
from .ai_config import router as ai_config_router
# 使用重构后的训练路由模块
from app.routers.training import router as training_router
# from app.api.channel_resolver import router as channel_resolver_router  # 暂时禁用，包含数据库依赖

api_router = APIRouter()

# 主要消息API路由（确保基础路径正确）
api_router.include_router(messages_crud_router, prefix="/messages", tags=["messages-crud"])
api_router.include_router(messages_batch_router, prefix="/messages", tags=["messages-batch"])  
api_router.include_router(messages_filter_router, prefix="/messages", tags=["messages-filter"])
api_router.include_router(messages_stats_router, prefix="/messages", tags=["messages-stats"])  # 修复：应在/messages下

# 保留原有消息路由作为备用
# 旧的messages_router已删除

# 其他API路由
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(config_router, prefix="/config", tags=["config"])
api_router.include_router(auth_router, prefix="/telegram-auth", tags=["telegram-auth"])  # Telegram用户认证（非管理员认证）
api_router.include_router(admin_auth_router, prefix="/admin/auth", tags=["admin-auth"])  # 管理员认证，使用不同路径
# 注册重构后的系统模块路由
api_router.include_router(system_health_router, prefix="/system", tags=["system-health"])
api_router.include_router(system_monitor_router, prefix="/system", tags=["system-monitor"])
api_router.include_router(system_logs_router, prefix="/system", tags=["system-logs"])
api_router.include_router(system_maintenance_router, prefix="/system", tags=["system-maintenance"])
api_router.include_router(system_admin_router, prefix="/system", tags=["system-admin"])
api_router.include_router(lock_router, prefix="/lock", tags=["lock"])
api_router.include_router(ai_control_router, prefix="/ai", tags=["ai-control"])
api_router.include_router(ai_config_router, tags=["ai-config"])
# 使用重构后的训练路由
api_router.include_router(training_router, prefix="/training-db", tags=["training"])
# api_router.include_router(channel_resolver_router, prefix="/channel-resolver", tags=["channel-resolver"])  # 暂时禁用