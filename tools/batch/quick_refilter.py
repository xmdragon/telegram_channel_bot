#!/usr/bin/env python3
"""
快速重新过滤指定消息
用法: python3 quick_refilter.py <message_id>
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

from app.core.database import get_db, Message
from sqlalchemy import select
from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.services.content_filter import content_filter


async def quick_refilter(message_id: int):
    """快速重新过滤指定消息"""
    async for db in get_db():
        # 获取消息
        result = await db.execute(
            select(Message).where(Message.id == message_id)
        )
        msg = result.scalar_one_or_none()
        
        if not msg:
            print(f"❌ 消息 {message_id} 不存在")
            return
        
        print(f"处理消息 {message_id}...")
        print(f"原始内容长度: {len(msg.content)} 字符")
        print(f"当前过滤长度: {len(msg.filtered_content) if msg.filtered_content else 0} 字符")
        
        # 强制重新加载训练数据
        print("重新加载训练数据...")
        intelligent_tail_filter._load_training_data(force_reload=True)
        
        # 重新过滤
        filtered_content = content_filter.filter_promotional_content(
            msg.content,
            channel_id=str(msg.source_channel) if msg.source_channel else None
        )
        
        # 更新数据库
        msg.filtered_content = filtered_content
        await db.commit()
        
        print(f"✅ 过滤完成: {len(msg.content)} -> {len(filtered_content)} 字符")
        print(f"减少了 {len(msg.content) - len(filtered_content)} 字符")
        
        # 如果有审核群消息，尝试更新
        if msg.review_message_id:
            try:
                from app.telegram.bot import telegram_bot
                if telegram_bot and telegram_bot.client:
                    await telegram_bot.update_review_message(msg)
                    print(f"✅ 审核群消息 {msg.review_message_id} 已更新")
            except Exception as e:
                print(f"⚠️ 更新审核群消息失败: {e}")
        
        break


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 quick_refilter.py <message_id>")
        print("示例: python3 quick_refilter.py 7911")
        sys.exit(1)
    
    try:
        message_id = int(sys.argv[1])
    except ValueError:
        print("❌ 消息ID必须是数字")
        sys.exit(1)
    
    asyncio.run(quick_refilter(message_id))