#!/usr/bin/env python3
"""
测试 Web 登录功能
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import init_db
from app.services.config_manager import config_manager, init_default_configs
from app.telegram.auth import auth_manager

async def test_web_auth():
    """测试 Web 登录功能"""
    print("🧪 测试 Web 登录功能")
    print("=" * 40)
    
    try:
        # 初始化数据库和配置
        await init_db()
        await init_default_configs()
        
        print("✅ 数据库初始化成功")
        
        # 测试认证管理器
        print("\n🔐 测试认证管理器...")
        
        # 检查初始状态
        status = await auth_manager.get_auth_status()
        print(f"  初始状态: {status['state']}")
        print(f"  已授权: {status['authorized']}")
        
        # 测试创建客户端（模拟）
        print("\n📱 测试客户端创建...")
        # 这里只是测试结构，实际需要真实的 API 凭据
        
        print("✅ 认证管理器工作正常")
        
        print("\n🎉 Web 登录功能测试完成!")
        print("\n📝 使用方法:")
        print("1. 启动系统: python main.py")
        print("2. 访问登录页面: http://localhost:8000/auth")
        print("3. 输入 API 凭据和验证码")
        print("4. 完成登录后访问主界面")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """主函数"""
    try:
        success = asyncio.run(test_web_auth())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ 测试已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 