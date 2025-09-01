#!/usr/bin/env python3
"""
Telegram消息采集审核系统 - 消息调度服务
独立的消息调度服务，处理自动转发和数据清理
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
from app.services.scheduler import MessageScheduler

# 确保日志目录存在
os.makedirs('./logs', exist_ok=True)

from logging.handlers import TimedRotatingFileHandler

# 创建自定义的文件处理器，只过滤数据库驱动模块日志
class FilteredTimedRotatingFileHandler(TimedRotatingFileHandler):
    """过滤特定模块的按时间轮转文件处理器"""
    def emit(self, record):
        # 只过滤数据库驱动模块的日志（系统已不使用SQL数据库，但保留以防遗留组件）
        if record.name.startswith(('sqlalchemy', 'asyncpg', 'databases')):
            return
        # 移除关键词过滤 - 避免误杀DELETE等正常操作日志
        super().emit(record)

# 在日志初始化前导入PathConfig
from app.core.path_config import PathConfig

file_handler = FilteredTimedRotatingFileHandler(
    filename=str(PathConfig.LOGS_DIR / "message_scheduler.log"),
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

class MessageSchedulerService:
    """消息调度服务"""
    
    def __init__(self):
        self.message_scheduler = None
        self.is_running = False
        self.health_monitor = None
        
    async def initialize(self):
        """初始化调度服务"""
        logger.info("⏰ 启动消息调度服务...")
        
        # 启动健康监控
        from app.services.health_monitor import create_health_monitor
        self.health_monitor = create_health_monitor("message_scheduler")
        await self.health_monitor.start()
        
        try:
            # 基础系统初始化
            logger.info("初始化存储层和认证服务...")
            
            # Redis管理器自动处理连接管理 - Linus式简洁
            from app.storage.redis_manager import redis_manager
            if not redis_manager.is_healthy():
                await self.health_monitor.set_unhealthy("Redis连接不可用")
                raise RuntimeError("Redis连接失败")
            logger.info("Redis管理器已就绪")
            
            # 初始化JSON存储层
            from app.storage.json_store import init_json_stores
            if not init_json_stores():
                await self.health_monitor.set_unhealthy("JSON存储层初始化失败")
                raise RuntimeError("初始化失败")
            
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
            
            # 启动消息调度器
            from app.telegram import bot as bot_module
            scheduler = MessageScheduler()
            scheduler.start()
            bot_module.message_scheduler = scheduler
            self.message_scheduler = scheduler
            
            # 启动统计数据广播器（从web_server迁移而来）
            from app.services.stats_broadcaster import init_stats_broadcaster
            await init_stats_broadcaster()
            logger.info("✅ 统计数据广播器已启动（scheduler负责）")
            
            # 设置健康状态
            await self.health_monitor.set_healthy({
                "scheduler_running": True,
                "auto_forward_enabled": True,
                "cleanup_jobs": ["old_data", "temp_media", "logs"],
                "stats_broadcaster": True
            })
            
            logger.info("✅ 消息调度服务启动完成")
            return True
            
        except Exception as e:
            if self.health_monitor:
                await self.health_monitor.set_unhealthy(f"初始化失败: {str(e)}")
            raise
    
    async def start(self):
        """启动调度服务"""
        if await self.initialize():
            self.is_running = True
            logger.info("⏰ 消息调度服务运行中...")
            
            # 保持服务运行
            try:
                while self.is_running:
                    # 检查调度服务开关
                    from app.services.config_manager import config_manager
                    scheduler_enabled = await config_manager.get_config('scheduler.enabled', True)
                    if not scheduler_enabled:
                        logger.debug("调度服务已禁用，等待启用...")
                        await asyncio.sleep(10)  # 暂停调度，等待启用
                        continue
                    
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("收到停止信号，正在关闭...")
                await self.stop()
    
    async def stop(self):
        """停止调度服务"""
        logger.info("⏰ 正在关闭消息调度服务...")
        self.is_running = False
        
        # 停止统计数据广播器
        try:
            from app.services.stats_broadcaster import shutdown_stats_broadcaster
            await shutdown_stats_broadcaster()
            logger.info("统计数据广播器已停止")
        except Exception as e:
            logger.error(f"停止统计数据广播器失败: {e}")
        
        # 停止消息调度器
        if self.message_scheduler:
            self.message_scheduler.shutdown()
        
        # 停止健康监控
        if self.health_monitor:
            await self.health_monitor.stop()
            
        logger.info("消息调度服务已关闭")

# 全局服务实例
scheduler_service = None

def signal_handler(signum, frame):
    """信号处理器 - Linus式修复：避免创建新事件循环"""
    logger.info(f"收到信号 {signum}，正在关闭服务...")
    if scheduler_service:
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_running_loop()
            # 在当前循环中调度停止任务
            loop.create_task(scheduler_service.stop())
        except RuntimeError:
            # 如果没有运行中的循环，创建新的（最后的选择）
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(scheduler_service.stop())
                loop.close()
            except Exception as e:
                logger.error(f"停止服务失败: {e}")
    sys.exit(0)

async def main():
    """主函数"""
    global scheduler_service
    
    # 创建PID文件用于健康检查
    try:
        with open('/tmp/scheduler.pid', 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"PID文件已创建: /tmp/scheduler.pid (PID: {os.getpid()})")
    except Exception as e:
        logger.warning(f"创建PID文件失败: {e}")
    
    # 注册信号处理器
    def cleanup_handler(signum, frame):
        logger.info(f"接收到信号 {signum}，清理PID文件...")
        try:
            os.remove('/tmp/scheduler.pid')
        except:
            pass
        signal_handler(signum, frame)
    
    signal.signal(signal.SIGINT, cleanup_handler)
    signal.signal(signal.SIGTERM, cleanup_handler)
    
    scheduler_service = MessageSchedulerService()
    await scheduler_service.start()

if __name__ == "__main__":
    logger.info("⏰ 启动独立消息调度服务...")
    asyncio.run(main())