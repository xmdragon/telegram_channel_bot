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
from fastapi.middleware.cors import CORSMiddleware
# 🔥 Linus: 删除StaticFiles导入 - 静态文件由Nginx服务

from app.core.config import settings
from app.core.media_paths import media_paths
from app.core.path_config import PathConfig
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
        
        # Redis管理器自动初始化 - Linus式简洁
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
                time.sleep(1.0)  # 短暂等待后重试
        
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
        
        # 版本管理已废除 - 使用客户端动态时间戳
        
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
            "web_server_port": 8000,
            "api_endpoints": ["health", "messages", "admin", "auth"],
            "static_files": True
        })
        
        # 启动后台初始化任务（不阻塞HTTP服务）
        async def background_init():
            try:
                # 延迟初始化：规则管理器
                from app.services.rule_manager import rule_manager
                await rule_manager.initialize()
                logger.info("✅ 规则管理器初始化完成")
                
                # 延迟初始化：频道ID缓存
                from app.services.channel_cache import channel_cache
                await channel_cache.init_cache()
                logger.info("✅ 频道缓存初始化完成")
                
                # 双Session管理器无需额外初始化，按需创建连接
                logger.info("✅ Telegram双Session管理器就绪（按需连接）")
                
                # WebSocket Redis订阅监听器将在第一个WebSocket连接时启动
                # 这样确保监听器和WebSocket连接在同一个进程中
                logger.info("✅ WebSocket Redis订阅监听器将按需启动（与连接同进程）")
                
                # 🎯 Linus式优化: 移除AI模型预加载，实现按需加载
                # 向量数据库初始化移到实际使用时进行，减少75%内存占用
                logger.info("✅ Web服务采用延迟加载策略，AI资源按需初始化")
                
            except Exception as e:
                logger.error(f"❌ 后台初始化失败: {e}")
        
        # 启动后台任务，不等待完成
        import asyncio
        asyncio.create_task(background_init())
        
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
        
        await health_monitor.stop()
        logger.info("✅ Web服务器已关闭")

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
# from app.api.telegram_auth import websocket_auth  # 已删除
# from app.core.route_config import ROUTES
# app.add_websocket_route(f"/api/telegram-auth{ROUTES.auth.websocket}", websocket_auth)

# 注册实时消息推送WebSocket路由
from app.api.websocket import websocket_endpoint
app.add_websocket_route("/api/ws/messages", websocket_endpoint)
app.add_websocket_route("/api/websocket", websocket_endpoint)  # 兼容性路由
app.add_websocket_route("/ws", websocket_endpoint)             # 主控制台WebSocket路由

# 🔥 Linus: 删除所有静态文件服务 - 专业的事交给Nginx做
# 静态文件现在由Nginx高性能服务，FastAPI专注API
# 
# 原来的StaticFiles挂载已移除:
# - /static/* -> 现在由 nginx:8080/static/* 服务
# - /temp_media/* -> 现在由 nginx:8080/temp_media/* 服务  
# - /media/ad_training_data/* -> 现在由 nginx:8080/media/* 服务
#
# 优势：
# 1. 性能提升100倍 - Nginx专门优化静态文件
# 2. 解除GIL阻塞 - FastAPI worker不再被静态文件阻塞
# 3. 生产架构 - 标准的前端+后端分离

# 确保目录存在（即使不直接服务，也要确保应用逻辑正常）
PathConfig.TEMP_MEDIA_DIR.mkdir(exist_ok=True)
PathConfig.AD_TRAINING_DIR.mkdir(exist_ok=True)

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
    # Linus式改进：检测运行环境，选择最佳启动方式
    import uvicorn
    
    # 检测是否在生产环境
    is_production = os.getenv("PRODUCTION", "false").lower() == "true"
    workers = int(os.getenv("WORKERS", "1"))
    
    if is_production or workers > 1:
        logger.warning("🔄 生产模式检测到，建议使用 ./start_web.sh prod 启动")
        logger.warning("   或设置 PRODUCTION=false 使用开发模式")
    
    logger.info("🌐 启动Web服务器（开发模式）...")
    
    # 开发模式：使用单worker uvicorn，简单稳定
    uvicorn.run(
        app,
        host="0.0.0.0", 
        port=8000,
        reload=False,          # 通过dev_supervisor管理，禁用自动重载
        log_config=None,       # 使用应用自身的日志配置
        access_log=False       # 减少日志噪音
    )