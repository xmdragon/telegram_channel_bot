#!/usr/bin/env python3
"""验证特定消息的工具脚本"""

import asyncio
import sys
import os
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_store import init_redis_stores, get_redis_message_store

async def verify_message(message_id: str = "7911"):
    """验证特定消息的过滤结果"""
    try:
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
            print(f"❌ 未找到消息 {channel_id}:{msg_id}")
            return
        
        print(f"📋 消息 {channel_id}:{msg_id} 详细信息:")
        print("=" * 60)
        
        # 基本信息
        print(f"状态: {msg_data.get('status', 'unknown')}")
        print(f"创建时间: {msg_data.get('created_at', '未知')}")
        print(f"更新时间: {msg_data.get('updated_at', '未知')}")
        print(f"是否广告: {msg_data.get('is_ad', False)}")
        
        # 内容分析
        original_content = msg_data.get('content', '')
        filtered_content = msg_data.get('filtered_content', '')
        original_len = len(original_content)
        filtered_len = len(filtered_content)
        removed_chars = original_len - filtered_len
        
        print(f"\n📊 内容统计:")
        print(f"原始长度: {original_len} 字符")
        print(f"过滤后长度: {filtered_len} 字符")
        print(f"移除字符: {removed_chars} 字符")
        
        if original_len > 0:
            filter_ratio = (removed_chars / original_len) * 100
            print(f"过滤率: {filter_ratio:.1f}%")
        
        # 媒体信息
        media_url = msg_data.get('media_url')
        media_hash = msg_data.get('media_hash')
        visual_hash = msg_data.get('visual_hash')
        
        if media_url or media_hash:
            print(f"\n🖼️ 媒体信息:")
            if media_url:
                print(f"媒体文件: {media_url}")
            if media_hash:
                print(f"媒体哈希: {media_hash}")
            if visual_hash:
                print(f"视觉哈希: {visual_hash}")
        
        # OCR信息
        if msg_data.get('ocr_processed'):
            ocr_text = msg_data.get('ocr_text', [])
            ocr_ad_score = msg_data.get('ocr_ad_score', 0)
            qr_codes = msg_data.get('qr_codes', [])
            
            print(f"\n🔍 OCR分析:")
            print(f"OCR处理: {'是' if msg_data.get('ocr_processed') else '否'}")
            print(f"文本区域: {len(ocr_text)} 个")
            print(f"广告分数: {ocr_ad_score}")
            
            if qr_codes:
                print(f"二维码: {len(qr_codes)} 个")
                for i, qr in enumerate(qr_codes, 1):
                    print(f"  {i}. {qr}")
            
            if ocr_text:
                print(f"\n检测到的文本:")
                for i, text in enumerate(ocr_text, 1):
                    print(f"  {i}. {text}")
        
        # 审核信息
        if msg_data.get('reviewed_by'):
            print(f"\n👤 审核信息:")
            print(f"审核人: {msg_data.get('reviewed_by')}")
            print(f"审核时间: {msg_data.get('review_time', '未知')}")
        
        # 转发信息
        review_msg_id = msg_data.get('review_message_id')
        target_msg_id = msg_data.get('target_message_id')
        forwarded_time = msg_data.get('forwarded_time')
        
        if review_msg_id or target_msg_id or forwarded_time:
            print(f"\n📤 转发信息:")
            if review_msg_id:
                print(f"审核消息ID: {review_msg_id}")
            if target_msg_id:
                print(f"目标消息ID: {target_msg_id}")
            if forwarded_time:
                print(f"转发时间: {forwarded_time}")
        
        # 组合消息信息
        if msg_data.get('is_combined'):
            grouped_id = msg_data.get('grouped_id')
            combined_messages = msg_data.get('combined_messages', [])
            print(f"\n📎 组合消息:")
            print(f"分组ID: {grouped_id}")
            print(f"组合消息数: {len(combined_messages)}")
        
        # 显示内容
        print(f"\n📝 原始内容:")
        print("-" * 60)
        if original_content:
            # 限制显示长度
            if len(original_content) > 500:
                print(original_content[:500] + "\n... (内容过长，已截断)")
            else:
                print(original_content)
        else:
            print("[无内容]")
        
        print(f"\n✂️ 过滤后内容:")
        print("-" * 60)
        if filtered_content:
            if len(filtered_content) > 500:
                print(filtered_content[:500] + "\n... (内容过长，已截断)")
            else:
                print(filtered_content)
        else:
            print("[无内容]")
        
        # 如果过滤掉了内容，显示可能被移除的部分
        if removed_chars > 0:
            print(f"\n🗑️ 可能被移除的内容分析:")
            print("-" * 60)
            
            # 简单的尾部检测
            if original_content and filtered_content:
                # 检查是否是尾部被移除
                if original_content.startswith(filtered_content):
                    removed_tail = original_content[len(filtered_content):]
                    print(f"移除的尾部内容:")
                    print(removed_tail[:200] + ("..." if len(removed_tail) > 200 else ""))
                else:
                    print("移除内容分布在各个位置，无法简单显示")
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主函数"""
    if len(sys.argv) > 1:
        message_id = sys.argv[1]
    else:
        message_id = input("请输入要验证的消息ID (格式: channel_id:message_id 或 message_id，默认7911): ").strip()
        if not message_id:
            message_id = "7911"  # 默认值，保持向后兼容
    
    await verify_message(message_id)

if __name__ == "__main__":
    asyncio.run(main())