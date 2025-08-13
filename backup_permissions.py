#!/usr/bin/env python3
"""
备份现有权限数据
"""
import asyncio
import json
from datetime import datetime
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, Permission, Admin, AdminPermission

async def backup_permissions():
    """备份权限数据"""
    async with AsyncSessionLocal() as db:
        # 备份权限定义
        result = await db.execute(select(Permission))
        permissions = result.scalars().all()
        
        permissions_data = []
        for perm in permissions:
            permissions_data.append({
                'id': perm.id,
                'name': perm.name,
                'module': perm.module,
                'action': perm.action,
                'description': perm.description
            })
        
        # 备份管理员权限分配
        result = await db.execute(select(AdminPermission))
        admin_permissions = result.scalars().all()
        
        admin_permissions_data = []
        for ap in admin_permissions:
            admin_permissions_data.append({
                'admin_id': ap.admin_id,
                'permission_id': ap.permission_id,
                'granted_by': ap.granted_by,
                'granted_at': ap.granted_at.isoformat() if ap.granted_at else None
            })
        
        # 备份管理员信息
        result = await db.execute(select(Admin))
        admins = result.scalars().all()
        
        admins_data = []
        for admin in admins:
            admins_data.append({
                'id': admin.id,
                'username': admin.username,
                'is_super_admin': admin.is_super_admin,
                'is_active': admin.is_active
            })
        
        # 保存备份
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'permissions': permissions_data,
            'admin_permissions': admin_permissions_data,
            'admins': admins_data
        }
        
        filename = f"permissions_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 权限数据已备份到: {filename}")
        print(f"  - 权限定义: {len(permissions_data)} 条")
        print(f"  - 权限分配: {len(admin_permissions_data)} 条")
        print(f"  - 管理员: {len(admins_data)} 个")
        
        return filename

if __name__ == "__main__":
    asyncio.run(backup_permissions())