#!/usr/bin/env python3
"""
更新消息 #4315 的过滤内容
"""
import asyncio
import logging
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, Message
from app.services.ai_filter import ai_filter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def update_specific_message():
    """更新特定消息"""
    
    # 加载AI模式
    ai_filter.load_patterns("data/ai_filter_patterns.json")
    logger.info(f"✅ 已加载 {len(ai_filter.channel_patterns)} 个频道的尾部模式")
    
    async with AsyncSessionLocal() as db:
        # 查找消息 #4315
        result = await db.execute(
            select(Message).where(Message.id == 4315)
        )
        msg = result.scalar_one_or_none()
        
        if msg and msg.content:
            logger.info(f"\n📨 找到消息 #4315")
            logger.info(f"  来源频道: {msg.source_channel}")
            logger.info(f"  原始内容长度: {len(msg.content)}")
            logger.info(f"  当前过滤内容长度: {len(msg.filtered_content) if msg.filtered_content else 0}")
            
            # 应用AI过滤
            if msg.source_channel:
                filtered_content = ai_filter.filter_channel_tail(msg.source_channel, msg.content)
                
                logger.info(f"\n🔧 应用AI过滤:")
                logger.info(f"  过滤后长度: {len(filtered_content)}")
                logger.info(f"  删除字符数: {len(msg.content) - len(filtered_content)}")
                
                if len(filtered_content) < len(msg.content):
                    # 更新数据库
                    msg.filtered_content = filtered_content
                    await db.commit()
                    logger.info(f"\n✅ 成功更新消息 #4315 的过滤内容")
                    
                    # 显示被过滤的内容
                    removed = msg.content[len(filtered_content):]
                    logger.info(f"\n被过滤的尾部内容:")
                    logger.info("-" * 40)
                    logger.info(removed)
                    logger.info("-" * 40)
                else:
                    logger.info(f"\n⚠️ 没有检测到需要过滤的内容")
            else:
                logger.error("消息没有源频道信息")
        else:
            logger.error("未找到消息 #4315")

if __name__ == "__main__":
    asyncio.run(update_specific_message())