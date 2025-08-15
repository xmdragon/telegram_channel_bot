#!/usr/bin/env python3
"""
初始化超级管理员账号（JSON存储版本）
"""
import asyncio
import getpass
import bcrypt
import json
import os
from datetime import datetime
from pathlib import Path
import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.json_store import init_json_stores, get_json_user_store
from app.core.path_config import PathConfig

async def load_permissions():
    """加载权限定义"""
    permissions_file = PathConfig.PERMISSIONS_CONFIG_FILE
    if not permissions_file.exists():
        print("❌ 权限文件不存在，请先运行 python3 init_storage.py")
        return []
    
    try:
        with open(permissions_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('permissions', [])
    except Exception as e:
        print(f"❌ 读取权限文件失败: {e}")
        return []

async def create_super_admin():
    """创建超级管理员账号"""
    print("🔐 创建超级管理员账号")
    print("-" * 40)
    
    # 初始化JSON存储
    if not init_json_stores():
        print("❌ JSON存储初始化失败")
        return False
    
    user_store = get_json_user_store()
    
    # 检查是否已存在超级管理员
    all_users = user_store.get_all_users()
    existing_super = None
    for user in all_users:
        if user.get('is_super_admin'):
            existing_super = user
            break
    
    if existing_super:
        print("⚠️  系统已存在超级管理员账号！")
        print(f"   现有超级管理员: {existing_super.get('username')}")
        try:
            confirm = input("是否要创建新的超级管理员？(yes/no): ").lower()
        except EOFError:
            confirm = 'no'
            print("非交互环境，取消创建")
        
        if confirm != 'yes':
            print("已取消创建")
            return False
    
    # 获取用户输入
    username = None
    while True:
        try:
            username = input("请输入用户名: ").strip()
        except EOFError:
            # 非交互环境，使用默认用户名
            username = "admin"
            print(f"非交互环境，使用默认用户名: {username}")
        
        if not username:
            print("❌ 用户名不能为空")
            continue
        
        # 检查用户名是否已存在
        if user_store.get_user_by_username(username):
            print(f"❌ 用户名 '{username}' 已存在")
            # 在非交互环境中，添加随机后缀
            if 'EOFError' in str(type(input)):
                import random
                username = f"{username}_{random.randint(1000, 9999)}"
                print(f"自动调整用户名为: {username}")
                break
            continue
        break
    
    # 获取密码
    password = None
    while True:
        try:
            password = getpass.getpass("请输入密码 (至少6位): ")
        except EOFError:
            # 非交互环境，使用默认密码
            password = "admin123"
            print("非交互环境，使用默认密码: admin123")
        
        if len(password) < 6:
            print("❌ 密码长度至少6位")
            if 'EOFError' in str(type(getpass.getpass)):
                password = "admin123456"  # 使用更长的默认密码
                break
            continue
        
        # 确认密码
        try:
            password_confirm = getpass.getpass("请再次输入密码: ")
            if password != password_confirm:
                print("❌ 两次输入的密码不一致")
                continue
        except EOFError:
            # 非交互环境，跳过确认
            pass
        break
    
    # 加载权限信息
    permissions = await load_permissions()
    if not permissions:
        print("⚠️  未找到权限定义，管理员将不具备任何权限")
    
    # 创建管理员用户
    try:
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        admin_data = {
            "username": username,
            "password_hash": password_hash,
            "is_super_admin": True,
            "is_active": True,
            "permissions": [perm['name'] for perm in permissions],  # 分配所有权限
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "last_login": None,
            "login_count": 0
        }
        
        user_id = user_store.create_user(admin_data)
        
        if user_id:
            print("\n✅ 超级管理员创建成功！")
            print(f"👤 用户名: {username}")
            print(f"🆔 用户ID: {user_id}")
            print(f"🔑 权限: 所有权限 ({len(permissions)} 项)")
            print(f"📅 创建时间: {admin_data['created_at']}")
            print("\n现在可以使用此账号登录系统了")
            print("\n登录地址:")
            print("  http://localhost:8000/static/login.html")
            
            return True
        else:
            print("❌ 创建管理员账号失败")
            return False
            
    except Exception as e:
        print(f"❌ 创建管理员时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

async def list_admins():
    """列出所有管理员账号"""
    print("👥 系统管理员列表")
    print("-" * 50)
    
    if not init_json_stores():
        print("❌ JSON存储初始化失败")
        return
    
    user_store = get_json_user_store()
    all_users = user_store.get_all_users()
    
    if not all_users:
        print("⚠️  系统中没有管理员账号")
        return
    
    admin_count = 0
    for user in all_users:
        if user.get('is_super_admin') or user.get('permissions'):
            admin_count += 1
            status = "🟢 活跃" if user.get('is_active', True) else "🔴 禁用"
            admin_type = "🔑 超级管理员" if user.get('is_super_admin') else "👤 普通管理员"
            
            print(f"{admin_count}. {user.get('username')} - {admin_type} - {status}")
            print(f"   ID: {user.get('id')}")
            print(f"   权限数: {len(user.get('permissions', []))}")
            print(f"   创建时间: {user.get('created_at', '未知')}")
            print(f"   最后登录: {user.get('last_login', '未登录')}")
            print()
    
    if admin_count == 0:
        print("⚠️  系统中没有管理员账号")
    else:
        print(f"📊 总计: {admin_count} 个管理员账号")

async def reset_admin_password():
    """重置管理员密码"""
    print("🔄 重置管理员密码")
    print("-" * 40)
    
    if not init_json_stores():
        print("❌ JSON存储初始化失败")
        return
    
    user_store = get_json_user_store()
    all_users = user_store.get_all_users()
    
    if not all_users:
        print("⚠️  系统中没有用户")
        return
    
    # 显示用户列表
    admin_users = [user for user in all_users if user.get('is_super_admin') or user.get('permissions')]
    
    if not admin_users:
        print("⚠️  系统中没有管理员账号")
        return
    
    print("请选择要重置密码的管理员:")
    for i, user in enumerate(admin_users, 1):
        admin_type = "🔑 超级管理员" if user.get('is_super_admin') else "👤 普通管理员"
        print(f"{i}. {user.get('username')} - {admin_type}")
    
    try:
        choice = input("请输入序号: ").strip()
        choice_idx = int(choice) - 1
        
        if choice_idx < 0 or choice_idx >= len(admin_users):
            print("❌ 无效的选择")
            return
        
        selected_user = admin_users[choice_idx]
        
        # 获取新密码
        new_password = getpass.getpass("请输入新密码 (至少6位): ")
        if len(new_password) < 6:
            print("❌ 密码长度至少6位")
            return
        
        # 更新密码
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        user_data = selected_user.copy()
        user_data['password_hash'] = password_hash
        user_data['updated_at'] = datetime.now().isoformat()
        
        success = user_store.update_user(selected_user['id'], user_data)
        
        if success:
            print(f"\n✅ 用户 '{selected_user['username']}' 的密码已重置")
        else:
            print("❌ 密码重置失败")
            
    except (ValueError, EOFError):
        print("❌ 操作已取消")
    except Exception as e:
        print(f"❌ 重置密码时出错: {e}")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='管理员账号管理工具')
    parser.add_argument('--create', action='store_true', help='创建超级管理员')
    parser.add_argument('--list', action='store_true', help='列出所有管理员')
    parser.add_argument('--reset-password', action='store_true', help='重置管理员密码')
    
    args = parser.parse_args()
    
    if args.list:
        await list_admins()
    elif args.reset_password:
        await reset_admin_password()
    elif args.create or len(sys.argv) == 1:  # 默认行为
        success = await create_super_admin()
        if not success:
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main())