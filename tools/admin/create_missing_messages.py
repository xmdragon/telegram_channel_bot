#!/usr/bin/env python3
"""
创建缺失的组图消息记录
为57756, 57758, 57759创建消息记录
"""

import redis
import json
import os
import sys
from datetime import datetime

# 确保在正确的目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(script_dir, '..', '..')
sys.path.insert(0, project_root)

def create_missing_messages():
    """创建缺失的组图消息"""
    
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        
        # 获取57757作为模板
        template_key = 'msg:-1001956665373:57757'
        template_data = {}
        
        # 尝试获取模板数据
        if r.type(template_key).decode() == 'hash':
            hash_data = r.hgetall(template_key)
            for key, value in hash_data.items():
                try:
                    template_data[key.decode('utf-8')] = value.decode('utf-8')
                except:
                    template_data[key.decode('utf-8')] = str(value)
        
        print(f"📋 获取到模板消息数据，包含 {len(template_data)} 个字段")
        
        # 要创建的消息列表
        missing_messages = [
            {
                'msg_id': 57756,
                'media_file': 'temp_media/57756_20250817_011606_photo.jpg',
                'content': '[组图] 图片 1/4'
            },
            {
                'msg_id': 57758, 
                'media_file': 'temp_media/57758_20250817_011607_photo.jpg',
                'content': '[组图] 图片 2/4'
            },
            {
                'msg_id': 57759,
                'media_file': 'temp_media/57759_20250817_011607_photo.jpg', 
                'content': '[组图] 图片 3/4'
            }
        ]
        
        created_count = 0
        
        for msg_info in missing_messages:
            msg_key = f"msg:-1001956665373:{msg_info['msg_id']}"
            
            # 检查消息是否已存在
            if r.exists(msg_key):
                print(f"⚠️  消息 {msg_info['msg_id']} 已存在，跳过")
                continue
            
            # 检查媒体文件是否存在
            media_path = os.path.join(project_root, msg_info['media_file'])
            if not os.path.exists(media_path):
                print(f"❌ 媒体文件不存在: {msg_info['media_file']}")
                continue
            
            # 创建新消息数据
            new_msg_data = template_data.copy()
            new_msg_data.update({
                'id': f"-1001956665373:{msg_info['msg_id']}",
                'message_id': str(msg_info['msg_id']),
                'content': msg_info['content'],
                'filtered_content': msg_info['content'],
                'media_type': 'photo',
                'media_url': msg_info['media_file'],
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            })
            
            # 保存到Redis (使用Hash格式)
            try:
                r.hset(msg_key, mapping=new_msg_data)
                print(f"✅ 创建消息 {msg_info['msg_id']} - {msg_info['media_file']}")
                created_count += 1
            except Exception as e:
                print(f"❌ 创建消息 {msg_info['msg_id']} 失败: {e}")
        
        print(f"\n📊 创建完成: {created_count}/{len(missing_messages)} 条消息")
        
        return created_count > 0
        
    except Exception as e:
        print(f"❌ 操作失败: {e}")
        return False

if __name__ == "__main__":
    print("🔧 开始创建缺失的组图消息...")
    success = create_missing_messages()
    
    if success:
        print("\n✅ 创建完成！")
        print("💡 现在可以查看完整的组图:")
        print("   - 消息57756: 图片 1/4")
        print("   - 消息57757: 主消息 + 组图说明") 
        print("   - 消息57758: 图片 2/4")
        print("   - 消息57759: 图片 3/4")
    else:
        print("\n❌ 创建失败")
        sys.exit(1)