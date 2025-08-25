#!/usr/bin/env python3
"""
查找引用已删除消息的duplicate_original_id
"""
import redis
import json

def find_duplicate_references():
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    target_id = "-1002557968812:2294"
    referencing_messages = []
    
    # 扫描所有消息
    for key in r.scan_iter("msg:*"):
        try:
            # 获取duplicate_original_id字段
            dup_id = r.hget(key, "duplicate_original_id")
            if dup_id and target_id in dup_id:
                # 获取消息基本信息
                msg_data = r.hgetall(key)
                message_id = msg_data.get("message_id", "unknown")
                channel_id = msg_data.get("source_channel", "unknown")
                content_preview = msg_data.get("content", "")[:50]
                
                print(f"\n找到引用消息: {key}")
                print(f"  消息ID: {message_id}")
                print(f"  频道: {channel_id}")
                print(f"  duplicate_original_id: {dup_id}")
                print(f"  内容预览: {content_preview}...")
                
                referencing_messages.append({
                    "key": key,
                    "message_id": message_id,
                    "duplicate_original_id": dup_id
                })
        except Exception as e:
            print(f"处理 {key} 时出错: {e}")
    
    print(f"\n总计找到 {len(referencing_messages)} 个消息引用了 {target_id}")
    
    # 检查目标消息是否存在
    target_key = f"msg:{target_id}"
    if r.exists(target_key):
        print(f"\n目标消息 {target_id} 存在")
    else:
        print(f"\n目标消息 {target_id} 不存在（已被删除）")
    
    return referencing_messages

if __name__ == "__main__":
    find_duplicate_references()