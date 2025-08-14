import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.services.content_filter import content_filter

# 测试消息内容
content = """**#柬泰冲突****：奥斯玛的也在撤退了！

**👌订阅频道：@miandianDs
👌投稿爆料： @QianQian106
👌海外交友； @tmiandianKs"""

print("测试ContentFilter...")

# 先重新加载训练模式
print("\n重新加载训练模式...")
content_filter.reload_trained_patterns()

# 测试过滤
filtered = content_filter.filter_promotional_content(content)

print(f"\n原始内容长度: {len(content)}")
print(f"过滤后长度: {len(filtered)}")
print("\n过滤后内容:")
print(filtered)
print("=" * 50)

# 再测试一次_apply_trained_tail_filters
print("\n直接测试_apply_trained_tail_filters:")
filtered2 = content_filter._apply_trained_tail_filters(content)
print(f"过滤后长度: {len(filtered2)}")
print("过滤后内容:")
print(filtered2)
