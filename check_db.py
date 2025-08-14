import asyncio
import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.core.database import get_db, Message
from sqlalchemy import select

async def check_message():
    async for db in get_db():
        result = await db.execute(
            select(Message).where(Message.id == 7891)
        )
        msg = result.scalar_one_or_none()
        
        if msg:
            print(f"消息ID: {msg.id}")
            print(f"原始内容长度: {len(msg.content) if msg.content else 0}")
            print(f"过滤内容长度: {len(msg.filtered_content) if msg.filtered_content else 0}")
            print(f"\n原始内容:")
            print(msg.content[:200] if msg.content else "无")
            print(f"\n过滤内容:")
            print(msg.filtered_content[:200] if msg.filtered_content else "无")
        else:
            print("消息7891不存在")
        
        break

asyncio.run(check_message())
