import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.services.intelligent_tail_filter import intelligent_tail_filter

# 消息7911的内容
content = """#网友投稿    #百乐门这超速抓人

天下公寓大路过来这里抓摩托超速的，玛德，老子上次就因为开摩托超速罚款，后面一直慢慢的开，这次我开的很慢，结果还是被抓罚款。到现在才看到亚太的坑比，就是想要搞钱吃

☎️投稿商务曝光☎️  ：@A166688899

👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn"""

# 只测试尾部部分
tail_part = """☎️投稿商务曝光☎️  ：@A166688899

👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn"""

print("分析尾部特征...")
print("=" * 50)

# 提取特征
features = intelligent_tail_filter.feature_extractor.extract_features(tail_part)
print("尾部特征:")
for name, value in features.items():
    if value > 0:
        print(f"  {name}: {value:.2f}")

# 计算特征得分
score = intelligent_tail_filter._calculate_feature_score(features)
print(f"\n特征得分: {score:.2f}")

# 判断是否为尾部
is_tail = intelligent_tail_filter.is_tail(tail_part)
print(f"是否判定为尾部: {is_tail}")

# 计算相似度
similarity = intelligent_tail_filter.calculate_similarity(tail_part)
print(f"与训练样本的相似度: {similarity:.2f}")

print("\n" + "=" * 50)
print("测试完整消息过滤:")
filtered, was_filtered, removed_tail = intelligent_tail_filter.filter_message(content)
print(f"是否检测到尾部: {was_filtered}")
if was_filtered:
    print(f"过滤后长度: {len(content)} -> {len(filtered)}")
    print(f"移除的内容:\n{removed_tail}")
else:
    print("未检测到尾部")
    
    # 尝试手动添加这个样本
    print("\n添加训练样本...")
    intelligent_tail_filter.add_training_sample(tail_part)
    
    # 再次测试
    print("再次测试...")
    filtered, was_filtered, removed_tail = intelligent_tail_filter.filter_message(content)
    print(f"是否检测到尾部: {was_filtered}")
    if was_filtered:
        print(f"过滤后长度: {len(content)} -> {len(filtered)}")
