#!/usr/bin/env python3
"""
Telegram消息采集审核系统主入口
"""
import warnings
import os

# PyTorch相关警告抑制（环境变量统一在启动脚本中设置）
warnings.filterwarnings("ignore", category=UserWarning, module="torch.utils.data.dataloader")
warnings.filterwarnings("ignore", message=".*pin_memory.*not supported on MPS.*")

# 抑制pkg_resources弃用警告
warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.media_paths import media_paths
from app.core.url_config import url_config
from app.api import api_router
from app.telegram.bot import TelegramBot
from app.services.scheduler import MessageScheduler
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 使用统一的日志配置
from app.core.logging_config import setup_logging, get_logger

# 初始化日志系统
setup_logging(service_name="main", log_level="INFO", console_output=True)
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("正在启动Telegram消息采集审核系统...")
    
    # Redis管理器自动处理连接管理 - Linus式简洁
    from app.storage.redis_manager import redis_manager
    if not redis_manager.is_healthy():
        logger.error("Redis连接不可用")
        raise RuntimeError("Redis连接失败")
    logger.info("Redis管理器已就绪")
    
    # 初始化JSON存储层
    from app.storage.json_store import init_json_stores
    if not init_json_stores():
        logger.error("JSON存储层初始化失败")
        raise RuntimeError("初始化失败")
    
    # 初始化认证服务
    from app.services.auth_service import init_auth_service
    if not init_auth_service():
        logger.error("认证服务初始化失败")
        raise RuntimeError("初始化失败")
    logger.info("认证服务已初始化")
    
    # 初始化频道ID缓存
    from app.services.channel_cache import channel_cache
    await channel_cache.init_cache()
    logger.debug("频道ID缓存检查完成")
    
    # 初始化训练数据目录和配置
    PathConfig.ensure_directories()
    logger.info("训练数据目录已初始化")
    
    # 加载数据库配置
    from app.core.config import settings
    await settings.load_db_configs()
    
    # 检查Telegram双Session认证状态
    from app.telegram.dual_session_manager import dual_session_manager
    connection_status = await dual_session_manager.get_connection_status()
    
    # 至少有一个Session连接即可启动完整功能
    auth_status = {
        'authorized': (connection_status.get('listener_connected', False) or 
                      connection_status.get('sender_connected', False))
    }
    
    # 初始化全局变量
    from app.telegram import bot as bot_module
    bot_module.telegram_bot = None
    bot_module.message_scheduler = None
    
    if not auth_status.get('authorized', False):
        logger.error("❌ Telegram未认证，系统无法启动完整功能")
        logger.error(f"请访问 {url_config.get_auth_url()} 完成Telegram登录")
        logger.error("获取API凭据请访问: https://my.telegram.org")
        # 不直接退出，允许用户通过Web界面进行认证
        logger.warning("系统将在有限功能模式下运行，等待用户完成认证...")
    else:
        # Telegram已认证，正常启动
        logger.info("✅ Telegram认证状态正常，启动消息监听...")
        
        # 启动Telegram客户端
        bot = TelegramBot()
        await bot.start()
        
        # 设置全局bot实例供其他模块使用
        bot_module.telegram_bot = bot
        
        # 启动消息调度器
        scheduler = MessageScheduler()
        scheduler.start()
        bot_module.message_scheduler = scheduler
        
        # 启动系统监控
        from app.services.system_monitor import system_monitor
        await system_monitor.start()
    
    logger.info("系统启动完成")
    
    yield
    
    # 关闭时清理
    logger.info("正在关闭系统...")
    
    # 只有在已认证并启动的情况下才清理
    from app.telegram import bot as bot_module
    if bot_module.telegram_bot:
        await bot_module.telegram_bot.stop()
        
        # 停止系统监控
        from app.services.system_monitor import system_monitor
        await system_monitor.stop()
        
    if bot_module.message_scheduler:
        bot_module.message_scheduler.shutdown()

# 创建FastAPI应用
app = FastAPI(
    title="Telegram消息采集审核系统",
    description="从多个Telegram频道采集消息并进行审核管理",
    version="1.0.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(api_router, prefix="/api")

# 直接注册WebSocket路由（避免prefix问题）
# from app.api.telegram_auth import websocket_auth  # 已删除
# from app.core.route_config import ROUTES
# app.add_websocket_route(f"/api/telegram-auth{ROUTES.auth.websocket}", websocket_auth)

# 注册实时消息推送WebSocket路由
from app.api.websocket import websocket_endpoint
app.add_websocket_route("/api/ws/messages", websocket_endpoint)
app.add_websocket_route("/api/websocket", websocket_endpoint)  # 兼容性路由

# 静态文件服务
app.mount("/static", StaticFiles(directory="static"), name="static")

# 临时媒体文件服务
from app.core.path_config import PathConfig
PathConfig.TEMP_MEDIA_DIR.mkdir(exist_ok=True)
app.mount("/temp_media", StaticFiles(directory=str(PathConfig.TEMP_MEDIA_DIR)), name="temp_media")

# 挂载训练数据媒体文件
PathConfig.AD_TRAINING_DIR.mkdir(exist_ok=True)
app.mount("/media/ad_training_data", StaticFiles(directory=str(PathConfig.AD_TRAINING_DIR)), name="training_media")

# 添加根路径重定向
@app.get("/")
async def root():
    """根路径重定向到主界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.INDEX_PAGE)

@app.get("/admin")
async def admin():
    """管理界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.ADMIN_PAGE)

@app.get("/config")
async def config():
    """配置管理界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.CONFIG_PAGE)

@app.get("/auth")
async def auth():
    """Telegram 登录界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.AUTH_PAGE)

@app.get("/status")
async def status():
    """系统状态检查界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.STATUS_PAGE)


@app.get("/train")
async def train():
    """AI训练界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.TRAIN_PAGE)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.WEB_PORT,
        reload=False
    )
