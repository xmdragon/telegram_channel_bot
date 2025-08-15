import sys
import json
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from pathlib import Path
from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation
from datetime import datetime

# 手动添加训练样本
tail_part = """☎️投稿商务曝光☎️  ：@A166688899

👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn"""

# 加载现有样本
TAIL_FILTER_SAMPLES_FILE = PathConfig.TAIL_FILTER_SAMPLES_FILE
data = SafeFileOperation.read_json_safe(TAIL_FILTER_SAMPLES_FILE)
samples = data.get("samples", []) if data else []

# 检查是否已存在
import hashlib
content_hash = hashlib.md5(tail_part.encode()).hexdigest()
exists = False
for sample in samples:
    existing_hash = hashlib.md5(sample.get('tail_part', '').encode()).hexdigest()
    if existing_hash == content_hash:
        exists = True
        print(f"样本已存在，ID: {sample.get('id')}")
        break

if not exists:
    # 添加新样本
    new_id = max([s.get('id', 0) for s in samples], default=0) + 1
    new_sample = {
        "id": new_id,
        "tail_part": tail_part,
        "created_at": datetime.now().isoformat()
    }
    samples.append(new_sample)
    
    # 保存
    SafeFileOperation.write_json_safe(TAIL_FILTER_SAMPLES_FILE, {
        "samples": samples,
        "updated_at": datetime.now().isoformat(),
        "description": "尾部过滤训练样本 - 只保留尾部数据"
    })
    
    print(f"✅ 添加了新样本，ID: {new_id}")
    print(f"  尾部行数: {len(tail_part.splitlines())}")
    print(f"  尾部长度: {len(tail_part)} 字符")
else:
    print("样本已存在，跳过添加")

# 测试过滤器功能
print("\n测试尾部过滤器...")
from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.services.content_filter import content_filter

# 强制重新加载训练数据
intelligent_tail_filter._load_training_data(force_reload=True)

# 测试内容
test_content = f"这是一个测试消息\n\n{tail_part}"
print(f"\n测试内容长度: {len(test_content)} 字符")

# 应用过滤器
filtered = content_filter.filter_promotional_content(test_content)
print(f"过滤结果: {len(test_content)} -> {len(filtered)} 字符")
print(f"\n过滤后内容:")
print(filtered[:200] + "..." if len(filtered) > 200 else filtered)
print("\n✅ 过滤测试完成")
