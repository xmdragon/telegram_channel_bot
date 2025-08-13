#!/usr/bin/env python3
"""
测试统一过滤引擎对赌博广告的检测效果
"""
import asyncio
from app.services.unified_filter_engine import unified_filter_engine

async def test_filter():
    """测试过滤引擎"""
    
    # 测试样本（类似N9的赌博广告）
    test_messages = [
        {
            "name": "典型赌博广告",
            "content": """⚡⚡⚡⚡⚡⚡⚡⚡
**钱包WG联名担保1000万U【 ****某某.COM**** 】查【****某某.TOP**** 】
** ⚡**公平公正，真实可靠。诚信透明的娱乐体验，所有派发链上可查！！！！！全网最公开公正**
**【验资：****@某某com_kf****】**

⚡⚡⚡⚡⚡⚡**
** ****新会员好礼 **😀 [**注册就送28.8U**](https://example.com/?id=642888594&currency=USDT&type=2)**
**注：绑定汇旺实名账号联系客服申请
🎁 首存100U赠送28U
🎁 二存/三存最高赠送8888U
**老用户好礼****😀**** **电子狂欢每日存款赠送10%
**天天存款天天送，存款完成联系在线客服申请，**"""
        },
        {
            "name": "首存优惠广告",
            "content": """🔥🔥🔥 线上娱乐城 🔥🔥🔥
首存100送50，最高送8888
U存U提，无需实名
不限IP，全球可玩
客服：@kefu_service"""
        },
        {
            "name": "多链接赌博广告",
            "content": """💰💰💰 日赚千万不是梦
官网1: https://site1.com
官网2: https://site2.com  
官网3: https://site3.com
备用: https://backup.com
USDT充值，秒到账"""
        },
        {
            "name": "正常消息",
            "content": """今天分享一个有趣的新闻，某某公司发布了新产品，
这个产品的特点是支持多种支付方式，用户体验很好。"""
        }
    ]
    
    print("=" * 60)
    print("测试统一过滤引擎")
    print("=" * 60)
    
    for test in test_messages:
        print(f"\n测试: {test['name']}")
        print("-" * 40)
        
        # 测试广告检测
        is_ad, filtered_content, reason = await unified_filter_engine.detect_advertisement(
            test['content'],
            channel_id="test_channel"
        )
        
        print(f"是否广告: {is_ad}")
        print(f"过滤原因: {reason}")
        print(f"内容长度: {len(test['content'])} -> {len(filtered_content)}")
        
        if is_ad and not filtered_content:
            print("✅ 高风险广告，内容已清空")
        elif is_ad:
            print("⚠️ 检测到广告内容")
        else:
            print("ℹ️ 正常消息")

if __name__ == "__main__":
    asyncio.run(test_filter())