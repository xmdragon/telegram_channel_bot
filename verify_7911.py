import asyncio
import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.core.database import get_db, Message
from sqlalchemy import select

async def verify():
    async for db in get_db():
        result = await db.execute(select(Message).where(Message.id == 7911))
        msg = result.scalar_one_or_none()
        
        if msg:
            print(f"消息7911过滤结果:")
            print(f"原始长度: {len(msg.content)}")
            print(f"过滤后长度: {len(msg.filtered_content) if msg.filtered_content else 0}")
            print(f"\n过滤后内容:")
            print(msg.filtered_content)
        break

asyncio.run(verify())
