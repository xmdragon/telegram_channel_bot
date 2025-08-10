#!/usr/bin/env python3
"""
测试广告检测准确性
"""
import asyncio
import logging
from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal, Message
from app.services.content_filter import ContentFilter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ad_detection():
    """测试广告检测"""
    
    filter = ContentFilter()
    await filter.load_keywords_from_db()
    
    async with AsyncSessionLocal() as db:
        # 获取被标记为广告的消息
        result = await db.execute(
            select(Message).where(
                and_(
                    Message.is_ad == True,
                    Message.content.isnot(None)
                )
            ).order_by(Message.created_at.desc()).limit(50)
        )
        ad_messages = result.scalars().all()
        
        logger.info(f"\n📊 分析 {len(ad_messages)} 条被标记为广告的消息\n")
        
        # 统计
        false_positives = []
        true_ads = []
        
        for msg in ad_messages:
            content = msg.content[:200] if msg.content else ""
            
            # 重新检测
            is_ad = filter.is_pure_advertisement(msg.content)
            ad_score = 10 if is_ad else 0  # 简化分数
            
            # 简单判断：如果没有链接和@用户名，可能是误判
            has_link = 'http' in msg.content or 't.me' in msg.content
            has_username = '@' in msg.content
            has_promo_keywords = any(kw in msg.content for kw in ['订阅', '投稿', '商务', '报名', '入群', '跑分', '担保', '优惠', '赌场', '博彩'])
            
            if is_ad and ad_score >= 8:
                true_ads.append(msg)
            else:
                # 可能是误判
                if not has_link and not has_username and not has_promo_keywords:
                    false_positives.append(msg)
                    logger.info(f"\n🔍 可能的误判 (ID: {msg.id}):")
                    logger.info(f"  广告分数: {ad_score}")
                    logger.info(f"  内容预览: {content}")
                else:
                    true_ads.append(msg)
        
        # 获取正常消息样本
        normal_result = await db.execute(
            select(Message).where(
                and_(
                    Message.is_ad == False,
                    Message.status == 'approved',
                    Message.content.isnot(None)
                )
            ).order_by(Message.created_at.desc()).limit(50)
        )
        normal_messages = normal_result.scalars().all()
        
        # 检测假阴性（应该被检测为广告但没有）
        false_negatives = []
        for msg in normal_messages:
            is_ad = filter.is_pure_advertisement(msg.content)
            ad_score = 10 if is_ad else 0
            
            # 检查是否包含明显的广告特征
            has_strong_ad_features = any(kw in msg.content for kw in ['赌场', '博彩', '首充', '返水', '优惠码'])
            
            if has_strong_ad_features and not is_ad:
                false_negatives.append(msg)
                logger.info(f"\n⚠️ 可能漏检 (ID: {msg.id}):")
                logger.info(f"  广告分数: {ad_score}")
                logger.info(f"  内容预览: {msg.content[:200]}")
        
        # 统计报告
        logger.info("\n" + "="*60)
        logger.info("📈 广告检测分析报告")
        logger.info("="*60)
        
        logger.info(f"\n📊 统计数据:")
        logger.info(f"  - 被标记为广告: {len(ad_messages)} 条")
        logger.info(f"  - 可能误判: {len(false_positives)} 条 ({len(false_positives)/len(ad_messages)*100:.1f}%)" if ad_messages else "  - 可能误判: 0 条")
        logger.info(f"  - 正确识别: {len(true_ads)} 条")
        logger.info(f"  - 可能漏检: {len(false_negatives)} 条")
        
        logger.info(f"\n💡 建议:")
        if len(false_positives) > len(ad_messages) * 0.2:  # 误判率超过20%
            logger.info("  ⚠️ 误判率较高，建议：")
            logger.info("  1. 提高广告判定阈值（当前为8分）")
            logger.info("  2. 减少低权重规则的影响")
            logger.info("  3. 增加内容保护规则")
        else:
            logger.info("  ✅ 广告检测准确率良好")
        
        if len(false_negatives) > 5:
            logger.info("  ⚠️ 存在一定漏检，建议增加相关关键词")

if __name__ == "__main__":
    asyncio.run(test_ad_detection())