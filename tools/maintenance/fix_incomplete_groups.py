#!/usr/bin/env python3
"""
Linus式组合消息修复工具
修复因超时机制导致的不完整消息组

背景：
旧的超时机制导致某些消息组不完整，缺失了重要的文本内容消息。
例如消息组 14045497824915669 只包含了4条消息（2247-2250），
但实际上应该包含5条消息（2246-2250），其中2246包含所有文本内容。

使用方法:
    python3 fix_incomplete_groups.py --check                    # 检查模式
    python3 fix_incomplete_groups.py --fix 14045497824915669    # 修复指定组
    python3 fix_incomplete_groups.py --fix-all                  # 修复所有不完整组
"""

import sys
import os
import asyncio
import argparse
from typing import List, Dict, Optional, Set
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.storage.redis_manager import redis_manager
from app.services.message_grouper import message_grouper
from app.utils.timezone import format_for_api


class IncompleteGroupsFixer:
    """不完整消息组修复器"""
    
    def __init__(self):
        redis_manager.is_healthy()
        self.redis_store = redis_manager
        
        # 初始化JSON存储层
        from app.storage.json_store import init_json_stores
        init_json_stores()
        
    async def check_incomplete_groups(self) -> List[Dict]:
        """检查不完整的消息组"""
        print("🔍 扫描不完整的消息组...")
        
        incomplete_groups = []
        
        # 获取所有频道
        from app.storage.json_store import get_json_channel_store
        channel_store = get_json_channel_store()
        channels_list = channel_store.get_all_channels()
        
        # 转换为以channel_id为键的字典
        channels = {}
        for channel in channels_list:
            channel_id = channel.get('channel_id')
            if channel_id:
                channels[channel_id] = channel
        
        for channel_id, channel_info in channels.items():
            print(f"\n📡 检查频道: {channel_info.get('title', channel_id)}")
            
            # 获取该频道的所有消息
            messages = self.redis_manager.get_messages_by_channel(channel_id, limit=1000)
            
            # 按grouped_id分组
            grouped_messages = {}
            for msg in messages:
                grouped_id = msg.get('grouped_id')
                if grouped_id and msg.get('is_combined'):
                    if grouped_id not in grouped_messages:
                        grouped_messages[grouped_id] = []
                    grouped_messages[grouped_id].append(msg)
            
            # 检查每个组是否可能不完整
            for grouped_id, group_msgs in grouped_messages.items():
                if len(group_msgs) != 1:
                    continue  # 应该只有一个组合消息
                    
                combined_msg = group_msgs[0]
                combined_messages = combined_msg.get('combined_messages', [])
                
                # 检查组合消息的文本内容
                content = combined_msg.get('content', '').strip()
                text_length = len(content.replace('[📎 媒体组:', '').split(']')[0])  # 移除媒体占位符
                
                # 启发式检测：如果只有媒体占位符，没有实际文本内容，可能不完整
                has_real_content = text_length > 50  # 至少有50个字符的实际内容
                
                if not has_real_content and len(combined_messages) > 1:
                    # 可能的不完整组
                    incomplete_info = {
                        'channel_id': channel_id,
                        'channel_title': channel_info.get('title', channel_id),
                        'grouped_id': grouped_id,
                        'combined_message_id': combined_msg.get('message_id'),
                        'telegram_message_ids': [msg.get('message_id') for msg in combined_messages],
                        'message_count': len(combined_messages),
                        'content_length': text_length,
                        'has_media': bool(combined_msg.get('media_group')),
                        'created_at': combined_msg.get('created_at')
                    }
                    incomplete_groups.append(incomplete_info)
                    
                    print(f"  ⚠️  可能不完整的组: {grouped_id}")
                    print(f"      消息数量: {len(combined_messages)}")
                    print(f"      文本长度: {text_length}")
                    print(f"      消息ID: {incomplete_info['telegram_message_ids']}")
        
        return incomplete_groups
    
    async def fix_group(self, grouped_id: str, channel_id: str = None) -> bool:
        """修复特定的消息组"""
        print(f"\n🔧 修复消息组: {grouped_id}")
        
        # 如果没有指定频道，尝试找到它
        if not channel_id:
            channel_id = await self._find_channel_for_group(grouped_id)
            if not channel_id:
                print(f"❌ 无法找到消息组 {grouped_id} 所属的频道")
                return False
        
        try:
            # 获取现有的组合消息
            existing_msg = await self._get_existing_combined_message(channel_id, grouped_id)
            if not existing_msg:
                print(f"❌ 未找到现有的组合消息: {grouped_id}")
                return False
            
            # 从现有消息中获取一个样本消息ID
            combined_messages = existing_msg.get('combined_messages', [])
            if not combined_messages:
                print(f"❌ 组合消息没有子消息列表")
                return False
            
            sample_message_id = combined_messages[0].get('message_id')
            if not sample_message_id:
                print(f"❌ 无法获取样本消息ID")
                return False
            
            print(f"📡 使用Linus式方法重新获取完整消息组...")
            
            # 使用Linus式方法获取完整的消息组
            await message_grouper._init_telegram_client()
            complete_group = await message_grouper._fetch_complete_group(
                channel_id, grouped_id, sample_message_id
            )
            
            if not complete_group:
                print(f"❌ 无法从Telegram获取完整消息组")
                return False
            
            print(f"✅ 获取到完整消息组: {len(complete_group)} 条消息")
            
            # 比较新旧消息数量
            old_count = len(combined_messages)
            new_count = len(complete_group)
            
            if new_count <= old_count:
                print(f"ℹ️  消息数量无变化或减少 ({old_count} -> {new_count})，可能已经是完整的")
                return True
            
            print(f"🔄 消息数量增加: {old_count} -> {new_count}")
            
            # 重新创建组合消息
            combined_message = await message_grouper._create_combined_message(complete_group, channel_id)
            processed_data = await message_grouper._save_combined_message(combined_message, channel_id)
            
            if not processed_data:
                print(f"❌ 处理新组合消息失败")
                return False
            
            # 删除旧的组合消息
            old_redis_id = existing_msg.get('id')
            if old_redis_id:
                success = self.redis_manager.delete_message(channel_id, old_redis_id)
                if success:
                    print(f"🗑️  删除旧的不完整消息: {old_redis_id}")
                else:
                    print(f"⚠️  删除旧消息失败: {old_redis_id}")
            
            # 保存新的完整组合消息
            await message_grouper._save_to_redis(processed_data, combined_message, channel_id)
            
            print(f"✅ 修复完成！新消息包含 {new_count} 条子消息")
            
            # 显示修复结果
            new_content = processed_data.get('content', '')
            content_length = len(new_content.replace('[📎 媒体组:', '').split(']')[0])
            print(f"📝 新文本内容长度: {content_length} 字符")
            
            return True
            
        except Exception as e:
            print(f"❌ 修复失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await message_grouper.disconnect_telegram_client()
    
    async def _find_channel_for_group(self, grouped_id: str) -> Optional[str]:
        """查找消息组所属的频道"""
        from app.storage.json_store import get_json_channel_store
        channel_store = get_json_channel_store()
        channels_list = channel_store.get_all_channels()
        
        for channel in channels_list:
            channel_id = channel.get('channel_id')
            if not channel_id:
                continue
            messages = self.redis_manager.get_messages_by_channel(channel_id, limit=100)
            for msg in messages:
                if msg.get('grouped_id') == grouped_id:
                    return channel_id
        return None
    
    async def _get_existing_combined_message(self, channel_id: str, grouped_id: str) -> Optional[Dict]:
        """获取现有的组合消息"""
        messages = self.redis_manager.get_messages_by_channel(channel_id, limit=200)
        for message in messages:
            if (message.get('grouped_id') == grouped_id and 
                message.get('is_combined') == True):
                return message
        return None
    
    async def fix_all_incomplete_groups(self) -> int:
        """修复所有不完整的消息组"""
        print("🚀 开始修复所有不完整的消息组...")
        
        incomplete_groups = await self.check_incomplete_groups()
        
        if not incomplete_groups:
            print("✅ 没有发现不完整的消息组")
            return 0
        
        print(f"\n📋 发现 {len(incomplete_groups)} 个可能不完整的消息组")
        
        fixed_count = 0
        for group_info in incomplete_groups:
            grouped_id = group_info['grouped_id']
            channel_id = group_info['channel_id']
            
            print(f"\n{'='*50}")
            print(f"修复组: {grouped_id}")
            print(f"频道: {group_info['channel_title']}")
            
            try:
                success = await self.fix_group(grouped_id, channel_id)
                if success:
                    fixed_count += 1
                    print(f"✅ 修复成功")
                else:
                    print(f"❌ 修复失败")
            except Exception as e:
                print(f"❌ 修复异常: {e}")
            
            # 短暂暂停，避免过快请求
            await asyncio.sleep(1)
        
        print(f"\n🎉 修复完成！成功修复 {fixed_count}/{len(incomplete_groups)} 个消息组")
        return fixed_count


async def main():
    parser = argparse.ArgumentParser(description='修复不完整的消息组')
    parser.add_argument('--check', action='store_true', help='检查不完整的消息组')
    parser.add_argument('--fix', type=str, help='修复指定的消息组ID')
    parser.add_argument('--fix-all', action='store_true', help='修复所有不完整的消息组')
    parser.add_argument('--channel-id', type=str, help='指定频道ID（与--fix一起使用）')
    
    args = parser.parse_args()
    
    if not any([args.check, args.fix, args.fix_all]):
        parser.print_help()
        return
    
    fixer = IncompleteGroupsFixer()
    
    try:
        if args.check:
            # 检查模式
            incomplete_groups = await fixer.check_incomplete_groups()
            
            print(f"\n📊 检查结果:")
            print(f"发现 {len(incomplete_groups)} 个可能不完整的消息组")
            
            if incomplete_groups:
                print("\n详细列表:")
                for i, group in enumerate(incomplete_groups, 1):
                    print(f"\n{i}. 组ID: {group['grouped_id']}")
                    print(f"   频道: {group['channel_title']}")
                    print(f"   消息数: {group['message_count']}")
                    print(f"   文本长度: {group['content_length']}")
                    print(f"   消息ID: {group['telegram_message_ids']}")
                    
                print(f"\n💡 使用 --fix <grouped_id> 修复特定组")
                print(f"💡 使用 --fix-all 修复所有不完整组")
        
        elif args.fix:
            # 修复指定组
            success = await fixer.fix_group(args.fix, args.channel_id)
            if success:
                print(f"\n🎉 修复成功！")
            else:
                print(f"\n💔 修复失败")
        
        elif args.fix_all:
            # 修复所有组
            fixed_count = await fixer.fix_all_incomplete_groups()
            print(f"\n🏁 总计修复了 {fixed_count} 个消息组")
            
    except KeyboardInterrupt:
        print("\n\n⏸️  用户中断操作")
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())