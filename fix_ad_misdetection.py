#!/usr/bin/env python3
"""
修复广告误判问题
"""
import asyncio
import logging
from sqlalchemy import select, and_, update
from app.core.database import AsyncSessionLocal, Message
from app.services.content_filter import ContentFilter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_ad_misdetection():
    """修复广告误判"""
    
    filter = ContentFilter()
    await filter.load_keywords_from_db()
    
    async with AsyncSessionLocal() as db:
        # 获取所有被标记为广告的pending消息
        result = await db.execute(
            select(Message).where(
                and_(
                    Message.is_ad == True,
                    Message.status == 'pending',
                    Message.content.isnot(None)
                )
            )
        )
        messages = result.scalars().all()
        
        logger.info(f"检查 {len(messages)} 条被标记为广告的待审核消息...")
        
        fixed_count = 0
        real_ads = 0
        
        for msg in messages:
            # 重新检测是否为广告
            is_ad = filter.is_pure_advertisement(msg.content)
            
            # 更严格的判定标准
            has_strong_ad_features = False
            
            # 检查强广告特征
            strong_ad_keywords = [
                '赌场', '博彩', '体育投注', '棋牌', '娱乐城', 'casino',
                '首充', '返水', '优惠码', '注册送', '日出千万',
                'USDT', '泰达币', '充值', '下注', '投注',
                '无需实名', '不限IP', '大额出款',
                '营业时间', '营业中', '接单中', '下单', '订购'
            ]
            
            for keyword in strong_ad_keywords:
                if keyword in msg.content:
                    has_strong_ad_features = True
                    break
            
            # 检查是否有多个推广链接或用户名
            link_count = msg.content.count('http://') + msg.content.count('https://')
            username_count = msg.content.count('@')
            
            # 如果没有强广告特征，且链接/用户名不多，则不是广告
            if not has_strong_ad_features and not is_ad and link_count < 3 and username_count < 3:
                # 这可能是误判，取消广告标记
                msg.is_ad = False
                fixed_count += 1
                logger.info(f"✅ 修复误判 ID:{msg.id} - {msg.content[:50]}...")
            else:
                real_ads += 1
        
        # 提交更改
        if fixed_count > 0:
            await db.commit()
            logger.info(f"\n✅ 成功修复 {fixed_count} 条误判的消息")
            logger.info(f"📊 保留 {real_ads} 条真实广告")
        else:
            logger.info("\n没有需要修复的误判")

async def reset_all_ad_flags():
    """重置所有广告标记（可选）"""
    async with AsyncSessionLocal() as db:
        # 将所有pending消息的is_ad设为False
        await db.execute(
            update(Message)
            .where(Message.status == 'pending')
            .values(is_ad=False)
        )
        await db.commit()
        logger.info("已重置所有待审核消息的广告标记")

async def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--reset-all':
        # 完全重置模式
        await reset_all_ad_flags()
    else:
        # 智能修复模式
        await fix_ad_misdetection()

if __name__ == "__main__":
    asyncio.run(main())