import sys
import logging
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

# 设置详细日志
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')

# 模拟更新过程
from app.services.content_filter import content_filter

# 测试消息
content = """**#柬泰冲突****：奥斯玛的也在撤退了！

**👌订阅频道：@miandianDs
👌投稿爆料： @QianQian106
👌海外交友； @tmiandianKs"""

print("=" * 50)
print("1. 重新加载训练模式...")
content_filter.reload_trained_patterns()

print("\n2. 应用过滤...")
filtered = content_filter.filter_promotional_content(content)

print(f"\n原始长度: {len(content)}")
print(f"过滤后长度: {len(filtered)}")
print(f"\n过滤后内容:\n{filtered}")
print("=" * 50)

# 测试intelligent_tail_filter是否已重新加载
from app.services.intelligent_tail_filter import intelligent_tail_filter
stats = intelligent_tail_filter.get_statistics()
print(f"\n当前加载的训练样本数: {stats['total_samples']}")
print(f"学习的关键词数: {stats['learned_keywords']}")
