#!/usr/bin/env python3
"""
Telegram消息采集审核系统 - Web服务器
独立的FastAPI服务，不包含Telegram采集功能
"""
import warnings
# 抑制pkg_resources弃用警告
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import asyncio
import logging
import os
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
# 🔥 删除StaticFiles导入 - 静态文件由Nginx服务

from dotenv import load_dotenv

# 加载环境变量 - 必须在所有app模块导入之前
load_dotenv()

from app.core.config import settings
from app.core.media_paths import media_paths
from app.core.path_config import PathConfig
from app.core.route_config import ROUTES
from app.api import api_router

# 使用统一的日志配置
from app.core.logging_config import setup_logging, get_logger

# 初始化日志系统
setup_logging(service_name="web", log_level="INFO", console_output=True)
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Web服务生命周期管理 - 优化版本，提升启动速度"""
    import time
    
    # 检查是否已经初始化（避免重复调用）
    if hasattr(app.state, 'initialized') and app.state.initialized:
        logger.debug("Web服务器已初始化，跳过重复初始化")
        yield
        return
    
    start_time = time.time()
    logger.info("🚀 启动Web服务器...")
    
    # 启动健康监控
    from app.services.health_monitor import create_health_monitor
    health_monitor = create_health_monitor("web_server")
    await health_monitor.start()
    
    try:
        # 阶段1：基础存储层初始化（最重要，必须先完成）
        logger.info("📦 初始化存储层...")
        storage_start = time.time()
        
        # Redis管理器自动初始化 - 简洁
        from app.storage.redis_manager import redis_manager
        
        # 检查Redis连接（触发lazy初始化）
        if not redis_manager.is_healthy():
            await health_monitor.set_unhealthy("Redis连接不可用")
            raise RuntimeError("Redis连接失败")
        logger.info("✅ Redis管理器已就绪")
        
        # 初始化JSON存储层（带重试机制）
        from app.storage.json_store import init_json_stores, is_json_stores_initialized
        json_retries = 3
        json_success = False
        
        for attempt in range(json_retries):
            if init_json_stores():
                # 验证初始化是否真正成功
                if is_json_stores_initialized():
                    json_success = True
                    break
                else:
                    logger.warning(f"JSON存储层初始化状态异常，重试 ({attempt + 1}/{json_retries})")
            else:
                logger.warning(f"JSON存储层初始化失败，重试 ({attempt + 1}/{json_retries})")
            
            if attempt < json_retries - 1:
                await asyncio.sleep(1.0)  # 短暂等待后重试
        
        if not json_success:
            await health_monitor.set_unhealthy("JSON存储层初始化失败")
            raise RuntimeError("JSON存储初始化失败")
            
        # 验证配置管理器是否能正常工作
        logger.info("🔧 验证配置管理器...")
        from app.services.config_manager import config_manager
        
        # 使用新的ensure_ready方法进行配置管理器验证
        config_ready = await config_manager.ensure_ready()
        
        if not config_ready:
            # 如果ensure_ready失败，获取详细诊断信息
            try:
                diagnostics = await config_manager.get_storage_diagnostics()
                logger.error(f"配置管理器就绪失败，诊断信息: {diagnostics}")
                
                # 最后一次尝试：强制重载
                logger.info("最后一次尝试：强制重载配置...")
                if await config_manager.force_reload_with_retry(max_retries=3):
                    config_ready = await config_manager.ensure_ready()
                    if config_ready:
                        logger.info("✅ 强制重载后配置管理器已就绪")
                    else:
                        logger.error("强制重载后配置管理器仍未就绪")
                
            except Exception as e:
                logger.error(f"获取配置诊断信息失败: {e}")
        
        if not config_ready:
            await health_monitor.set_unhealthy("配置管理器验证失败")
            raise RuntimeError("配置管理器初始化或验证失败")
            
        # 获取最终状态信息
        try:
            final_diagnostics = await config_manager.get_storage_diagnostics()
            cache_size = final_diagnostics.get('cache_size', 0)
            state_sync = final_diagnostics.get('state_sync_ok', 'unknown')
            logger.info(f"✅ 配置管理器验证成功 (Redis配置: {cache_size}项, 状态同步: {state_sync})")
        except Exception as e:
            logger.warning(f"获取最终诊断信息失败: {e}")
            logger.info("✅ 配置管理器验证成功")
        
        # 加载配置到Redis缓存（Redis单一真相源架构）
        logger.info("📦 加载配置到Redis缓存...")
        config_load_success = await config_manager.load_all_to_redis()
        if not config_load_success:
            logger.warning("⚠️ 配置加载到Redis失败，但系统仍可正常运行（将回退到JSON文件）")
        
        storage_time = time.time() - storage_start
        logger.info(f"✅ 存储层初始化和验证完成 ({storage_time:.2f}s)")
        
        # 阶段2：配置和认证初始化（并行处理）
        config_start = time.time()
        
        # 初始化认证服务
        from app.services.auth_service import init_auth_service
        if not init_auth_service():
            await health_monitor.set_unhealthy("认证服务初始化失败")
            raise RuntimeError("认证服务初始化失败")
        logger.info("✅ 认证服务已初始化")
        
        config_time = time.time() - config_start
        logger.info(f"✅ 配置初始化完成 ({config_time:.2f}s)")
        
        # 阶段3：基础组件初始化（快速启动必需）
        misc_start = time.time()
        
        # 确保目录结构（快速）
        PathConfig.ensure_directories()
        
        # 基础配置加载（快速）
        from app.core.config import settings
        await settings.load_db_configs()
        
        misc_time = time.time() - misc_start
        logger.info(f"✅ 基础组件初始化完成 ({misc_time:.2f}s)")
        
        # 设置健康状态（提早设置，让健康检查通过）
        await health_monitor.set_healthy({
            "web_server_port": settings.WEB_PORT,
            "api_endpoints": ["health", "messages", "admin", "auth"],
            "static_files": True
        })
        
        # 启动后台初始化任务（不阻塞HTTP服务）
        async def background_init():
            try:
                # 频道缓存功能已移除，直接使用配置管理器
                logger.info("✅ 配置管理器已就绪")
                
                # 双Session管理器无需额外初始化，按需创建连接
                logger.info("✅ Telegram双Session管理器就绪（按需连接）")
                
                # WebSocket Redis订阅监听器将在第一个WebSocket连接时启动
                # 这样确保监听器和WebSocket连接在同一个进程中
                logger.info("✅ WebSocket Redis订阅监听器将按需启动（与连接同进程）")
                
                # 🎯 优化: 采用延迟加载策略，按需初始化资源
                # 规则引擎初始化移到实际使用时进行，减少内存占用
                logger.info("✅ Web服务采用延迟加载策略，资源按需初始化")
                
            except Exception as e:
                logger.error(f"❌ 后台初始化失败: {e}")
        
        # 启动后台任务，不等待完成（保存引用防止GC）
        app.state.background_init_task = asyncio.create_task(background_init())
        
        # 标记已初始化
        app.state.initialized = True
        
        total_time = time.time() - start_time
        logger.info(f"🎉 Web服务器启动完成！总耗时: {total_time:.2f}s")
        
        yield
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"❌ 启动失败 ({total_time:.2f}s): {str(e)}")
        await health_monitor.set_unhealthy(f"启动失败: {str(e)}")
        raise
    finally:
        # 关闭时清理
        logger.info("🛑 正在关闭Web服务器...")

        # WebSocket Redis订阅监听器会在连接关闭时自动停止
        logger.info("✅ WebSocket Redis订阅监听器将自动清理")

        # 关闭Redis连接
        try:
            from app.storage.redis_manager import redis_manager
            redis_manager.client.close()
            logger.info("✅ Redis连接已关闭")
        except Exception as e:
            logger.warning(f"关闭Redis连接失败: {e}")

        await health_monitor.stop()
        logger.info("✅ Web服务器已关闭")

# 创建FastAPI应用
app = FastAPI(
    title="Telegram消息采集审核系统 - Web服务",
    description="Web界面和API服务，不包含Telegram采集功能",
    version="1.0.0",
    lifespan=lifespan
)

# 配置CORS - 限制允许的来源
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:8080,http://localhost:8008").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(api_router, prefix=ROUTES.web_server.api_prefix)

# 注册实时消息推送WebSocket路由
from app.api.websocket import websocket_endpoint
app.add_websocket_route(ROUTES.websocket_routes.api_messages, websocket_endpoint)
app.add_websocket_route(ROUTES.websocket_routes.api_websocket, websocket_endpoint)  # 兼容性路由
app.add_websocket_route(ROUTES.websocket_routes.main, websocket_endpoint)             # 主控制台WebSocket路由

# 🔥 删除所有静态文件服务 - 专业的事交给Nginx做
# 静态文件现在由Nginx高性能服务，FastAPI专注API
# 
# 静态文件与媒体服务（回退模式）
# 说明：生产建议由 Nginx 提供静态与媒体服务；为兼容本地/非Docker环境，这里提供可开关的回退挂载。
SERVE_STATIC_FALLBACK = os.getenv("SERVE_STATIC_FALLBACK", "true").lower() == "true"
if SERVE_STATIC_FALLBACK:
    # 挂载 /static 与 /temp_media 以及训练媒体，便于本地直接预览
    PathConfig.TEMP_MEDIA_DIR.mkdir(exist_ok=True)
    PathConfig.TRAINING_DIR.mkdir(exist_ok=True)
    app.mount(ROUTES.web_server.static_mount, StaticFiles(directory="static"), name="static")
    app.mount(ROUTES.web_server.temp_media_mount, StaticFiles(directory=str(PathConfig.TEMP_MEDIA_DIR)), name="temp_media")
    logger.info("🧩 已启用本地静态与媒体回退服务（SERVE_STATIC_FALLBACK=true）")
else:
    logger.info("🚀 生产模式：静态与媒体由外部服务器提供（SERVE_STATIC_FALLBACK=false）")

# 添加根路径重定向
@app.get(ROUTES.web.root)
async def root():
    """根路径重定向到主界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.INDEX_PAGE)

