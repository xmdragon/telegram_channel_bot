import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.services.content_filter import content_filter

# 测试不同类型的消息
test_cases = [
    {
        "name": "消息7911 - 短正文+长尾部",
        "content": """#网友投稿    #百乐门这超速抓人

天下公寓大路过来这里抓摩托超速的，玛德，老子上次就因为开摩托超速罚款，后面一直慢慢的开，这次我开的很慢，结果还是被抓罚款。到现在才看到亚太的坑比，就是想要搞钱吃

☎️投稿商务曝光☎️  ：@A166688899

👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn"""
    },
    {
        "name": "极短消息 - 只有标题+尾部",
        "content": """突发新闻！

📣关注频道 @channel123
👍投稿爆料 @contact456"""
    },
    {
        "name": "纯尾部消息",
        "content": """📣关注频道 @channel123
👍投稿爆料 @contact456
🔗更多资讯 t.me/news789"""
    }
]

# 强制重新加载训练数据
print("重新加载训练数据...")
intelligent_tail_filter._load_training_data(force_reload=True)
stats = intelligent_tail_filter.get_statistics()
print(f"加载了 {stats['total_samples']} 个训练样本\n")

for case in test_cases:
    print("=" * 60)
    print(f"测试: {case['name']}")
    print(f"原始长度: {len(case['content'])} 字符")
    
    # 测试intelligent_tail_filter
    filtered, was_filtered, tail = intelligent_tail_filter.filter_message(case['content'])
    
    if was_filtered:
        print(f"✅ intelligent_tail_filter检测到尾部")
        print(f"   过滤后: {len(filtered)} 字符")
        if filtered:
            print(f"   保留内容: {filtered[:50]}..." if len(filtered) > 50 else f"   保留内容: {filtered}")
        else:
            print(f"   整条消息被识别为推广")
    else:
        print(f"❌ intelligent_tail_filter未检测到尾部")
    
    # 测试完整的content_filter
    filtered2 = content_filter.filter_promotional_content(case['content'])
    print(f"\ncontent_filter过滤后: {len(filtered2)} 字符")
    
    print()
