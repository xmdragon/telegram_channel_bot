#!/usr/bin/env python3
"""
修复消息 #5764 的内容
从截图可以看到原始消息包含刘帅曝光的内容
"""
import asyncio
import sys
sys.path.append('.')

from app.core.database import AsyncSessionLocal, Message
from sqlalchemy import select, update
from app.services.content_filter import ContentFilter
from datetime import datetime

# 消息 #5764 的真实内容（从截图提取）
REAL_CONTENT = """🎥曝光：此人 刘帅 之前一直混迹 #小梦拉 骗吃骗喝 这两天拉骗不到吃的喝的了 跑来梦波丢车费都没有 特别是在女孩子面前 装逼口袋一分钱拿不出来 连开房钱都没有 昨天晚上在梦波荣誉酒店又骗一个女孩子去开房 开房还叫我帮他开 身上没有钱 各位兄弟们看见此人 千万不要被他骗了 还有各位老板女们 他就是一个不要脸的渣道 千万不要上当了 口袋里面一毛钱没有 还装逼

😆😆😆😆😆**本频道推荐**😆😆😆😆😆

华硕品质 坚若磐石 全天在线 欢迎咨询

💸华硕科技：币盘EX 交L 易L 所L 包L网L

📱包网搭建联系：@yefan11_

🥜 银 河 国 际

营销 专属回馈：现已上线 
银河国际：https://t.me/Vhft"""

async def fix_message():
    """修复消息内容"""
    async with AsyncSessionLocal() as session:
        # 查询消息 #5764
        query = select(Message).where(Message.id == 5764)
        result = await session.execute(query)
        message = result.scalar_one_or_none()
        
        if not message:
            print("❌ 未找到消息 #5764")
            return
        
        print(f"找到消息 #5764")
        print(f"  Telegram消息ID: {message.message_id}")
        print(f"  频道: {message.source_channel}")
        print(f"  当前原始内容长度: {len(message.content) if message.content else 0}")
        print(f"  当前过滤内容长度: {len(message.filtered_content) if message.filtered_content else 0}")
        
        # 更新原始内容
        print("\n📝 更新原始内容...")
        old_content = message.content
        
        # 使用内容过滤器重新处理
        content_filter = ContentFilter()
        is_ad, filtered_content, filter_reason = content_filter.filter_message_sync(
            REAL_CONTENT,
            channel_id=message.source_channel
        )
        
        print(f"\n过滤结果:")
        print(f"  是否广告: {is_ad}")
        print(f"  过滤原因: {filter_reason}")
        print(f"  过滤后长度: {len(filtered_content)}")
        print(f"  过滤后内容预览: {filtered_content[:200]}...")
        
        # 更新数据库
        stmt = (
            update(Message)
            .where(Message.id == 5764)
            .values(
                content=REAL_CONTENT,
                filtered_content=filtered_content,
                is_ad=is_ad,
                filter_reason=filter_reason,
                updated_at=datetime.now()
            )
        )
        
        await session.execute(stmt)
        await session.commit()
        
        print("\n✅ 消息 #5764 已修复!")
        print(f"  原始内容: {len(old_content) if old_content else 0} -> {len(REAL_CONTENT)} 字符")
        print(f"  过滤内容: 0 -> {len(filtered_content)} 字符")
        
        # 验证修复
        result = await session.execute(query)
        updated_message = result.scalar_one_or_none()
        print(f"\n验证:")
        print(f"  数据库原始内容长度: {len(updated_message.content)}")
        print(f"  数据库过滤内容长度: {len(updated_message.filtered_content)}")
        
        # 检查关键内容是否恢复
        if '刘帅' in updated_message.content:
            print("  ✅ '刘帅'曝光内容已恢复")
        if '曝光' in updated_message.filtered_content:
            print("  ✅ 曝光内容保留在过滤后文本中")

if __name__ == "__main__":
    asyncio.run(fix_message())