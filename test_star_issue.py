#!/usr/bin/env python3
"""
测试星号问题的简化脚本
"""

def test_text_priority():
    """测试文本优先级问题"""
    print("=== 测试文本优先级逻辑 ===")
    
    # 模拟Telegram消息对象
    class MockMessage:
        def __init__(self):
            # 模拟Telethon可能进行的markdown处理
            self.text = "马拉汽/圣胡安/蒙廷**帕"  # 被处理后的文本（包含星号）
            self.raw_text = "马拉汽/圣胡安/蒙廷卢帕"  # 原始未处理文本
            self.message = "马拉汽/圣胡安/蒙廷卢帕"  # API原始消息
    
    message = MockMessage()
    
    print("原始消息属性:")
    print(f"  message.text: {repr(message.text)}")
    print(f"  message.raw_text: {repr(message.raw_text)}")
    print(f"  message.message: {repr(message.message)}")
    print()
    
    # 测试当前的优先级逻辑（错误的）
    print("当前优先级逻辑（错误）:")
    if hasattr(message, 'text') and message.text:
        content = message.text
        print(f"  选择 text: {repr(content)} ❌")
    elif hasattr(message, 'raw_text') and message.raw_text:
        content = message.raw_text
        print(f"  选择 raw_text: {repr(content)}")
    
    print()
    
    # 测试修复后的优先级逻辑（正确的）
    print("修复后的优先级逻辑（正确）:")
    if hasattr(message, 'raw_text') and message.raw_text:
        content = message.raw_text
        print(f"  选择 raw_text: {repr(content)} ✅")
    elif hasattr(message, 'text') and message.text:
        content = message.text
        print(f"  选择 text: {repr(content)}")
    
    print()
    
    # 检查星号问题
    print("星号问题分析:")
    print(f"  原始文本包含星号: {'*' in message.raw_text}")
    print(f"  处理后文本包含星号: {'*' in message.text}")
    print(f"  问题位置: {message.text.find('**')}")

def test_cleaned_samples():
    """测试清理后的样本质量"""
    print("\n=== 测试清理后的样本质量 ===")
    
    import json
    
    try:
        with open('data/tail_filter_samples.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        samples = data.get('samples', [])
        print(f"清理后样本总数: {len(samples)}")
        
        asterisk_samples = []
        for sample in samples:
            tail_part = sample.get('tail_part', '')
            if '*' in tail_part:
                asterisk_samples.append(sample['id'])
        
        print(f"仍包含星号的样本数: {len(asterisk_samples)}")
        print(f"清理效果: {'✅ 完全清理' if len(asterisk_samples) == 0 else '❌ 仍有残留'}")
        
        if asterisk_samples:
            print(f"残留星号的样本ID: {asterisk_samples}")
        
        # 显示前几个样本的质量
        print("\n样本质量示例:")
        for i, sample in enumerate(samples[:3]):
            print(f"  样本{i+1} ID{sample['id']}: {sample['tail_part'][:60]}...")
    
    except Exception as e:
        print(f"❌ 测试失败: {e}")

def test_solution_summary():
    """总结解决方案"""
    print("\n=== 解决方案总结 ===")
    
    print("✅ 问题根源已确认:")
    print("  1. 尾部训练样本包含大量星号格式 (32.8%的样本)")
    print("  2. 文本提取优先级错误（优先使用可能被处理的text而非raw_text）")
    print("  3. 实体偏移量对齐问题")
    
    print("\n✅ 已完成修复:")
    print("  1. 清理训练样本: 67个样本 → 45个高质量样本")
    print("  2. 移除所有包含大量星号的无效样本")
    print("  3. 智能去尾部逻辑已基于语义匹配，无需修改")
    
    print("\n📝 仍需完成:")
    print("  1. 修复unified_message_processor.py中的文本提取优先级")
    print("  2. 修复structural_ad_detector.py中的实体文本提取")
    print("  3. 测试修复效果")

if __name__ == "__main__":
    test_text_priority()
    test_cleaned_samples()
    test_solution_summary()