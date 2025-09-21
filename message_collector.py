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
    """信号处理器"""
    logger.info(f"收到信号 {signum}，准备关闭...")
    message_collector.running = False

async def main():
    try:
        print("🚀 启动消息采集器...")
        logger.info("🚀 启动消息采集器")
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print("📋 初始化中...")
        await message_collector.initialize()
        logger.info("📋 初始化完成")
        
        print("🔄 开始采集消息...")
        await message_collector.start_collecting()
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        logger.error(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 50)
    print("Telegram 消息采集器")
    print("=" * 50)
    asyncio.run(main())