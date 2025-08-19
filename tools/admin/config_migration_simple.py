#!/usr/bin/env python3
"""
配置重构迁移工具（简化版）
直接操作JSON文件，将混乱的channels.*配置重构为清晰结构
"""
import json
import shutil
from pathlib import Path
from datetime import datetime


def analyze_config(config_file):
    """分析当前配置"""
    print("🔍 分析当前配置结构...")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 找出所有channels.*配置
    channels_configs = {k: v for k, v in config.items() if k.startswith('channels.')}
    
    print(f"\n📊 发现 {len(channels_configs)} 个channels.*配置:")
    for key, config_obj in channels_configs.items():
        value = config_obj.get('value', '')
        description = config_obj.get('description', '')
        print(f"  • {key}: '{value}' ({description})")
    
    return config, channels_configs


def create_migration_plan(config):
    """创建迁移计划"""
    print(f"\n📋 配置分析:")
    
    # 要删除的配置
    to_delete = [
        'channels.source_channels',          # 已废弃
        'channels.target_channel',           # 冗余（用target.channel_link代替）
        'channels.review_group',             # 冗余（用review.group_link代替）
        'channels.review_group_id_cached'    # 完全不必要
    ]
    
    # 要重命名的配置
    to_rename = {
        'channels.history_message_limit': 'source.history_limit',
        'channels.signature': 'target.signature',
        'channels.target_channel_id': 'target.channel_id',
        'channels.review_group_id': 'review.group_id'
    }
    
    # 要新增的配置（从现有值推导）
    to_add = []
    
    # 从target_channel推导target.channel_link
    target_channel = config.get('channels.target_channel', {}).get('value', '')
    if target_channel:
        to_add.append({
            'key': 'target.channel_link',
            'value': target_channel,
            'description': '目标频道链接（用户配置）',
            'config_type': 'string'
        })
    
    # 从review_group推导review.group_link
    review_group = config.get('channels.review_group', {}).get('value', '')
    if review_group:
        to_add.append({
            'key': 'review.group_link',
            'value': review_group,
            'description': '审核群链接（用户配置）',
            'config_type': 'string'
        })
    
    print(f"  ❌ 将删除 {len(to_delete)} 个废弃/冗余配置:")
    for key in to_delete:
        if key in config:
            print(f"     - {key}")
    
    print(f"  📋 将重命名 {len(to_rename)} 个配置:")
    for old_key, new_key in to_rename.items():
        if old_key in config:
            print(f"     • {old_key} → {new_key}")
    
    print(f"  ✨ 将新增 {len(to_add)} 个配置:")
    for item in to_add:
        print(f"     + {item['key']}: {item['value']}")
    
    return to_delete, to_rename, to_add


def execute_migration(config_file, to_delete, to_rename, to_add, dry_run=True):
    """执行迁移"""
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    if dry_run:
        print(f"\n🔄 迁移计划（干跑模式）:")
        return
    
    print(f"\n🔄 执行迁移:")
    
    # 创建备份
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = config_file.parent / f"system_config_migration_backup_{timestamp}.json"
    shutil.copy2(config_file, backup_file)
    print(f"✅ 配置已备份到: {backup_file}")
    
    # 删除废弃配置
    deleted_count = 0
    for key in to_delete:
        if key in config:
            del config[key]
            deleted_count += 1
            print(f"🗑️  删除: {key}")
    
    # 重命名配置
    renamed_count = 0
    for old_key, new_key in to_rename.items():
        if old_key in config:
            config[new_key] = config[old_key]
            del config[old_key]
            renamed_count += 1
            print(f"📋 重命名: {old_key} → {new_key}")
    
    # 新增配置
    added_count = 0
    for item in to_add:
        key = item['key']
        config[key] = {
            'value': item['value'],
            'config_type': item['config_type'],
            'description': item['description'],
            'is_active': True,
            'updated_at': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat()
        }
        added_count += 1
        print(f"✨ 新增: {key}")
    
    # 更新整体时间戳
    config['updated_at'] = datetime.now().isoformat()
    
    # 保存配置
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 迁移完成!")
    print(f"   删除: {deleted_count} 个配置")
    print(f"   重命名: {renamed_count} 个配置")
    print(f"   新增: {added_count} 个配置")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='配置重构迁移工具')
    parser.add_argument('--execute', action='store_true', help='执行实际迁移（默认为干跑模式）')
    args = parser.parse_args()
    
    # 配置文件路径
    project_root = Path(__file__).parent.parent.parent
    config_file = project_root / "data/config/system.json"
    
    print(f"🚀 配置重构迁移工具")
    print(f"📁 配置文件: {config_file}")
    
    if not config_file.exists():
        print(f"❌ 配置文件不存在: {config_file}")
        return
    
    try:
        # 分析配置
        config, channels_configs = analyze_config(config_file)
        
        # 创建迁移计划
        to_delete, to_rename, to_add = create_migration_plan(config)
        
        # 执行迁移
        execute_migration(config_file, to_delete, to_rename, to_add, dry_run=not args.execute)
        
        if not args.execute:
            print(f"\n💡 使用 --execute 参数执行实际迁移")
    
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()