#!/usr/bin/env python3
"""
清理channels.json文件中的重复数据并添加缺失的字段
"""
import json
import os
from datetime import datetime

def cleanup_channels():
    channels_file = "/Users/eric/workspace/telegram_channel_bot/data/config/channels.json"
    
    # 读取原始数据
    with open(channels_file, 'r', encoding='utf-8') as f:
        original_data = json.load(f)
    
    print(f"原始数据包含 {len(original_data)} 个键")
    
    # 提取channel_前缀的数据
    cleaned_data = {}
    channel_keys = [k for k in original_data.keys() if k.startswith('channel_')]
    at_keys = [k for k in original_data.keys() if k.startswith('@')]
    
    print(f"找到 {len(channel_keys)} 个channel_前缀的键")
    print(f"找到 {len(at_keys)} 个@前缀的键")
    
    for key in channel_keys:
        channel = original_data[key].copy()
        
        # 添加channel_title字段
        if 'channel_title' not in channel:
            # 从channel_name提取，去掉@符号
            channel_name = channel.get('channel_name', '')
            if channel_name.startswith('@'):
                channel_name = channel_name[1:]
            # 使用频道名作为默认标题
            channel['channel_title'] = channel_name or '未设置标题'
        
        # 确保有description字段
        if 'description' not in channel:
            channel['description'] = ''
        
        # 更新时间戳
        current_time = datetime.now().isoformat()
        if 'updated_at' not in channel:
            channel['updated_at'] = current_time
        
        cleaned_data[key] = channel
    
    print(f"清理后数据包含 {len(cleaned_data)} 个频道")
    
    # 备份原文件
    backup_file = channels_file + '.cleanup_backup'
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(original_data, f, indent=2, ensure_ascii=False)
    print(f"原始数据已备份到: {backup_file}")
    
    # 保存清理后的数据
    with open(channels_file, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
    
    print(f"清理完成！")
    print(f"- 删除了 {len(at_keys)} 个重复的@前缀频道")
    print(f"- 保留了 {len(cleaned_data)} 个正常频道")
    print(f"- 为所有频道添加了channel_title字段")

if __name__ == "__main__":
    cleanup_channels()