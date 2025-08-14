#!/usr/bin/env python3
"""
将智能过滤器内存中学习的样本保存到文件
"""

import json
from datetime import datetime
from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.core.training_config import TrainingDataConfig

def save_learned_samples():
    """保存内存中学习的样本到文件"""
    
    # 读取现有文件数据
    tail_file = TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE
    with open(tail_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        existing_samples = data.get('samples', [])
    
    print(f"文件中现有样本: {len(existing_samples)} 个")
    
    # 获取内存中的所有样本
    memory_samples = intelligent_tail_filter.tail_samples
    print(f"内存中总样本: {len(memory_samples)} 个")
    
    # 找出新增的样本（不在文件中的）
    existing_tails = {s.get('tail_part', '').strip() for s in existing_samples if s.get('tail_part')}
    
    new_samples = []
    sample_id = len(existing_samples) + 1
    
    for tail in memory_samples:
        tail_stripped = tail.strip()
        if tail_stripped and tail_stripped not in existing_tails:
            new_samples.append({
                "id": sample_id,
                "tail_part": tail,
                "created_at": datetime.now().isoformat(),
                "source": "batch_filter_learning"  # 标记来源
            })
            existing_tails.add(tail_stripped)
            sample_id += 1
    
    print(f"新增样本: {len(new_samples)} 个")
    
    if new_samples:
        # 合并样本
        all_samples = existing_samples + new_samples
        
        # 保存到文件
        with open(tail_file, 'w', encoding='utf-8') as f:
            json.dump({"samples": all_samples}, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 成功保存 {len(all_samples)} 个样本到文件")
        
        # 统计信息
        stats = intelligent_tail_filter.get_statistics()
        print(f"\n📊 模型统计:")
        print(f"  • 总样本数: {stats['total_samples']}")
        print(f"  • 学习关键词: {stats['learned_keywords']}")
        print(f"  • 特征数量: {stats['feature_count']}")
    else:
        print("✅ 没有新样本需要保存")
    
    return len(all_samples) if new_samples else len(existing_samples)

if __name__ == "__main__":
    total = save_learned_samples()
    print(f"\n最终文件中样本总数: {total}")