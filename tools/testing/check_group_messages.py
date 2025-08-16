#!/usr/bin/env python3
"""
检查组图消息状态
查看消息ID #-1001956665373:57756-57759 的当前状态
"""
import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

def check_group_messages():
    """检查组图消息状态"""
    print("🔍 检查组图消息状态...")
    
    try:
        # 直接读取Redis数据文件
        redis_data_file = "data/redis_data.json"
        
        if not os.path.exists(redis_data_file):
            print(f"❌ Redis数据文件不存在: {redis_data_file}")
            return False
        
        # 读取数据
        with open(redis_data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 目标频道和消息ID
        channel_id = "-1001956665373"
        target_message_ids = [57756, 57757, 57758, 57759]
        
        # 获取频道消息
        messages_key = f"messages:{channel_id}"
        if messages_key not in data:
            print(f"❌ 频道 {channel_id} 没有消息数据")
            return False
        
        channel_data = data[messages_key]
        if isinstance(channel_data, str):
            channel_data = json.loads(channel_data)
        
        messages = channel_data.get('messages', [])
        print(f"📊 频道 {channel_id} 共有 {len(messages)} 条消息")
        
        # 查找目标消息
        found_messages = []
        for msg in messages:
            telegram_id = msg.get('telegram_message_id')
            if telegram_id in target_message_ids:
                found_messages.append(msg)
        
        print(f"\n📋 找到 {len(found_messages)}/{len(target_message_ids)} 条目标消息:")
        
        for msg in found_messages:
            telegram_id = msg.get('telegram_message_id')
            print(f"\n✅ 消息 #{telegram_id}:")
            print(f"   Redis ID: {msg.get('message_id')}")
            print(f"   内容: {msg.get('content', '')[:50]}...")
            print(f"   媒体类型: {msg.get('media_type', 'None')}")
            
            media_url = msg.get('media_url', 'None')
            if media_url and media_url != 'None':
                # 检查媒体文件是否存在
                if os.path.exists(media_url):
                    file_size = os.path.getsize(media_url)
                    print(f"   媒体文件: ✅ {media_url} ({file_size} bytes)")
                else:
                    print(f"   媒体文件: ❌ {media_url} (不存在)")
            else:
                print(f"   媒体文件: None")
            
            print(f"   分组ID: {msg.get('grouped_id', 'None')}")
            print(f"   是否组合: {msg.get('is_combined', False)}")
            print(f"   状态: {msg.get('status', 'unknown')}")
            print(f"   创建时间: {msg.get('created_at', 'unknown')}")
        
        # 查找组合消息
        combined_messages = [msg for msg in messages if msg.get('is_combined')]
        if combined_messages:
            print(f"\n🔗 组合消息 ({len(combined_messages)} 条):")
            for msg in combined_messages:
                grouped_id = msg.get('grouped_id')
                combined_msgs = msg.get('combined_messages', [])
                media_group = msg.get('media_group', [])
                
                # 检查是否与目标消息相关
                is_target_group = False
                if combined_msgs:
                    for cmsg in combined_msgs:
                        if cmsg.get('message_id') in target_message_ids:
                            is_target_group = True
                            break
                
                if is_target_group:
                    print(f"\n   📦 目标组合消息 (Redis ID: {msg.get('message_id')}):")
                    print(f"      分组ID: {grouped_id}")
                    print(f"      包含消息: {len(combined_msgs)}")
                    print(f"      媒体组: {len(media_group)}")
                    print(f"      内容: {msg.get('content', '')[:100]}...")
        
        # 检查缺失的消息
        missing_ids = set(target_message_ids) - set(msg.get('telegram_message_id') for msg in found_messages)
        if missing_ids:
            print(f"\n⚠️  缺失的消息ID: {missing_ids}")
            
            # 建议解决方案
            print(f"\n💡 建议解决方案:")
            print(f"   1. 检查消息是否在组合器待处理队列中")
            print(f"   2. 重新运行历史消息采集")
            print(f"   3. 检查过滤器是否误过滤了这些消息")
        else:
            print(f"\n🎉 所有目标消息都已找到！")
        
        return len(missing_ids) == 0
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = check_group_messages()
    sys.exit(0 if result else 1)