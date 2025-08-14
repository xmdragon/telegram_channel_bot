#!/usr/bin/env python3
"""
备份权限和用户数据（JSON存储版本）
"""
import asyncio
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.json_store import init_json_stores, get_json_user_store

async def backup_permissions_and_users():
    """备份权限和用户数据"""
    
    # 初始化JSON存储
    if not init_json_stores():
        print("❌ JSON存储初始化失败")
        return False
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = Path(f"data/backups/backup_{timestamp}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🗂️  开始备份到: {backup_dir}")
    
    backup_files = []
    
    try:
        # 1. 备份权限定义文件
        permissions_file = Path("data/permissions.json")
        if permissions_file.exists():
            backup_perms_file = backup_dir / "permissions.json"
            shutil.copy2(permissions_file, backup_perms_file)
            backup_files.append("permissions.json")
            print(f"✅ 备份权限文件: {permissions_file} -> {backup_perms_file}")
        else:
            print("⚠️  权限文件不存在")
        
        # 2. 备份用户数据
        user_store = get_json_user_store()
        all_users = user_store.get_all_users()
        
        if all_users:
            users_backup_file = backup_dir / "users.json"
            
            # 清理敏感信息的用户数据
            safe_users_data = []
            for user in all_users:
                safe_user = user.copy()
                # 保留密码哈希但添加警告
                if 'password_hash' in safe_user:
                    safe_user['_password_notice'] = "密码哈希已保留用于恢复，请妥善保管备份文件"
                
                safe_users_data.append(safe_user)
            
            users_data = {
                'timestamp': datetime.now().isoformat(),
                'users': safe_users_data,
                'total_count': len(safe_users_data),
                'admin_count': len([u for u in safe_users_data if u.get('is_super_admin') or u.get('permissions')])
            }
            
            with open(users_backup_file, 'w', encoding='utf-8') as f:
                json.dump(users_data, f, ensure_ascii=False, indent=2)
                
            backup_files.append("users.json")
            print(f"✅ 备份用户数据: {len(all_users)} 个用户")
        else:
            print("⚠️  没有用户数据需要备份")
        
        # 3. 备份配置数据
        config_file = Path("data/configs.json")
        if config_file.exists():
            backup_config_file = backup_dir / "configs.json"
            shutil.copy2(config_file, backup_config_file)
            backup_files.append("configs.json")
            print(f"✅ 备份配置文件")
        else:
            print("⚠️  配置文件不存在")
        
        # 4. 备份训练数据文件
        training_files = [
            "data/tail_filter_samples.json",
            "data/ocr_samples.json",
            "data/feedback_learning.json",
            "data/ad_training_data.json"
        ]
        
        for training_file in training_files:
            source_path = Path(training_file)
            if source_path.exists():
                dest_path = backup_dir / source_path.name
                shutil.copy2(source_path, dest_path)
                backup_files.append(source_path.name)
                print(f"✅ 备份训练数据: {source_path.name}")
        
        # 5. 创建备份清单
        manifest = {
            'timestamp': datetime.now().isoformat(),
            'backup_type': 'full_system_backup',
            'files': backup_files,
            'created_by': 'backup_permissions.py',
            'restore_instructions': {
                'permissions': '将 permissions.json 复制到 data/ 目录',
                'users': '使用 init_admin.py --restore 恢复用户数据',
                'configs': '将 configs.json 复制到 data/ 目录',
                'training_data': '将训练数据文件复制到 data/ 目录'
            }
        }
        
        manifest_file = backup_dir / "MANIFEST.json"
        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        
        # 6. 创建压缩备份（可选）
        try:
            import zipfile
            zip_filename = f"backup_{timestamp}.zip"
            
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in backup_dir.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(backup_dir.parent)
                        zipf.write(file_path, arcname)
            
            print(f"\n📦 创建压缩备份: {zip_filename}")
            print(f"   大小: {os.path.getsize(zip_filename)} 字节")
            
        except ImportError:
            print("⚠️  zipfile模块不可用，跳过压缩备份")
        except Exception as e:
            print(f"⚠️  创建压缩备份失败: {e}")
        
        # 7. 显示备份摘要
        print(f"\n🎉 备份完成！")
        print(f"📁 备份目录: {backup_dir}")
        print(f"📄 备份文件: {len(backup_files)} 个")
        for file in backup_files:
            print(f"   • {file}")
        
        return str(backup_dir)
        
    except Exception as e:
        print(f"❌ 备份过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

async def list_backups():
    """列出所有备份"""
    
    backups_dir = Path("data/backups")
    if not backups_dir.exists():
        print("📁 备份目录不存在")
        return
    
    backup_dirs = [d for d in backups_dir.iterdir() if d.is_dir() and d.name.startswith('backup_')]
    
    if not backup_dirs:
        print("📁 没有找到备份")
        return
    
    print("📋 现有备份列表:")
    print("-" * 60)
    
    # 按时间排序
    backup_dirs.sort(key=lambda x: x.name, reverse=True)
    
    for i, backup_dir in enumerate(backup_dirs, 1):
        manifest_file = backup_dir / "MANIFEST.json"
        
        if manifest_file.exists():
            try:
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                timestamp = manifest.get('timestamp', 'Unknown')
                file_count = len(manifest.get('files', []))
                backup_type = manifest.get('backup_type', 'unknown')
                
                print(f"{i}. {backup_dir.name}")
                print(f"   时间: {timestamp}")
                print(f"   类型: {backup_type}")
                print(f"   文件: {file_count} 个")
                print(f"   路径: {backup_dir}")
                
                # 显示文件列表
                if manifest.get('files'):
                    files_preview = ', '.join(manifest['files'][:3])
                    if len(manifest['files']) > 3:
                        files_preview += f" 等{len(manifest['files'])}个文件"
                    print(f"   包含: {files_preview}")
                
            except Exception as e:
                print(f"{i}. {backup_dir.name} (清单文件读取失败: {e})")
                
        else:
            # 没有清单文件，显示基本信息
            file_count = len(list(backup_dir.glob('*.json')))
            print(f"{i}. {backup_dir.name}")
            print(f"   文件: {file_count} 个JSON文件")
            print(f"   路径: {backup_dir}")
        
        print()

async def restore_from_backup(backup_path: str):
    """从备份恢复数据"""
    
    backup_dir = Path(backup_path)
    if not backup_dir.exists():
        print(f"❌ 备份目录不存在: {backup_dir}")
        return False
    
    manifest_file = backup_dir / "MANIFEST.json"
    if not manifest_file.exists():
        print("⚠️  备份目录中没有找到清单文件，将尝试直接恢复")
    
    print(f"🔄 开始从备份恢复: {backup_dir}")
    
    try:
        restored_files = []
        
        # 恢复权限文件
        backup_perms = backup_dir / "permissions.json"
        if backup_perms.exists():
            dest_perms = Path("data/permissions.json")
            dest_perms.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_perms, dest_perms)
            restored_files.append("permissions.json")
            print(f"✅ 恢复权限文件")
        
        # 恢复配置文件
        backup_config = backup_dir / "configs.json"
        if backup_config.exists():
            dest_config = Path("data/configs.json")
            shutil.copy2(backup_config, dest_config)
            restored_files.append("configs.json")
            print(f"✅ 恢复配置文件")
        
        # 恢复训练数据文件
        training_files = [
            "tail_filter_samples.json",
            "ocr_samples.json", 
            "feedback_learning.json",
            "ad_training_data.json"
        ]
        
        for file_name in training_files:
            backup_file = backup_dir / file_name
            if backup_file.exists():
                dest_file = Path("data") / file_name
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, dest_file)
                restored_files.append(file_name)
                print(f"✅ 恢复训练数据: {file_name}")
        
        # 用户数据需要特殊处理
        backup_users = backup_dir / "users.json"
        if backup_users.exists():
            print("⚠️  找到用户数据备份，但需要手动恢复")
            print("   请使用: init_admin.py --restore-users 恢复用户数据")
            print(f"   备份文件: {backup_users}")
        
        print(f"\n🎉 恢复完成！")
        print(f"📄 恢复文件: {len(restored_files)} 个")
        for file in restored_files:
            print(f"   • {file}")
        
        if backup_users.exists():
            print(f"\n⚠️  注意：用户数据需要手动恢复")
        
        return True
        
    except Exception as e:
        print(f"❌ 恢复过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

async def cleanup_old_backups(keep_count: int = 5):
    """清理旧备份，保留最新的几个"""
    
    backups_dir = Path("data/backups")
    if not backups_dir.exists():
        print("📁 备份目录不存在")
        return
    
    backup_dirs = [d for d in backups_dir.iterdir() if d.is_dir() and d.name.startswith('backup_')]
    
    if len(backup_dirs) <= keep_count:
        print(f"📁 当前备份数 ({len(backup_dirs)}) 不超过保留数 ({keep_count})，无需清理")
        return
    
    # 按时间排序，最新的在前
    backup_dirs.sort(key=lambda x: x.name, reverse=True)
    
    # 要删除的备份
    to_delete = backup_dirs[keep_count:]
    
    print(f"🗑️  准备清理 {len(to_delete)} 个旧备份，保留最新的 {keep_count} 个")
    
    for backup_dir in to_delete:
        try:
            shutil.rmtree(backup_dir)
            print(f"   ✅ 删除: {backup_dir.name}")
        except Exception as e:
            print(f"   ❌ 删除失败 {backup_dir.name}: {e}")
    
    print("🧹 备份清理完成")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='权限和用户数据备份工具')
    parser.add_argument('--backup', action='store_true', help='创建备份')
    parser.add_argument('--list', action='store_true', help='列出所有备份')
    parser.add_argument('--restore', help='从指定备份恢复')
    parser.add_argument('--cleanup', type=int, metavar='N', help='清理旧备份，保留最新N个')
    
    args = parser.parse_args()
    
    if args.list:
        await list_backups()
    elif args.restore:
        await restore_from_backup(args.restore)
    elif args.cleanup:
        await cleanup_old_backups(args.cleanup)
    elif args.backup or len(sys.argv) == 1:  # 默认行为
        await backup_permissions_and_users()
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main())