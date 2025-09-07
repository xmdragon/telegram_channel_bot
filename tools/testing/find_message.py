#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.storage.redis_manager import redis_manager

# 目标消息
channel_id = "-1002137718790"
message_id = "16490"

print(f"查找消息: {channel_id}:{message_id}")
print("=" * 60)

# 1. 尝试从Redis获取
message = redis_manager.get_message(channel_id, message_id, silent=True)
if message:
    print("✅ 找到消息:")
    print(f"  状态: {message.get('status')}")
    print(f"  内容: {message.get('content', '')[:200]}...")
    if message.get('reject_reason'):
        print(f"  ❌ 拒绝原因: {message.get('reject_reason')}")
    if message.get('filter_reason'):
        print(f"  ⚠️ 过滤原因: {message.get('filter_reason')}")
    print(f"  是否为广告: {message.get('is_ad')}")
    print("\n完整数据:")
    print(json.dumps(message, indent=2, ensure_ascii=False))
else:
    print("❌ 消息不存在")
    
    # 查看该频道最近的消息
    print(f"\n查看频道 {channel_id} 的最近消息:")
    messages = redis_manager.get_messages_by_channel(channel_id, limit=10)
    if messages:
        for msg in messages:
            print(f"  #{msg.get('message_id')} - 状态:{msg.get('status')} - {msg.get('content', '')[:50]}...")
    else:
        print("  该频道没有消息")