"""
API路由模块
"""
from fastapi import APIRouter
from .messages import router as messages_router
from .admin import router as admin_router
from .config import router as config_router
from .auth import router as auth_router

api_router = APIRouter()

api_router.include_router(messages_router, prefix="/messages", tags=["messages"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(config_router, prefix="/config", tags=["config"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])