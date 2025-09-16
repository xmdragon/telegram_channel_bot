#!/usr/bin/env python3
"""
从原始tail_part内容重新生成过滤规则
1. 从git历史中提取的原始tail_part样本
2. 将每行转换为合适的规则
3. 按具体程度排序（具体的在前，通用的在后）
4. 去除重复和处理覆盖关系
"""

import json
import re
from pathlib import Path
from datetime import datetime
import subprocess

def get_original_tail_parts():
    """从git历史获取原始tail_part内容"""
    # 获取历史版本的tail_filter_samples.json
    cmd = ['git', 'show', '7ac8f50:data/training/tail/tail_filter_samples.json']
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"Failed to get historical data: {result.stderr}")

    data = json.loads(result.stdout)

    # 提取所有tail_part内容
    tail_parts = []
    for sample in data.get('samples', []):
        if 'tail_part' in sample and sample['tail_part']:
            tail_parts.append(sample['tail_part'])

    return tail_parts

def extract_lines_from_tail_parts(tail_parts):
    """从tail_part内容中提取所有有意义的行"""
    all_lines = []

    for tail_part in tail_parts:
        lines = tail_part.split('\n')
        for line in lines:
            line = line.strip()
            # 跳过空行和纯分隔符行
            if not line:
                continue
            # 跳过纯emoji或符号分隔行
            if all(c in '—〰️😉👌😒😶‍🌫️➖✝️' for c in line):
                continue
            # 跳过过短的纯emoji行
            if len(line) < 3 and all(ord(c) > 0x1F000 for c in line):
                continue

            all_lines.append(line)

    return all_lines

def line_to_rule(line):
    """将一行文本转换为合适的过滤规则"""
    original_line = line

    # 先检查是否包含需要转换为模式的内容
    has_username = '@' in line
    has_tg_link = 't.me/' in line or 'https://t.me/' in line

    # 保留特定用户名的列表
    specific_usernames = ['@awen636', '@xiaoyaya6', '@YT798', '@Pyz22', '@MT0666',
                          '@dny103v', '@shuis665', '@sijiguanjia888', '@cn_zhm0']
    has_specific_username = any(username in line for username in specific_usernames)

    if has_username and not has_specific_username:
        # 替换通用的@用户名为模式
        line = re.sub(r'@[a-zA-Z0-9_]+', r'@\\w+', line)

    if has_tg_link:
        # 处理Telegram链接模式
        # https://t.me/+xxx 格式
        line = re.sub(r'https://t\.me/\+[a-zA-Z0-9_-]+', r'https://t\\.me/\\+[a-zA-Z0-9_]+', line)
        # https://t.me/xxx 格式
        line = re.sub(r'https://t\.me/[a-zA-Z0-9_]+', r'https://t\\.me/[a-zA-Z0-9_]+', line)
        # t.me/+xxx 格式
        line = re.sub(r't\.me/\+[a-zA-Z0-9_-]+', r't\\.me/\\+[a-zA-Z0-9_]+', line)
        # t.me/xxx 格式
        line = re.sub(r't\.me/[a-zA-Z0-9_]+', r't\\.me/[a-zA-Z0-9_]+', line)

    # 现在转义特殊字符（但保留我们已经添加的正则模式）
    # 需要转义的字符
    chars_to_escape = ['.', '(', ')', '[', ']', '{', '}', '*', '+', '?', '^', '$', '|', '-']
    for char in chars_to_escape:
        # 但不转义我们的模式中的字符
        if char == '.' and r't\\.me' in line:
            continue  # 已经处理了
        if char == '+' and (r'\\w+' in line or r'[a-zA-Z0-9_]+' in line or r'\\+' in line):
            continue  # 是我们的模式的一部分
        if char == '[' and r'[a-zA-Z0-9_]' in line:
            continue
        if char == ']' and r'[a-zA-Z0-9_]' in line:
            continue
        if char == '-' and r'[a-zA-Z0-9_-]' in line:
            continue

        line = line.replace(char, '\\' + char)

    # 处理可选的空格（但保留原有的语义）
    line = re.sub(r' {2,}', r'\\s*', line)  # 多个空格变为\s*
    line = re.sub(r' ', r'\\s*', line)      # 单个空格也变为\s*（更宽松的匹配）

    return line

