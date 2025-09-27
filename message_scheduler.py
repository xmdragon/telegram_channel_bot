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
        self.auto_forwarder_task = None  # 管理auto_forwarder任务
        self.scheduler_task = None  # 管理调度器任务
        
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

            # 创建并启动消息调度器（使用异步版本）
            scheduler = MessageScheduler()
            self.scheduler_task = asyncio.create_task(scheduler.start())
            self.message_scheduler = scheduler

            # 启动auto_forwarder作为独立的异步任务
            from app.services.auto_forwarder import auto_forwarder
            self.auto_forwarder_task = asyncio.create_task(
                auto_forwarder.run_continuous()
            )
            logger.info("✅ 自动转发服务已作为异步任务启动")

            # 设置健康状态
            await self.health_monitor.set_healthy({
                "scheduler_running": True,
                "auto_forward_enabled": True,
                "cleanup_jobs": ["old_data", "temp_media", "logs", "channel_sync"],
                "pure_asyncio": True  # 标记使用纯asyncio实现
            })

            logger.info("✅ 消息调度服务启动完成 (纯asyncio)")
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
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("收到停止信号，正在关闭...")
                await self.stop()
    
    async def stop(self):
        """停止调度服务"""
        logger.info("⏰ 正在关闭消息调度服务...")
        self.is_running = False

        # 停止auto_forwarder任务
        if self.auto_forwarder_task:
            from app.services.auto_forwarder import auto_forwarder
            auto_forwarder.stop()  # 设置停止标志
            self.auto_forwarder_task.cancel()  # 取消任务
            try:
                await self.auto_forwarder_task
            except asyncio.CancelledError:
                pass
            logger.info("自动转发任务已停止")

        # 停止消息调度器（现在是异步的）
        if self.message_scheduler:
            await self.message_scheduler.shutdown()
            logger.info("调度器任务已停止")

        # 等待调度器任务完成
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass

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
        logger.debug(f"PID文件已创建: /tmp/scheduler.pid")
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
            logger.debug("PID文件已清理")
        except:
            pass

if __name__ == "__main__":
    logger.info("⏰ 消息调度服务启动 - PID:%d", os.getpid())
    asyncio.run(main())