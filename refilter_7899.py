#!/usr/bin/env python3
"""重新过滤特定消息的工具脚本"""

import sys
import asyncio
import os
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_store import init_redis_stores, get_redis_message_store
from app.services.intelligent_tail_filter import intelligent_tail_filter
from app.services.content_filter import content_filter

async def refilter_message(message_id: str):
    """重新过滤指定消息ID的消息"""
    
    # 初始化Redis存储
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    if not init_redis_stores(redis_url):
        print("❌ Redis连接失败")
        return
    
    store = get_redis_message_store()
    
    # 解析消息ID（格式：channel_id:message_id 或单独的数字ID）
    if ':' in message_id:
        channel_id, msg_id = message_id.split(':', 1)
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
        print(f"❌ 未找到消息 {channel_id}:{msg_id}")
        return
    
    print(f"\n🔍 重新过滤消息 {channel_id}:{msg_id}")
    print(f"原始内容长度: {len(msg_data.get('content', ''))} 字符")
    print(f"当前过滤后长度: {len(msg_data.get('filtered_content', '')) if msg_data.get('filtered_content') else 0} 字符")
    
    # 强制重新加载训练数据
    try:
        intelligent_tail_filter._load_training_data(force_reload=True)
        print("✅ 重新加载训练数据")
    except Exception as e:
        print(f"⚠️ 重新加载训练数据失败: {e}")
    
    # 重新过滤
    original_content = msg_data.get('content', '')
    if not original_content:
        print("⚠️ 消息内容为空")
        return
    
    try:
        filtered = content_filter.filter_promotional_content(original_content)
        
        print(f"\n📝 新的过滤结果:")
        print(f"过滤后长度: {len(filtered)} 字符")
        print(f"内容预览: {filtered[:200]}{'...' if len(filtered) > 200 else ''}")
        
        # 更新Redis存储
        current_filtered = msg_data.get('filtered_content', '')
        if filtered != current_filtered:
            # 更新消息数据
            update_data = {
                'filtered_content': filtered,
                'updated_at': msg_data.get('updated_at', '')
            }
            
            # 保存更新的消息
            msg_data.update(update_data)
            success = store.save_message(channel_id, msg_id, msg_data)
            
            if success:
                print("\n✅ Redis存储已更新")
            else:
                print("\n❌ Redis存储更新失败")
        else:
            print("\n⚠️ 过滤结果相同，无需更新")
    
    except Exception as e:
        print(f"❌ 过滤处理失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主函数"""
    if len(sys.argv) > 1:
        message_id = sys.argv[1]
    else:
        message_id = input("请输入要重新过滤的消息ID (格式: channel_id:message_id 或 message_id): ").strip()
    
    if not message_id:
        print("❌ 消息ID不能为空")
        return
    
    await refilter_message(message_id)

if __name__ == "__main__":
    asyncio.run(main())