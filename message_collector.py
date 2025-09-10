import asyncio
import logging
import os
from pathlib import Path

from app.services.message_collector import message_collector

async def main():
    try:
        await message_collector.initialize()
        await message_collector.start_collecting()
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())