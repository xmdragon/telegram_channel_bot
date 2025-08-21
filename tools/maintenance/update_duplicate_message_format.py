#!/usr/bin/env python3
"""
更新重复消息格式 - 将旧的纯文本格式转换为新的HTML格式
"""

import re
import json
import redis
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent.parent))

def update_duplicate_message_format():
    """更新重复消息的filtered_content格式"""
    
    # 连接Redis
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
        print("✅ Redis连接成功")
    except Exception as e:
        print(f"❌ Redis连接失败: {e}")
        return False
    
    # 先查看所有键
    all_keys = r.keys("*")
    print(f"📊 Redis中共有 {len(all_keys)} 个键")
    
    # 查找消息相关的键
    message_keys = [key for key in all_keys if 'message' in key.lower()]
    print(f"📊 找到 {len(message_keys)} 个消息相关的键")
    if message_keys:
        print("🔍 消息键示例:", message_keys[:5])
    
    updated_count = 0
    
    for key in message_keys:
        try:
            message_data = r.get(key)
            if not message_data:
                continue
                
            message = json.loads(message_data)
            filtered_content = message.get('filtered_content', '')
            
            # 检查是否是旧格式的重复消息标记
            old_pattern = r'\[重复内容，原消息ID: (\d+)\]'
            match = re.search(old_pattern, filtered_content)
            
            if match:
                original_id = match.group(1)
                # 转换为新格式
                new_content = f'[重复内容，原消息ID: <span class="duplicate-message-link" data-message-id="{original_id}">{original_id}</span>]'
                
                message['filtered_content'] = new_content
                
                # 更新到Redis
                r.set(key, json.dumps(message))
                updated_count += 1
                
                print(f"✅ 更新消息 {key}: {original_id}")
                
        except Exception as e:
            print(f"❌ 处理 {key} 时出错: {e}")
            continue
    
    print(f"🎉 共更新了 {updated_count} 个重复消息")
    return True

if __name__ == "__main__":
    print("🔄 开始更新重复消息格式...")
    success = update_duplicate_message_format()
    if success:
        print("✅ 更新完成！请刷新页面查看效果")
    else:
        print("❌ 更新失败")