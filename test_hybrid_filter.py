#!/usr/bin/env python3
"""
测试混合智能过滤器的效果
"""

import logging
from app.services.hybrid_tail_filter import hybrid_tail_filter

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_filter():
    """测试各种场景"""
    
    test_cases = [
        {
            'name': '明显的推广尾部',
            'content': '''今天柬埔寨发生了一件大事，引起了广泛关注。
据报道，当地时间下午，某地发生了重要事件。

🔔订阅东南亚大事件曝光-聚焦时事
🔗 https://t.me/dongnanya0027
☎️ 投稿澄清爆料：@DNW8888''',
            'expected': True
        },
        {
            'name': '带分隔符的推广',
            'content': '''这是一条重要的新闻消息，内容非常详细。
事件的具体情况如下所述。

----------------
[东南亚无小事](https://t.me/+-9WcXvqUn6UxMDA9)  |  [博闻资讯](https://bowen888.com/)  |  [吃瓜群众](https://t.me/bagua888888)  |''',
            'expected': True
        },
        {
            'name': '正常的学术引用（不应过滤）',
            'content': '''根据研究显示，这个现象非常普遍。
**重要发现**：数据表明增长了30%。

参考文献：
1. 张三, 2024, "研究报告"
2. 李四, 2023, "分析文章"

因此，我们可以得出结论，这是一个重要的发现。''',
            'expected': False
        },
        {
            'name': '正文中的链接（不应过滤）',
            'content': '''今天我们要讨论的是技术问题。
具体可以参考官方文档：https://docs.example.com

总之，这个方法非常有效，建议大家尝试。''',
            'expected': False
        },
        {
            'name': '多个联系方式的推广',
            'content': '''重要通知：明天有活动。

😍加入我们：https://t.me/jpz_888
💬 大寨子群聊 @dazhaizi888
☎️ 商务合作：@business123
🔔 订阅频道：@channel456''',
            'expected': True
        },
        {
            'name': '纯emoji装饰（可能误判）',
            'content': '''消息内容正文部分。

😀😀😀😀😀😀😀😀😀😀''',
            'expected': False  # 纯emoji不应该被判为推广
        }
    ]
    
    print("="*60)
    print("混合智能过滤器测试")
    print("="*60)
    
    correct = 0
    total = len(test_cases)
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试案例 {i}: {case['name']}")
        print("-"*40)
        
        content = case['content']
        expected = case['expected']
        
        # 执行过滤
        filtered, has_tail, tail = hybrid_tail_filter.filter_message(content)
        
        # 判断结果
        success = has_tail == expected
        if success:
            correct += 1
            status = "✅ 正确"
        else:
            status = "❌ 错误"
        
        print(f"预期结果: {'检测到尾部' if expected else '无尾部'}")
        print(f"实际结果: {'检测到尾部' if has_tail else '无尾部'}")
        print(f"判断结果: {status}")
        
        if has_tail:
            print(f"移除字符: {len(tail)} 个")
            print(f"尾部内容: {tail[:100]}..." if len(tail) > 100 else f"尾部内容: {tail}")
    
    print("\n" + "="*60)
    print(f"测试结果: {correct}/{total} 正确 ({correct/total*100:.1f}%)")
    print("="*60)
    
    # 显示过滤器统计
    stats = hybrid_tail_filter.get_filter_stats()
    print(f"\n过滤器配置:")
    print(f"  • 判定阈值: {stats['threshold']}")
    print(f"  • 最大尾部占比: {stats['max_tail_ratio']:.0%}")
    print(f"  • 最小尾部长度: {stats['min_tail_length']} 字符")
    print(f"  • 结构样本数: {stats['structural_samples']}")
    print(f"  • 学习关键词: {stats['learned_keywords']}")

if __name__ == "__main__":
    test_filter()