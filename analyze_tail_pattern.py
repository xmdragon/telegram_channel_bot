#!/usr/bin/env python3
"""
分析尾部模式的相似度
"""
import asyncio
import logging
from app.services.ai_filter import ai_filter
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def analyze_tail_similarity():
    """分析尾部相似度"""
    
    # 加载AI模式
    ai_filter.load_patterns("data/ai_filter_patterns.json")
    
    channel_id = "-1002495270592"  # @yyds518899
    
    # 消息 #4315 的尾部
    new_tail = """👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn"""

    # 之前学习的典型尾部（从训练数据中）
    typical_tails = [
        """🔥美国华人卖菜🔥 https://t.me/mgqp0
🔥报名入群： @yydsxiaomei
🔥 免费报名跑分担保👇👇""",
        """🔥菲律宾招聘咨询🔥  @a5161899
🔥报名入群： @yydsxiaomei
🔥美国华人卖菜 https://t.me/mgqp0
🔥 免费报名跑分担保👇👇""",
        """🔥亚太新闻频道🔥 https://t.me/yyds518899
🔥菲律宾招聘咨询🔥  @a5161899
🔥报名入群： @yydsxiaomei
🔥 免费报名跑分担保👇👇"""
    ]
    
    logger.info("=" * 60)
    logger.info("🔍 分析尾部相似度")
    logger.info("=" * 60)
    
    # 计算新尾部的嵌入
    new_embedding = ai_filter.model.encode([new_tail])[0]
    
    # 获取已学习的模式
    if channel_id in ai_filter.channel_patterns:
        pattern = ai_filter.channel_patterns[channel_id]
        centroid = pattern['centroid']
        
        # 计算与中心的相似度
        from sklearn.metrics.pairwise import cosine_similarity
        similarity = cosine_similarity(
            new_embedding.reshape(1, -1),
            centroid.reshape(1, -1)
        )[0][0]
        
        logger.info(f"\n📊 与学习模式的相似度: {similarity:.3f}")
        logger.info(f"   阈值: {pattern['threshold']}")
        logger.info(f"   是否匹配: {'✅' if similarity >= pattern['threshold'] else '❌'}")
        
        # 分析典型尾部
        logger.info(f"\n🔍 与典型尾部的相似度对比:")
        for i, tail in enumerate(typical_tails, 1):
            tail_embedding = ai_filter.model.encode([tail])[0]
            tail_similarity = cosine_similarity(
                tail_embedding.reshape(1, -1),
                centroid.reshape(1, -1)
            )[0][0]
            logger.info(f"\n典型尾部 {i} 相似度: {tail_similarity:.3f}")
            logger.info(f"内容预览: {tail[:50]}...")
        
        # 分析差异
        logger.info(f"\n📝 尾部内容差异分析:")
        logger.info(f"\n新尾部特征:")
        logger.info(f"  - 包含频道链接: {'✅' if 't.me' in new_tail else '❌'}")
        logger.info(f"  - 包含'报名入群': {'✅' if '报名入群' in new_tail else '❌'}")
        logger.info(f"  - 包含'跑分担保': {'✅' if '跑分担保' in new_tail else '❌'}")
        logger.info(f"  - 包含emoji火焰: {'✅' if '🔥' in new_tail else '❌'}")
        logger.info(f"  - 包含'亚太': {'✅' if '亚太' in new_tail else '❌'}")
        
        logger.info(f"\n典型尾部特征:")
        logger.info(f"  - 包含频道链接: ✅")
        logger.info(f"  - 包含'报名入群': ✅")
        logger.info(f"  - 包含'跑分担保': ✅")
        logger.info(f"  - 包含emoji火焰: ✅")
        
        # 建议
        logger.info(f"\n💡 问题分析:")
        logger.info(f"  新尾部使用了不同的格式和内容：")
        logger.info(f"  1. 使用👍而不是🔥作为emoji")
        logger.info(f"  2. 没有'报名入群'和'跑分担保'等关键词")
        logger.info(f"  3. 添加了新的频道（色情吃瓜）和服务（中文包）")
        logger.info(f"  4. 格式结构不同，行数和内容都有变化")
        
        logger.info(f"\n🔧 解决方案:")
        logger.info(f"  1. 需要重新训练，包含新格式的尾部样本")
        logger.info(f"  2. 或者手动添加这种新格式到训练数据")
        logger.info(f"  3. 降低相似度阈值（但可能误判）")

asyncio.run(analyze_tail_similarity())