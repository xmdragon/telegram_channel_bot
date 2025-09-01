#!/usr/bin/env python3
"""
存储系统初始化脚本 (Redis + JSON)
注意：系统现已使用Redis+JSON存储架构，无需传统数据库初始化
"""
import asyncio
import logging

print("⚠️  注意：系统已升级至Redis+JSON存储架构")
print("🔧 系统会在首次启动时自动初始化所有存储组件")
print("")
print("📋 初始化包括：")
print("   - Redis连接和数据结构")
print("   - JSON配置文件系统")
print("   - 默认系统配置")
print("   - 管理员认证系统")
print("   - 权限系统")
print("")
print("🚀 请直接运行以下命令启动系统：")
print("   ./dev.sh          # 开发模式（推荐）")
print("   ./start.sh        # 生产模式")
print("   python3 main.py   # 手动启动")
print("")
print("🔑 默认管理员账户：")
print("   用户名: admin")
print("   密码: admin123")
print("   登录地址: http://localhost:8000/static/login.html")
print("")

async def legacy_init_support():
    """为兼容旧脚本提供的遗留支持"""
    try:
        print("🔄 执行兼容性初始化...")
        
        # 初始化存储层
        from app.storage.redis_manager import redis_manager
        from app.storage.json_store import init_json_stores
        
        if not redis_manager.is_healthy():
            print("❌ Redis初始化失败")
            return False
            
        if not init_json_stores():
            print("❌ JSON存储初始化失败")
            return False
            
        # 初始化认证服务
        from app.services.auth_service import init_auth_service
        if not init_auth_service():
            print("❌ 认证服务初始化失败")
            return False
        
        print("✅ 兼容性初始化完成")
        print("💡 建议直接使用 ./dev.sh 启动系统以获得完整功能")
        return True
        
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return False

async def main():
    """主函数"""
    print("=" * 60)
    print("🚀 Telegram消息采集审核系统 v3.0")
    print("⚡ Redis + JSON 存储架构")
    print("=" * 60)
    
    # 执行兼容性初始化
    success = await legacy_init_support()
    
    if success:
        print("\n🎉 系统初始化完成！")
        print("📖 详细文档请查看：")
        print("   - CLAUDE.md（开发指南）")
        print("   - README.md（用户手册）")
    else:
        print("\n💥 初始化失败，请检查系统环境")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))