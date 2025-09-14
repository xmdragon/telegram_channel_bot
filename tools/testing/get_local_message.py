#!/usr/bin/env python3
"""
本地消息查询工具
从Redis中获取消息的完整信息，包括组合消息的所有细节

使用方法:
    python3 get_local_message.py -1002557968812:2251
    python3 get_local_message.py -1002557968812:2251 --raw  # 显示原始JSON
    python3 get_local_message.py -1002557968812:2251 --media  # 显示媒体文件详情
"""

import sys
import os
import json
import argparse
from typing import Optional, Dict, Any
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.storage.redis_manager import redis_manager
from app.utils.timezone import format_for_api


class LocalMessageViewer:
    """本地消息查看器"""
    
    def __init__(self):
        self.redis_store = redis_manager
        
    def parse_message_id(self, message_id: str) -> tuple:
        """解析消息ID
        
        支持格式:
        - channel_id:message_id (如 -1002557968812:2251 或 1521754979:261368)
        - channel_id:message_id:xxx (兼容旧格式)
        """
        parts = message_id.split(':')
        if len(parts) >= 2:
            channel_id = parts[0]
            # 统一转换为完整的channel_id格式
            if not channel_id.startswith('-100'):
                # 如果没有-100前缀，添加它
                channel_id = f"-100{channel_id}"
            return channel_id, int(parts[1])
        else:
            raise ValueError(f"无效的消息ID格式: {message_id}")
    
    def get_message(self, channel_id: str, message_id: int) -> Optional[Dict[str, Any]]:
        """获取消息"""
        return self.redis_store.get_message(channel_id, message_id, silent=True)
    
    def display_message(self, msg: Dict[str, Any], show_raw: bool = False, show_media: bool = False):
        """显示消息信息"""
        if show_raw:
            # 原始JSON输出
            print(json.dumps(msg, ensure_ascii=False, indent=2, default=str))
            return
            
        print("\n" + "=" * 70)
        print(f"📨 消息详情")
        print("=" * 70)
        
        # 基本信息
        print(f"\n📍 基本信息:")
        print(f"  消息ID: {msg.get('source_channel')}:{msg.get('message_id')}")
        print(f"  内部ID: {msg.get('id')}")
        print(f"  状态: {msg.get('status', 'unknown')}")
        created_at = msg.get('created_at')
        if isinstance(created_at, str):
            print(f"  创建时间: {created_at}")
        else:
            print(f"  创建时间: {format_for_api(created_at)}")
            
        updated_at = msg.get('updated_at')
        if updated_at:
            if isinstance(updated_at, str):
                print(f"  更新时间: {updated_at}")
            else:
                print(f"  更新时间: {format_for_api(updated_at)}")
        
        # 标记信息
        print(f"\n🏷️ 标记:")
        # 正确处理 is_ad 字段（可能是布尔值或字符串）
        is_ad_value = msg.get('is_ad')
        if isinstance(is_ad_value, str):
            is_ad_display = '是' if is_ad_value.lower() == 'true' else '否'
        else:
            is_ad_display = '是' if is_ad_value else '否'
        print(f"  是否广告: {is_ad_display} (原值: {is_ad_value})")
        print(f"  是否组合: {'是' if msg.get('is_combined') else '否'}")
        if msg.get('grouped_id'):
            print(f"  组ID: {msg.get('grouped_id')}")
        if msg.get('filter_reason'):
            print(f"  过滤原因: {msg.get('filter_reason')}")
        
        # 文本内容
        print(f"\n📝 文本内容:")
        original_content = msg.get('content', '')
        filtered_content = msg.get('filtered_content', '')
        
        if original_content:
            print(f"  原始内容 ({len(original_content)} 字符):")
            # 显示前500字符
            display_text = original_content[:500] + "..." if len(original_content) > 500 else original_content
            for line in display_text.split('\n'):
                print(f"    {line}")
        else:
            print("  原始内容: (无)")
            
        if filtered_content and filtered_content != original_content:
            print(f"\n  过滤后内容 ({len(filtered_content)} 字符):")
            display_text = filtered_content[:500] + "..." if len(filtered_content) > 500 else filtered_content
            for line in display_text.split('\n'):
                print(f"    {line}")
                
            # 计算差异
            diff = len(original_content) - len(filtered_content)
            if diff > 0:
                print(f"\n  ✂️ 过滤掉了 {diff} 字符 ({diff/len(original_content)*100:.1f}%)")
        
        # 媒体信息
        if msg.get('media_type') or msg.get('media_url'):
            print(f"\n🖼️ 媒体信息:")
            print(f"  类型: {msg.get('media_type', 'unknown')}")
            if msg.get('media_url'):
                print(f"  路径: {msg.get('media_url')}")
            if msg.get('media_hash'):
                print(f"  哈希: {msg.get('media_hash')[:16]}...")
        
        # 组合消息详情
        if msg.get('is_combined'):
            print(f"\n📦 组合消息信息:")
            
            # 统计组合的消息
            combined_messages = msg.get('combined_messages', [])
            if combined_messages:
                print(f"  包含 {len(combined_messages)} 条原始消息:")
                for i, cm in enumerate(combined_messages, 1):
                    print(f"    {i}. 消息 #{cm.get('message_id')}")
                    if cm.get('content'):
                        preview = cm['content'][:50] + "..." if len(cm['content']) > 50 else cm['content']
                        print(f"       文本: {preview}")
                    if cm.get('media_info'):
                        print(f"       媒体: {cm['media_info'].get('media_type', 'unknown')}")
            
            # 媒体组信息
            media_group = msg.get('media_group', [])
            if media_group:
                print(f"\n  媒体组 ({len(media_group)} 个文件):")
                
                # 统计媒体类型
                media_stats = {}
                available_count = 0
                failed_count = 0
                
                for media in media_group:
                    media_type = media.get('media_type', 'unknown')
                    media_stats[media_type] = media_stats.get(media_type, 0) + 1
                    
                    if media.get('download_failed'):
                        failed_count += 1
                    elif media.get('file_path'):
                        available_count += 1
                
                # 显示统计
                for media_type, count in media_stats.items():
                    type_name = {
                        'photo': '图片',
                        'video': '视频',
                        'document': '文件',
                        'animation': '动图',
                        'audio': '音频'
                    }.get(media_type, media_type)
                    print(f"    {type_name}: {count} 个")
                
                print(f"    可用: {available_count}/{len(media_group)}")
                if failed_count > 0:
                    print(f"    ⚠️ 下载失败: {failed_count} 个")
                
                # 详细媒体列表
                if show_media:
                    print(f"\n  媒体文件列表:")
                    for i, media in enumerate(media_group, 1):
                        status = "✅" if media.get('file_path') else "❌"
                        print(f"    {i}. {status} 消息#{media.get('message_id')} - {media.get('media_type')}")
                        if media.get('file_path'):
                            print(f"       文件: {media['file_path']}")
                        if media.get('error'):
                            print(f"       错误: {media['error']}")
            
            # 显示media_group_display（前端显示用）
            media_display = msg.get('media_group_display', [])
            if media_display and show_media:
                print(f"\n  前端媒体显示 ({len(media_display)} 个):")
                for i, media in enumerate(media_display, 1):
                    print(f"    {i}. {media.get('media_type')} - {media.get('display_url', 'No URL')}")
        
        # 重复消息信息
        details = msg.get('details')
        if details and details.get('is_duplicate'):
            print(f"\n🔁 重复消息信息:")
            details = msg['details']
            print(f"  原始消息ID: {details.get('original_message_id')}")
            print(f"  重复类型: {details.get('duplicate_type')}")
            if details.get('similarity_score'):
                print(f"  相似度: {details['similarity_score']:.2%}")
        
        # 处理记录
        if msg.get('processed_at'):
            print(f"\n⚙️ 处理记录:")
            processed_at = msg.get('processed_at')
            if isinstance(processed_at, str):
                print(f"  处理时间: {processed_at}")
            else:
                print(f"  处理时间: {format_for_api(processed_at)}")
                
            if msg.get('forward_task_id'):
                print(f"  转发任务: {msg.get('forward_task_id')}")
                
            published_at = msg.get('published_at')
            if published_at:
                if isinstance(published_at, str):
                    print(f"  发布时间: {published_at}")
                else:
                    print(f"  发布时间: {format_for_api(published_at)}")
                
        print("\n" + "=" * 70)
    
    def check_related_messages(self, channel_id: str, message_id: int, msg: Dict[str, Any]):
        """检查相关消息"""
        print(f"\n🔍 相关消息检查:")
        print("-" * 40)
        
        # 如果是组合消息，检查各个组成部分
        if msg.get('is_combined') and msg.get('combined_messages'):
            print(f"组合消息的各个部分:")
            for cm in msg['combined_messages']:
                sub_msg_id = cm.get('message_id')
                if sub_msg_id:
                    sub_msg = self.redis_store.get_message(channel_id, int(sub_msg_id), silent=True)
                    if sub_msg:
                        print(f"  ✅ 消息 #{sub_msg_id} 存在 (已合并)")
                    else:
                        print(f"  ❌ 消息 #{sub_msg_id} 不存在 (可能已删除)")
        
        # 如果有grouped_id，查找同组的其他消息
        if msg.get('grouped_id'):
            print(f"\n同组消息 (grouped_id={msg['grouped_id']}):")
            # 这需要遍历Redis，暂时简化处理
            print("  (需要完整扫描才能找到同组消息)")
        
        # 检查前后消息
        print(f"\n邻近消息:")
        for offset in [-2, -1, 1, 2]:
            nearby_id = message_id + offset
            nearby_msg = self.redis_store.get_message(channel_id, nearby_id, silent=True)
            if nearby_msg:
                marker = "📦" if nearby_msg.get('is_combined') else "📄"
                status = nearby_msg.get('status', 'unknown')
                print(f"  {marker} #{nearby_id} - {status}")


