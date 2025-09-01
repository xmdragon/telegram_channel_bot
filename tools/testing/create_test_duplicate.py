#!/usr/bin/env python3
"""
创建测试重复消息来验证对比功能
"""
import sys
import asyncio
import json
from datetime import datetime

# 添加项目路径
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_manager import redis_manager

async def create_test_duplicate():
    """创建测试重复消息数据"""
    print("=== 创建测试重复消息 ===")
    
    try:
        # 初始化Redis
        # redis_store = RedisMessageStore()  # 已替换为redis_manager
        
        # 测试数据
        test_channel = "test_channel_duplicate"
        original_msg_id = 1001
        duplicate_msg_id = 1002
        
        # 1. 创建原始消息
        original_msg = {
            'source_channel': test_channel,
            'message_id': original_msg_id,
            'content': '这是原始测试消息，包含一些独特的内容。\n\n这里有一个链接：https://example.com/original \n\n以及一些特殊字符：🎉✨🚀',
            'status': 'approved',
            'created_at': datetime.utcnow().isoformat(),
            'media_type': None,
            'is_ad': False,
            'source_channel_title': '测试频道',
            'reviewed_by': 'system',
            'reviewed_at': datetime.utcnow().isoformat()
        }
        
        # 2. 创建重复消息（包含我们新增的重复信息字段）
        duplicate_msg = {
            'source_channel': test_channel,
            'message_id': duplicate_msg_id,
            'content': '这是重复测试消息，包含一些相同的内容。\n\n这里有一个链接：https://example.com/duplicate \n\n以及一些特殊字符：🎉✨🚀',
            'status': 'rejected',
            'created_at': datetime.utcnow().isoformat(),
            'media_type': None,
            'is_ad': False,
            'source_channel_title': '测试频道',
            'filter_reason': 'duplicate_detector',
            'reject_reason': '检测到重复内容 (text)',
            # 🔧 这是我们新增的字段
            'duplicate_original_id': f"{test_channel}:{original_msg_id}",
            'duplicate_type': 'text'
        }
        
        # 3. 保存消息
        print(f"保存原始消息: {test_channel}:{original_msg_id}")
        success1 = redis_manager.save_message(test_channel, original_msg_id, original_msg)
        
        print(f"保存重复消息: {test_channel}:{duplicate_msg_id}")
        success2 = redis_manager.save_message(test_channel, duplicate_msg_id, duplicate_msg)
        
        if success1 and success2:
            print("✅ 测试消息创建成功！")
            
            # 4. 验证数据
            print("\n验证数据...")
            orig_retrieved = redis_manager.get_message(test_channel, original_msg_id)
            dup_retrieved = redis_manager.get_message(test_channel, duplicate_msg_id)
            
            if orig_retrieved and dup_retrieved:
                print("✅ 数据验证成功")
                print(f"   原始消息状态: {orig_retrieved.get('status')}")
                print(f"   重复消息状态: {dup_retrieved.get('status')}")
                print(f"   重复信息: {dup_retrieved.get('duplicate_original_id')}")
                print(f"   重复类型: {dup_retrieved.get('duplicate_type')}")
                
                # 5. 输出测试URL
                print(f"\n🌐 测试链接:")
                print(f"   查看所有消息: http://localhost:8000/static/index.html")
                print(f"   查看重复消息: http://localhost:8000/static/index.html (点击重复消息统计)")
                
                # 6. 提供清理命令
                print(f"\n🧹 清理测试数据命令:")
                print(f"   python3 -c \"")
                print(f"import sys; sys.path.append('/Users/eric/workspace/telegram_channel_bot')") 
                print(f"from app.storage.redis_manager import redis_manager")
                print(f"r = RedisMessageStore()")
                print(f"r.delete_message('{test_channel}', {original_msg_id})")
                print(f"r.delete_message('{test_channel}', {duplicate_msg_id})")
                print(f"print('测试数据已清理')\"")
                
            else:
                print("❌ 数据验证失败")
        else:
            print("❌ 消息保存失败")
            
    except Exception as e:
        print(f"创建失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(create_test_duplicate())