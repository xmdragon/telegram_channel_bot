"""
API路由模块
"""
from fastapi import APIRouter
from .messages import router as messages_router
from .admin import router as admin_router
from .config import router as config_router
from .auth import router as auth_router
from .system import router as system_router
from .lock import router as lock_router
from .admin_auth import router as admin_auth_router
from app.routers.training import router as training_router
from app.api.channel_resolver import router as channel_resolver_router

api_router = APIRouter()

api_router.include_router(messages_router, prefix="/messages", tags=["messages"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(config_router, prefix="/config", tags=["config"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(admin_auth_router, prefix="/auth", tags=["admin-auth"])  # 修改为/auth前缀
api_router.include_router(system_router, tags=["system"])
api_router.include_router(lock_router, prefix="/lock", tags=["lock"])
api_router.include_router(training_router, prefix="/training", tags=["training"])
api_router.include_router(channel_resolver_router, prefix="/channel-resolver", tags=["channel-resolver"])