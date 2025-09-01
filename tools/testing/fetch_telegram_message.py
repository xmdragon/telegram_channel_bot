#!/usr/bin/env python3
"""
Telegram消息抓取工具
用于从Telegram链接直接抓取原始消息，包括组合消息
用于对比系统中的消息与原始消息是否一致

使用方法:
    python3 fetch_telegram_message.py https://t.me/cn_zhm0/2247
    python3 fetch_telegram_message.py https://t.me/cn_zhm0/2247 --compare  # 与系统中的消息对比
"""

import sys
import os
import re
import json
import asyncio
import argparse
from typing import Optional, Dict, List, Any
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument
from app.storage.redis_store import get_redis_message_store
from app.utils.timezone import format_for_api
from app.storage.json_store import JSONStore


class TelegramMessageFetcher:
    """Telegram消息抓取器"""
    
    def __init__(self):
        self.client = None
        
        # 从JSON配置文件读取Telegram设置
        config_file = os.path.join(os.path.dirname(__file__), '../../data/config/system.json')
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        self.api_id = int(config_data.get('telegram.api_id', {}).get('value', '0'))
        self.api_hash = config_data.get('telegram.api_hash', {}).get('value', '')
        self.session_string = config_data.get('telegram.session', {}).get('value', '')
        
    async def connect(self):
        """连接到Telegram"""
        try:
            print("🔌 连接到Telegram...")
            self.client = TelegramClient(
                StringSession(self.session_string),
                self.api_id,
                self.api_hash
            )
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                print("❌ Telegram会话未授权")
                return False
                
            print("✅ 成功连接到Telegram")
            return True
            
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False
    
    def parse_telegram_link(self, link: str) -> tuple:
        """解析Telegram链接
        
        Returns:
            (channel_username, message_id)
        """
        # 支持多种格式
        patterns = [
            r'https?://t\.me/([^/]+)/(\d+)',  # https://t.me/channel/123
            r'https?://telegram\.me/([^/]+)/(\d+)',  # https://telegram.me/channel/123
            r'@([^/]+)/(\d+)',  # @channel/123
            r'([^/]+)/(\d+)'  # channel/123
        ]
        
        for pattern in patterns:
            match = re.match(pattern, link)
            if match:
                return match.group(1), int(match.group(2))
        
        raise ValueError(f"无法解析Telegram链接: {link}")
    
    async def fetch_message(self, channel: str, message_id: int) -> Optional[Dict]:
        """抓取单条消息"""
        try:
            # 获取消息
            message = await self.client.get_messages(channel, ids=message_id)
            
            if not message:
                print(f"❌ 消息不存在: {channel}/{message_id}")
                return None
            
            return await self._extract_message_data(message)
            
        except Exception as e:
            print(f"❌ 抓取消息失败: {e}")
            return None
    
    async def fetch_message_group(self, channel: str, message_id: int) -> List[Dict]:
        """抓取组合消息
        
        如果消息属于媒体组，抓取整个组的所有消息
        """
        try:
            # 获取主消息
            main_message = await self.client.get_messages(channel, ids=message_id)
            
            if not main_message:
                print(f"❌ 消息不存在: {channel}/{message_id}")
                return []
            
            messages = []
            
            # 检查是否有grouped_id
            if hasattr(main_message, 'grouped_id') and main_message.grouped_id:
                print(f"🔍 检测到媒体组: grouped_id={main_message.grouped_id}")
                
                # 获取附近的消息来找到完整的组
                # Telegram媒体组通常在相近的ID范围内
                start_id = max(1, message_id - 20)
                end_id = message_id + 20
                
                nearby_messages = await self.client.get_messages(
                    channel,
                    min_id=start_id,
                    max_id=end_id,
                    limit=100
                )
                
                # 过滤出同一组的消息
                group_messages = []
                for msg in nearby_messages:
                    if hasattr(msg, 'grouped_id') and msg.grouped_id == main_message.grouped_id:
                        group_messages.append(msg)
                
                # 按ID排序
                group_messages.sort(key=lambda x: x.id)
                
                print(f"📦 找到 {len(group_messages)} 条组合消息")
                
                # 提取每条消息的数据
                for msg in group_messages:
                    msg_data = await self._extract_message_data(msg)
                    if msg_data:
                        messages.append(msg_data)
                        
            else:
                # 单条消息
                msg_data = await self._extract_message_data(main_message)
                if msg_data:
                    messages.append(msg_data)
                    
            return messages
            
        except Exception as e:
            print(f"❌ 抓取消息组失败: {e}")
            return []
    
    async def _extract_message_data(self, message: Message) -> Dict:
        """提取消息数据"""
        try:
            data = {
                'id': message.id,
                'date': message.date.isoformat() if message.date else None,
                'text': message.text or message.message or '',
                'caption': message.raw_text if hasattr(message, 'raw_text') else '',
                'grouped_id': str(message.grouped_id) if hasattr(message, 'grouped_id') and message.grouped_id else None,
                'media_type': None,
                'media_info': None,
                'has_media': bool(message.media),
                'forwards': message.forwards if hasattr(message, 'forwards') else 0,
                'views': message.views if hasattr(message, 'views') else 0,
            }
            
            # 提取媒体信息
            if message.media:
                if isinstance(message.media, MessageMediaPhoto):
                    data['media_type'] = 'photo'
                    data['media_info'] = {
                        'type': 'photo',
                        'has_spoiler': getattr(message.media, 'spoiler', False)
                    }
                elif isinstance(message.media, MessageMediaDocument):
                    data['media_type'] = 'document'
                    doc = message.media.document
                    if doc:
                        mime_type = doc.mime_type if hasattr(doc, 'mime_type') else ''
                        if 'video' in mime_type:
                            data['media_type'] = 'video'
                        elif 'audio' in mime_type:
                            data['media_type'] = 'audio'
                        elif 'image' in mime_type:
                            data['media_type'] = 'photo'
                            
                        data['media_info'] = {
                            'type': data['media_type'],
                            'mime_type': mime_type,
                            'size': doc.size if hasattr(doc, 'size') else 0
                        }
            
            return data
            
        except Exception as e:
            print(f"⚠️ 提取消息数据失败: {e}")
            return None
    
    async def compare_with_system(self, channel_username: str, message_id: int, fetched_messages: List[Dict]):
        """与系统中的消息对比"""
        try:
            redis_store = redis_manager
            
            # 尝试查找系统中的消息
            # 需要先获取频道ID
            from app.storage.json_store import JSONStore
            json_store = JSONStore()
            channels = json_store.get_channels()
            
            channel_id = None
            for ch_id, ch_info in channels.items():
                if ch_info.get('username') == f"@{channel_username}" or \
                   ch_info.get('username') == channel_username:
                    channel_id = ch_id
                    break
            
            if not channel_id:
                print(f"⚠️ 系统中未找到频道: {channel_username}")
                return
            
            print(f"\n📊 对比分析")
            print("=" * 60)
            
            if len(fetched_messages) == 1:
                # 单条消息
                msg = fetched_messages[0]
                system_msg = redis_manager.get_message(channel_id, message_id, silent=True)
                
                if system_msg:
                    self._compare_single_message(msg, system_msg)
                else:
                    print(f"❌ 系统中未找到消息: {channel_id}:{message_id}")
                    
            else:
                # 组合消息
                print(f"原始消息组: {len(fetched_messages)} 条")
                
                # 查找系统中对应的组合消息
                main_msg_id = fetched_messages[0]['id']
                system_msg = redis_manager.get_message(channel_id, main_msg_id, silent=True)
                
                if system_msg:
                    if system_msg.get('is_combined'):
                        combined_msgs = system_msg.get('combined_messages', [])
                        print(f"系统组合消息: {len(combined_msgs)} 条")
                        
                        # 对比内容
                        self._compare_group_messages(fetched_messages, system_msg)
                    else:
                        print(f"⚠️ 系统中的消息不是组合消息")
                else:
                    print(f"❌ 系统中未找到消息: {channel_id}:{main_msg_id}")
                    
        except Exception as e:
            print(f"❌ 对比失败: {e}")
    
    def _compare_single_message(self, original: Dict, system: Dict):
        """对比单条消息"""
        print("\n📝 文本内容对比:")
        print("-" * 40)
        
        orig_text = original.get('text', '') or original.get('caption', '')
        sys_text = system.get('content', '')
        sys_filtered = system.get('filtered_content', '')
        
        print(f"原始文本长度: {len(orig_text)} 字符")
        print(f"系统原始文本: {len(sys_text)} 字符")
        print(f"系统过滤文本: {len(sys_filtered)} 字符")
        
        if orig_text != sys_text:
            print("⚠️ 文本内容不一致!")
            if len(orig_text) > len(sys_text):
                print(f"   系统丢失了 {len(orig_text) - len(sys_text)} 字符")
            
        print("\n🖼️ 媒体对比:")
        print("-" * 40)
        print(f"原始媒体类型: {original.get('media_type', 'None')}")
        print(f"系统媒体类型: {system.get('media_type', 'None')}")
        
        if original.get('has_media') and not system.get('media_type'):
            print("⚠️ 系统丢失了媒体文件!")
    
    def _compare_group_messages(self, original_group: List[Dict], system_msg: Dict):
        """对比组合消息"""
        print("\n📝 组合消息对比:")
        print("-" * 40)
        
        # 收集所有原始文本
        orig_texts = []
        orig_media_count = 0
        
        for msg in original_group:
            text = msg.get('text', '') or msg.get('caption', '')
            if text:
                orig_texts.append(text)
            if msg.get('has_media'):
                orig_media_count += 1
        
        # 系统文本
        sys_text = system_msg.get('content', '')
        sys_filtered = system_msg.get('filtered_content', '')
        sys_media_group = system_msg.get('media_group', [])
        
        print(f"原始消息数: {len(original_group)}")
        print(f"原始文本段: {len(orig_texts)}")
        print(f"原始媒体数: {orig_media_count}")
        print()
        print(f"系统组合文本长度: {len(sys_text)} 字符")
        print(f"系统媒体数: {len(sys_media_group)}")
        
        # 检查是否有消息丢失
        combined_msgs = system_msg.get('combined_messages', [])
        orig_ids = {msg['id'] for msg in original_group}
        sys_ids = {int(msg['message_id']) for msg in combined_msgs}
        
        missing_ids = orig_ids - sys_ids
        if missing_ids:
            print(f"\n⚠️ 系统丢失了消息: {missing_ids}")
            for msg_id in missing_ids:
                for msg in original_group:
                    if msg['id'] == msg_id:
                        print(f"   消息 #{msg_id}: {msg.get('text', '')[:50]}...")
        
        # 显示原始文本内容
        if orig_texts:
            print("\n原始文本内容:")
            for i, text in enumerate(orig_texts, 1):
                print(f"  {i}. {text[:100]}..." if len(text) > 100 else f"  {i}. {text}")
    
    async def disconnect(self):
        """断开连接"""
        if self.client:
            await self.client.disconnect()
            print("👋 已断开Telegram连接")


