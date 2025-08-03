#!/usr/bin/env python3
"""
Telethon 设置脚本
帮助用户配置 Telegram API 凭据和手机号码
"""
import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import init_db
from app.services.config_manager import config_manager, init_default_configs

async def setup_telethon():
    """设置 Telethon 配置"""
    print("🚀 Telegram 消息审核系统 - Telethon 设置")
    print("=" * 50)
    
    # 初始化数据库和配置
    await init_db()
    await init_default_configs()
    
    print("\n📋 配置步骤:")
    print("1. 访问 https://my.telegram.org")
    print("2. 登录您的 Telegram 账号")
    print("3. 点击 'API development tools'")
    print("4. 创建一个新的应用")
    print("5. 记录下 API ID 和 API Hash")
    print("\n")
    
    # 获取 API ID
    api_id = input("请输入您的 Telegram API ID: ").strip()
    if not api_id:
        print("❌ API ID 不能为空")
        return
    
    try:
        api_id = int(api_id)
    except ValueError:
        print("❌ API ID 必须是数字")
        return
    
    # 获取 API Hash
    api_hash = input("请输入您的 Telegram API Hash: ").strip()
    if not api_hash:
        print("❌ API Hash 不能为空")
        return
    
    # 获取手机号码
    phone = input("请输入您的 Telegram 手机号码 (格式: +8613800138000): ").strip()
    if not phone:
        print("❌ 手机号码不能为空")
        return
    
    # 验证手机号码格式
    if not phone.startswith('+'):
        print("❌ 手机号码必须以 + 开头")
        return
    
    # 保存配置
    print("\n💾 正在保存配置...")
    
    try:
        await config_manager.set_config("telegram.api_id", str(api_id), "Telegram API ID", "string")
        await config_manager.set_config("telegram.api_hash", api_hash, "Telegram API Hash", "string")
        await config_manager.set_config("telegram.phone", phone, "Telegram手机号码", "string")
        
        print("✅ 配置保存成功!")
        
        # 测试连接
        print("\n🔗 正在测试连接...")
        await test_telethon_connection(api_id, api_hash, phone)
        
    except Exception as e:
        print(f"❌ 保存配置失败: {e}")
        return
    
    print("\n🎉 设置完成!")
    print("\n📝 下一步:")
    print("1. 运行 'python main.py' 启动系统")
    print("2. 首次启动时会要求输入验证码")
    print("3. 访问 http://localhost:8000/config 配置频道设置")

async def test_telethon_connection(api_id: int, api_hash: str, phone: str):
    """测试 Telethon 连接"""
    try:
        from telethon import TelegramClient
        
        # 创建临时客户端进行测试
        client = TelegramClient(f'test_session_{phone}', api_id, api_hash)
        
        print("正在连接到 Telegram...")
        await client.connect()
        
        if not await client.is_user_authorized():
            print("⚠️  需要验证码验证，请在系统启动时输入")
        else:
            print("✅ 连接成功，账号已授权")
        
        await client.disconnect()
        
    except Exception as e:
        print(f"❌ 连接测试失败: {e}")
        print("请检查 API ID、API Hash 和手机号码是否正确")

def main():
    """主函数"""
    try:
        asyncio.run(setup_telethon())
    except KeyboardInterrupt:
        print("\n\n❌ 设置已取消")
    except Exception as e:
        print(f"\n❌ 设置失败: {e}")

if __name__ == "__main__":
    main() 