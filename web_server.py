#!/usr/bin/env python3
"""
Telegram消息采集审核系统 - Web服务器
独立的FastAPI服务，不包含Telegram采集功能
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
from app.api import api_router

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

# 在日志初始化前导入PathConfig
from app.core.path_config import PathConfig

file_handler = FilteredTimedRotatingFileHandler(
    filename=str(PathConfig.APP_LOG_FILE),
    when='H',  # 按小时轮转
    interval=1,  # 每1小时
    backupCount=24*7,  # 保留7天的日志
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# 创建错误级别的文件处理器
error_handler = FilteredTimedRotatingFileHandler(
    filename=str(PathConfig.ERROR_LOG_FILE),
    when='H',
    interval=1,
    backupCount=24*7,
    encoding='utf-8'
)
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# 配置根日志记录器
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(error_handler)

# 控制台输出（开发环境）
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
))
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Web服务生命周期管理 - 仅包含基础初始化"""
    logger.info("🌐 启动Web服务器...")
    
    # 启动健康监控
    from app.services.health_monitor import create_health_monitor
    health_monitor = create_health_monitor("web_server")
    await health_monitor.start()
    
    try:
        # 基础系统初始化
        logger.info("初始化存储层和认证服务...")
        
        # 初始化Redis存储层
        from app.storage.redis_store import init_redis_stores
        if not init_redis_stores():
            await health_monitor.set_unhealthy("Redis存储层初始化失败")
            raise RuntimeError("初始化失败")
        logger.info("Redis连接已初始化")
        
        # 初始化JSON存储层
        from app.storage.json_store import init_json_stores
        if not init_json_stores():
            await health_monitor.set_unhealthy("JSON存储层初始化失败")
            raise RuntimeError("初始化失败")
        
        # 初始化默认配置
        from app.services.config_manager import init_default_configs
        await init_default_configs()
        
        # 初始化认证服务
        from app.services.auth_service import init_auth_service
        if not init_auth_service():
            await health_monitor.set_unhealthy("认证服务初始化失败")
            raise RuntimeError("初始化失败")
        logger.info("认证服务已初始化")
        
        # 初始化频道ID缓存
        from app.services.channel_cache import channel_cache
        await channel_cache.init_cache()
        logger.info("频道ID缓存已初始化")
        
        # 初始化训练数据目录和配置
        PathConfig.ensure_directories()
        logger.info("训练数据目录已初始化")
        
        # 加载数据库配置
        from app.core.config import settings
        await settings.load_db_configs()
        
        # 初始化认证服务
        from app.telegram.auth import auth_manager
        await auth_manager.initialize()
        logger.info("认证服务已初始化")
        
        # 设置健康状态
        await health_monitor.set_healthy({
            "web_server_port": 8000,
            "api_endpoints": ["health", "messages", "admin", "auth"],
            "static_files": True
        })
        
        logger.info("✅ Web服务器启动完成")
        
        yield
        
    except Exception as e:
        await health_monitor.set_unhealthy(f"启动失败: {str(e)}")
        raise
    finally:
        # 关闭时清理
        logger.info("🌐 正在关闭Web服务器...")
        await health_monitor.stop()
        logger.info("Web服务器已关闭")

# 创建FastAPI应用
app = FastAPI(
    title="Telegram消息采集审核系统 - Web服务",
    description="Web界面和API服务，不包含Telegram采集功能",
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

# 健康检查API端点
@app.get("/api/health")
async def health_check():
    """获取系统健康状态"""
    from app.services.health_monitor import HealthCheckService
    return await HealthCheckService.get_system_summary()

@app.get("/api/health/{service_name}")
async def service_health_check(service_name: str):
    """获取指定服务的健康状态"""
    from app.services.health_monitor import HealthCheckService
    health = await HealthCheckService.get_service_health(service_name)
    if health:
        return health.to_dict()
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="服务未找到")

if __name__ == "__main__":
    import uvicorn
    logger.info("🌐 启动独立Web服务器...")
    uvicorn.run(
        "web_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # 开发模式支持热重载
    )