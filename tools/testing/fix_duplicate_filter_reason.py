#!/usr/bin/env python3
"""
修复测试重复消息的filter_reason
"""
import sys
import asyncio

# 添加项目路径
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_store import RedisMessageStore

async def fix_duplicate_filter_reason():
    """修复重复消息的filter_reason"""
    print("=== 修复重复消息filter_reason ===")
    
    try:
        # 初始化Redis
        redis_store = RedisMessageStore()
        
        # 查找所有包含duplicate_original_id的消息
        msg_keys = redis_store.redis.keys("msg:*")
        fixed_count = 0
        
        for key in msg_keys:
            try:
                msg_data = redis_store.redis.hgetall(key)
                if not msg_data:
                    continue
                
                # 转换字节数据
                msg = {}
                for k, v in msg_data.items():
                    if isinstance(k, bytes):
                        k = k.decode('utf-8')
                    if isinstance(v, bytes):
                        v = v.decode('utf-8')
                    msg[k] = v
                
                # 检查是否有duplicate_original_id但没有正确的filter_reason
                if msg.get('duplicate_original_id') and msg.get('filter_reason') != 'duplicate_detector':
                    # 更新filter_reason
                    msg['filter_reason'] = 'duplicate_detector'
                    if not msg.get('reject_reason'):
                        msg['reject_reason'] = '检测到重复内容 (text)'
                    
                    # 解析channel_id和message_id
                    channel_id = msg.get('source_channel')
                    message_id = msg.get('message_id')
                    
                    if channel_id and message_id:
                        redis_store.save_message(channel_id, int(message_id), msg)
                        fixed_count += 1
                        print(f"   ✅ 修复消息: {channel_id}:{message_id}")
                        
            except Exception as e:
                continue
        
        print(f"\n总共修复了 {fixed_count} 条重复消息的filter_reason")
        
        # 验证修复结果
        print(f"\n验证修复结果...")
        duplicate_count = 0
        
        for key in msg_keys:
            try:
                msg_data = redis_store.redis.hgetall(key)
                if not msg_data:
                    continue
                
                msg = {}
                for k, v in msg_data.items():
                    if isinstance(k, bytes):
                        k = k.decode('utf-8')
                    if isinstance(v, bytes):
                        v = v.decode('utf-8')
                    msg[k] = v
                
                # 统计重复消息
                if (msg.get('duplicate_original_id') or 
                    (msg.get('filter_reason') and 'duplicate' in msg.get('filter_reason').lower()) or
                    (msg.get('reject_reason') and '重复' in msg.get('reject_reason'))):
                    duplicate_count += 1
                        
            except Exception as e:
                continue
        
        print(f"   当前重复消息总数: {duplicate_count}")
        
        print(f"\n🌐 现在可以测试重复消息页面:")
        print(f"   http://localhost:8000/static/index.html")
        print(f"   (点击「重复消息」统计卡片，应该能看到多条消息)")
        
        print("\n=== 修复完成 ===")
        
    except Exception as e:
        print(f"修复失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(fix_duplicate_filter_reason())