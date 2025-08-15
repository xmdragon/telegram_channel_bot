#!/usr/bin/env python3
"""
权限迁移脚本 - 将旧权限映射到新的细化权限
"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal, Permission, Admin, AdminPermission

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 旧权限到新权限的映射关系
OLD_TO_NEW_MAPPING = {
    'training.submit': ['training.mark_ad', 'training.mark_tail'],  # 拆分训练提交权限
    'config.edit': ['filter.add_keyword'],  # 配置编辑包含添加关键词
    'channels.edit': ['channels.refetch'],  # 频道编辑包含补抓功能
}

async def add_new_permissions():
    """添加新的权限定义"""
    new_permissions = [
        # 频道管理新权限
        {"name": "channels.refetch", "module": "channels", "action": "refetch", "description": "补抓消息"},
        
        # 训练管理细化权限
        {"name": "training.mark_ad", "module": "training", "action": "mark_ad", "description": "标记为广告"},
        {"name": "training.mark_tail", "module": "training", "action": "mark_tail", "description": "标记尾部内容"},
        
        # 过滤管理新模块
        {"name": "filter.view", "module": "filter", "action": "view", "description": "查看过滤规则"},
        {"name": "filter.add_keyword", "module": "filter", "action": "add_keyword", "description": "添加过滤关键词"},
        {"name": "filter.execute", "module": "filter", "action": "execute", "description": "执行过滤操作"},
        {"name": "filter.manage", "module": "filter", "action": "manage", "description": "管理过滤规则"},
    ]
    
    async with AsyncSessionLocal() as db:
        added_count = 0
        for perm_def in new_permissions:
            # 检查权限是否已存在
            result = await db.execute(
                select(Permission).where(Permission.name == perm_def['name'])
            )
            existing = result.scalars().first()
            
            if not existing:
                permission = Permission(**perm_def)
                db.add(permission)
                added_count += 1
                logger.info(f"添加新权限: {perm_def['name']}")
            else:
                logger.info(f"权限已存在，跳过: {perm_def['name']}")
        
        await db.commit()
        logger.info(f"✅ 添加了 {added_count} 个新权限")
        return added_count

async def migrate_admin_permissions():
    """迁移管理员权限"""
    async with AsyncSessionLocal() as db:
        # 获取所有管理员
        result = await db.execute(select(Admin).where(Admin.is_super_admin == False))
        admins = result.scalars().all()
        
        migration_count = 0
        
        for admin in admins:
            logger.info(f"处理管理员: {admin.username}")
            
            # 获取管理员现有权限
            result = await db.execute(
                select(Permission)
                .join(AdminPermission)
                .where(AdminPermission.admin_id == admin.id)
            )
            current_permissions = result.scalars().all()
            
            # 需要添加的新权限
            new_permissions_to_add = set()
            
            for perm in current_permissions:
                # 检查是否需要映射到新权限
                if perm.name in OLD_TO_NEW_MAPPING:
                    for new_perm_name in OLD_TO_NEW_MAPPING[perm.name]:
                        new_permissions_to_add.add(new_perm_name)
                        logger.info(f"  映射 {perm.name} -> {new_perm_name}")
            
            # 添加新权限
            for new_perm_name in new_permissions_to_add:
                # 获取新权限对象
                result = await db.execute(
                    select(Permission).where(Permission.name == new_perm_name)
                )
                new_perm = result.scalars().first()
                
                if new_perm:
                    # 检查是否已有这个权限
                    result = await db.execute(
                        select(AdminPermission).where(
                            and_(
                                AdminPermission.admin_id == admin.id,
                                AdminPermission.permission_id == new_perm.id
                            )
                        )
                    )
                    existing = result.scalars().first()
                    
                    if not existing:
                        # 查找第一个超级管理员作为授权者
                        super_admin_result = await db.execute(
                            select(Admin).where(Admin.is_super_admin == True).limit(1)
                        )
                        super_admin = super_admin_result.scalars().first()
                        granted_by_id = super_admin.id if super_admin else admin.id
                        
                        # 添加权限分配
                        admin_perm = AdminPermission(
                            admin_id=admin.id,
                            permission_id=new_perm.id,
                            granted_by=granted_by_id,  # 使用动态的授权者ID
                            granted_at=datetime.utcnow()
                        )
                        db.add(admin_perm)
                        migration_count += 1
                        logger.info(f"  ✅ 授予权限: {new_perm_name}")
                    else:
                        logger.info(f"  已有权限: {new_perm_name}")
        
        await db.commit()
        logger.info(f"✅ 完成权限迁移，共迁移 {migration_count} 个权限分配")
        return migration_count

async def verify_migration():
    """验证迁移结果"""
    async with AsyncSessionLocal() as db:
        # 统计权限数量
        result = await db.execute(select(Permission))
        permissions = result.scalars().all()
        
        permission_stats = {}
        for perm in permissions:
            if perm.module not in permission_stats:
                permission_stats[perm.module] = []
            permission_stats[perm.module].append(perm.name)
        
        logger.info("\n📊 权限统计:")
        for module, perms in sorted(permission_stats.items()):
            logger.info(f"  {module}: {len(perms)} 个权限")
            for perm_name in sorted(perms):
                logger.info(f"    - {perm_name}")
        
        # 检查管理员权限
        result = await db.execute(select(Admin).where(Admin.is_super_admin == False))
        admins = result.scalars().all()
        
        logger.info("\n👥 管理员权限分配:")
        for admin in admins:
            result = await db.execute(
                select(Permission)
                .join(AdminPermission)
                .where(AdminPermission.admin_id == admin.id)
            )
            admin_perms = result.scalars().all()
            
            logger.info(f"  {admin.username}: {len(admin_perms)} 个权限")
            for perm in admin_perms:
                logger.info(f"    - {perm.name}")

async def main():
    """主函数"""
    try:
        logger.info("🚀 开始权限迁移...")
        
        # 1. 添加新权限
        logger.info("\n步骤1: 添加新权限定义")
        await add_new_permissions()
        
        # 2. 迁移管理员权限
        logger.info("\n步骤2: 迁移管理员权限")
        await migrate_admin_permissions()
        
        # 3. 验证迁移结果
        logger.info("\n步骤3: 验证迁移结果")
        await verify_migration()
        
        logger.info("\n✅ 权限迁移完成！")
        
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())