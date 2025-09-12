#!/usr/bin/env python3
"""
清理尾部过滤样本文件，只保留核心字段
"""
import json
import os
import shutil
from datetime import datetime

def clean_tail_samples():
    """清理尾部过滤样本文件中的多余字段"""
    
    # 样本文件路径
    samples_file = "/home/grom/telegram_channel_bot/data/training/tail/tail_filter_samples.json"
    
    if not os.path.exists(samples_file):
        print(f"样本文件不存在: {samples_file}")
        return
    
    # 创建备份
    backup_file = f"{samples_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(samples_file, backup_file)
    print(f"已创建备份: {backup_file}")
    
    # 读取样本
    with open(samples_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    samples = data.get('samples', [])
    print(f"原始样本数量: {len(samples)}")
    
    # 需要保留的核心字段
    core_fields = {'id', 'tail_part', 'rules', 'created_at'}
    
    # 清理样本
    cleaned_samples = []
    for sample in samples:
        # 只保留核心字段
        cleaned_sample = {
            key: value for key, value in sample.items() 
            if key in core_fields
        }
        
        # 确保必要字段存在
        if 'id' not in cleaned_sample:
            cleaned_sample['id'] = len(cleaned_samples) + 1
        if 'tail_part' not in cleaned_sample:
            # 尝试从旧字段获取
            cleaned_sample['tail_part'] = sample.get('tailPart', sample.get('ad_part', ''))
        if 'rules' not in cleaned_sample:
            cleaned_sample['rules'] = []
        if 'created_at' not in cleaned_sample:
            cleaned_sample['created_at'] = datetime.now().isoformat()
        
        # 只添加有实际内容的样本
        if cleaned_sample.get('tail_part'):
            cleaned_samples.append(cleaned_sample)
    
    print(f"清理后样本数量: {len(cleaned_samples)}")
    
    # 统计被删除的字段
    removed_fields = set()
    for sample in samples:
        for key in sample.keys():
            if key not in core_fields:
                removed_fields.add(key)
    
    if removed_fields:
        print(f"删除的字段: {', '.join(sorted(removed_fields))}")
    
    # 保存清理后的数据
    with open(samples_file, 'w', encoding='utf-8') as f:
        json.dump({"samples": cleaned_samples}, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 样本文件已清理完成")
    print(f"   保留字段: {', '.join(core_fields)}")
    print(f"   原始样本: {len(samples)}")
    print(f"   清理后: {len(cleaned_samples)}")

if __name__ == "__main__":
    clean_tail_samples()