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
print("每行内容:")
for i, line in enumerate(lines):
    print(f"  {i}: {line[:50]}..." if len(line) > 50 else f"  {i}: {line}")

print("\n测试从不同位置开始的尾部:")
for i in range(len(lines) - 1, 0, -1):
    potential_tail = '\n'.join(lines[i:])
    if len(potential_tail) < 15:
        continue
    
    is_tail = intelligent_tail_filter.is_tail(potential_tail)
    score = intelligent_tail_filter._calculate_feature_score(
        intelligent_tail_filter.feature_extractor.extract_features(potential_tail)
    )
    
    print(f"从第{i}行开始: 得分={score:.2f}, 是尾部={is_tail}, 长度={len(potential_tail)}")
    
    if is_tail:
        print(f"  ✅ 找到尾部起始位置: 第{i}行")
        print(f"  尾部内容: {potential_tail[:50]}...")
        break

# 检查filter_message的具体逻辑
print("\n" + "=" * 50)
print("调试filter_message逻辑:")

# 模拟filter_message的扫描
best_split = len(lines)
best_score = 0
best_tail = None

scan_lines = min(20, max(int(len(lines) * 0.8), 5))
print(f"扫描范围: 最后{scan_lines}行")

for i in range(len(lines) - 1, 0, -1):
    potential_tail = '\n'.join(lines[i:])
    
    if len(potential_tail) < 15:
        continue
    
    if intelligent_tail_filter.is_tail(potential_tail):
        features = intelligent_tail_filter.feature_extractor.extract_features(potential_tail)
        feature_score = intelligent_tail_filter._calculate_feature_score(features)
        similarity = intelligent_tail_filter.calculate_similarity(potential_tail)
        
        position_weight = (len(lines) - i) / scan_lines
        combined_score = (feature_score * 0.4 + similarity * 0.4 + position_weight * 0.2)
        
        print(f"第{i}行: 特征={feature_score:.2f}, 相似度={similarity:.2f}, 位置权重={position_weight:.2f}, 综合={combined_score:.2f}")
        
        if combined_score > best_score:
            best_score = combined_score
            best_split = i
            best_tail = potential_tail

if best_tail:
    print(f"\n最佳分割点: 第{best_split}行, 得分={best_score:.2f}")
    clean_content = '\n'.join(lines[:best_split]).rstrip()
    min_ratio = 0.2 if len(content) < 200 else 0.3
    if len(clean_content) > len(content) * min_ratio:
        print(f"✅ 可以过滤: {len(content)} -> {len(clean_content)}")
    else:
        print(f"❌ 过滤后内容太少: {len(clean_content)} < {len(content) * min_ratio}")
else:
    print("未找到合适的分割点")
