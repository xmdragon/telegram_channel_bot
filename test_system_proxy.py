#!/usr/bin/env python3
"""测试系统代理和Telegram连接"""
import os
import asyncio
import urllib.request
from telethon import TelegramClient
from telethon.sessions import StringSession

def check_system_proxy():
    """检查系统代理设置"""
    print("=== 系统代理设置 ===")
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    all_proxy = os.environ.get('ALL_PROXY') or os.environ.get('all_proxy')
    
    print(f"HTTP_PROXY: {http_proxy}")
    print(f"HTTPS_PROXY: {https_proxy}")
    print(f"ALL_PROXY: {all_proxy}")
    
    # 测试网络连接
    print("\n=== 测试网络连接 ===")
    try:
        response = urllib.request.urlopen('https://www.google.com', timeout=5)
        print("✅ 可以访问Google")
    except Exception as e:
        print(f"❌ 无法访问Google: {e}")
    
    try:
        response = urllib.request.urlopen('https://api.telegram.org', timeout=5)
        print("✅ 可以访问Telegram API")
    except Exception as e:
        print(f"❌ 无法访问Telegram API: {e}")
    
    return http_proxy, https_proxy, all_proxy

async def test_telegram_with_proxy():
    """测试Telegram连接（使用系统代理）"""
    api_id = 24382238
    api_hash = "a9267901950e6271bc2ad8e3db0aa80f"
    
    # 检查系统代理
    http_proxy, https_proxy, all_proxy = check_system_proxy()
    
    # 尝试从环境变量解析代理
    proxy = None
    proxy_url = https_proxy or http_proxy or all_proxy
    
    if proxy_url:
        print(f"\n检测到系统代理: {proxy_url}")
        # 解析代理URL
        # 格式: http://127.0.0.1:1087 或 socks5://127.0.0.1:1086
        try:
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            
            if parsed.scheme in ['socks5', 'socks5h']:
                import socks
                proxy = (socks.SOCKS5, parsed.hostname, parsed.port)
                print(f"使用SOCKS5代理: {parsed.hostname}:{parsed.port}")
            elif parsed.scheme in ['http', 'https']:
                proxy = ('http', parsed.hostname, parsed.port)
                print(f"使用HTTP代理: {parsed.hostname}:{parsed.port}")
        except Exception as e:
            print(f"解析代理失败: {e}")
    
    print(f"\n=== 测试Telegram连接 ===")
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash[:10]}...")
    
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
        
        is_authorized = await client.is_user_authorized()
        print(f"授权状态: {'已授权' if is_authorized else '未授权'}")
        
        await client.disconnect()
        return True
        
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        
        print("\n=== 解决方案 ===")
        if not proxy_url:
            print("未检测到系统代理，请确保：")
            print("1. Shadowrocket已开启并连接")
            print("2. 在终端中设置代理环境变量：")
            print("   export http_proxy=http://127.0.0.1:1087")
            print("   export https_proxy=http://127.0.0.1:1087")
            print("   export all_proxy=socks5://127.0.0.1:1086")
        else:
            print("已检测到代理但连接失败，可能原因：")
            print("1. 代理服务器无法访问Telegram")
            print("2. API凭据有问题")
            print("3. 需要使用不同类型的代理（HTTP/SOCKS5）")
        
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(test_telegram_with_proxy())
        if not success:
            print("\n提示：运行以下命令设置代理后重试：")
            print("export https_proxy=http://127.0.0.1:1087")
            print("export http_proxy=http://127.0.0.1:1087")
            print("export all_proxy=socks5://127.0.0.1:1086")
    except KeyboardInterrupt:
        print("\n测试中断")