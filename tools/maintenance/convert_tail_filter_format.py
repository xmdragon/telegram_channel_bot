#!/usr/bin/env python3
"""
转换尾部过滤样本格式
从以tail_part为单位转换为以rules为单位
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.path_config import PathConfig


def convert_tail_filter_format():
    """转换尾部过滤样本格式"""
    
    # 文件路径
    samples_file = PathConfig.DATA_DIR / "training" / "tail" / "tail_filter_samples.json"
    
    # 读取现有数据
    print("读取现有数据...")
    with open(samples_file, 'r', encoding='utf-8') as f:
        old_data = json.load(f)
    
    samples = old_data.get('samples', [])
    print(f"发现 {len(samples)} 个样本")
    
    # 收集所有唯一规则
    all_rules = set()
    rule_sources = {}  # 记录每个规则的来源样本
    
    for sample in samples:
        rules = sample.get('rules', [])
        sample_id = sample.get('id', 'unknown')
        
        for rule in rules:
            if rule:  # 忽略空规则
                all_rules.add(rule)
                if rule not in rule_sources:
                    rule_sources[rule] = []
                rule_sources[rule].append(sample_id)
    
    # 转换为列表并排序（保持稳定性）
    unique_rules = sorted(list(all_rules))
    
    print(f"提取到 {len(unique_rules)} 个唯一规则")
    
    # 统计重复情况
    duplicated_rules = {rule: len(sources) for rule, sources in rule_sources.items() if len(sources) > 1}
    if duplicated_rules:
        print(f"发现 {len(duplicated_rules)} 个重复规则:")
        for rule, count in sorted(duplicated_rules.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {count}次: {rule[:50]}..." if len(rule) > 50 else f"  {count}次: {rule}")
    
    # 统计原始规则数（用于打印信息）
    original_rule_count = sum(len(s.get('rules', [])) for s in samples)

    # 创建新格式数据
    new_data = {
        "rules": unique_rules,
        "updated_at": datetime.now().isoformat(),
        "total_count": len(unique_rules)
    }

    # 保存新格式数据
    print("\n保存新格式数据...")
    with open(samples_file, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 转换完成！")
    print(f"   原始规则数: {original_rule_count}")
    print(f"   唯一规则数: {len(unique_rules)}")
    print(f"   减少了: {original_rule_count - len(unique_rules)} 个重复规则")
    print(f"   文件已保存到: {samples_file}")
    
    return new_data


if __name__ == "__main__":
    try:
        convert_tail_filter_format()
    except Exception as e:
        print(f"❌ 转换失败: {e}")
        sys.exit(1)