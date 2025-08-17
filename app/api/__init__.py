"""
API路由模块
"""
from fastapi import APIRouter
from .messages import router as messages_router
from .messages_crud import router as messages_crud_router
from .messages_batch import router as messages_batch_router
from .messages_filter import router as messages_filter_router
from .messages_stats import router as messages_stats_router
from .admin import router as admin_router
from .config import router as config_router
from .auth import router as auth_router
from .system import router as system_router
from .lock import router as lock_router
from .admin_auth import router as admin_auth_router
from app.routers.training_db import router as training_router  # 使用修复后的基于JSON的训练路由
# from app.api.channel_resolver import router as channel_resolver_router  # 暂时禁用，包含数据库依赖

api_router = APIRouter()

# 新的模块化消息API路由
api_router.include_router(messages_crud_router, prefix="/messages", tags=["messages-crud"])
api_router.include_router(messages_batch_router, prefix="/messages", tags=["messages-batch"])  
api_router.include_router(messages_filter_router, prefix="/messages", tags=["messages-filter"])
api_router.include_router(messages_stats_router, prefix="/stats", tags=["messages-stats"])

# 保留原有消息路由（逐步迁移）
api_router.include_router(messages_router, prefix="/messages/legacy", tags=["messages-legacy"])

# 其他API路由
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(config_router, prefix="/config", tags=["config"])
api_router.include_router(auth_router, prefix="/auth", tags=["telegram-auth"])  # Telegram认证
api_router.include_router(admin_auth_router, prefix="/admin/auth", tags=["admin-auth"])  # 管理员认证，使用不同路径
api_router.include_router(system_router, tags=["system"])
api_router.include_router(lock_router, prefix="/lock", tags=["lock"])
api_router.include_router(training_router, prefix="/training-db", tags=["training"])  # 修复后重新启用
# api_router.include_router(channel_resolver_router, prefix="/channel-resolver", tags=["channel-resolver"])  # 暂时禁用