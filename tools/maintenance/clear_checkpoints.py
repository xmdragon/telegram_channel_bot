#!/usr/bin/env python3
"""
临时脚本：清除所有 Redis checkpoint，让消息采集重新开始
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, '/Users/eric/workspace/telegram_channel_bot')

def clear_checkpoints():
    """清除所有频道的 checkpoint"""
    try:
        from app.storage.redis_client import get_redis_client
        
        # 直接连接 Redis
        redis = get_redis_client()
        if not redis:
            print("❌ 无法连接到 Redis")
            return False
            
        # 获取所有 checkpoint 相关的键
        checkpoint_keys = redis.keys("channel:checkpoint*")
        
        if checkpoint_keys:
            # 删除所有 checkpoint
            redis.delete(*checkpoint_keys)
            print(f"✅ 已清除 {len(checkpoint_keys)} 个 checkpoint")
            
            # 显示清除的键
            print("\n清除的键列表：")
            for key in checkpoint_keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                print(f"  - {key_str}")
                
            return True
        else:
            print("📄 没有找到任何 checkpoint，可能已经清除或从未设置")
            return True
            
    except Exception as e:
        print(f"❌ 清除 checkpoint 失败: {e}")
        return False

def main():
    print("🧹 开始清除 Redis checkpoint...")
    print("=" * 50)
    
    success = clear_checkpoints()
    
    print("=" * 50)
    if success:
        print("✅ 操作完成！")
        print("💡 现在重启采集服务，系统将重新开始采集历史消息")
    else:
        print("❌ 操作失败！请检查 Redis 连接")
        
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())