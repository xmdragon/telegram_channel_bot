import asyncio
import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.core.database import get_db, Message
from sqlalchemy import select
from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.services.content_filter import content_filter

async def refilter_message():
    async for db in get_db():
        # 获取消息7891
        result = await db.execute(
            select(Message).where(Message.id == 7891)
        )
        msg = result.scalar_one_or_none()
        
        if not msg:
            print("消息7891不存在")
            return
        
        print(f"消息ID: {msg.id}")
        print(f"原始内容长度: {len(msg.content)}")
        print(f"当前过滤内容长度: {len(msg.filtered_content) if msg.filtered_content else 0}")
        
        # 强制重新加载训练数据
        print("\n重新加载训练数据...")
        intelligent_tail_filter._load_training_data(force_reload=True)
        
        # 重新过滤
        print("应用过滤...")
        filtered_content = content_filter.filter_promotional_content(
            msg.content,
            channel_id=str(msg.source_channel) if msg.source_channel else None
        )
        
        print(f"\n新的过滤内容长度: {len(filtered_content)}")
        print(f"减少了: {len(msg.content) - len(filtered_content)} 字符")
        
        # 更新数据库
        msg.filtered_content = filtered_content
        await db.commit()
        
        print("\n数据库已更新")
        print(f"过滤后内容:\n{filtered_content}")
        
        break

asyncio.run(refilter_message())
