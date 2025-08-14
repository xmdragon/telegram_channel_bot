#!/usr/bin/env python3
"""测试重新过滤消息的工具脚本"""

import asyncio
import sys
import os
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_store import init_redis_stores, get_redis_message_store
from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.services.content_filter import content_filter

async def test_refilter(message_id):
    """测试重新过滤指定消息ID的消息"""
    
    # 初始化Redis存储
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    if not init_redis_stores(redis_url):
        print("❌ Redis连接失败")
        return
    
    store = get_redis_message_store()
    
    # 解析消息ID
    if ':' in str(message_id):
        channel_id, msg_id = str(message_id).split(':', 1)
        msg_id = int(msg_id)
    else:
        # 搜索所有频道中的消息
        msg_id = int(message_id)
        channel_id = None
        
        # 尝试从所有消息中查找
        all_messages = store.get_all_messages(limit=1000)
        target_msg = None
        for msg in all_messages:
            if msg.get('message_id') == msg_id:
                target_msg = msg
                channel_id = msg.get('channel_id')
                break
        
        if not target_msg:
            print(f"❌ 未找到消息 #{msg_id}")
            return
    
    # 获取消息数据
    msg_data = store.get_message(channel_id, msg_id)
    
    if not msg_data:
        print(f"❌ 消息{message_id}不存在")
        return
    
    print(f"\n📋 消息ID: {channel_id}:{msg_id}")
    print(f"原始内容长度: {len(msg_data.get('content', ''))} 字符")
    print(f"原始内容:\n{msg_data.get('content', '')}\n")
    print(f"当前过滤内容长度: {len(msg_data.get('filtered_content', ''))}")
    print(f"当前过滤内容:\n{msg_data.get('filtered_content', '')}\n")
    print("-" * 50)
    
    # 强制重新加载训练数据
    print("🔄 重新加载训练数据...")
    try:
        intelligent_tail_filter._load_training_data(force_reload=True)
        stats = intelligent_tail_filter.get_statistics()
        print(f"✅ 加载了 {stats['total_samples']} 个训练样本")
    except Exception as e:
        print(f"⚠️ 加载训练数据失败: {e}")
    
    original_content = msg_data.get('content', '')
    if not original_content:
        print("⚠️ 消息内容为空")
        return
    
    # 测试intelligent_tail_filter直接过滤
    print("\n🧪 测试intelligent_tail_filter:")
    try:
        filtered, was_filtered, tail = intelligent_tail_filter.filter_message(original_content)
        if was_filtered:
            print(f"✅ 检测到尾部，过滤后: {len(original_content)} -> {len(filtered)}")
            print(f"移除的尾部:\n{tail}")
        else:
            print("❌ 未检测到尾部")
    except Exception as e:
        print(f"❌ intelligent_tail_filter测试失败: {e}")
    
    # 测试完整的content_filter
    print("\n🔍 测试content_filter.filter_promotional_content:")
    try:
        filtered_content = content_filter.filter_promotional_content(
            original_content,
            channel_id=channel_id
        )
        print(f"过滤后: {len(original_content)} -> {len(filtered_content)}")
        
        current_filtered = msg_data.get('filtered_content', '')
        if len(filtered_content) < len(current_filtered):
            print("\n✅ 新的过滤更有效，更新Redis存储...")
            
            # 更新消息数据
            msg_data['filtered_content'] = filtered_content
            success = store.save_message(channel_id, msg_id, msg_data)
            
            if success:
                print("✅ Redis存储已更新")
            else:
                print("❌ Redis存储更新失败")
        else:
            print("\n⚠️ 当前过滤已经是最优的")
        
        print(f"\n📝 最终过滤内容预览:\n{filtered_content[:500]}{'...' if len(filtered_content) > 500 else ''}")
        
    except Exception as e:
        print(f"❌ content_filter测试失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主函数"""
    if len(sys.argv) > 1:
        message_id = sys.argv[1]
    else:
        message_id = input("请输入要测试过滤的消息ID (格式: channel_id:message_id 或 message_id): ").strip()
    
    if not message_id:
        print("❌ 消息ID不能为空")
        return
    
    await test_refilter(message_id)

if __name__ == "__main__":
    asyncio.run(main())