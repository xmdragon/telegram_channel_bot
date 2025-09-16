"""
配置管理API - 路由聚合模块
将分散的配置相关API聚合在一起
"""
from fastapi import APIRouter

# 原本用于聚合配置相关路由，现在channels功能已统一到独立的channels.py
# 其他配置功能已集成到双Session认证系统

router = APIRouter()

# 配置路由现在为空，主要功能已迁移：
# - 频道管理 → /api/channels/ (channels.py)
# - 基础配置 → 双Session认证系统
# - 批量操作 → 双Session认证系统


