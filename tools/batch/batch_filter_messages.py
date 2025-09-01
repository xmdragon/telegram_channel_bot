#!/usr/bin/env python3
"""
批量对现有未审核消息应用语义尾部过滤策略
"""
import asyncio
import sys
import os
import json
from datetime import datetime

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.storage.redis_manager import redis_manager
from app.services.tail_filter_engine import TailFilterEngine

# 直接使用Redis URL，避免复杂的配置依赖
REDIS_URL = "redis://localhost:6379"


async def batch_filter_messages():
    """批量过滤现有未审核消息"""
    print("🚀 开始批量过滤现有未审核消息...")
    
    # 初始化Redis存储
    init_redis_stores(REDIS_URL)
    redis_store = redis_manager
    
    # 初始化过滤引擎
    filter_engine = TailFilterEngine()
    
    try:
        # 获取所有未审核的消息
        messages = redis_manager.get_messages_by_status('pending', limit=1000)
        
        if not messages:
            print("📭 没有找到未审核的消息")
            return
        
        print(f"📊 找到 {len(messages)} 条未审核消息，开始应用语义尾部过滤...")
        
        filtered_count = 0
        processed_count = 0
        
        for message in messages:
            try:
                if not message.get('content'):
                    continue
                
                channel_id = str(message['channel_id'])
                message_id = int(message['message_id'])
                content = message['content']
                
                # 应用语义尾部过滤
                has_media = bool(
                    message.get('media_type') or 
                    message.get('media_url') or 
                    (message.get('combined_messages') and 
                     any(m.get('media_type') for m in message.get('combined_messages', [])))
                )
                
                filtered_content, was_filtered, removed_tail, analysis = filter_engine.filter_message(
                    content, has_media
                )
                
                # 更新Redis中的过滤后内容
                full_msg = redis_manager.get_message(channel_id, message_id)
                if full_msg:
                    full_msg['filtered_content'] = filtered_content
                    redis_manager.save_message(channel_id, message_id, full_msg)
                
                processed_count += 1
                
                if was_filtered:
                    filtered_count += 1
                    print(f"🔧 消息 {channel_id}:{message_id}: 过滤 {len(content)} → {len(filtered_content)} 字符")
                else:
                    print(f"✅ 消息 {channel_id}:{message_id}: 无需过滤 ({len(content)} 字符)")
                    
            except Exception as e:
                print(f"❌ 处理消息 {message.get('channel_id')}:{message.get('message_id')} 时出错: {str(e)}")
                continue
        
        print(f"\n🎉 批量过滤完成!")
        print(f"📊 处理统计:")
        print(f"   - 处理消息数: {processed_count}")
        print(f"   - 过滤消息数: {filtered_count}")
        print(f"   - 保持原样数: {processed_count - filtered_count}")
        if processed_count > 0:
            print(f"   - 过滤率: {(filtered_count/processed_count*100):.1f}%")
        else:
            print("   - 过滤率: 0.0%")
        
    except Exception as e:
        print(f"❌ 批量过滤失败: {str(e)}")
        raise


async def show_filter_statistics():
    """显示过滤统计信息"""
    print("\n📊 过滤效果统计...")
    
    # 初始化Redis存储
    init_redis_stores(REDIS_URL)
    redis_store = redis_manager
    
    try:
        # 获取所有消息
        messages = redis_manager.get_all_messages(limit=5000)
        
        if not messages:
            print("📭 没有找到过滤数据")
            return
        
        total_messages = len(messages)
        filtered_messages = 0
        total_original_length = 0
        total_filtered_length = 0
        
        for message in messages:
            try:
                content = message.get('content')
                filtered_content = message.get('filtered_content')
                
                if content and filtered_content:
                    original_len = len(content)
                    filtered_len = len(filtered_content)
                    
                    total_original_length += original_len
                    total_filtered_length += filtered_len
                    
                    # 如果过滤后的内容比原始内容短，说明被过滤了
                    if filtered_len < original_len:
                        filtered_messages += 1
                        
            except Exception as e:
                continue
        
        print(f"📈 过滤统计结果:")
        print(f"   - 总消息数: {total_messages}")
        print(f"   - 被过滤消息数: {filtered_messages}")
        if total_messages > 0:
            print(f"   - 过滤率: {(filtered_messages/total_messages*100):.1f}%")
        else:
            print("   - 过滤率: 0.0%")
        print(f"   - 原始总长度: {total_original_length} 字符")
        print(f"   - 过滤后总长度: {total_filtered_length} 字符")
        if total_original_length > 0:
            print(f"   - 内容保留率: {(total_filtered_length/total_original_length*100):.1f}%")
        else:
            print("   - 内容保留率: 100.0%")
        
    except Exception as e:
        print(f"❌ 统计失败: {str(e)}")


async def main():
    """主函数"""
    if len(sys.argv) > 1 and sys.argv[1] == '--stats':
        await show_filter_statistics()
    else:
        await batch_filter_messages()
        await show_filter_statistics()


if __name__ == "__main__":
    asyncio.run(main())