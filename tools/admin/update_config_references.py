#!/usr/bin/env python3
"""
批量更新配置引用工具
将代码中对旧配置名的引用更新为新配置名
"""
import os
import re
from pathlib import Path


def update_file_references(file_path, replacements):
    """更新单个文件中的配置引用"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        updated = False
        
        for old_config, new_config in replacements.items():
            # 匹配引号中的配置名
            patterns = [
                rf'(["\']){old_config}\1',  # "old_config" 或 'old_config'
                rf'([`]){old_config}\1',    # `old_config`
            ]
            
            for pattern in patterns:
                new_content = re.sub(pattern, rf'\1{new_config}\1', content)
                if new_content != content:
                    content = new_content
                    updated = True
        
        if updated:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
    
    except Exception as e:
        print(f"❌ 更新文件失败 {file_path}: {e}")
        return False


def main():
    project_root = Path(__file__).parent.parent.parent
    
    # 配置映射：旧配置名 -> 新配置名
    config_replacements = {
        'channels.source_channels': 'DELETED',  # 已删除，不替换
        'target.channel_id': 'target.channel_id',
        'review.group_id': 'review.group_id',
        'source.history_limit': 'source.history_limit',
        'target.signature': 'target.signature',
        'target.channel_link': 'target.channel_link',
        'review.group_link': 'review.group_link',
        'channels.review_group_id_cached': 'DELETED',  # 已删除，不替换
    }
    
    # 只处理需要替换的配置（排除已删除的）
    active_replacements = {k: v for k, v in config_replacements.items() if v != 'DELETED'}
    
    print(f"🔄 批量更新配置引用工具")
    print(f"📁 项目根目录: {project_root}")
    print(f"📋 配置映射:")
    for old, new in active_replacements.items():
        print(f"   • {old} → {new}")
    
    # 要扫描的文件模式
    file_patterns = [
        "app/**/*.py",
        "tools/**/*.py",
        "*.py"
    ]
    
    files_to_update = []
    for pattern in file_patterns:
        files_to_update.extend(project_root.glob(pattern))
    
    # 排除迁移脚本本身和备份文件
    exclude_patterns = [
        "config_migration",
        "backup",
        "__pycache__",
        ".git"
    ]
    
    filtered_files = []
    for file_path in files_to_update:
        if any(exclude in str(file_path) for exclude in exclude_patterns):
            continue
        filtered_files.append(file_path)
    
    print(f"\n🔍 扫描 {len(filtered_files)} 个Python文件...")
    
    updated_files = []
    for file_path in filtered_files:
        if update_file_references(file_path, active_replacements):
            updated_files.append(file_path)
            print(f"✅ 更新: {file_path.relative_to(project_root)}")
    
    print(f"\n✅ 更新完成!")
    print(f"   共更新 {len(updated_files)} 个文件")
    
    if updated_files:
        print(f"\n📋 已更新的文件:")
        for file_path in updated_files:
            print(f"   • {file_path.relative_to(project_root)}")


if __name__ == "__main__":
    main()