#!/usr/bin/env python3
"""
数据库初始化脚本
"""
import asyncio
from app.core.database import init_db, AsyncSessionLocal, Permission
from app.services.config_manager import init_default_configs
from sqlalchemy import select

async def init_permissions():
    """初始化权限数据"""
    # 定义所有权限
    PERMISSION_DEFINITIONS = [
        # 消息管理
        {"name": "messages.view", "module": "messages", "action": "view", "description": "查看消息"},
        {"name": "messages.approve", "module": "messages", "action": "approve", "description": "批准消息"},
        {"name": "messages.reject", "module": "messages", "action": "reject", "description": "拒绝消息"},
        {"name": "messages.edit", "module": "messages", "action": "edit", "description": "编辑消息"},
        {"name": "messages.delete", "module": "messages", "action": "delete", "description": "删除消息"},
        
        # 配置管理
        {"name": "config.view", "module": "config", "action": "view", "description": "查看配置"},
        {"name": "config.edit", "module": "config", "action": "edit", "description": "修改配置"},
        
        # 频道管理
        {"name": "channels.view", "module": "channels", "action": "view", "description": "查看频道"},
        {"name": "channels.add", "module": "channels", "action": "add", "description": "添加频道"},
        {"name": "channels.edit", "module": "channels", "action": "edit", "description": "编辑频道"},
        {"name": "channels.delete", "module": "channels", "action": "delete", "description": "删除频道"},
        
        # 训练管理
        {"name": "training.view", "module": "training", "action": "view", "description": "查看训练数据"},
        {"name": "training.submit", "module": "training", "action": "submit", "description": "提交训练数据"},
        {"name": "training.manage", "module": "training", "action": "manage", "description": "管理训练数据"},
        
        # 系统管理
        {"name": "system.view_status", "module": "system", "action": "view_status", "description": "查看系统状态"},
        {"name": "system.view_logs", "module": "system", "action": "view_logs", "description": "查看系统日志"},
        {"name": "system.restart", "module": "system", "action": "restart", "description": "重启系统"},
        
        # 管理员管理
        {"name": "admin.manage_users", "module": "admin", "action": "manage_users", "description": "管理用户"},
        {"name": "admin.manage_permissions", "module": "admin", "action": "manage_permissions", "description": "管理权限"},
    ]
    
    async with AsyncSessionLocal() as db:
        # 检查是否已有权限数据
        result = await db.execute(select(Permission))
        existing = result.scalars().first()
        
        if not existing:
            # 批量创建权限
            for perm_def in PERMISSION_DEFINITIONS:
                permission = Permission(**perm_def)
                db.add(permission)
            
            await db.commit()
            print(f"✅ 初始化 {len(PERMISSION_DEFINITIONS)} 个权限项")
        else:
            print("ℹ️  权限数据已存在，跳过初始化")

async def initialize_database():
    """初始化数据库和基础数据"""
    print("🚀 正在初始化 Telegram 消息审核系统...")
    
    # 创建表结构
    print("📊 初始化数据库...")
    await init_db()
    print("✅ 数据库表创建完成")
    
    # 初始化权限数据
    print("🔐 初始化权限数据...")
    await init_permissions()
    print("✅ 权限数据初始化完成")
    
    # 初始化默认配置
    print("⚙️  初始化默认配置...")
    await init_default_configs()
    print("✅ 默认配置初始化完成")
    
    
    print("\n🎉 系统初始化完成！")
    print("\n📋 下一步操作：")
    print("1. 运行 python3 init_admin.py 创建超级管理员")
    print("2. 启动系统: python3 main.py")
    print("3. 访问 http://localhost:8000/login.html 登录系统")
    print("4. 访问 http://localhost:8000 开始使用系统")

if __name__ == "__main__":
    asyncio.run(initialize_database())