@app.get(ROUTES.web.admin)
async def admin():
    """管理界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.ADMIN_PAGE)

@app.get(ROUTES.web.config)
async def config():
    """配置管理界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.CONFIG_PAGE)

@app.get(ROUTES.web.auth)
async def auth():
    """Telegram 登录界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.AUTH_PAGE)

@app.get(ROUTES.web.status)
async def status():
    """系统状态检查界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.STATUS_PAGE)

@app.get(ROUTES.web.train)
async def train():
    """规则管理界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=media_paths.TRAIN_PAGE)

if __name__ == "__main__":
    # 改进：检测运行环境，选择最佳启动方式
    import uvicorn
    
    # 检测是否在生产环境
    is_production = os.getenv("PRODUCTION", "false").lower() == "true"
    workers = int(os.getenv("WORKERS", "1"))
    
    if is_production or workers > 1:
        logger.warning("🔄 生产模式检测到，建议使用 ./start_web.sh prod 启动")
        logger.warning("   或设置 PRODUCTION=false 使用开发模式")
    
    logger.info("🌐 Web服务器启动 - PID:%d, 端口:%d", os.getpid(), settings.WEB_PORT)
    
    # 开发模式：使用单worker uvicorn，简单稳定
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.WEB_PORT,
        reload=False,          # 通过dev_supervisor管理，禁用自动重载
        log_config=None,       # 使用应用自身的日志配置
        access_log=False,      # 减少日志噪音
        # 连接管理参数，防止CLOSE-WAIT堆积
        timeout_keep_alive=5,        # keep-alive 超时 5 秒
        limit_concurrency=100,       # 限制并发连接数
        timeout_graceful_shutdown=10 # 优雅关闭超时
    )
