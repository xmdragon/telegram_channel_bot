#!/usr/bin/env python3
"""
Telegram消息采集审核系统主入口
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.api import api_router
from app.telegram.bot import TelegramClient
from app.services.scheduler import MessageScheduler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("正在启动Telegram消息采集审核系统...")
    
    # 初始化数据库
    await init_db()
    
    # 初始化默认配置
    from app.services.config_manager import init_default_configs
    await init_default_configs()
    
    # 加载数据库配置
    from app.core.config import settings
    await settings.load_db_configs()
    
    # 启动Telegram客户端
    bot = TelegramClient()
    await bot.start()
    
    # 启动消息调度器
    scheduler = MessageScheduler()
    scheduler.start()
    
    logger.info("系统启动完成")
    
    yield
    
    # 关闭时清理
    logger.info("正在关闭系统...")
    await bot.stop()
    scheduler.shutdown()

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
from app.api.auth import websocket_auth
app.add_websocket_route("/api/auth/ws/auth", websocket_auth)

# 静态文件服务
app.mount("/static", StaticFiles(directory="static"), name="static")

# 添加根路径重定向
@app.get("/")
async def root():
    """根路径重定向到主界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")

@app.get("/admin")
async def admin():
    """管理界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/admin.html")

@app.get("/config")
async def config():
    """配置管理界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/config.html")

@app.get("/auth")
async def auth():
    """Telegram 登录界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/auth.html")

@app.get("/status")
async def status():
    """系统状态检查界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/status.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )