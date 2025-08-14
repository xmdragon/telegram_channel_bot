#!/usr/bin/env python3
"""
恢复到原始的68个高质量手动样本
"""

import json
from pathlib import Path

def restore_original_samples():
    """只保留原始的68个手动标注样本"""
    
    # 读取备份文件
    backup_file = Path('data/tail_filter_samples_backup_20250813.json')
    target_file = Path('data/tail_filter_samples.json')
    
    with open(backup_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        all_samples = data.get('samples', [])
    
    print(f"备份文件中总样本数: {len(all_samples)}")
    
    # 只保留没有source字段或source为manual的样本（原始手动样本）
    original_samples = []
    for sample in all_samples:
        # 原始样本没有source字段，或者source为manual
        if 'source' not in sample or sample.get('source') == 'manual':
            # 只保留前68个
            if len(original_samples) < 68:
                # 清理sample，只保留必要字段
                clean_sample = {
                    "id": sample.get('id', len(original_samples) + 1),
                    "tail_part": sample.get('tail_part', ''),
                    "created_at": sample.get('created_at', '')
                }
                if clean_sample['tail_part']:  # 确保有内容
                    original_samples.append(clean_sample)
    
    print(f"恢复到 {len(original_samples)} 个原始样本")
    
    # 保存清理后的数据
    with open(target_file, 'w', encoding='utf-8') as f:
        json.dump({"samples": original_samples}, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 成功恢复到原始样本")
    
    # 显示前3个样本作为验证
    print("\n前3个样本预览:")
    for i, sample in enumerate(original_samples[:3], 1):
        tail_preview = sample['tail_part'][:50] if len(sample['tail_part']) > 50 else sample['tail_part']
        print(f"  {i}. {tail_preview}...")
    
    return len(original_samples)

if __name__ == "__main__":
    total = restore_original_samples()
    print(f"\n最终样本数: {total}")