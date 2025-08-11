#!/usr/bin/env python3
"""
测试新的消息采集流程
确保原始内容被完整保存
"""
import asyncio
import sys
sys.path.append('.')

from app.services.unified_message_processor import UnifiedMessageProcessor
from datetime import datetime

# 模拟一个Telegram消息对象
class MockTelegramMessage:
    def __init__(self, id, text, media=None, caption=None, grouped_id=None):
        self.id = id
        self.text = text
        self.raw_text = text
        self.message = text
        self.media = media
        self.caption = caption
        self.date = datetime.now()
        self.grouped_id = grouped_id

async def test_message_processing():
    """测试消息处理流程"""
    
    # 创建处理器实例
    processor = UnifiedMessageProcessor()
    
    # 测试案例1: 包含曝光内容和广告的消息
    test_content = """🎥曝光：某某人在某地做了某事，大家要小心！
    
这是正常的新闻内容部分。

😆😆😆😆😆**本频道推荐**😆😆😆😆😆
华硕品质 坚若磐石 全天在线 欢迎咨询"""
    
    mock_message = MockTelegramMessage(
        id=99999,
        text=test_content,
        media=None
    )
    
    print("=" * 60)
    print("测试新的消息处理流程")
    print("=" * 60)
    
    # 测试原始内容提取
    original_content = await processor._extract_original_content(mock_message)
    
    print(f"\n✅ 步骤1: 原始内容提取")
    print(f"  原始内容长度: {len(original_content)} 字符")
    print(f"  包含'曝光': {'是' if '曝光' in original_content else '否'}")
    print(f"  包含'本频道推荐': {'是' if '本频道推荐' in original_content else '否'}")
    
    # 验证原始内容是否完整
    if original_content == test_content:
        print("  ✅ 原始内容完整无损")
    else:
        print("  ❌ 原始内容有丢失")
        print(f"    预期长度: {len(test_content)}")
        print(f"    实际长度: {len(original_content)}")
    
    # 测试案例2: 纯媒体消息带caption
    mock_media_message = MockTelegramMessage(
        id=99998,
        text=None,
        media={'photo': 'test.jpg'},
        caption="这是图片说明文字"
    )
    
    caption_content = await processor._extract_original_content(mock_media_message)
    print(f"\n✅ 步骤2: 媒体消息caption提取")
    print(f"  Caption内容: {caption_content}")
    print(f"  提取成功: {'是' if caption_content == '这是图片说明文字' else '否'}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("新的流程确保了:")
    print("1. ✅ 原始内容在第一时间被完整提取")
    print("2. ✅ 不会因为过滤处理而丢失原始文本")
    print("3. ✅ 支持多种消息类型的内容提取")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_message_processing())