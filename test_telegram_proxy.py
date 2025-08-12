#!/usr/bin/env python3
"""测试Telegram连接（支持代理）"""
import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
import socks

async def test_connection_with_proxy():
    # 你的API凭据
    api_id = 24382238
    api_hash = "a9267901950e6271bc2ad8e3db0aa80f"
    
    # 代理设置（如果需要）
    # 示例：SOCKS5代理
    # proxy = (socks.SOCKS5, 'proxy_host', proxy_port, True, 'username', 'password')
    # 示例：HTTP代理
    # proxy = ('http', 'proxy_host', proxy_port, True, 'username', 'password')
    
    # 如果不需要代理，设为None
    proxy = None
    
    print(f"测试连接到Telegram...")
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash[:10]}...")
    print(f"使用代理: {'是' if proxy else '否'}")
    
    # 创建客户端
    client = TelegramClient(
        StringSession(),
        api_id,
        api_hash,
        proxy=proxy,
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
        
        print("\n==========================")
        print("代理配置说明：")
        print("==========================")
        print("如果需要使用代理，请编辑此文件并配置proxy变量")
        print("\nSOCKS5代理示例：")
        print("proxy = (socks.SOCKS5, '127.0.0.1', 1080)")
        print("\nHTTP代理示例：")
        print("proxy = ('http', '127.0.0.1', 8080)")
        print("\n带认证的代理示例：")
        print("proxy = (socks.SOCKS5, 'host', port, True, 'username', 'password')")
        
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(test_connection_with_proxy())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试中断")
        sys.exit(1)