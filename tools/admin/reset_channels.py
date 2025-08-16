#!/usr/bin/env python3
"""
重置频道采集状态和进度
清空所有频道的时间戳，使其从最新消息开始采集
"""

import json
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.config_manager import ConfigManager

def reset_channels():
    """重置所有频道状态"""
    print("🔄 开始重置频道状态...")
    
    config_manager = ConfigManager()
    channels = config_manager.get_channels()
    
    print(f"📋 找到 {len(channels)} 个频道")
    
    reset_count = 0
    for channel_key, channel_data in channels.items():
        if isinstance(channel_data, dict):
            # 重置updated_at为空，这样会从最新消息开始采集
            if 'updated_at' in channel_data:
                del channel_data['updated_at']
                reset_count += 1
                print(f"  ✅ 重置频道: {channel_data.get('channel_name', channel_key)}")
    
    # 保存配置
    config_manager.save_channels(channels)
    
    print(f"✅ 成功重置 {reset_count} 个频道的采集状态")
    print("🚀 频道将从最新消息开始采集")

if __name__ == "__main__":
    reset_channels()