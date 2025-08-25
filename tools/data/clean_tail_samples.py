#!/usr/bin/env python3
"""
清理尾部过滤样本数据
- 移除包含大量正文的样本，只保留纯尾部推广内容
- 去重复ID
- 按ID排序
"""

import json
import sys
from pathlib import Path

def is_pure_tail_content(tail_part: str) -> bool:
    """
    判断是否为纯尾部内容（不包含大量正文）
    """
    if not tail_part:
        return False
    
    lines = tail_part.strip().split('\n')
    
    # 如果内容太长（超过200字符）且包含句号、句子结构，可能包含正文
    if len(tail_part) > 200:
        sentence_indicators = ['。', '，', '？', '！', '；', '：']
        sentence_count = sum(1 for char in tail_part if char in sentence_indicators)
        
        # 如果标点符号太多，可能是正文内容
        if sentence_count > 5:
            return False
        
        # 检查是否包含明显的正文内容关键词
        body_keywords = ['专家', '听证会', '宪法法院', '兄弟们', '帖子', '年前', '追查']
        if any(keyword in tail_part for keyword in body_keywords):
            return False
    
    # 检查是否包含明显的推广关键词
    promo_keywords = [
        '📣', '订阅', '频道', '@', '💬', '商务', '对接', '联系', 
        '😍', '投稿', '澄清', '爆料', '🔗', 't.me', 'https://', 
        '☎️', '免费', '♾', '🔔', '👌', '➡️', '点击', '加入'
    ]
    
    has_promo_content = any(keyword in tail_part for keyword in promo_keywords)
    
    # 如果没有推广关键词且内容很长，可能不是纯尾部
    if not has_promo_content and len(tail_part) > 200:
        return False
    
    return True

def clean_tail_samples(input_file: Path, output_file: Path):
    """清理尾部样本数据"""
    
    # 读取原始数据
    print(f"读取原始数据: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    original_samples = data.get('samples', [])
    print(f"原始样本数量: {len(original_samples)}")
    
    # 清理数据
    seen_ids = set()
    cleaned_samples = []
    removed_samples = []
    
    for sample in original_samples:
        sample_id = sample.get('id')
        tail_part = sample.get('tail_part', '')
        
        # 跳过重复ID
        if sample_id in seen_ids:
            print(f"跳过重复ID: {sample_id}")
            removed_samples.append({
                'id': sample_id,
                'reason': 'duplicate_id',
                'tail_part': tail_part[:100] + '...' if len(tail_part) > 100 else tail_part
            })
            continue
            
        # 检查是否为纯尾部内容
        if not is_pure_tail_content(tail_part):
            print(f"移除包含正文的样本 ID {sample_id}: {tail_part[:50]}...")
            removed_samples.append({
                'id': sample_id,
                'reason': 'contains_body_text',
                'tail_part': tail_part[:100] + '...' if len(tail_part) > 100 else tail_part
            })
            continue
        
        seen_ids.add(sample_id)
        cleaned_samples.append(sample)
    
    # 按ID排序
    cleaned_samples.sort(key=lambda x: x.get('id', 0))
    
    print(f"清理后样本数量: {len(cleaned_samples)}")
    print(f"移除样本数量: {len(removed_samples)}")
    
    # 保存清理后的数据
    cleaned_data = {
        'samples': cleaned_samples,
        'updated_at': data.get('updated_at'),
        'total_count': len(cleaned_samples),
        'cleaning_info': {
            'original_count': len(original_samples),
            'cleaned_count': len(cleaned_samples),
            'removed_count': len(removed_samples),
            'removed_samples': removed_samples[:10]  # 只保存前10个被移除的样本信息
        }
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
    
    print(f"清理后的数据已保存到: {output_file}")
    
    # 显示被移除的样本详情
    if removed_samples:
        print("\n被移除的样本:")
        for sample in removed_samples[:5]:  # 显示前5个
            print(f"  ID {sample['id']} ({sample['reason']}): {sample['tail_part']}")

if __name__ == '__main__':
    input_file = Path('data/training/tail/tail_filter_samples.json')
    output_file = input_file  # 直接覆盖原文件
    
    clean_tail_samples(input_file, output_file)
    print("✅ 数据清理完成！")