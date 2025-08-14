import asyncio
import sys
from datetime import datetime, timedelta
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.core.database import get_db, Message
from sqlalchemy import select, desc

async def check_recent():
    async for db in get_db():
        # 获取最近10条pending消息
        result = await db.execute(
            select(Message)
            .where(Message.status == "pending")
            .order_by(desc(Message.created_at))
            .limit(10)
        )
        messages = result.scalars().all()
        
        print("最近的pending消息:")
        print("-" * 80)
        for msg in messages:
            # 检查是否有过滤
            original_len = len(msg.content) if msg.content else 0
            filtered_len = len(msg.filtered_content) if msg.filtered_content else 0
            
            print(f"ID: {msg.id} | 时间: {msg.created_at.strftime('%H:%M:%S')}")
            print(f"  原始长度: {original_len} | 过滤后: {filtered_len} | 减少: {original_len - filtered_len}")
            
            # 显示内容前50个字符
            content_preview = (msg.content[:50] + "...") if msg.content and len(msg.content) > 50 else msg.content
            print(f"  内容: {content_preview}")
            
            # 检查是否有尾部特征
            if msg.content and any(keyword in msg.content for keyword in ["@", "订阅", "投稿", "👌", "📣"]):
                print(f"  ⚠️ 可能包含尾部推广")
            
            print()
        
        break

asyncio.run(check_recent())
