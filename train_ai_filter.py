#!/usr/bin/env python3
"""
训练AI过滤器
从数据库中提取数据并训练智能过滤模型
"""
import asyncio
import logging
from sqlalchemy import select, and_, func
from app.core.database import AsyncSessionLocal, Message, Channel
from app.services.ai_filter import ai_filter
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def train_channel_tails():
    """训练频道的尾部模式 - 基于整体数据智能采样"""
    async with AsyncSessionLocal() as db:
        # 获取所有消息，按频道分组
        result = await db.execute(
            select(Message).where(
                Message.source_channel.isnot(None)
            ).order_by(Message.created_at.desc()).limit(1000)  # 从整体数据池采样
        )
        all_messages = result.scalars().all()
        
        # 按频道分组消息
        channel_messages = defaultdict(list)
        for msg in all_messages:
            if msg.source_channel:
                channel_messages[msg.source_channel].append(msg)
        
        logger.info(f"从 {len(channel_messages)} 个频道收集到 {len(all_messages)} 条消息")
        
        # 智能采样 - 不再要求每个频道固定数量
        learned_channels = 0
        skipped_channels = 0
        
        for channel_id, messages in channel_messages.items():
            # 获取频道信息（可选）
            channel_result = await db.execute(
                select(Channel).where(Channel.channel_id == channel_id)
            )
            channel = channel_result.scalar_one_or_none()
            channel_name = channel.channel_name if channel else f"频道{channel_id}"
            
            # 不再强制要求最少消息数，让AI过滤器自己判断
            if len(messages) < 3:
                logger.info(f"{channel_name} 样本太少（{len(messages)}条），跳过")
                skipped_channels += 1
                continue
            
            # 提取消息内容
            contents = []
            for msg in messages:
                # 优先使用原始内容来学习完整的尾部模式
                content = msg.content or msg.filtered_content
                if content:
                    contents.append(content)
            
            if contents:
                logger.info(f"分析 {channel_name} 的消息模式（{len(contents)}条）...")
                success = await ai_filter.learn_channel_pattern(channel_id, contents)
                if success:
                    learned_channels += 1
                    logger.info(f"✅ {channel_name} 发现尾部模式并学习成功")
                else:
                    skipped_channels += 1
                    logger.info(f"ℹ️ {channel_name} 未发现固定尾部模式（正常情况）")
        
        # 输出统计
        logger.info(f"\n📊 尾部模式学习统计:")
        logger.info(f"  - 总频道数: {len(channel_messages)}")
        logger.info(f"  - 发现尾部模式: {learned_channels} 个频道")
        logger.info(f"  - 无尾部模式: {skipped_channels} 个频道")
        if len(channel_messages) > 0:
            success_rate = learned_channels/len(channel_messages)*100
            logger.info(f"  - 检出率: {success_rate:.1f}%（不是所有频道都有尾部）")

async def train_ad_classifier():
    """训练广告分类器"""
    async with AsyncSessionLocal() as db:
        # 获取标记为广告的消息
        ad_result = await db.execute(
            select(Message).where(
                Message.is_ad == True
            ).limit(500)
        )
        ad_messages = ad_result.scalars().all()
        
        # 获取正常消息（已批准的）
        normal_result = await db.execute(
            select(Message).where(
                and_(
                    Message.is_ad == False,
                    Message.status == 'approved'
                )
            ).limit(500)
        )
        normal_messages = normal_result.scalars().all()
        
        logger.info(f"准备训练数据: {len(ad_messages)} 个广告样本, {len(normal_messages)} 个正常样本")
        
        # 提取内容
        ad_samples = []
        for msg in ad_messages:
            content = msg.content or msg.filtered_content
            if content:
                ad_samples.append(content)
        
        normal_samples = []
        for msg in normal_messages:
            content = msg.filtered_content or msg.content
            if content:
                normal_samples.append(content)
        
        if ad_samples or normal_samples:
            logger.info("开始训练广告分类器...")
            await ai_filter.train_ad_classifier(ad_samples, normal_samples)
            logger.info("✅ 广告分类器训练完成")
        else:
            logger.warning("没有足够的训练样本")

async def test_ai_filter():
    """测试AI过滤器效果"""
    # 测试广告检测
    test_ads = [
        "🎰 最新优惠 首存100送100 💰",
        "营业时间：10:00-22:00 微信：xxx123",
        "这是一条正常的新闻内容，没有广告"
    ]
    
    logger.info("\n=== 测试广告检测 ===")
    for text in test_ads:
        is_ad, confidence = ai_filter.is_advertisement(text)
        logger.info(f"文本: {text[:30]}...")
        logger.info(f"  -> 是否广告: {is_ad}, 置信度: {confidence:.2f}")
    
    # 测试尾部过滤
    if ai_filter.channel_patterns:
        logger.info("\n=== 测试尾部过滤 ===")
        channel_id = list(ai_filter.channel_patterns.keys())[0]
        test_content = """
重要新闻内容正文部分
这是新闻的详细描述

订阅频道 @channel123
商务合作 @business456
更多精彩内容请关注
"""
        filtered = ai_filter.filter_channel_tail(channel_id, test_content)
        logger.info(f"原始长度: {len(test_content)}, 过滤后: {len(filtered)}")

async def main():
    """主函数"""
    logger.info("🚀 开始训练AI过滤器...")
    
    # 等待AI过滤器初始化
    await asyncio.sleep(2)
    
    if not ai_filter.initialized:
        logger.error("AI过滤器初始化失败，请检查依赖库是否正确安装")
        return
    
    # 训练频道尾部模式
    logger.info("\n📚 步骤1: 学习频道尾部模式")
    await train_channel_tails()
    
    # 训练广告分类器
    logger.info("\n🎯 步骤2: 训练广告分类器")
    await train_ad_classifier()
    
    # 保存模型
    logger.info("\n💾 步骤3: 保存训练结果")
    ai_filter.save_patterns("data/ai_filter_patterns.json")
    
    # 测试效果
    logger.info("\n🧪 步骤4: 测试AI过滤器")
    await test_ai_filter()
    
    logger.info("\n✅ AI过滤器训练完成！")
    
    # 显示统计
    logger.info(f"\n📊 整体训练统计:")
    logger.info(f"  - 识别到尾部模式的频道: {len(ai_filter.channel_patterns)} 个")
    logger.info(f"  - 广告样本: {len(ai_filter.ad_embeddings)} 个")
    logger.info(f"  - 正常样本: {len(ai_filter.normal_embeddings)} 个")
    logger.info(f"\n💡 说明: 不是所有频道都有固定尾部，这是正常现象")

if __name__ == "__main__":
    asyncio.run(main())