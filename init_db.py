#!/usr/bin/env python3
"""
数据库初始化脚本
"""
import asyncio
from app.core.database import init_db, AsyncSessionLocal, Channel, FilterRule, SystemConfig
from app.core.config import base_settings
from app.services.config_manager import init_default_configs

async def initialize_database():
    """初始化数据库和基础数据"""
    print("正在初始化数据库...")
    
    # 创建表结构
    await init_db()
    print("✅ 数据库表创建完成")
    
    # 初始化默认配置
    await init_default_configs()
    print("✅ 默认配置初始化完成")
    
    # 插入基础频道配置（如果需要）
    async with AsyncSessionLocal() as db:
        # 检查是否已有频道数据
        existing_channels = await db.execute("SELECT COUNT(*) FROM channels")
        count = existing_channels.scalar()
        
        if count == 0:
            print("ℹ️  未检测到现有频道配置，可通过以下方式添加：")
            print("   1. 访问 http://localhost:8000/admin 管理界面")
            print("   2. 访问 http://localhost:8000/config 配置界面")
            print("   3. 使用命令行工具: python scripts/manage.py add-channel")
        
        # 添加默认过滤规则
        existing_rules = await db.execute("SELECT COUNT(*) FROM filter_rules")
        rule_count = existing_rules.scalar()
        
        if rule_count == 0:
            default_rules = [
                FilterRule(rule_type="keyword", pattern="广告", action="flag"),
                FilterRule(rule_type="keyword", pattern="推广", action="flag"),
                FilterRule(rule_type="keyword", pattern="代理", action="flag"),
                FilterRule(rule_type="regex", pattern=r"微信[：:]\s*\w+", action="flag"),
                FilterRule(rule_type="regex", pattern=r"QQ[：:]\s*\d+", action="flag"),
            ]
            
            for rule in default_rules:
                db.add(rule)
            
            await db.commit()
            print("✅ 默认过滤规则添加完成")
    
    print("🎉 数据库初始化完成！")
    print("\n📋 重要提醒:")
    print("   系统现在使用数据库存储配置，不再依赖 .env 文件")
    print("   请通过以下方式配置系统：")
    print("\n🌐 Web界面配置:")
    print("   1. 启动系统: python main.py")
    print("   2. 访问配置界面: http://localhost:8000/config")
    print("   3. 配置Telegram相关参数")
    print("\n⚙️ 必须配置的参数:")
    print("   - telegram.bot_token: Telegram机器人Token")
    print("   - telegram.api_id: Telegram API ID")
    print("   - telegram.api_hash: Telegram API Hash")
    print("   - channels.source_channels: 源频道列表")
    print("   - channels.review_group_id: 审核群ID")
    print("   - channels.target_channel_id: 目标频道ID")
    print("\n🔧 命令行配置:")
    print("   python scripts/manage.py add-channel @channel_id '频道名称'")

if __name__ == "__main__":
    asyncio.run(initialize_database())