async def main():
    parser = argparse.ArgumentParser(description='抓取Telegram消息')
    parser.add_argument('link', help='Telegram消息链接')
    parser.add_argument('--compare', action='store_true', help='与系统中的消息对比')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    
    args = parser.parse_args()
    
    # 导入StringSession
    from telethon.sessions import StringSession
    
    fetcher = TelegramMessageFetcher()
    
    try:
        # 连接
        if not await fetcher.connect():
            return
        
        # 解析链接
        channel, message_id = fetcher.parse_telegram_link(args.link)
        print(f"📍 目标: {channel} / 消息 #{message_id}")
        
        # 抓取消息
        messages = await fetcher.fetch_message_group(channel, message_id)
        
        if not messages:
            print("❌ 未能抓取到消息")
            return
        
        # 输出结果
        if args.json:
            print(json.dumps(messages, ensure_ascii=False, indent=2))
        else:
            print(f"\n✅ 成功抓取 {len(messages)} 条消息")
            print("=" * 60)
            
            for i, msg in enumerate(messages, 1):
                print(f"\n消息 {i}/{len(messages)} - ID: {msg['id']}")
                print("-" * 40)
                
                if msg.get('grouped_id'):
                    print(f"组ID: {msg['grouped_id']}")
                
                text = msg.get('text') or msg.get('caption') or ''
                if text:
                    print(f"文本: {text[:200]}..." if len(text) > 200 else f"文本: {text}")
                else:
                    print("文本: (无)")
                
                if msg.get('media_type'):
                    print(f"媒体: {msg['media_type']}")
                    
                print(f"时间: {msg.get('date', 'Unknown')}")
        
        # 对比分析
        if args.compare:
            await fetcher.compare_with_system(channel, message_id, messages)
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await fetcher.disconnect()


if __name__ == "__main__":
    asyncio.run(main())