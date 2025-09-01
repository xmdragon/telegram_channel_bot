#!/usr/bin/env python3
"""
更新测试重复消息，添加频道标题和链接前缀
"""
import sys
import asyncio

# 添加项目路径
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_manager import redis_manager

async def update_test_duplicate():
    """更新测试重复消息数据"""
    print("=== 更新测试重复消息 ===")
    
    try:
        # 初始化Redis
        # redis_store = RedisMessageStore()  # 已替换为redis_manager
        
        # 测试数据参数
        test_channel = "test_channel_duplicate"
        original_msg_id = 1001
        duplicate_msg_id = 1002
        
        # 更新原始消息
        original_msg = redis_manager.get_message(test_channel, original_msg_id)
        if original_msg:
            original_msg.update({
                'source_channel_title': '测试重复频道',
                'source_channel_link_prefix': 'https://t.me/c/test_channel_duplicate',
                'media_display_url': None,  # 确保没有媒体显示URL
            })
            redis_manager.save_message(test_channel, original_msg_id, original_msg)
            print(f"✅ 原始消息已更新: {test_channel}:{original_msg_id}")
        else:
            print(f"❌ 找不到原始消息: {test_channel}:{original_msg_id}")
        
        # 更新重复消息
        duplicate_msg = redis_manager.get_message(test_channel, duplicate_msg_id)
        if duplicate_msg:
            duplicate_msg.update({
                'source_channel_title': '测试重复频道',
                'source_channel_link_prefix': 'https://t.me/c/test_channel_duplicate',
                'media_display_url': None,  # 确保没有媒体显示URL
            })
            redis_manager.save_message(test_channel, duplicate_msg_id, duplicate_msg)
            print(f"✅ 重复消息已更新: {test_channel}:{duplicate_msg_id}")
        else:
            print(f"❌ 找不到重复消息: {test_channel}:{duplicate_msg_id}")
        
        # 验证更新
        print("\n验证更新结果...")
        orig_updated = redis_manager.get_message(test_channel, original_msg_id)
        dup_updated = redis_manager.get_message(test_channel, duplicate_msg_id)
        
        if orig_updated and dup_updated:
            print(f"   ✅ 原始消息频道标题: {orig_updated.get('source_channel_title')}")
            print(f"   ✅ 重复消息频道标题: {dup_updated.get('source_channel_title')}")
            print(f"   ✅ 重复消息重复信息: {dup_updated.get('duplicate_original_id')}")
            print(f"   ✅ 重复消息链接前缀: {dup_updated.get('source_channel_link_prefix')}")
            
            print(f"\n🌐 测试链接:")
            print(f"   重复消息对比页面: http://localhost:8000/static/index.html")
            print(f"   (点击统计面板中的「重复消息」)")
        else:
            print("   ❌ 更新验证失败")
        
        print("\n=== 更新完成 ===")
        
    except Exception as e:
        print(f"更新失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(update_test_duplicate())