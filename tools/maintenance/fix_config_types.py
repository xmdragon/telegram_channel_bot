#!/usr/bin/env python3
"""
修复system.json配置类型不一致问题
Linus原则：消除特殊情况，让数据类型与值保持一致
"""

import json
from pathlib import Path


def fix_system_config():
    """修复system.json中的类型不一致问题"""
    config_path = Path(__file__).parent.parent.parent / "data/config/system.json"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 需要修复的配置项及其正确类型
    fixes = {
        # 整数类型修复
        "source.history_limit": {
            "config_type": "integer",
            "description": "首次采集频道时获取的历史消息条数"
        },
        
        # 布尔类型修复（带描述）
        "filter.footer_promo_enabled": {
            "config_type": "boolean", 
            "description": "启用尾部推广过滤"
        },
        "filter.markdown_enabled": {
            "config_type": "boolean",
            "description": "启用Markdown格式过滤"
        },
        "filter.promo_vector_enabled": {
            "config_type": "boolean",
            "description": "启用推广向量检测"
        },
        "filter.duplicate_enabled": {
            "config_type": "boolean",
            "description": "启用重复内容检测"
        },
        "review.auto_reject_duplicates": {
            "config_type": "boolean",
            "description": "自动拒绝重复消息"
        }
    }
    
    # 应用修复
    fixed_count = 0
    for key, fix in fixes.items():
        if key in config:
            old_type = config[key]["config_type"]
            config[key]["config_type"] = fix["config_type"]
            
            # 添加或更新描述
            if fix.get("description"):
                config[key]["description"] = fix["description"]
            
            # 确保值与类型一致
            value = config[key]["value"]
            if fix["config_type"] == "boolean":
                # 将字符串"true"/"false"保持为字符串（系统设计）
                if value not in ["true", "false"]:
                    config[key]["value"] = "false"
            elif fix["config_type"] == "integer":
                # 确保整数值是字符串格式的数字
                try:
                    int(value)
                except ValueError:
                    config[key]["value"] = "0"
            
            if old_type != fix["config_type"]:
                print(f"✅ 修复 {key}: {old_type} → {fix['config_type']}")
                fixed_count += 1
    
    # 处理重复配置：删除target.auto_forward_enabled（保留review.auto_forward_enabled）
    if "target.auto_forward_enabled" in config and "review.auto_forward_enabled" in config:
        # 确保review版本有正确的值
        if config["target.auto_forward_enabled"]["value"] == "true":
            config["review.auto_forward_enabled"]["value"] = "true"
        del config["target.auto_forward_enabled"]
        print("✅ 删除重复配置: target.auto_forward_enabled")
        fixed_count += 1
    
    # 保存修复后的配置
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 修复完成: {fixed_count} 个配置项")
    return fixed_count


def verify_config():
    """验证配置类型一致性"""
    config_path = Path(__file__).parent.parent.parent / "data/config/system.json"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    issues = []
    for key, item in config.items():
        value = item["value"]
        config_type = item["config_type"]
        
        # 检查类型一致性
        if config_type == "boolean":
            if value not in ["true", "false"]:
                issues.append(f"{key}: 布尔类型但值为 '{value}'")
        elif config_type == "integer":
            try:
                int(value)
            except ValueError:
                issues.append(f"{key}: 整数类型但值为 '{value}'")
        
        # 检查描述是否为空
        if not item.get("description"):
            issues.append(f"{key}: 缺少描述")
    
    if issues:
        print("\n⚠️ 发现问题:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✅ 配置验证通过")
    
    return len(issues) == 0


if __name__ == "__main__":
    print("🔧 开始修复system.json配置类型...")
    print("-" * 50)
    
    # 执行修复
    fix_system_config()
    
    print("\n🔍 验证配置...")
    print("-" * 50)
    
    # 验证结果
    if verify_config():
        print("\n🎯 所有配置类型已修复并验证通过")
    else:
        print("\n⚠️ 仍有配置问题需要手动检查")