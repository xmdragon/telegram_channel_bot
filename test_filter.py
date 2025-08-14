import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.services.intelligent_tail_filter import intelligent_tail_filter

# 测试消息内容
content = """**#柬泰冲突****：奥斯玛的也在撤退了！

**👌订阅频道：@miandianDs
👌投稿爆料： @QianQian106
👌海外交友； @tmiandianKs"""

# 强制重新加载训练数据
intelligent_tail_filter._load_training_data(force_reload=True)

# 测试过滤
filtered, was_filtered, tail = intelligent_tail_filter.filter_message(content)

print(f"原始内容长度: {len(content)}")
print(f"过滤后长度: {len(filtered)}")
print(f"是否检测到尾部: {was_filtered}")
print(f"检测到的尾部: {tail}")
print("\n过滤后内容:")
print(filtered)
