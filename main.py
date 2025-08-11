#!/usr/bin/env python3
"""
Telegram消息采集审核系统主入口
"""
import warnings
# 抑制pkg_resources弃用警告
warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import asyncio
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.api import api_router
from app.telegram.bot import TelegramBot
from app.services.scheduler import MessageScheduler

# 确保日志目录存在
os.makedirs('./logs', exist_ok=True)

from logging.handlers import TimedRotatingFileHandler

# 创建自定义的文件处理器，过滤数据库日志
class FilteredTimedRotatingFileHandler(TimedRotatingFileHandler):
    """过滤特定模块的按时间轮转文件处理器"""
    def emit(self, record):
        # 过滤掉数据库相关的日志
        if record.name.startswith(('sqlalchemy', 'asyncpg', 'databases')):
            return
        # 过滤掉包含特定关键词的日志
        if any(keyword in record.getMessage().lower() for keyword in ['sql', 'database', 'query', 'insert', 'update', 'delete', 'select']):
            return
        super().emit(record)

# 创建按小时轮转的日志处理器
file_handler = FilteredTimedRotatingFileHandler(
    filename='./logs/app.log',
    when='H',  # 按小时轮转
    interval=1,  # 每1小时
    backupCount=24*7,  # 保留7天的日志
    encoding='utf-8'
)
file_handler.suffix = "%Y%m%d_%H"  # 文件名后缀格式

# 创建错误日志处理器（只记录WARNING及以上级别）
error_handler = TimedRotatingFileHandler(
    filename='./logs/error.log',
    when='D',  # 按天轮转
    interval=1,  # 每1天
    backupCount=30,  # 保留30天的日志
    encoding='utf-8'
)
error_handler.suffix = "%Y%m%d"
error_handler.setLevel(logging.WARNING)  # 只记录WARNING及以上级别
error_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n'
    '%(pathname)s:%(lineno)d\n'  # 添加文件路径和行号
)
error_handler.setFormatter(error_formatter)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
        file_handler,  # 按时间轮转输出到文件
        error_handler  # 错误日志单独记录
    ]
)
logger = logging.getLogger(__name__)

# 减少不必要的日志输出
logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)  # 只显示错误级别的SQL日志
logging.getLogger('sqlalchemy.pool').setLevel(logging.ERROR)    # 关闭连接池日志
logging.getLogger('sqlalchemy.orm').setLevel(logging.ERROR)     # 关闭ORM日志
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)   # 减少访问日志
logging.getLogger('httpx').setLevel(logging.WARNING)            # 减少HTTP客户端日志
logging.getLogger('telethon').setLevel(logging.WARNING)         # 减少Telethon日志

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
    
    # 检查Telegram认证状态
    from app.telegram.auth import auth_manager
    auth_status = await auth_manager.get_auth_status()
    
    # 初始化全局变量
    from app.telegram import bot as bot_module
    bot_module.telegram_bot = None
    bot_module.message_scheduler = None
    
    if not auth_status.get('authorized', False):
        logger.error("❌ Telegram未认证，系统无法启动完整功能")
        logger.error("请访问 http://localhost:8000/auth.html 完成Telegram登录")
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
from app.api.auth import websocket_auth
app.add_websocket_route("/api/auth/ws/auth", websocket_auth)

# 注册实时消息推送WebSocket路由
from app.api.websocket import websocket_endpoint
app.add_websocket_route("/api/ws/messages", websocket_endpoint)
app.add_websocket_route("/api/websocket", websocket_endpoint)  # 兼容性路由

# 静态文件服务
app.mount("/static", StaticFiles(directory="static"), name="static")

# 临时媒体文件服务
import os
temp_media_dir = "./temp_media"
if not os.path.exists(temp_media_dir):
    os.makedirs(temp_media_dir)
app.mount("/temp_media", StaticFiles(directory=temp_media_dir), name="temp_media")

# 挂载训练数据媒体文件
training_media_dir = Path("data/ad_training_data")
training_media_dir.mkdir(exist_ok=True)
app.mount("/media/ad_training_data", StaticFiles(directory=str(training_media_dir)), name="training_media")

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


@app.get("/train")
async def train():
    """AI训练界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/train.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )
