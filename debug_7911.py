import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.services.intelligent_tail_filter import intelligent_tail_filter

content = """#网友投稿    #百乐门这超速抓人

天下公寓大路过来这里抓摩托超速的，玛德，老子上次就因为开摩托超速罚款，后面一直慢慢的开，这次我开的很慢，结果还是被抓罚款。到现在才看到亚太的坑比，就是想要搞钱吃

☎️投稿商务曝光☎️  ：@A166688899

👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn"""

lines = content.split('\n')
print(f"总行数: {len(lines)}")

# 测试从第4行开始的尾部（应该是正确的分割点）
tail_from_4 = '\n'.join(lines[4:])
print(f"\n从第4行开始的尾部:")
print(f"内容: {tail_from_4[:50]}...")
print(f"is_tail判定: {intelligent_tail_filter.is_tail(tail_from_4)}")

features = intelligent_tail_filter.feature_extractor.extract_features(tail_from_4)
score = intelligent_tail_filter._calculate_feature_score(features)
print(f"特征得分: {score:.2f}")

# 测试从第10行开始的尾部
tail_from_10 = '\n'.join(lines[10:])
print(f"\n从第10行开始的尾部:")
print(f"内容: {tail_from_10}")
print(f"is_tail判定: {intelligent_tail_filter.is_tail(tail_from_10)}")

# 手动调试filter_message逻辑
print("\n" + "=" * 50)
print("模拟filter_message扫描:")
for i in range(len(lines) - 1, 0, -1):
    potential_tail = '\n'.join(lines[i:])
    if len(potential_tail) < 15:
        continue
    
    is_tail = intelligent_tail_filter.is_tail(potential_tail)
    print(f"第{i}行: 长度={len(potential_tail):3}, is_tail={is_tail}")
    
    if is_tail:
        print(f"  -> 找到尾部起点: 第{i}行")
        clean_content = '\n'.join(lines[:i]).rstrip()
        print(f"  -> 剩余正文长度: {len(clean_content)}")
        print(f"  -> 正文内容: {clean_content[:50]}...")
        break
