#!/usr/bin/env python3
"""
训练AI过滤器
从数据库中提取数据并训练智能过滤模型
"""
import asyncio
import logging
import json
from pathlib import Path
from app.services.ai_filter import ai_filter
from app.core.path_config import PathConfig
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def train_channel_tails():
    """训练频道的尾部模式 - 从训练数据文件学习"""
    # 加载手动训练数据
    manual_training_file = PathConfig.MANUAL_TRAINING_FILE
    if not manual_training_file.exists():
        logger.warning("手动训练数据文件不存在")
        return
    
    with open(manual_training_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        samples = data.get('samples', [])
    
    if not samples:
        logger.warning("没有可用的训练数据")
        return
    
    # 按频道分组训练数据
    channel_samples = defaultdict(list)
    for sample in samples:
        channel_id = sample.get('channel_id')
        original_message = sample.get('original_message')
        if channel_id and original_message:
            channel_samples[channel_id].append(original_message)
    
    logger.info(f"从 {len(channel_samples)} 个频道加载了 {len(samples)} 个训练样本")
    
    # 训练每个频道
    learned_channels = 0
    skipped_channels = 0
    
    for channel_id, messages in channel_samples.items():
        # 获取频道名称
        channel_name = f"频道{channel_id}"
        for sample in samples:
            if sample.get('channel_id') == channel_id and sample.get('channel_name'):
                channel_name = sample['channel_name']
                break
        
        if len(messages) < 3:
            logger.info(f"{channel_name} 样本太少（{len(messages)}条），跳过")
            skipped_channels += 1
            continue
        
        logger.info(f"分析 {channel_name} 的消息模式（{len(messages)}条）...")
        success = await ai_filter.learn_channel_pattern(channel_id, messages)
        if success:
            learned_channels += 1
            logger.info(f"✅ {channel_name} 发现尾部模式并学习成功")
        else:
            skipped_channels += 1
            logger.info(f"ℹ️ {channel_name} 未发现固定尾部模式（正常情况）")
        
    # 输出统计
    logger.info(f"\n📊 尾部模式学习统计:")
    logger.info(f"  - 总频道数: {len(channel_samples)}")
    logger.info(f"  - 发现尾部模式: {learned_channels} 个频道")
    logger.info(f"  - 无尾部模式: {skipped_channels} 个频道")
    if len(channel_samples) > 0:
        success_rate = learned_channels/len(channel_samples)*100
        logger.info(f"  - 检出率: {success_rate:.1f}%（不是所有频道都有尾部）")

async def train_ad_classifier():
    """训练广告分类器"""
    # 加载广告训练数据
    ad_training_file = PathConfig.AD_TRAINING_FILE
    if ad_training_file.exists():
        with open(ad_training_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            ad_samples_data = data.get('samples', [])
            ad_samples = [s.get('content', '') for s in ad_samples_data if s.get('content')]
    else:
        ad_samples = []
    
    # 暂时不加载正常样本（正常内容太多样化）
    normal_samples = []
    
    logger.info(f"准备训练数据: {len(ad_samples)} 个广告样本, {len(normal_samples)} 个正常样本")
    
    if ad_samples:
        logger.info("开始训练广告分类器...")
        try:
            await ai_filter.train_ad_classifier(ad_samples, normal_samples)
            logger.info("✅ 广告分类器训练完成")
        except Exception as e:
            logger.error(f"广告分类器训练失败: {e}")
    else:
        logger.warning("没有可用的广告训练数据")

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
    ai_filter.save_patterns(str(PathConfig.AI_FILTER_PATTERNS_FILE))
    
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