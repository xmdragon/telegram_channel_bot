#!/usr/bin/env python3
"""
Telegram消息采集审核系统 - 消息调度服务
独立的消息调度服务，处理自动转发和数据清理
"""
import warnings
# 抑制pkg_resources弃用警告
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from app.core.config import settings
from app.services.scheduler import MessageScheduler
from app.core.path_config import PathConfig

# 使用统一的日志配置
from app.core.logging_config import setup_logging, get_logger

# 初始化日志系统
setup_logging(service_name="scheduler", log_level="INFO", console_output=True)
logger = get_logger(__name__)

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
            
            # Redis管理器自动处理连接管理 - 简洁
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
            
            # 频道缓存功能已移除
            logger.debug("配置管理器已就绪")
            
            # 初始化训练数据目录和配置
            PathConfig.ensure_directories()
            logger.info("训练数据目录已初始化")
            
            # 加载数据库配置
            await settings.load_db_configs()
            
            # 启动消息调度器
            scheduler = MessageScheduler()
            scheduler.start()
            self.message_scheduler = scheduler
            
            
            # 设置健康状态
            await self.health_monitor.set_healthy({
                "scheduler_running": True,
                "auto_forward_enabled": True,
                "cleanup_jobs": ["old_data", "temp_media", "logs"],
                "stats_broadcaster": False
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
    """信号处理器 - 优雅关闭服务"""
    logger.info(f"收到信号 {signum}，正在关闭服务...")
    if scheduler_service:
        # 设置停止标志，让主循环自然退出
        scheduler_service.is_running = False
        logger.info("已设置停止标志，等待服务自然关闭...")

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
    try:
        await scheduler_service.start()
    finally:
        # 确保PID文件被清理
        try:
            os.remove('/tmp/scheduler.pid')
            logger.info("PID文件已清理")
        except:
            pass

if __name__ == "__main__":
    logger.info("⏰ 启动独立消息调度服务...")
    asyncio.run(main())