#!/usr/bin/env python3
"""
修复尾部过滤规则中的转义问题
主要修复：
1. 双反斜杠点号 \\\\. -> \\.
2. 字符类中多余的反斜杠 [a\\-zA\\-Z0\\-9_] -> [a-zA-Z0-9_]
3. \\w\\+ -> \\w+
"""

import json
import re
from pathlib import Path
from datetime import datetime

def fix_rule_escaping(rule):
    """修复规则中的转义问题"""
    original_rule = rule

    # 1. 修复双反斜杠点号
    rule = rule.replace(r'\\.', r'\.')

    # 2. 修复字符类中的多余反斜杠
    # [a\-zA\-Z0\-9_] -> [a-zA-Z0-9_]
    rule = rule.replace(r'[a\-zA\-Z0\-9_]', r'[a-zA-Z0-9_]')

    # 3. 修复 \w\+ -> \w+
    rule = rule.replace(r'\w\+', r'\w+')

    # 4. 修复其他常见的过度转义
    # 修复字符类中的连字符
    rule = re.sub(r'\[([^\]]*?)\\-([^\]]*?)\]', r'[\1-\2]', rule)

    # 5. 修复多余的反斜杠（但保留必要的转义）
    # 保留这些必要的转义: \s \w \d \. \+ \* \? \( \) \[ \] \{ \}
    # 不需要转义的字符: : ： ， 。 ！ ？ 【 】 、 / @ # $ % & = _ -

    # 修复中文标点不需要的转义
    unnecessary_escapes = {
        r'\：': '：',
        r'\，': '，',
        r'\。': '。',
        r'\！': '！',
        r'\？': '？',
        r'\【': '【',
        r'\】': '】',
        r'\（': '（',
        r'\）': '）',
        r'\/': '/',
        r'\@': '@',
        r'\#': '#',
        r'\&': '&',
        r'\=': '=',
        r'\_': '_',
    }

    for escaped, unescaped in unnecessary_escapes.items():
        rule = rule.replace(escaped, unescaped)

    return rule

def test_rule(rule, test_samples):
    """测试规则是否能正确匹配"""
    results = []
    for sample in test_samples:
        try:
            match = bool(re.search(rule, sample))
            results.append((sample, match))
        except Exception as e:
            results.append((sample, f"Error: {e}"))
    return results

def main():
    print("=== 修复尾部过滤规则转义问题 ===\n")

    # 读取当前规则
    rules_file = Path('/home/grom/telegram_channel_bot/data/training/tail/tail_filter_samples.json')

    with open(rules_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rules = data.get('rules', [])
    print(f"原始规则数量: {len(rules)}")

    # 统计需要修复的规则
    rules_to_fix = []
    for i, rule in enumerate(rules):
        if (r'\\.' in rule or
            r'[a\-zA\-Z0\-9_]' in rule or
            r'\w\+' in rule or
            any(esc in rule for esc in [r'\：', r'\，', r'\。', r'\！', r'\？'])):
            rules_to_fix.append(i)

    print(f"需要修复的规则数量: {len(rules_to_fix)}")

    # 修复规则
    fixed_rules = []
    fix_count = 0

    for i, rule in enumerate(rules):
        original_rule = rule
        fixed_rule = fix_rule_escaping(rule)

        if original_rule != fixed_rule:
            fix_count += 1
            print(f"\n修复规则 {i}:")
            print(f"  原始: {original_rule[:60]}..." if len(original_rule) > 60 else f"  原始: {original_rule}")
            print(f"  修复: {fixed_rule[:60]}..." if len(fixed_rule) > 60 else f"  修复: {fixed_rule}")

        fixed_rules.append(fixed_rule)

    print(f"\n总共修复了 {fix_count} 条规则")

    # 测试一些典型的修复案例
    print("\n测试修复后的规则:")
    test_samples = [
        ('😍加入我们：https://t.me/abc', r'😍加入我们：https://t\.me/[a-zA-Z0-9_]+'),
        ('@test123', r'@\w+'),
        ('便民信息：', r'便民信息：'),
    ]

    for sample, pattern in test_samples:
        # 在修复后的规则中查找匹配的规则
        for rule in fixed_rules:
            if pattern in rule or rule == pattern:
                try:
                    match = bool(re.search(rule, sample))
                    print(f"  '{sample}' 匹配规则 '{rule[:40]}...': {match}")
                    break
                except:
                    pass

    # 备份原文件
    backup_file = rules_file.with_suffix('.json.backup_before_escaping_fix')
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n原文件已备份到: {backup_file}")

    # 保存修复后的规则
    data['rules'] = fixed_rules
    data['updated_at'] = datetime.now().isoformat()
    # 删除metadata字段（如果存在）
    if 'metadata' in data:
        del data['metadata']

    with open(rules_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 规则转义问题修复完成！")
    print(f"   - 总规则数: {len(fixed_rules)}")
    print(f"   - 修复规则数: {fix_count}")
    print(f"   - 保存位置: {rules_file}")

if __name__ == '__main__':
    main()