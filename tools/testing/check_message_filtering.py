#!/usr/bin/env python3
"""
检查指定消息的过滤详情
"""

import sys
import os
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.storage.redis_manager import redis_manager
from app.services.unified_filter_engine import filter_engine_compat


async def check_message_filtering(message_id: str):
    """检查消息过滤详情"""
    print(f"🔍 检查消息ID: {message_id} 的过滤情况")
    print("=" * 60)
    
    # 初始化存储
    try:
        redis_manager.is_healthy()
        redis_store = redis_manager
        
        # 分离频道ID和消息ID
        if ':' not in message_id:
            print(f"❌ 消息ID格式错误，应为 channel_id:message_id")
            return
        
        channel_id, msg_id = message_id.split(':', 1)
        
        # 获取消息
        message = redis_manager.get_message(channel_id, msg_id)
        if not message:
            print(f"❌ 消息 {message_id} 不存在")
            return
        
        print(f"📝 消息基本信息:")
        print(f"   ID: {message.get('id')}")
        print(f"   频道: {message.get('channel_id')}")
        print(f"   状态: {message.get('status')}")
        print(f"   创建时间: {message.get('created_at')}")
        print(f"   消息类型: {message.get('message_type', 'unknown')}")
        if message.get('rejected_reason'):
            print(f"   拒绝原因: {message.get('rejected_reason')}")
        if message.get('reject_reason'):
            print(f"   拒绝原因2: {message.get('reject_reason')}")
        if message.get('filter_reason'):
            print(f"   过滤原因: {message.get('filter_reason')}")
        
        print(f"   来源频道: {message.get('source_channel')}")
        print(f"   OCR处理: {message.get('ocr_processed')}")
        print(f"   OCR广告得分: {message.get('ocr_ad_score')}")
        print(f"   是否组合消息: {message.get('is_combined')}")
        print(f"   移除隐藏链接: {message.get('removed_hidden_links')}")
        
        # 显示实体信息
        if message.get('entities'):
            print(f"   消息实体: {message.get('entities')}")
        
        # 显示完整消息信息用于调试
        print(f"\n🔍 完整消息数据:")
        for key, value in message.items():
            if key not in ['content', 'filtered_content']:  # 这些会单独显示
                print(f"   {key}: {value}")
        
        if message.get('media_files'):
            print(f"   媒体文件: {message.get('media_files')}")
        if message.get('caption'):
            print(f"   媒体说明: {message.get('caption')}")
        
        # 获取原始内容
        content = message.get('content', '')
        filtered_content = message.get('filtered_content', content)
        
        print(f"\n📄 内容信息:")
        print(f"   原始长度: {len(content)} 字符")
        print(f"   过滤后长度: {len(filtered_content)} 字符")
        print(f"   内容变化: {'是' if content != filtered_content else '否'}")
        
        print(f"\n📝 原始内容:")
        print("-" * 40)
        print(content[:500] + "..." if len(content) > 500 else content)
        
        if content != filtered_content:
            print(f"\n📄 过滤后内容:")
            print("-" * 40)
            print(filtered_content[:500] + "..." if len(filtered_content) > 500 else filtered_content)
        
        # 使用当前过滤器重新分析
        print(f"\n🔍 重新分析过滤流程:")
        print("-" * 40)
        
        try:
            is_ad, new_filtered_content, filter_reason, _ = await filter_engine_compat.filter_message(
                content,
                channel_id=message.get('channel_id'),
                message_obj=None,
                media_files=None
            )
            
            print(f"当前过滤结果:")
            print(f"   广告判定: {'是' if is_ad else '否'}")
            print(f"   过滤原因: {filter_reason or '无'}")
            print(f"   内容长度变化: {len(content)} → {len(new_filtered_content)}")
            
            if new_filtered_content != content:
                print(f"\n📄 当前过滤器处理后的内容:")
                print("-" * 40)
                print(new_filtered_content[:500] + "..." if len(new_filtered_content) > 500 else new_filtered_content)
        
        except Exception as e:
            print(f"❌ 重新分析失败: {e}")
        
        print(f"\n📊 对比总结:")
        print(f"   原始消息状态: {message.get('status')}")
        print(f"   原始拒绝原因: {message.get('rejected_reason', '无')}")
        print(f"   当前会如何处理: {'拒绝' if is_ad else '通过'}")
        
        if message.get('status') == 'rejected' and not is_ad:
            print(f"   ⚠️ 注意：原本被拒绝的消息，现在会通过")
        elif message.get('status') == 'approved' and is_ad:
            print(f"   ⚠️ 注意：原本通过的消息，现在会被拒绝")
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 check_message_filtering.py <message_id>")
        print("示例: python3 check_message_filtering.py -1002557968812:2353")
        sys.exit(1)
    
    message_id = sys.argv[1]
    asyncio.run(check_message_filtering(message_id))