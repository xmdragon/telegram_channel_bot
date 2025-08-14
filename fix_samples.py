import sys
import json
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from pathlib import Path
from app.core.training_config import TrainingDataConfig
from app.utils.safe_file_ops import SafeFileOperation
from datetime import datetime

# 加载现有样本
TAIL_FILTER_SAMPLES_FILE = TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE
data = SafeFileOperation.read_json_safe(TAIL_FILTER_SAMPLES_FILE)
samples = data.get("samples", []) if data else []

print(f"当前样本数量: {len(samples)}")

# 修正样本47和48 - 只保留真正的尾部广告部分
correct_tail = """🛎失联导航：@Wdubai
✅订阅频道：@dubai0
🙋‍♂️便民信息：
【[迪拜互助群](https://t.me/+PquyxdGQsXEwZjUx)】【[TG中文包](tg://setlanguage?lang=classic-zh-cn)】【[签证查询](https://smartservices.icp.gov.ae/echannels/web/client/default.html?from=timeline&isappinstalled=0#/fileValidity)】"""

# 找到并修正样本47和48
fixed_count = 0
for sample in samples:
    if sample['id'] in [47, 48]:
        old_length = len(sample['tail_part'])
        sample['tail_part'] = correct_tail
        sample['updated_at'] = datetime.now().isoformat()
        print(f"修正样本 ID {sample['id']}: {old_length} -> {len(correct_tail)} 字符")
        fixed_count += 1

if fixed_count > 0:
    # 保存修正后的数据
    SafeFileOperation.write_json_safe(TAIL_FILTER_SAMPLES_FILE, {
        "samples": samples,
        "updated_at": datetime.now().isoformat(),
        "description": "尾部过滤训练样本 - 只保留尾部数据"
    })
    print(f"\n✅ 成功修正 {fixed_count} 个样本")
else:
    print("未找到需要修正的样本")

# 显示修正后的样本
print("\n修正后的迪拜相关样本:")
for sample in samples:
    if 'Wdubai' in sample.get('tail_part', ''):
        print(f"\nID: {sample['id']}")
        print(f"尾部长度: {len(sample['tail_part'])} 字符")
        print(f"尾部行数: {len(sample['tail_part'].splitlines())} 行")