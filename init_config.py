#!/usr/bin/env python3
"""
初始化系统配置
"""
import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.config_manager import init_default_configs
from app.core.database import init_db

async def main():
    """初始化系统配置"""
    print("🚀 正在初始化 Telegram 消息审核系统...")
    
    try:
        # 初始化数据库
        print("📊 初始化数据库...")
        await init_db()
        print("✅ 数据库初始化完成")
        
        # 初始化默认配置
        print("⚙️ 初始化默认配置...")
        await init_default_configs()
        print("✅ 默认配置初始化完成")
        
        print("\n🎉 系统初始化完成！")
        print("\n📋 系统配置概览：")
        print("  • Telegram API 配置：需要手动设置 api_id, api_hash, phone")
        print("  • 频道监听：支持添加/移除频道，设置监听状态")
        print("  • 账号采集：支持黑白名单管理")
        print("  • 广告过滤：支持文中关键词和行中关键词过滤")
        print("  • 系统配置：支持导出/导入配置")
        
        print("\n🌐 访问地址：")
        print("  • 主界面：http://localhost:8000")
        print("  • 配置管理：http://localhost:8000/config")
        print("  • 系统状态：http://localhost:8000/status")
        print("  • Telegram 登录：http://localhost:8000/auth")
        
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 