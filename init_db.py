#!/usr/bin/env python3
"""
数据库初始化脚本
"""
import asyncio
from app.core.database import init_db
from app.services.config_manager import init_default_configs

async def initialize_database():
    """初始化数据库和基础数据"""
    print("🚀 正在初始化 Telegram 消息审核系统...")
    
    # 创建表结构
    print("📊 初始化数据库...")
    await init_db()
    print("✅ 数据库表创建完成")
    
    # 初始化默认配置
    print("⚙️  初始化默认配置...")
    await init_default_configs()
    print("✅ 默认配置初始化完成")
    
    
    print("\n🎉 系统初始化完成！")
    print("\n📋 下一步操作：")
    print("1. 启动系统: python3 main.py")
    print("2. 访问 http://localhost:8000/auth.html 进行Telegram认证")
    print("3. 访问 http://localhost:8000/config.html 配置系统参数")
    print("4. 访问 http://localhost:8000/keywords.html 管理过滤关键词")
    print("5. 访问 http://localhost:8000 开始审核消息")

if __name__ == "__main__":
    asyncio.run(initialize_database())