import asyncio
import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.core.database import get_db, Message
from sqlalchemy import select
from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.services.content_filter import content_filter

async def test_refilter(message_id):
    async for db in get_db():
        # 获取消息
        result = await db.execute(
            select(Message).where(Message.id == message_id)
        )
        msg = result.scalar_one_or_none()
        
        if not msg:
            print(f"消息{message_id}不存在")
            return
        
        print(f"消息ID: {msg.id}")
        print(f"原始内容:\n{msg.content}\n")
        print(f"当前过滤内容:\n{msg.filtered_content}\n")
        print("-" * 50)
        
        # 强制重新加载训练数据
        print("重新加载训练数据...")
        intelligent_tail_filter._load_training_data(force_reload=True)
        stats = intelligent_tail_filter.get_statistics()
        print(f"加载了 {stats['total_samples']} 个训练样本")
        
        # 测试intelligent_tail_filter直接过滤
        print("\n测试intelligent_tail_filter:")
        filtered, was_filtered, tail = intelligent_tail_filter.filter_message(msg.content)
        if was_filtered:
            print(f"✅ 检测到尾部，过滤后: {len(msg.content)} -> {len(filtered)}")
            print(f"移除的尾部:\n{tail}")
        else:
            print("❌ 未检测到尾部")
        
        # 测试完整的content_filter
        print("\n测试content_filter.filter_promotional_content:")
        filtered_content = content_filter.filter_promotional_content(
            msg.content,
            channel_id=str(msg.source_channel) if msg.source_channel else None
        )
        print(f"过滤后: {len(msg.content)} -> {len(filtered_content)}")
        
        if len(filtered_content) < len(msg.filtered_content):
            print("\n✅ 新的过滤更有效，更新数据库...")
            msg.filtered_content = filtered_content
            await db.commit()
            print("数据库已更新")
        else:
            print("\n当前过滤已经是最优的")
        
        print(f"\n最终过滤内容:\n{filtered_content}")
        
        break

# 测试消息7911
asyncio.run(test_refilter(7911))
