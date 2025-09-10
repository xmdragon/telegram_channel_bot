import asyncio
import logging
import os
from pathlib import Path
import sys

# 导入PathConfig获取正确的日志文件路径
from app.core.path_config import PathConfig

# 确保日志目录存在
PathConfig.ensure_directories()

# 设置日志配置，确保有输出
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # 控制台输出
        logging.FileHandler(PathConfig.APP_LOG_FILE, mode='a')  # 使用PathConfig
    ]
)

logger = logging.getLogger(__name__)

from app.services.message_collector import message_collector

async def main():
    try:
        print("🚀 启动消息采集器...")
        logger.info("🚀 启动消息采集器")
        
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