def main():
    parser = argparse.ArgumentParser(description='查询本地Redis中的消息')
    parser.add_argument('message_id', help='消息ID (格式: channel_id:message_id)')
    parser.add_argument('--raw', action='store_true', help='显示原始JSON数据')
    parser.add_argument('--media', action='store_true', help='显示详细媒体信息')
    parser.add_argument('--related', action='store_true', help='检查相关消息')
    
    args = parser.parse_args()
    
    # 初始化Redis连接
    redis_manager.is_healthy()
    
    viewer = LocalMessageViewer()
    
    try:
        # 解析消息ID
        channel_id, message_id = viewer.parse_message_id(args.message_id)
        print(f"🔍 查询消息: {channel_id}:{message_id}")
        
        # 获取消息
        msg = viewer.get_message(channel_id, message_id)
        
        if not msg:
            print(f"❌ 消息不存在: {channel_id}:{message_id}")
            print("\n提示：")
            print("1. 检查消息ID格式是否正确")
            print("2. 确认Redis服务正在运行")
            print("3. 消息可能已被删除或未采集")
            return
        
        # 显示消息
        viewer.display_message(msg, show_raw=args.raw, show_media=args.media)
        
        # 检查相关消息
        if args.related and not args.raw:
            viewer.check_related_messages(channel_id, message_id, msg)
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()