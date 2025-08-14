#!/usr/bin/env python3
"""检查最近消息的工具脚本"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_store import init_redis_stores, get_redis_message_store

async def check_recent_messages(limit: int = 10, status_filter: str = None):
    """检查最近的消息"""
    try:
        # 初始化Redis存储
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        if not init_redis_stores(redis_url):
            print("❌ Redis连接失败")
            return
        
        store = get_redis_message_store()
        
        # 根据状态过滤获取消息
        if status_filter:
            messages = store.get_messages_by_status(status_filter, limit)
            print(f"\n📋 最近的 {status_filter} 状态消息 (共 {len(messages)} 条):")
        else:
            messages = store.get_all_messages(limit)
            print(f"\n📋 最近的所有消息 (共 {len(messages)} 条):")
        
        print("-" * 80)
        
        if not messages:
            print("⚠️ 未找到消息")
            return
        
        # 分析消息
        total_filtered_chars = 0
        total_original_chars = 0
        tail_detected_count = 0
        
        for i, msg in enumerate(messages, 1):
            # 基本信息
            msg_id = msg.get('message_id', 'N/A')
            channel_id = msg.get('channel_id', 'N/A')
            status = msg.get('status', 'unknown')
            created_at = msg.get('created_at', '')
            
            # 内容分析
            original_content = msg.get('content', '')
            filtered_content = msg.get('filtered_content', '')
            original_len = len(original_content)
            filtered_len = len(filtered_content)
            removed_chars = original_len - filtered_len
            
            total_original_chars += original_len
            total_filtered_chars += removed_chars
            
            # 时间格式化
            time_str = "未知时间"
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    time_str = dt.strftime('%m-%d %H:%M:%S')
                except:
                    time_str = created_at[:19] if created_at else "未知时间"
            
            print(f"{i}. ID: {channel_id}:{msg_id} | 状态: {status} | 时间: {time_str}")
            print(f"   原始长度: {original_len} | 过滤后: {filtered_len} | 减少: {removed_chars} 字符", end="")
            
            if original_len > 0:
                filter_ratio = (removed_chars / original_len) * 100
                print(f" ({filter_ratio:.1f}%)")
            else:
                print()
            
            # 显示内容前100个字符
            content_preview = (original_content[:100] + "...") if len(original_content) > 100 else original_content
            print(f"   内容: {content_preview}")
            
            # 检查尾部推广特征
            tail_keywords = ["@", "订阅", "投稿", "👌", "📣", "加入", "关注", "群组", "频道", "联系", "推广"]
            detected_keywords = [kw for kw in tail_keywords if kw in original_content]
            
            if detected_keywords:
                tail_detected_count += 1
                print(f"   ⚠️ 可能包含尾部推广: {', '.join(detected_keywords)}")
            
            # 检查媒体信息
            media_url = msg.get('media_url')
            media_hash = msg.get('media_hash')
            if media_url:
                print(f"   🖼️ 包含媒体: {media_url.split('/')[-1] if '/' in media_url else media_url}")
            
            # 检查OCR处理结果
            if msg.get('ocr_processed'):
                ocr_text = msg.get('ocr_text', [])
                ocr_ad_score = msg.get('ocr_ad_score', 0)
                if ocr_text:
                    print(f"   🔍 OCR检测: {len(ocr_text)} 个文本区域, 广告分数: {ocr_ad_score}")
            
            # 检查是否是广告
            if msg.get('is_ad'):
                print(f"   🚫 标记为广告")
            
            print()
        
        # 统计摘要
        print("=" * 80)
        print(f"📊 统计摘要:")
        print(f"   总消息数: {len(messages)}")
        print(f"   总原始字符: {total_original_chars}")
        print(f"   总过滤字符: {total_filtered_chars}")
        if total_original_chars > 0:
            filter_percentage = (total_filtered_chars / total_original_chars) * 100
            print(f"   平均过滤率: {filter_percentage:.1f}%")
        print(f"   疑似尾部推广: {tail_detected_count} 条 ({tail_detected_count/len(messages)*100:.1f}%)")
        
        # 状态分布
        status_count = {}
        for msg in messages:
            status = msg.get('status', 'unknown')
            status_count[status] = status_count.get(status, 0) + 1
        
        print(f"   状态分布: {dict(status_count)}")
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()

async def show_message_counts():
    """显示消息计数统计"""
    try:
        # 初始化Redis存储
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        if not init_redis_stores(redis_url):
            print("❌ Redis连接失败")
            return
        
        store = get_redis_message_store()
        
        print("\n📈 消息计数统计:")
        print("-" * 40)
        
        # 全局计数
        statuses = ['pending', 'approved', 'rejected', 'auto_forwarded']
        for status in statuses:
            count = store.get_message_count(status=status)
            print(f"{status:15}: {count:6} 条")
        
        # 获取所有频道的检查点
        from app.storage.redis_store import get_redis_channel_store
        channel_store = get_redis_channel_store()
        checkpoints = channel_store.get_all_checkpoints()
        
        if checkpoints:
            print("\n📍 频道采集点:")
            print("-" * 40)
            for channel_id, last_msg_id in checkpoints.items():
                channel_total = store.get_message_count(channel_id=channel_id)
                print(f"{channel_id:15}: 最新 #{last_msg_id}, 总共 {channel_total} 条")
        
    except Exception as e:
        print(f"❌ 统计失败: {e}")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='检查最近消息')
    parser.add_argument('--limit', '-l', type=int, default=10, help='显示消息数量 (默认: 10)')
    parser.add_argument('--status', '-s', choices=['pending', 'approved', 'rejected', 'auto_forwarded'], 
                       help='按状态过滤')
    parser.add_argument('--stats', action='store_true', help='显示统计信息')
    
    args = parser.parse_args()
    
    if args.stats:
        await show_message_counts()
    else:
        await check_recent_messages(args.limit, args.status)

if __name__ == "__main__":
    asyncio.run(main())