def calculate_rule_specificity(rule):
    """计算规则的具体程度（数字越大越具体）"""
    score = 0

    # 纯文本（没有正则符号）最具体
    regex_chars = ['\\w', '\\s', '\\d', '[', ']', '(', ')', '+', '*', '?', '^', '$']
    if not any(char in rule for char in regex_chars):
        score += 1000

    # 包含具体中文字符的更具体
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', rule))
    score += chinese_chars * 10

    # 包含具体标点的更具体
    if any(char in rule for char in ['：', '，', '。', '！', '？', '【', '】']):
        score += 50

    # 包含emoji的更具体
    emoji_count = sum(1 for char in rule if ord(char) > 0x1F300)
    score += emoji_count * 20

    # 包含具体用户名或频道名的更具体
    if '@' in rule and '\\w+' not in rule:
        score += 300  # 具体的用户名

    # 包含具体URL的更具体
    if 't.me/' in rule and '[a-zA-Z0-9_]+' not in rule:
        score += 250

    # 正则通配符越多越不具体
    wildcards = rule.count('\\w+') + rule.count('\\s*') + rule.count('[a-zA-Z0-9_]+')
    score -= wildcards * 30

    # 特别通用的规则得分很低
    if rule == '@\\w+':
        score = -1000
    elif rule == 't\\.me/[a-zA-Z0-9_]+':
        score = -900
    elif rule == 'https://t\\.me/[a-zA-Z0-9_]+':
        score = -850
    elif rule == 't\\.me/\\+[a-zA-Z0-9_]+':
        score = -880
    elif rule in ['订阅', '订阅频道', '订阅\\s*频道']:
        score = -700
    elif rule in ['便民信息', '便民信息：', '便民信息\\s*：']:
        score = -600
    elif '订阅' in rule and '频道' in rule and chinese_chars < 10:
        score = -500

    return score

def remove_duplicates_and_subpatterns(rules_with_scores):
    """去除重复规则和被包含的子模式"""
    # 按分数排序（高分在前）
    rules_with_scores.sort(key=lambda x: x[1], reverse=True)

    final_rules = []
    seen_rules = set()

    for rule, score in rules_with_scores:
        # 跳过已见过的完全相同规则
        if rule in seen_rules:
            continue

        # 检查是否被更具体的规则覆盖
        is_covered = False
        for existing_rule, existing_score in final_rules:
            # 如果当前规则更通用且可能匹配更具体的规则，跳过
            if score < existing_score:
                # 简单的包含检查
                if rule in existing_rule:
                    is_covered = True
                    break
                # 检查是否是更通用的模式
                if rule == '@\\w+' and '@' in existing_rule:
                    is_covered = True
                    break

        if not is_covered:
            final_rules.append((rule, score))
            seen_rules.add(rule)

    return final_rules

def main():
    print("=== 从原始tail_part内容重新生成过滤规则 ===\n")

    # 1. 获取原始tail_part内容
    print("1. 从git历史获取原始tail_part内容...")
    tail_parts = get_original_tail_parts()
    print(f"   找到 {len(tail_parts)} 个原始tail_part样本")

    # 2. 提取所有有意义的行
    print("\n2. 提取所有有意义的行...")
    lines = extract_lines_from_tail_parts(tail_parts)
    print(f"   提取了 {len(lines)} 行内容")

    # 3. 转换为规则
    print("\n3. 将每行转换为过滤规则...")
    rules = []
    for line in lines:
        rule = line_to_rule(line)
        rules.append(rule)

    # 去重
    unique_rules = list(set(rules))
    print(f"   生成了 {len(unique_rules)} 条唯一规则（去重前 {len(rules)} 条）")

    # 4. 计算具体程度并排序
    print("\n4. 计算规则具体程度并排序...")
    rules_with_scores = [(rule, calculate_rule_specificity(rule)) for rule in unique_rules]

    # 5. 去除被覆盖的子模式
    print("\n5. 去除被覆盖的子模式...")
    final_rules = remove_duplicates_and_subpatterns(rules_with_scores)
    print(f"   最终保留 {len(final_rules)} 条规则")

    # 显示排序结果示例
    print("\n排序后的规则（前10个最具体的）:")
    for rule, score in final_rules[:10]:
        display_rule = rule[:60] + '...' if len(rule) > 60 else rule
        print(f"  得分 {score:4d}: {display_rule}")

    print("\n排序后的规则（后10个最通用的）:")
    for rule, score in final_rules[-10:]:
        display_rule = rule[:60] + '...' if len(rule) > 60 else rule
        print(f"  得分 {score:4d}: {display_rule}")

    # 6. 保存结果
    rules_file = Path('/home/grom/telegram_channel_bot/data/training/tail/tail_filter_samples.json')

    # 备份当前文件
    backup_file = rules_file.with_suffix('.json.backup_regenerated')
    with open(rules_file, 'r', encoding='utf-8') as f:
        current_data = json.load(f)
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(current_data, f, ensure_ascii=False, indent=2)
    print(f"\n6. 当前规则已备份到: {backup_file}")

    # 准备新数据
    new_data = {
        'rules': [rule for rule, score in final_rules],
        'updated_at': datetime.now().isoformat(),
        'total_count': len(final_rules)
    }

    # 保存新规则
    with open(rules_file, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 规则重新生成完成！")
    print(f"   - 原始样本: {len(tail_parts)} 个")
    print(f"   - 提取行数: {len(lines)} 行")
    print(f"   - 生成规则: {len(unique_rules)} 条")
    print(f"   - 最终规则: {len(final_rules)} 条")
    print(f"   - 保存位置: {rules_file}")

if __name__ == '__main__':
    main()