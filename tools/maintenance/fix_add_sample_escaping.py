#!/usr/bin/env python3
"""
修复add_sample方法，确保新增规则时正确处理转义
"""

import re

def line_to_rule(line):
    """将一行文本转换为合适的过滤规则"""
    import re

    # 保留特定用户名的列表
    specific_usernames = ['@awen636', '@xiaoyaya6', '@YT798', '@Pyz22', '@MT0666',
                          '@dny103v', '@shuis665', '@sijiguanjia888', '@cn_zhm0']

    # 先检查是否有特定用户名
    has_specific_username = any(username in line for username in specific_usernames)

    # 开始构建规则
    rule = line

    # 1. 处理@用户名（如果不是特定用户名）
    if '@' in rule and not has_specific_username:
        # 替换通用的@用户名为模式
        rule = re.sub(r'@[a-zA-Z0-9_]+', r'@\\w+', rule)

    # 2. 处理Telegram链接
    # https://t.me/+xxx 格式
    rule = re.sub(r'https://t\.me/\+[a-zA-Z0-9_-]+', r'https://t\.me/\\+[a-zA-Z0-9_]+', rule)
    # https://t.me/xxx 格式
    rule = re.sub(r'https://t\.me/[a-zA-Z0-9_]+', r'https://t\.me/[a-zA-Z0-9_]+', rule)
    # t.me/+xxx 格式
    rule = re.sub(r't\.me/\+[a-zA-Z0-9_-]+', r't\.me/\\+[a-zA-Z0-9_]+', rule)
    # t.me/xxx 格式（不包括https://）
    rule = re.sub(r'(?<!https://)t\.me/[a-zA-Z0-9_]+', r't\.me/[a-zA-Z0-9_]+', rule)

    # 3. 转义特殊正则字符（但保留我们已经处理的模式）
    # 转义点号（但不转义已经在t\.me中的）
    rule = re.sub(r'(?<!\\)\.(?!me)', r'\.', rule)

    # 转义其他特殊字符
    special_chars = {
        '(': r'\(',
        ')': r'\)',
        '[': r'\[',
        ']': r'\]',
        '{': r'\{',
        '}': r'\}',
        '*': r'\*',
        '?': r'\?',
        '^': r'\^',
        '$': r'\$',
        '|': r'\|',
    }

    for char, escaped in special_chars.items():
        # 但不转义我们模式中的字符
        if char == '[' and '[a-zA-Z0-9_]' in rule:
            continue
        if char == ']' and '[a-zA-Z0-9_]' in rule:
            continue
        if char == '*' and r'\*' in rule:  # 已经转义的*
            continue
        rule = rule.replace(char, escaped)

    # 4. 处理空格 - 使其更灵活
    rule = re.sub(r' +', r'\\s*', rule)

    # 5. 修复可能的双转义问题
    rule = rule.replace(r'\\\\w+', r'\\w+')
    rule = rule.replace(r'\\\\s*', r'\\s*')
    rule = rule.replace(r'\\.', r'\.')

    return rule

# 测试函数
def test_conversion():
    test_cases = [
        ("😍加入我们：https://t.me/abc", "😍加入我们：https://t\\.me/[a-zA-Z0-9_]+"),
        ("免费投稿爆料：@test123", "免费投稿爆料：@\\w+"),
        ("订阅频道：@cn_zhm0", "订阅频道：@cn_zhm0"),  # 特定用户名保留
        ("便民信息：", "便民信息："),
        ("t.me/+UNWEBNeUmh84MDVl", "t\\.me/\\+[a-zA-Z0-9_]+"),
        ("【TG中文包】【大事件爆料】", "【TG中文包】【大事件爆料】"),
    ]

    print("测试line_to_rule转换:")
    for input_text, expected in test_cases:
        result = line_to_rule(input_text)
        status = "✅" if result == expected else "❌"
        print(f"{status} 输入: {input_text}")
        print(f"   期望: {expected}")
        print(f"   结果: {result}")
        if result != expected:
            print(f"   差异: 结果与期望不同")
        print()

if __name__ == "__main__":
    test_conversion()

    print("\n建议的add_sample方法修改:")
    print("""
在add_sample方法中，应该在处理每行时调用line_to_rule函数：

# 原代码（第314-317行）:
if '\\n' in tail_part:
    lines = tail_part.split('\\n')
    new_rules = [line.strip() for line in lines if line.strip()]
else:
    new_rules = rules if rules else [tail_part.strip()]

# 修改为:
if '\\n' in tail_part:
    lines = tail_part.split('\\n')
    new_rules = []
    for line in lines:
        line = line.strip()
        if line:
            # 转换为正则规则
            rule = line_to_rule(line)
            new_rules.append(rule)
else:
    if rules:
        new_rules = rules
    else:
        # 单行也需要转换
        rule = line_to_rule(tail_part.strip())
        new_rules = [rule]
""")