import sys
import asyncio
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.core.database import get_db, Message
from sqlalchemy import select
from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.services.content_filter import content_filter

async def refilter_7899():
    async for db in get_db():
        result = await db.execute(select(Message).where(Message.id == 7899))
        msg = result.scalar_one_or_none()
        
        if msg:
            print("消息 #7899 重新过滤")
            print(f"原始内容长度: {len(msg.content)} 字符")
            print(f"当前过滤后长度: {len(msg.filtered_content) if msg.filtered_content else 0} 字符")
            
            # 强制重新加载训练数据
            intelligent_tail_filter._load_training_data(force_reload=True)
            print("✅ 重新加载训练数据")
            
            # 重新过滤
            filtered = content_filter.filter_promotional_content(msg.content)
            
            print(f"\n新的过滤结果:")
            print(f"过滤后长度: {len(filtered)} 字符")
            print(f"内容: {filtered}")
            
            # 更新数据库
            if filtered != msg.filtered_content:
                msg.filtered_content = filtered
                await db.commit()
                print("\n✅ 数据库已更新")
            else:
                print("\n⚠️ 过滤结果相同，无需更新")
        else:
            print("未找到消息 #7899")
        break

asyncio.run(refilter_7899())