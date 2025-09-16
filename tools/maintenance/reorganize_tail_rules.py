#!/usr/bin/env python3
"""
重新组织尾部过滤规则
1. 将多行规则按行分割
2. 按规则的具体程度排序（具体的在前，通用的在后）
3. 去除重复规则
"""

import json
import re
from pathlib import Path
from datetime import datetime

def split_multiline_rules(rules):
    """将包含换行符的规则按行分割"""
    new_rules = []
    for rule in rules:
        if '\n' in rule:
            # 分割多行规则
            lines = rule.split('\n')
            for line in lines:
                line = line.strip()
                if line:
                    new_rules.append(line)
        else:
            new_rules.append(rule)
    return new_rules

def calculate_rule_specificity(rule):
    """计算规则的具体程度（数字越大越具体）"""
    score = 0

    # 纯文本（没有正则符号）最具体
    if not any(char in rule for char in ['\\', '[', ']', '(', ')', '+', '*', '?', '.', '^', '$']):
        score += 1000

    # 包含具体文字的更具体
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', rule))
    score += chinese_chars * 10

    # 包含具体符号的更具体
    if '：' in rule or '，' in rule or '。' in rule:
        score += 50

    # 包含emoji的更具体
    if any(ord(char) > 0x1F000 for char in rule):
        score += 100

    # 正则通配符越多越不具体
    wildcards = rule.count('\\w+') + rule.count('\\s*') + rule.count('[a-zA-Z0-9_]+')
    score -= wildcards * 20

    # 特别通用的规则得分很低
    if rule == '@\\w+':
        score = -1000
    elif rule == '订阅\\s*频道\\s*↓':
        score = -900
    elif rule == 'https://t\\\\.me/[a-zA-Z0-9_]+':
        score = -800
    elif rule == 't\\\\.me/[a-zA-Z0-9_]+':
        score = -850
    elif rule == 't\\\\.me/\\+[a-zA-Z0-9_]+':
        score = -820
    elif rule == '便民信息：':
        score = -700
    elif rule == '测试规则':
        score = -600

    # 包含具体@用户名的比通用@\w+具体
    if '@' in rule and rule != '@\\w+':
        if '\\w+' not in rule:
            score += 200  # 具体用户名
        else:
            score += 50   # 带前缀/后缀的@\w+

    return score

def remove_duplicate_rules(rules):
    """去除重复的规则"""
    seen = set()
    unique_rules = []
    for rule in rules:
        if rule not in seen:
            seen.add(rule)
            unique_rules.append(rule)
    return unique_rules

def check_rule_coverage(rules):
    """检查规则覆盖关系"""
    coverage_issues = []

    for i, rule1 in enumerate(rules):
        for j, rule2 in enumerate(rules):
            if i >= j:
                continue

            # 简单检查：如果rule1包含在rule2中，或者rule1是rule2的子模式
            try:
                # 对于简单的包含关系
                if rule1 in rule2 and rule1 != rule2:
                    coverage_issues.append(f"规则 '{rule1}' 包含在 '{rule2}' 中")

                # 对于正则模式的覆盖（简化检查）
                if rule1 == '@\\w+' and '@' in rule2 and '\\w+' in rule2:
                    coverage_issues.append(f"通用规则 '{rule1}' 会匹配 '{rule2}'")

            except Exception as e:
                pass

    return coverage_issues

def main():
    # 读取当前规则
    rules_file = Path('/home/grom/telegram_channel_bot/data/training/tail/tail_filter_samples.json')

    with open(rules_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rules = data.get('rules', [])
    print(f"原始规则数量: {len(rules)}")

    # 1. 分割多行规则
    rules = split_multiline_rules(rules)
    print(f"分割多行后规则数量: {len(rules)}")

    # 2. 去除重复
    rules = remove_duplicate_rules(rules)
    print(f"去重后规则数量: {len(rules)}")

    # 3. 按具体程度排序（具体的在前，通用的在后）
    rules_with_scores = [(rule, calculate_rule_specificity(rule)) for rule in rules]
    rules_with_scores.sort(key=lambda x: x[1], reverse=True)

    # 打印排序结果示例
    print("\n排序后的规则（前10个最具体的）:")
    for rule, score in rules_with_scores[:10]:
        print(f"  得分{score:4d}: {rule[:50]}..." if len(rule) > 50 else f"  得分{score:4d}: {rule}")

    print("\n排序后的规则（后10个最通用的）:")
    for rule, score in rules_with_scores[-10:]:
        print(f"  得分{score:4d}: {rule[:50]}..." if len(rule) > 50 else f"  得分{score:4d}: {rule}")

    # 只保留规则，不要分数
    sorted_rules = [rule for rule, score in rules_with_scores]

    # 4. 检查覆盖问题
    coverage_issues = check_rule_coverage(sorted_rules)
    if coverage_issues:
        print("\n检测到的覆盖问题（前10个）:")
        for issue in coverage_issues[:10]:
            print(f"  - {issue}")

    # 5. 保存重新组织后的规则
    data['rules'] = sorted_rules
    data['updated_at'] = datetime.now().isoformat()
    data['total_count'] = len(sorted_rules)

    # 备份原文件
    backup_file = rules_file.with_suffix('.json.backup')
    with open(backup_file, 'w', encoding='utf-8') as f:
        with open(rules_file, 'r', encoding='utf-8') as orig:
            f.write(orig.read())
    print(f"\n原文件已备份到: {backup_file}")

    # 保存新文件
    with open(rules_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"规则已重新组织并保存，共 {len(sorted_rules)} 条规则")

if __name__ == '__main__':
    main()