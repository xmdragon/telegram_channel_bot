#!/usr/bin/env python3
"""
Telethon 集成测试脚本
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import init_db
from app.services.config_manager import config_manager, init_default_configs
from app.telegram.bot import TelegramClient

async def test_telethon_integration():
    """测试 Telethon 集成"""
    print("🧪 测试 Telethon 集成")
    print("=" * 40)
    
    try:
        # 初始化数据库和配置
        await init_db()
        await init_default_configs()
        
        # 获取配置
        api_id = await config_manager.get_config("telegram.api_id")
        api_hash = await config_manager.get_config("telegram.api_hash")
        phone = await config_manager.get_config("telegram.phone")
        
        print(f"📋 配置检查:")
        print(f"  API ID: {'✅ 已配置' if api_id else '❌ 未配置'}")
        print(f"  API Hash: {'✅ 已配置' if api_hash else '❌ 未配置'}")
        print(f"  手机号码: {'✅ 已配置' if phone else '❌ 未配置'}")
        
        if not all([api_id, api_hash, phone]):
            print("\n❌ 缺少必要的配置，请先运行 setup_telethon.py")
            return False
        
        # 测试创建客户端
        print("\n🔗 测试客户端创建...")
        try:
            client = TelegramClient()
            print("✅ 客户端创建成功")
        except Exception as e:
            print(f"❌ 客户端创建失败: {e}")
            return False
        
        # 测试配置获取
        print("\n⚙️  测试配置获取...")
        try:
            source_channels = await config_manager.get_config("channels.source_channels", [])
            review_group_id = await config_manager.get_config("channels.review_group_id", "")
            target_channel_id = await config_manager.get_config("channels.target_channel_id", "")
            
            print(f"  源频道: {len(source_channels)} 个")
            print(f"  审核群: {'✅ 已配置' if review_group_id else '❌ 未配置'}")
            print(f"  目标频道: {'✅ 已配置' if target_channel_id else '❌ 未配置'}")
            
        except Exception as e:
            print(f"❌ 配置获取失败: {e}")
            return False
        
        print("\n✅ 所有测试通过!")
        print("\n📝 下一步:")
        print("1. 运行 'python main.py' 启动系统")
        print("2. 首次启动时会要求输入验证码")
        print("3. 访问 http://localhost:8000/config 完成频道配置")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """主函数"""
    try:
        success = asyncio.run(test_telethon_integration())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ 测试已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 