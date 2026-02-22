import asyncio
import logging
import os
import signal
from pathlib import Path
import sys

# 使用统一的日志配置
from app.core.logging_config import setup_logging, get_logger
from app.core.path_config import PathConfig

# 确保日志目录存在
PathConfig.ensure_directories()

# 初始化日志系统
setup_logging(service_name="collector", log_level="INFO", console_output=True)
logger = get_logger(__name__)

from app.services.message_collector import message_collector

def signal_handler(signum, frame):
    """信号处理器 - 不调用logger，避免死锁"""
    message_collector.running = False

async def main():
    try:
        logger.info("消息采集器启动中...")

        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        await message_collector.initialize()
        logger.info("消息采集器初始化完成")

        await message_collector.start_collecting()

    except Exception as e:
        logger.error(f"消息采集器启动失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 优雅关闭：断开Telethon客户端
        if message_collector.telethon_client and message_collector.telethon_client.is_connected():
            try:
                await message_collector.telethon_client.disconnect()
                logger.info("Telethon客户端已断开连接")
            except Exception as e:
                logger.warning(f"断开Telethon客户端失败: {e}")
        logger.info("消息采集器已关闭")

if __name__ == "__main__":
    logger.info("🚀 Telegram消息采集器 - PID:%d", os.getpid())
    asyncio.run(main())