#!/usr/bin/env python3
"""
初始化超级管理员账号
"""
import asyncio
import getpass
import bcrypt
from datetime import datetime
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, Admin, Permission, AdminPermission


async def create_super_admin():
    """创建超级管理员账号"""
    print("🔐 创建超级管理员账号")
    print("-" * 40)
    
    async with AsyncSessionLocal() as db:
        # 检查是否已存在超级管理员
        result = await db.execute(select(Admin).where(Admin.is_super_admin == True))
        existing_super = result.scalars().first()
        
        if existing_super:
            print("⚠️  系统已存在超级管理员账号！")
            confirm = input("是否要创建新的超级管理员？(yes/no): ").lower()
            if confirm != 'yes':
                print("已取消创建")
                return
        
        # 获取用户输入
        while True:
            username = input("请输入用户名: ").strip()
            if not username:
                print("❌ 用户名不能为空")
                continue
            
            # 检查用户名是否已存在
            result = await db.execute(select(Admin).where(Admin.username == username))
            if result.scalars().first():
                print(f"❌ 用户名 '{username}' 已存在")
                continue
            break
        
        # 获取密码
        while True:
            password = getpass.getpass("请输入密码 (至少6位): ")
            if len(password) < 6:
                print("❌ 密码长度至少6位")
                continue
            
            password_confirm = getpass.getpass("请再次输入密码: ")
            if password != password_confirm:
                print("❌ 两次输入的密码不一致")
                continue
            break
        
        # 创建管理员
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        admin = Admin(
            username=username,
            password_hash=password_hash,
            is_super_admin=True,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(admin)
        await db.flush()  # 获取admin.id
        
        # 给超级管理员分配所有权限
        result = await db.execute(select(Permission))
        all_permissions = result.scalars().all()
        
        for permission in all_permissions:
            admin_permission = AdminPermission(
                admin_id=admin.id,
                permission_id=permission.id,
                granted_at=datetime.utcnow()
            )
            db.add(admin_permission)
        
        await db.commit()
        
        print("\n✅ 超级管理员创建成功！")
        print(f"👤 用户名: {username}")
        print(f"🔑 权限: 所有权限 ({len(all_permissions)} 项)")
        print("\n现在可以使用此账号登录系统了")


if __name__ == "__main__":
    asyncio.run(create_super_admin())