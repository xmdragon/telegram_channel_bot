#!/usr/bin/env python3
"""
分隔符模式保存工具 - 确保正则表达式正确保存到JSON
"""
import json
import re
from pathlib import Path

def save_separator_patterns(patterns_list, output_file=None):
    """
    保存分隔符模式到JSON文件
    
    Args:
        patterns_list: 模式列表，每个元素为 (regex, description) 元组
        output_file: 输出文件路径，默认为配置文件位置
    """
    if output_file is None:
        output_file = Path("/home/grom/telegram_channel_bot/data/training/tail/separator_patterns.json")
    
    patterns_data = {
        "patterns": [],
        "updated_at": "",
        "total_count": 0
    }
    
    for regex, description in patterns_list:
        # 验证正则表达式是否有效
        try:
            re.compile(regex)
        except re.error as e:
            print(f"无效的正则表达式: {regex}")
            print(f"错误: {e}")
            continue
        
        patterns_data["patterns"].append({
            "regex": regex,
            "description": description
        })
    
    # 更新统计信息
    from datetime import datetime
    patterns_data["updated_at"] = datetime.now().isoformat()
    patterns_data["total_count"] = len(patterns_data["patterns"])
    
    # 保存到文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(patterns_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已保存 {len(patterns_data['patterns'])} 个分隔符模式到: {output_file}")
    return patterns_data

def get_default_patterns():
    """获取默认的分隔符模式"""
    return [
        # emoji包裹推广内容
        (r"[\U0001F300-\U0001F9FF\u2600-\u27BF]{5,}[\s\S]*?[\U0001F300-\U0001F9FF\u2600-\u27BF]{5,}", 
         "emoji包裹推广内容"),
        
        # 符号包裹推广内容 - 注意：字符集内的方括号不需要转义
        (r"[━═─▬\-—=*+~_|<>#{}[\]().,:;'\"!?@#$%^&]{5,}[\s\S]*?[━═─▬\-—=*+~_|<>#{}[\]().,:;'\"!?@#$%^&]{5,}", 
         "符号包裹推广内容"),
        
        # 连续emoji内容
        (r"[\U0001F300-\U0001F9FF\u2600-\u27BF]{5,}", 
         "连续emoji内容"),
    ]

if __name__ == "__main__":
    # 使用默认模式更新配置文件
    patterns = get_default_patterns()
    save_separator_patterns(patterns)
    
    # 验证保存的内容
    config_file = Path("/home/grom/telegram_channel_bot/data/training/tail/separator_patterns.json")
    with open(config_file, 'r', encoding='utf-8') as f:
        saved_data = json.load(f)
    
    print("\n验证保存的正则：")
    for pattern_data in saved_data["patterns"]:
        regex = pattern_data["regex"]
        desc = pattern_data["description"]
        try:
            compiled = re.compile(regex)
            print(f"✅ {desc}: 正则有效")
        except re.error as e:
            print(f"❌ {desc}: 正则无效 - {e}")