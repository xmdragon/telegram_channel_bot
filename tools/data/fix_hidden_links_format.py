#!/usr/bin/env python3
"""
修复隐藏链接数据格式
将旧格式的 removed_elements 转换为前端期望的格式

Author: Claude
Created: 2025-08-19
"""
import json
import sys
import os
import logging
from typing import Dict, List, Any

# 添加项目根目录到路径
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_manager import redis_manager

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_hidden_links_format(message_data: Dict[str, Any]) -> bool:
    """修复消息的隐藏链接格式"""
    if not message_data.get('removed_hidden_links'):
        return False
    
    changed = False
    fixed_links = []
    
    for link in message_data['removed_hidden_links']:
        # 检查是否为旧格式
        if isinstance(link, dict) and link.get('type') == 'entity' and 'content' in link:
            # 旧格式：{'type': 'entity', 'content': {...}}
            content = link['content']
            
            # 提取链接文本和URL
            text = ""
            url = content.get('url', '') if isinstance(content, dict) else ""
            
            # 尝试从消息文本中提取链接文本
            if isinstance(content, dict) and message_data.get('content'):
                offset = content.get('offset', 0)
                length = content.get('length', 0)
                message_content = message_data['content']
                
                if offset + length <= len(message_content):
                    text = message_content[offset:offset + length]
            
            # 转换为新格式
            fixed_link = {
                'text': text or "隐藏链接",
                'url': url,
                'type': 'hidden_link'
            }
            fixed_links.append(fixed_link)
            changed = True
            
        elif isinstance(link, dict) and 'text' in link and 'url' in link:
            # 已经是新格式，保持不变
            fixed_links.append(link)
        else:
            # 未知格式，创建默认格式
            fixed_link = {
                'text': str(link) if link else "隐藏链接",
                'url': "",
                'type': 'hidden_link'
            }
            fixed_links.append(fixed_link)
            changed = True
    
    if changed:
        message_data['removed_hidden_links'] = fixed_links
        logger.info(f"修复了 {len(fixed_links)} 个隐藏链接的格式")
    
    return changed


async def main():
    """主修复程序"""
    try:
        # 直接获取Redis存储实例
        from app.storage.redis_store import RedisMessageStore
        redis_store = RedisMessageStore()
        
        # 获取所有消息
        all_messages = redis_manager.get_all_messages(limit=1000)
        logger.info(f"找到 {len(all_messages)} 条消息")
        
        fixed_count = 0
        total_links_fixed = 0
        
        for message in all_messages:
            if message.get('removed_hidden_links'):
                original_links_count = len(message['removed_hidden_links'])
                
                if fix_hidden_links_format(message):
                    # 更新消息到Redis
                    message_id = f"{message['source_channel']}:{message['message_id']}"
                    
                    # 更新消息数据
                    channel_id = message['source_channel']
                    msg_id = message['message_id']
                    success = await redis_manager.update_message(channel_id, msg_id, {
                        'removed_hidden_links': message['removed_hidden_links']
                    })
                    
                    if success:
                        fixed_count += 1
                        total_links_fixed += original_links_count
                        logger.info(f"✅ 修复消息 {message_id} 的 {original_links_count} 个隐藏链接")
                    else:
                        logger.error(f"❌ 修复消息 {message_id} 失败")
        
        logger.info(f"🎉 修复完成！共修复 {fixed_count} 条消息，总计 {total_links_fixed} 个隐藏链接")
        
    except Exception as e:
        logger.error(f"修复过程出错: {e}", exc_info=True)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())