#!/usr/bin/env python3
"""
测试智能过滤系统
验证新系统不会破坏消息内容
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.intelligent_learning_system import intelligent_learning_system
from app.services.content_filter import content_filter


def test_message_7842():
    """测试消息7842不会被破坏"""
    print("\n" + "=" * 60)
    print("测试消息 #7842 过滤")
    print("=" * 60)
    
    # 消息7842的原始内容
    original = """#国内资讯**

马云为了保命，已上交全部个人财产给国家**

截正2025年8月10日**，蚂蚁集团已完成"解除马云先生控制权"，**集团表示是创始人马云自愿放弃的。

**马云把全部家产上交国家堪称时代楷模 ，**像马云这样主动把全部身家上交国家求饶一条狗命的企业家，马云不是第一个，也不会是最后一个。**第一批把全部身家上交国家保命的是王健林和赵本山**

📣**  **订阅👑👑👑👑👑👑**频道  ↓
****🔗**** **t.me/+8rnBOqnrjxM3M2Y1
✅**投稿澄清爆料**：** **@dny228"""
    
    print("原始内容长度:", len(original))
    print("\n原始内容预览（前100字）:")
    print(original[:100])
    
    # 使用新的智能过滤系统
    filtered, was_filtered, removed_tail = intelligent_learning_system.filter_message(original)
    
    print("\n过滤结果:")
    print(f"- 是否过滤: {was_filtered}")
    print(f"- 过滤后长度: {len(filtered)}")
    
    if was_filtered:
        print(f"- 删除了 {len(original) - len(filtered)} 字符")
        print(f"- 删除比例: {(len(original) - len(filtered)) / len(original) * 100:.1f}%")
        
        print("\n过滤后内容预览（前200字）:")
        print(filtered[:200])
        
        # 验证正文是否完整
        critical_content = [
            "马云为了保命",
            "蚂蚁集团",
            "王健林和赵本山"
        ]
        
        print("\n正文完整性检查:")
        all_intact = True
        for content in critical_content:
            if content in filtered:
                print(f"✅ '{content}' - 保留")
            else:
                print(f"❌ '{content}' - 被删除（错误！）")
                all_intact = False
        
        if all_intact:
            print("\n✅ 测试通过：正文内容完整保留")
        else:
            print("\n❌ 测试失败：正文内容被破坏")
    else:
        print("\n⚠️ 未检测到需要过滤的内容")
    
    return was_filtered and all([c in filtered for c in ["马云为了保命", "蚂蚁集团", "王健林和赵本山"]])


def test_edge_cases():
    """测试边缘情况"""
    print("\n" + "=" * 60)
    print("边缘情况测试")
    print("=" * 60)
    
    test_cases = [
        {
            'name': '纯推广内容',
            'content': """📣订阅频道：@test123
💬商务合作：@business
😍投稿爆料：@submit""",
            'should_filter': True
        },
        {
            'name': '纯新闻内容',
            'content': """国际新闻

今天发生了重要事件，政府发布了新政策。
该政策将影响数百万人的生活。
专家表示这是历史性的决定。""",
            'should_filter': False
        },
        {
            'name': '新闻+推广',
            'content': """重要新闻

马云宣布新计划，将投资100亿美元。
这将创造10万个就业机会。

📣订阅我们的频道：@news123
☎️投稿联系：@contact""",
            'should_filter': True
        }
    ]
    
    all_passed = True
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {case['name']}")
        print("-" * 40)
        
        filtered, was_filtered, _ = intelligent_learning_system.filter_message(case['content'])
        
        expected = "应该过滤" if case['should_filter'] else "不应该过滤"
        actual = "已过滤" if was_filtered else "未过滤"
        
        if was_filtered == case['should_filter']:
            print(f"✅ 通过 - {expected}，{actual}")
        else:
            print(f"❌ 失败 - {expected}，但{actual}")
            all_passed = False
        
        if was_filtered:
            print(f"   过滤后长度: {len(filtered)} (原始: {len(case['content'])})")
    
    return all_passed


def test_no_self_destruction():
    """测试不会自我破坏"""
    print("\n" + "=" * 60)
    print("自我破坏防护测试")
    print("=" * 60)
    
    # 模拟一个包含训练样本文字的消息
    message = """重要新闻

今天的新闻报道提到，很多人都在关注订阅频道的问题。
专家建议大家理性看待投稿爆料的现象。

这是正文内容，不应该被删除。"""
    
    print("测试内容:")
    print(message)
    
    filtered, was_filtered, _ = intelligent_learning_system.filter_message(message)
    
    # 检查关键内容是否保留
    key_phrases = ["重要新闻", "今天的新闻报道", "专家建议", "这是正文内容"]
    
    print("\n内容保护检查:")
    all_protected = True
    for phrase in key_phrases:
        if phrase in filtered:
            print(f"✅ '{phrase}' - 保护成功")
        else:
            print(f"❌ '{phrase}' - 被错误删除")
            all_protected = False
    
    if all_protected:
        print("\n✅ 测试通过：不会自我破坏")
    else:
        print("\n❌ 测试失败：内容被错误删除")
    
    return all_protected


def main():
    """运行所有测试"""
    print("\n" + "🧪" * 30)
    print("智能过滤系统测试")
    print("🧪" * 30)
    
    # 获取系统统计
    stats = intelligent_learning_system.get_statistics()
    print(f"\n系统状态:")
    print(f"- 已学习模式数: {stats['pattern_count']}")
    print(f"- 处理样本数: {stats['learning_stats']['samples_processed']}")
    print(f"- 有效样本数: {stats['learning_stats']['samples_accepted']}")
    
    # 运行测试
    tests = [
        ("消息#7842测试", test_message_7842),
        ("边缘情况测试", test_edge_cases),
        ("自我破坏防护", test_no_self_destruction)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ {name} 出错: {e}")
            results.append((name, False))
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status} - {name}")
    
    print(f"\n总计: {passed_count}/{total_count} 测试通过")
    
    if passed_count == total_count:
        print("\n🎉 所有测试通过！新系统工作正常。")
    else:
        print("\n⚠️ 部分测试失败，需要进一步调试。")


if __name__ == "__main__":
    main()