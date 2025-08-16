#!/usr/bin/env python3
"""
Telegram消息采集审核系统 - Telegram采集服务
独立的Telegram消息采集服务，不包含Web服务器
"""
import warnings
# 抑制pkg_resources弃用警告
warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from app.core.config import settings
from app.telegram.bot import TelegramBot

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
    filename=str(PathConfig.LOGS_DIR / "telegram_collector.log"),
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

class TelegramCollectorService:
    """Telegram采集服务"""
    
    def __init__(self):
        self.telegram_bot = None
        self.is_running = False
        self.health_monitor = None
        
    async def initialize(self):
        """初始化采集服务"""
        logger.info("📡 启动Telegram采集服务...")
        
        # 启动健康监控
        from app.services.health_monitor import create_health_monitor
        self.health_monitor = create_health_monitor("telegram_collector")
        await self.health_monitor.start()
        
        try:
            # 基础系统初始化
            logger.info("初始化存储层和认证服务...")
            
            # 初始化Redis存储层
            from app.storage.redis_store import init_redis_stores
            if not init_redis_stores():
                await self.health_monitor.set_unhealthy("Redis存储层初始化失败")
                raise RuntimeError("初始化失败")
            logger.info("Redis连接已初始化")
            
            # 初始化JSON存储层
            from app.storage.json_store import init_json_stores
            if not init_json_stores():
                await self.health_monitor.set_unhealthy("JSON存储层初始化失败")
                raise RuntimeError("初始化失败")
            
            # 初始化默认配置
            from app.services.config_manager import init_default_configs
            await init_default_configs()
            
            # 初始化认证服务
            from app.services.auth_service import init_auth_service
            if not init_auth_service():
                await self.health_monitor.set_unhealthy("认证服务初始化失败")
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
            await settings.load_db_configs()
            
            # 初始化认证服务
            from app.telegram.auth import auth_manager
            await auth_manager.initialize()
            logger.info("认证服务已初始化")
            
            # 检查Telegram认证状态
            auth_status = await auth_manager.get_auth_status()
            
            # 初始化全局变量
            from app.telegram import bot as bot_module
            bot_module.telegram_bot = None
            
            if not auth_status.get('authorized', False):
                await self.health_monitor.set_unhealthy("Telegram未认证", {
                    "auth_status": "unauthorized",
                    "auth_url": "http://localhost:8000/auth.html"
                })
                logger.error("❌ Telegram未认证，采集服务无法启动")
                logger.error("请访问 http://localhost:8000/auth.html 完成Telegram登录")
                logger.error("获取API凭据请访问: https://my.telegram.org")
                logger.warning("采集服务将在有限功能模式下运行，等待用户完成认证...")
                return False
            else:
                # Telegram已认证，正常启动
                logger.info("✅ Telegram认证状态正常，启动消息监听...")
                
                # 启动Telegram客户端
                bot = TelegramBot()
                await bot.start()
                
                # 设置全局bot实例供其他模块使用
                bot_module.telegram_bot = bot
                self.telegram_bot = bot
                
                # 启动系统监控
                from app.services.system_monitor import system_monitor
                await system_monitor.start()
                
                # 设置健康状态
                await self.health_monitor.set_healthy({
                    "telegram_authenticated": True,
                    "bot_running": True,
                    "system_monitor": True
                })
                
                logger.info("✅ Telegram采集服务启动完成")
                return True
                
        except Exception as e:
            if self.health_monitor:
                await self.health_monitor.set_unhealthy(f"初始化失败: {str(e)}")
            raise
    
    async def start(self):
        """启动采集服务"""
        if await self.initialize():
            self.is_running = True
            logger.info("📡 Telegram采集服务运行中...")
            
            # 保持服务运行
            try:
                while self.is_running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("收到停止信号，正在关闭...")
                await self.stop()
        else:
            logger.warning("⚠️ Telegram采集服务启动失败，等待认证...")
            # 在等待认证模式下运行
            try:
                while True:
                    await asyncio.sleep(10)
                    # 定期检查认证状态
                    from app.telegram.auth import auth_manager
                    auth_status = await auth_manager.get_auth_status()
                    if auth_status.get('authorized', False):
                        logger.info("检测到Telegram认证完成，重新启动采集服务...")
                        if await self.initialize():
                            self.is_running = True
                            break
            except KeyboardInterrupt:
                logger.info("收到停止信号，正在关闭...")
    
    async def stop(self):
        """停止采集服务"""
        logger.info("📡 正在关闭Telegram采集服务...")
        self.is_running = False
        
        # 停止Telegram Bot
        if self.telegram_bot:
            await self.telegram_bot.stop()
            
        # 停止系统监控
        from app.services.system_monitor import system_monitor
        await system_monitor.stop()
        
        # 停止健康监控
        if self.health_monitor:
            await self.health_monitor.stop()
        
        logger.info("Telegram采集服务已关闭")

# 全局服务实例
collector_service = None

def signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"收到信号 {signum}，正在关闭服务...")
    if collector_service:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(collector_service.stop())
        loop.close()
    sys.exit(0)

async def main():
    """主函数"""
    global collector_service
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    collector_service = TelegramCollectorService()
    await collector_service.start()

if __name__ == "__main__":
    logger.info("📡 启动独立Telegram采集服务...")
    asyncio.run(main())