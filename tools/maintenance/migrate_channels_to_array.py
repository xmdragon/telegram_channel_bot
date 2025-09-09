#!/usr/bin/env python3
"""
频道数据结构迁移脚本
从复杂对象键名结构迁移到简洁数组结构

执行步骤：
1. 备份当前数据
2. 转换数据结构
3. 删除无用字段
4. 验证数据完整性
5. 保存新格式

Linus原则：彻底简化，删除所有不必要的复杂性
"""
import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

class ChannelMigrator:
    """频道数据迁移器"""
    
    def __init__(self):
        self.channels_file = PathConfig.CHANNELS_CONFIG_FILE
        self.backup_dir = PathConfig.BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def backup_current_data(self) -> str:
        """备份当前数据"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = self.backup_dir / f"channels_backup_before_array_migration_{timestamp}.json"
        
        if self.channels_file.exists():
            shutil.copy2(self.channels_file, backup_file)
            print(f"✅ 数据已备份到: {backup_file}")
            return str(backup_file)
        else:
            print(f"⚠️  频道文件不存在: {self.channels_file}")
            return ""
    
    def load_current_data(self) -> dict:
        """加载当前数据"""
        if not self.channels_file.exists():
            print("❌ 频道文件不存在，无需迁移")
            return {}
        
        try:
            data = SafeFileOperation.read_json_safe(self.channels_file)
            print(f"📖 已加载当前数据，包含 {len(data)} 个频道")
            return data
        except Exception as e:
            print(f"❌ 读取频道文件失败: {e}")
            return {}
    
    def check_data_format(self, data: dict) -> str:
        """检查数据格式"""
        if not data:
            return "empty"
        
        if isinstance(data, list):
            return "array"  # 已经是数组格式
        
        if isinstance(data, dict):
            # 检查是否为旧的对象键名格式
            keys = list(data.keys())
            if keys and keys[0].startswith('channel_'):
                return "object_keys"  # 旧的对象键名格式
            else:
                return "unknown"
        
        return "unknown"
    
    def convert_to_array(self, old_data: dict) -> list:
        """转换为数组格式"""
        if not old_data:
            return []
        
        new_channels = []
        
        for key, channel in old_data.items():
            if not isinstance(channel, dict):
                continue
            
            # 删除无用字段
            clean_channel = channel.copy()
            
            # 删除无用字段：channel_type (全是source)
            if 'channel_type' in clean_channel:
                del clean_channel['channel_type']
                
            # 删除无用字段：is_active (全是true，存在即活跃)
            if 'is_active' in clean_channel:
                del clean_channel['is_active']
            
            new_channels.append(clean_channel)
        
        # 按ID排序
        new_channels.sort(key=lambda x: x.get('id', 0))
        
        print(f"🔄 已转换 {len(new_channels)} 个频道到数组格式")
        return new_channels
    
    def validate_conversion(self, old_data: dict, new_data: list) -> bool:
        """验证转换结果"""
        if not old_data:
            return len(new_data) == 0
        
        # 检查数量
        if len(old_data) != len(new_data):
            print(f"❌ 数量不匹配: 旧={len(old_data)}, 新={len(new_data)}")
            return False
        
        # 检查关键字段
        old_ids = set()
        old_names = set() 
        
        for channel in old_data.values():
            if isinstance(channel, dict):
                old_ids.add(channel.get('id'))
                old_names.add(channel.get('channel_name'))
        
        new_ids = set(ch.get('id') for ch in new_data)
        new_names = set(ch.get('channel_name') for ch in new_data)
        
        if old_ids != new_ids:
            print(f"❌ ID不匹配: 旧={sorted(old_ids)}, 新={sorted(new_ids)}")
            return False
        
        if old_names != new_names:
            print(f"❌ 频道名不匹配: 差异={old_names.symmetric_difference(new_names)}")
            return False
        
        print("✅ 数据验证通过")
        return True
    
    def save_new_format(self, new_data: list) -> bool:
        """保存新格式"""
        try:
            success = SafeFileOperation.write_json_safe(self.channels_file, new_data, backup=False)
            if success:
                print(f"✅ 新格式已保存到: {self.channels_file}")
                return True
            else:
                print("❌ 保存新格式失败")
                return False
        except Exception as e:
            print(f"❌ 保存失败: {e}")
            return False
    
    def migrate(self, dry_run: bool = False) -> bool:
        """执行迁移"""
        print("🚀 开始频道数据结构迁移")
        print("=" * 50)
        
        # 1. 加载当前数据
        current_data = self.load_current_data()
        if not current_data:
            print("✅ 无数据需要迁移")
            return True
        
        # 2. 检查数据格式
        format_type = self.check_data_format(current_data)
        print(f"📊 当前数据格式: {format_type}")
        
        if format_type == "array":
            print("✅ 数据已经是数组格式，无需迁移")
            return True
        
        if format_type != "object_keys":
            print(f"❌ 不支持的数据格式: {format_type}")
            return False
        
        # 3. 备份数据
        if not dry_run:
            backup_file = self.backup_current_data()
            if not backup_file:
                print("❌ 备份失败，中止迁移")
                return False
        
        # 4. 转换数据
        new_data = self.convert_to_array(current_data)
        
        # 5. 验证转换
        if not self.validate_conversion(current_data, new_data):
            print("❌ 数据验证失败，中止迁移")
            return False
        
        # 6. 预览新数据结构
        print("\n📋 新数据结构预览:")
        if new_data:
            sample = new_data[0].copy()
            # 只显示关键字段
            preview = {
                "id": sample.get("id"),
                "channel_name": sample.get("channel_name"),
                "channel_id": sample.get("channel_id"),
                "channel_title": sample.get("channel_title")
            }
            print(json.dumps(preview, indent=2, ensure_ascii=False))
            print(f"... (共 {len(new_data)} 个频道)")
        
        if dry_run:
            print("\n🔍 预演模式，不会实际修改文件")
            print("✅ 迁移预演完成，数据格式正确")
            return True
        
        # 7. 保存新格式
        if self.save_new_format(new_data):
            print("\n✅ 迁移完成！")
            print(f"📊 统计信息:")
            print(f"  - 迁移频道数: {len(new_data)}")
            print(f"  - 删除字段: channel_type, is_active")
            print(f"  - 数据结构: 对象键名 → 简洁数组")
            return True
        else:
            print("❌ 迁移失败")
            return False

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="频道数据结构迁移工具")
    parser.add_argument("--dry-run", action="store_true", help="预演模式，不实际修改文件")
    parser.add_argument("--force", action="store_true", help="强制执行，不询问确认")
    
    args = parser.parse_args()
    
    migrator = ChannelMigrator()
    
    if not args.dry_run and not args.force:
        print("⚠️  这将修改频道数据结构，请确认:")
        print("   1. 将对象键名结构转换为数组结构")
        print("   2. 删除无用字段 (channel_type, is_active)")
        print("   3. 自动备份原始数据")
        
        confirm = input("\n确认执行迁移? [y/N]: ").lower().strip()
        if confirm != 'y':
            print("❌ 用户取消迁移")
            return
    
    success = migrator.migrate(dry_run=args.dry_run)
    
    if success:
        print("\n🎉 频道数据结构迁移成功！")
        if not args.dry_run:
            print("💡 建议接下来:")
            print("   1. 重启应用测试新数据结构")
            print("   2. 验证频道添加功能是否正常")
            print("   3. 确认无问题后删除备份文件")
    else:
        print("\n❌ 迁移失败")
        sys.exit(1)

if __name__ == "__main__":
    main()