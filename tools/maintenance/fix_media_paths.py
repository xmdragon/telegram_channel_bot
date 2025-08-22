#!/usr/bin/env python3
"""
一次性修复媒体路径工具
修复所有组合消息中缺失的媒体文件路径

使用方法:
    python3 fix_media_paths.py --check        # 检查需要修复的消息
    python3 fix_media_paths.py --fix-all      # 修复所有缺失的媒体路径
    python3 fix_media_paths.py --fix 2246     # 修复指定消息ID
"""

import sys
import os
import asyncio
import argparse
from typing import List, Dict, Optional
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.storage.redis_store import get_redis_message_store, init_redis_stores
from app.storage.json_store import init_json_stores, get_json_channel_store
from app.core.path_config import PathConfig


class MediaPathFixer:
    """媒体路径修复器"""
    
    def __init__(self):
        init_redis_stores()
        init_json_stores()
        self.redis_store = get_redis_message_store()
        self.temp_media_dir = PathConfig.TEMP_MEDIA_DIR
        
    async def check_missing_media_paths(self) -> List[Dict]:
        """检查所有缺失媒体路径的消息"""
        print("🔍 扫描缺失媒体路径的消息...")
        
        missing_media_messages = []
        
        # 获取所有频道
        channel_store = get_json_channel_store()
        channels_list = channel_store.get_all_channels()
        
        for channel in channels_list:
            channel_id = channel.get('channel_id')
            if not channel_id:
                continue
            
            channel_title = channel.get('title', channel_id)
            print(f"\n📡 检查频道: {channel_title}")
            
            # 获取该频道的组合消息
            messages = self.redis_store.get_messages_by_channel(channel_id, limit=500)
            
            for msg in messages:
                if not msg.get('is_combined') or not msg.get('media_group'):
                    continue
                
                media_group = msg.get('media_group', [])
                missing_count = 0
                total_media = len(media_group)
                
                for media_item in media_group:
                    if not media_item.get('file_path'):
                        missing_count += 1
                
                if missing_count > 0:
                    # 找到缺失媒体路径的消息
                    message_info = {
                        'channel_id': channel_id,
                        'channel_title': channel_title,
                        'message_id': msg.get('message_id'),
                        'redis_id': msg.get('id'),
                        'grouped_id': msg.get('grouped_id'),
                        'total_media': total_media,
                        'missing_count': missing_count,
                        'content_length': len(msg.get('content', '')),
                        'created_at': msg.get('created_at'),
                        'combined_messages': msg.get('combined_messages', [])
                    }
                    missing_media_messages.append(message_info)
                    
                    print(f"  ⚠️  消息 #{msg.get('message_id')}: {missing_count}/{total_media} 媒体路径缺失")
        
        return missing_media_messages
    
    async def fix_message_media_paths(self, message_info: Dict) -> bool:
        """修复单个消息的媒体路径"""
        try:
            channel_id = message_info['channel_id']
            message_id = message_info['message_id']
            redis_id = message_info['redis_id']
            
            print(f"\n🔧 修复消息 #{message_id} 的媒体路径...")
            
            # 获取当前消息数据 - 处理redis_id为None的情况
            if redis_id is not None:
                current_msg = self.redis_store.get_message(channel_id, redis_id, silent=True)
            else:
                # 如果redis_id为None，通过message_id查找
                messages = self.redis_store.get_messages_by_channel(channel_id, limit=500)
                current_msg = None
                for msg in messages:
                    if msg.get('message_id') == message_id and msg.get('is_combined'):
                        current_msg = msg
                        break
            
            if not current_msg:
                print(f"❌ 未找到消息: {channel_id}#{message_id}")
                return False
            
            media_group = current_msg.get('media_group', [])
            if not media_group:
                print(f"❌ 消息没有媒体组")
                return False
            
            # 修复每个媒体项的路径
            fixed_count = 0
            for i, media_item in enumerate(media_group):
                if media_item.get('file_path'):
                    continue  # 已有路径，跳过
                
                media_message_id = media_item.get('message_id')
                if not media_message_id:
                    continue
                
                # 查找对应的本地文件
                local_file = await self._find_local_media_file(media_message_id)
                if local_file:
                    media_item['file_path'] = local_file
                    fixed_count += 1
                    print(f"  ✅ 媒体 {i+1}: {os.path.basename(local_file)}")
                else:
                    print(f"  ❌ 媒体 {i+1}: 未找到本地文件 (ID: {media_message_id})")
            
            if fixed_count > 0:
                # 更新Redis中的消息
                updated_msg = current_msg.copy()
                updated_msg['media_group'] = media_group
                
                # 保存更新后的消息 - 使用message_id而不是redis_id
                success = await self._update_redis_message(channel_id, message_id, updated_msg)
                if success:
                    print(f"✅ 成功修复 {fixed_count}/{len(media_group)} 个媒体路径")
                    return True
                else:
                    print(f"❌ 保存更新失败")
                    return False
            else:
                print(f"⚠️ 没有找到可修复的媒体文件")
                return False
                
        except Exception as e:
            print(f"❌ 修复失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _find_local_media_file(self, message_id: int) -> Optional[str]:
        """查找本地媒体文件"""
        try:
            # 搜索以message_id开头的文件
            pattern = f"{message_id}_*"
            matching_files = list(self.temp_media_dir.glob(pattern))
            
            if matching_files:
                # 返回第一个匹配的文件路径
                return str(matching_files[0])
            
            return None
            
        except Exception as e:
            print(f"查找本地媒体文件失败 (ID: {message_id}): {e}")
            return None
    
    async def _update_redis_message(self, channel_id: str, message_id: int, updated_msg: Dict) -> bool:
        """更新Redis中的消息"""
        try:
            # 使用Redis存储的保存方法 - 按message_id保存
            success = self.redis_store.save_message(channel_id, message_id, updated_msg)
            return success
        except Exception as e:
            print(f"更新Redis消息失败: {e}")
            return False
    
    async def fix_all_missing_media_paths(self) -> int:
        """修复所有缺失的媒体路径"""
        print("🚀 开始修复所有缺失的媒体路径...")
        
        missing_messages = await self.check_missing_media_paths()
        
        if not missing_messages:
            print("✅ 没有发现缺失媒体路径的消息")
            return 0
        
        print(f"\n📋 发现 {len(missing_messages)} 个需要修复的消息")
        
        fixed_count = 0
        for i, message_info in enumerate(missing_messages, 1):
            print(f"\n{'='*50} ({i}/{len(missing_messages)})")
            print(f"消息: #{message_info['message_id']}")
            print(f"频道: {message_info['channel_title']}")
            print(f"缺失: {message_info['missing_count']}/{message_info['total_media']} 媒体")
            
            try:
                success = await self.fix_message_media_paths(message_info)
                if success:
                    fixed_count += 1
                else:
                    print(f"❌ 修复失败")
            except Exception as e:
                print(f"❌ 修复异常: {e}")
            
            # 短暂暂停，避免过快操作
            await asyncio.sleep(0.5)
        
        print(f"\n🎉 修复完成！成功修复 {fixed_count}/{len(missing_messages)} 个消息")
        return fixed_count
    
    async def fix_specific_message(self, message_id: int, channel_id: str = None) -> bool:
        """修复指定消息的媒体路径"""
        print(f"🔧 修复指定消息: #{message_id}")
        
        # 如果没有指定频道，查找消息所在的频道
        if not channel_id:
            channel_id = await self._find_channel_for_message(message_id)
            if not channel_id:
                print(f"❌ 无法找到消息 #{message_id} 所属的频道")
                return False
        
        # 查找Redis中的消息
        messages = self.redis_store.get_messages_by_channel(channel_id, limit=500)
        target_message = None
        
        for msg in messages:
            if msg.get('message_id') == message_id and msg.get('is_combined'):
                target_message = msg
                break
        
        if not target_message:
            print(f"❌ 未找到组合消息: {channel_id}#{message_id}")
            return False
        
        # 构建消息信息
        message_info = {
            'channel_id': channel_id,
            'channel_title': channel_id,
            'message_id': target_message.get('message_id'),
            'redis_id': target_message.get('id'),
            'grouped_id': target_message.get('grouped_id'),
            'total_media': len(target_message.get('media_group', [])),
            'missing_count': sum(1 for m in target_message.get('media_group', []) if not m.get('file_path'))
        }
        
        return await self.fix_message_media_paths(message_info)
    
    async def _find_channel_for_message(self, message_id: int) -> Optional[str]:
        """查找消息所属的频道"""
        channel_store = get_json_channel_store()
        channels_list = channel_store.get_all_channels()
        
        for channel in channels_list:
            channel_id = channel.get('channel_id')
            if not channel_id:
                continue
            
            messages = self.redis_store.get_messages_by_channel(channel_id, limit=500)
            for msg in messages:
                if msg.get('message_id') == message_id:
                    return channel_id
        
        return None


async def main():
    parser = argparse.ArgumentParser(description='修复缺失的媒体文件路径')
    parser.add_argument('--check', action='store_true', help='检查缺失媒体路径的消息')
    parser.add_argument('--fix-all', action='store_true', help='修复所有缺失的媒体路径')
    parser.add_argument('--fix', type=int, help='修复指定消息ID的媒体路径')
    parser.add_argument('--channel-id', type=str, help='指定频道ID（与--fix一起使用）')
    
    args = parser.parse_args()
    
    if not any([args.check, args.fix_all, args.fix]):
        parser.print_help()
        return
    
    fixer = MediaPathFixer()
    
    try:
        if args.check:
            # 检查模式
            missing_messages = await fixer.check_missing_media_paths()
            
            print(f"\n📊 检查结果:")
            print(f"发现 {len(missing_messages)} 个缺失媒体路径的消息")
            
            if missing_messages:
                print("\n详细列表:")
                for i, msg_info in enumerate(missing_messages, 1):
                    print(f"\n{i}. 消息 #{msg_info['message_id']}")
                    print(f"   频道: {msg_info['channel_title']}")
                    print(f"   缺失: {msg_info['missing_count']}/{msg_info['total_media']} 媒体")
                    print(f"   内容长度: {msg_info['content_length']} 字符")
                    
                print(f"\n💡 使用 --fix <message_id> 修复指定消息")
                print(f"💡 使用 --fix-all 修复所有缺失路径")
        
        elif args.fix:
            # 修复指定消息
            success = await fixer.fix_specific_message(args.fix, args.channel_id)
            if success:
                print(f"\n🎉 修复成功！")
            else:
                print(f"\n💔 修复失败")
        
        elif args.fix_all:
            # 修复所有消息
            fixed_count = await fixer.fix_all_missing_media_paths()
            print(f"\n🏁 总计修复了 {fixed_count} 个消息的媒体路径")
            
    except KeyboardInterrupt:
        print("\n\n⏸️  用户中断操作")
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())