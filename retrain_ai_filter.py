#!/usr/bin/env python3
"""
重新训练AI过滤器
使用改进的学习策略，只学习真正的尾部内容
"""
import asyncio
import logging
from pathlib import Path
from app.services.ai_filter import ai_filter
from app.core.training_config import TrainingDataConfig
from datetime import datetime, timedelta
import json
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def retrain_ai_filter():
    """重新训练AI过滤器"""
    
    logger.info("🔄 开始重新训练AI过滤器...")
    
    # 清理现有的频道模式
    ai_filter.channel_patterns = {}
    logger.info("✅ 已清理现有模式")
    
    # 从训练数据文件获取样本
    training_file = TrainingDataConfig.MANUAL_TRAINING_FILE
    if not training_file.exists():
        logger.error("训练数据文件不存在")
        return
    
    with open(training_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        samples = data.get('samples', [])
    
    # 按频道分组消息
    messages_by_channel = defaultdict(list)
    for sample in samples:
        channel_id = sample.get('channel_id')
        content = sample.get('original_message')
        if channel_id and content:
            messages_by_channel[channel_id].append(content)
        
    logger.info(f"📊 获取了 {len(messages_by_channel)} 个频道的训练样本")
        
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
    patterns_file = TrainingDataConfig.AI_FILTER_PATTERNS_FILE
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