#!/usr/bin/env python3
"""
配置重构迁移工具
将混乱的channels.*配置重构为清晰的target.*/review.*/source.*结构
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime
import shutil

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.storage.json_store import get_json_config_store
from app.utils.safe_file_ops import SafeFileOperation


class ConfigMigration:
    def __init__(self):
        # 直接读取JSON文件，避免依赖存储层初始化
        self.config_file = project_root / "data/config/system.json"
        self.backup_dir = project_root / "data/backups"
        
    def analyze_current_config(self):
        """分析当前配置结构"""
        print("🔍 分析当前配置结构...")
        
        # 直接读取配置文件
        if not self.config_file.exists():
            print(f"❌ 配置文件不存在: {self.config_file}")
            return {}
        
        current_config = SafeFileOperation.read_json_safe(self.config_file)
        
        # 找出所有channels.*配置
        channels_configs = {k: v for k, v in current_config.items() if k.startswith('channels.')}
        
        print(f"\n📊 发现 {len(channels_configs)} 个channels.*配置:")
        for key, config in channels_configs.items():
            value = config.get('value', '')
            description = config.get('description', '')
            print(f"  • {key}: {value} ({description})")
        
        # 分析使用情况
        print(f"\n📋 配置分析:")
        print(f"  ❌ 废弃配置:")
        print(f"     - channels.source_channels: 已废弃，应删除")
        print(f"  ⚠️  冗余配置:")
        print(f"     - channels.target_channel + channels.target_channel_id")
        print(f"     - channels.review_group + channels.review_group_id + channels.review_group_id_cached")
        print(f"  ✅ 保留配置:")
        print(f"     - channels.history_message_limit → source.history_limit")
        print(f"     - channels.signature → target.signature")
        
        return channels_configs
    
    def create_migration_plan(self, current_config):
        """创建迁移计划"""
        plan = {
            'delete': [],      # 要删除的配置
            'migrate': [],     # 要迁移的配置
            'new': []          # 要新增的配置
        }
        
        # 删除废弃和冗余配置
        plan['delete'] = [
            'channels.source_channels',          # 已废弃
            'channels.target_channel',           # 冗余（有target_channel_id）
            'channels.review_group',             # 冗余（有review_group_id）
            'channels.review_group_id_cached'    # 完全不必要
        ]
        
        # 迁移配置
        migrations = [
            ('channels.history_message_limit', 'source.history_limit'),
            ('channels.signature', 'target.signature'),
            ('channels.target_channel_id', 'target.channel_id'),
            ('channels.review_group_id', 'review.group_id')
        ]
        
        for old_key, new_key in migrations:
            if old_key in current_config:
                old_config = current_config[old_key]
                plan['migrate'].append({
                    'old_key': old_key,
                    'new_key': new_key,
                    'value': old_config.get('value'),
                    'description': old_config.get('description'),
                    'config_type': old_config.get('config_type')
                })
        
        # 新增配置（从现有值推导）
        target_channel = current_config.get('channels.target_channel', {}).get('value', '')
        review_group = current_config.get('channels.review_group', {}).get('value', '')
        
        if target_channel:
            plan['new'].append({
                'key': 'target.channel_link',
                'value': target_channel,
                'description': '目标频道链接（用户配置）',
                'config_type': 'string'
            })
        
        if review_group:
            plan['new'].append({
                'key': 'review.group_link',
                'value': review_group,
                'description': '审核群链接（用户配置）',
                'config_type': 'string'
            })
        
        return plan
    
    def backup_config(self):
        """备份当前配置"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"config_migration_backup_{timestamp}.json"
        
        # 确保备份目录存在
        self.backup_dir.mkdir(exist_ok=True)
        
        # 复制当前配置文件
        shutil.copy2(self.config_file, backup_file)
        print(f"✅ 配置已备份到: {backup_file}")
        return backup_file
    
    def execute_migration(self, plan, dry_run=True):
        """执行迁移"""
        if dry_run:
            print(f"\n🔄 迁移计划（干跑模式）:")
        else:
            print(f"\n🔄 执行迁移:")
            
        # 显示删除计划
        if plan['delete']:
            print(f"\n🗑️  将删除 {len(plan['delete'])} 个配置:")
            for key in plan['delete']:
                print(f"   - {key}")
                if not dry_run:
                    # 直接从配置中删除
                    if key in current_config:
                        del current_config[key]
        
        # 显示迁移计划
        if plan['migrate']:
            print(f"\n📋 将迁移 {len(plan['migrate'])} 个配置:")
            for migration in plan['migrate']:
                old_key = migration['old_key']
                new_key = migration['new_key']
                print(f"   • {old_key} → {new_key}")
                
                if not dry_run:
                    # 创建新配置
                    self.config_store.set_config(
                        new_key,
                        migration['value'],
                        migration['description'],
                        migration['config_type']
                    )
                    # 删除旧配置
                    self.config_store.delete_config(old_key)
        
        # 显示新增计划
        if plan['new']:
            print(f"\n✨ 将新增 {len(plan['new'])} 个配置:")
            for new_config in plan['new']:
                key = new_config['key']
                value = new_config['value']
                print(f"   + {key}: {value}")
                
                if not dry_run:
                    self.config_store.set_config(
                        key,
                        value,
                        new_config['description'],
                        new_config['config_type']
                    )
        
        if not dry_run:
            print(f"\n✅ 迁移完成！")
        else:
            print(f"\n💡 使用 --execute 参数执行实际迁移")
    
    def run(self, execute=False):
        """运行迁移"""
        print(f"🚀 配置重构迁移工具")
        print(f"📁 配置文件: {self.config_file}")
        
        # 分析当前配置
        current_config = self.analyze_current_config()
        
        # 创建迁移计划
        plan = self.create_migration_plan(current_config)
        
        if execute:
            # 备份配置
            self.backup_config()
            
            # 执行迁移
            self.execute_migration(plan, dry_run=False)
        else:
            # 干跑模式
            self.execute_migration(plan, dry_run=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='配置重构迁移工具')
    parser.add_argument('--execute', action='store_true', help='执行实际迁移（默认为干跑模式）')
    args = parser.parse_args()
    
    try:
        migration = ConfigMigration()
        migration.run(execute=args.execute)
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()