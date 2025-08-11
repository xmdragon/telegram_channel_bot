#!/usr/bin/env python3
"""
重新训练AI过滤器
使用改进的学习策略，只学习真正的尾部内容
"""
import asyncio
import logging
from pathlib import Path
from app.services.ai_filter import ai_filter
from app.core.database import AsyncSessionLocal, Message
from sqlalchemy import select, text
from datetime import datetime, timedelta
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def retrain_ai_filter():
    """重新训练AI过滤器"""
    
    logger.info("🔄 开始重新训练AI过滤器...")
    
    # 清理现有的频道模式
    ai_filter.channel_patterns = {}
    logger.info("✅ 已清理现有模式")
    
    # 从数据库获取最近的消息样本
    async with AsyncSessionLocal() as db:
        # 获取每个频道的最近消息
        query = text("""
            SELECT source_channel, content, created_at
            FROM messages
            WHERE content IS NOT NULL 
            AND LENGTH(content) > 100
            AND created_at > :since
            ORDER BY source_channel, created_at DESC
        """)
        
        # 获取最近7天的消息
        since = datetime.now() - timedelta(days=7)
        result = await db.execute(query, {"since": since})
        messages_by_channel = {}
        
        for row in result:
            channel_id = str(row[0])
            content = row[1]
            
            if channel_id not in messages_by_channel:
                messages_by_channel[channel_id] = []
            
            # 限制每个频道最多50条消息
            if len(messages_by_channel[channel_id]) < 50:
                messages_by_channel[channel_id].append(content)
        
        logger.info(f"📊 获取了 {len(messages_by_channel)} 个频道的消息")
        
        # 为每个频道重新训练
        success_count = 0
        failed_count = 0
        
        for channel_id, messages in messages_by_channel.items():
            if len(messages) >= 5:  # 至少需要5条消息
                logger.info(f"🎯 训练频道 {channel_id} ({len(messages)} 条消息)...")
                
                try:
                    # 使用新的学习策略
                    result = await ai_filter.learn_channel_pattern(channel_id, messages)
                    
                    if result:
                        success_count += 1
                        logger.info(f"✅ 频道 {channel_id} 训练成功")
                    else:
                        failed_count += 1
                        logger.info(f"⚠️ 频道 {channel_id} 未发现固定尾部模式")
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"❌ 频道 {channel_id} 训练失败: {e}")
            else:
                logger.info(f"⏭️ 频道 {channel_id} 样本不足，跳过")
        
        logger.info(f"\n📈 训练结果统计:")
        logger.info(f"  - 成功训练: {success_count} 个频道")
        logger.info(f"  - 未发现模式: {failed_count} 个频道")
        logger.info(f"  - 总频道数: {len(messages_by_channel)}")
    
    # 保存新的模式
    patterns_file = Path("data/ai_filter_patterns.json")
    ai_filter.save_patterns(str(patterns_file))
    logger.info(f"💾 新模式已保存到 {patterns_file}")
    
    # 显示学习到的模式统计
    if ai_filter.channel_patterns:
        logger.info("\n📊 学习到的模式详情:")
        for channel_id, pattern in ai_filter.channel_patterns.items():
            sample_count = pattern.get('sample_count', 0)
            logger.info(f"  - 频道 {channel_id}: {sample_count} 个尾部样本")
    
    logger.info("\n✨ AI过滤器重新训练完成！")
    
    # 验证新模型的效果
    await verify_new_model()

async def verify_new_model():
    """验证新模型的效果"""
    logger.info("\n🔍 验证新模型效果...")
    
    # 测试几个已知的例子
    test_cases = [
        {
            "channel_id": "-1002305901042",
            "content": """白雪公主现实版 逃进东南亚这片大森林

走出校园出来东南亚之后，我才发现自己就像童话里的白雪公主，被迫离开舒适的城堡，跌入这片充满陷阱的森林。

ps: 自己对号入座吧😂😂😂😂

----------------
[东南亚无小事](https://t.me/xxx) | [博闻资讯](https://bowen888.com/)""",
            "expected": "应该只过滤掉分隔线之后的推广链接"
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        logger.info(f"\n测试案例 {i}: {test['expected']}")
        filtered = ai_filter.filter_channel_tail(test["channel_id"], test["content"])
        
        if filtered == test["content"]:
            logger.info("  结果: 未过滤任何内容")
        else:
            logger.info(f"  结果: {len(test['content'])} -> {len(filtered)} 字符")
            logger.info(f"  保留内容预览: {filtered[:100]}...")

if __name__ == "__main__":
    asyncio.run(retrain_ai_filter())