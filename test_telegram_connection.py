#!/usr/bin/env python3
"""测试Telegram连接"""
import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

async def test_connection():
    # 你的API凭据
    api_id = 24382238
    api_hash = "a9267901950e6271bc2ad8e3db0aa80f"
    
    print(f"测试连接到Telegram...")
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash[:10]}...")
    
    # 创建客户端
    client = TelegramClient(
        StringSession(),
        api_id,
        api_hash,
        connection_retries=3,
        retry_delay=5,
        timeout=30
    )
    
    try:
        print("\n尝试连接...")
        await client.connect()
        print("✅ 连接成功！")
        
        # 检查授权状态
        is_authorized = await client.is_user_authorized()
        print(f"授权状态: {'已授权' if is_authorized else '未授权'}")
        
        if not is_authorized:
            print("\n需要进行登录认证")
            print("请在Web界面完成认证流程")
        
        await client.disconnect()
        print("\n连接测试完成")
        return True
        
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        
        if "0 bytes read" in str(e):
            print("\n可能的原因：")
            print("1. 网络连接问题")
            print("2. 防火墙或代理设置")
            print("3. Telegram服务器暂时不可用")
            print("4. API凭据可能有问题")
            print("\n建议：")
            print("1. 检查网络连接")
            print("2. 尝试使用VPN或代理")
            print("3. 稍后重试")
            print("4. 在 https://my.telegram.org 验证API凭据")
        
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(test_connection())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试中断")
        sys.exit(1)