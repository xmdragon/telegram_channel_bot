#!/usr/bin/env python3
"""
修复消息57757的组图问题
添加媒体信息和组图占位符
"""

import requests
import json
import sys
import os

# 确保在正确的目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(script_dir, '..', '..')
sys.path.insert(0, project_root)

def fix_message_57757():
    """修复消息57757的媒体信息"""
    
    # API基础URL
    base_url = "http://localhost:8000"
    
    # 获取当前消息信息
    print("🔍 获取消息57757当前状态...")
    response = requests.get(f"{base_url}/api/messages/-1001956665373:57757")
    
    if response.status_code != 200:
        print(f"❌ 获取消息失败: {response.status_code}")
        return False
    
    data = response.json()
    if not data.get('success'):
        print(f"❌ 获取消息失败: {data}")
        return False
    
    message = data['message']
    print(f"📄 当前消息信息:")
    print(f"   媒体类型: {message.get('media_type')}")
    print(f"   媒体URL: {message.get('media_url')}")
    print(f"   内容长度: {len(message.get('content', ''))}")
    
    # 检查是否已经有组图标记
    current_content = message.get('content', '')
    if '[组图包含:' in current_content:
        print("✅ 消息已经包含组图标记，无需修复")
        return True
    
    # 检查媒体文件是否存在
    media_files = [
        'temp_media/57756_20250817_011606_photo.jpg',
        'temp_media/57757_20250817_011606_photo.jpg', 
        'temp_media/57758_20250817_011607_photo.jpg',
        'temp_media/57759_20250817_011607_photo.jpg'
    ]
    
    existing_files = []
    for file in media_files:
        if os.path.exists(os.path.join(project_root, file)):
            existing_files.append(file)
    
    print(f"📁 找到 {len(existing_files)} 个媒体文件")
    
    if not existing_files:
        print("❌ 没有找到任何媒体文件")
        return False
    
    # 使用内部修复方式
    try:
        print("🔧 使用内部API修复...")
        
        # 直接操作Redis
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        
        # 尝试不同的键格式
        possible_keys = [
            'msg:-1001956665373:57757',
            'message:-1001956665373:57757',
            '-1001956665373:57757'
        ]
        
        fixed = False
        for key in possible_keys:
            try:
                # 尝试hash操作
                if r.exists(key):
                    data_type = r.type(key).decode()
                    print(f"🔍 找到键 {key}，类型: {data_type}")
                    
                    if data_type == 'hash':
                        # Hash类型
                        r.hset(key, 'media_type', 'grouped_media')
                        r.hset(key, 'media_url', 'temp_media/57757_20250817_011606_photo.jpg')
                        
                        # 获取当前内容
                        current_content = r.hget(key, 'content')
                        if current_content:
                            current_content = current_content.decode('utf-8')
                            new_content = current_content + '\n\n[组图包含: 4个图片 - 57756, 57757, 57758, 57759]'
                            r.hset(key, 'content', new_content)
                            r.hset(key, 'filtered_content', new_content)
                        
                        print(f"✅ 使用Hash方式修复消息 {key}")
                        fixed = True
                        break
                        
                    elif data_type == 'string':
                        # String类型
                        msg_str = r.get(key)
                        if msg_str:
                            msg_data = json.loads(msg_str.decode('utf-8'))
                            msg_data['media_type'] = 'grouped_media'
                            msg_data['media_url'] = 'temp_media/57757_20250817_011606_photo.jpg'
                            
                            original_content = msg_data.get('content', '')
                            new_content = original_content + '\n\n[组图包含: 4个图片 - 57756, 57757, 57758, 57759]'
                            msg_data['content'] = new_content
                            msg_data['filtered_content'] = new_content
                            
                            r.set(key, json.dumps(msg_data, ensure_ascii=False))
                            print(f"✅ 使用String方式修复消息 {key}")
                            fixed = True
                            break
                            
            except Exception as e:
                print(f"❌ 处理键 {key} 失败: {e}")
                continue
        
        if not fixed:
            print("❌ 无法找到或修复Redis中的消息数据")
            return False
            
        print("✅ 消息57757修复完成")
        return True
        
    except ImportError:
        print("❌ Redis模块不可用")
        return False
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        return False

if __name__ == "__main__":
    print("🔧 开始修复消息57757...")
    success = fix_message_57757()
    
    if success:
        print("\n✅ 修复完成！")
        print("💡 可以通过以下方式验证：")
        print("   1. 访问 http://localhost:8000/static/login.html")
        print("   2. 登录后查看消息57757")
        print("   3. 应该能看到组图标记和媒体文件")
    else:
        print("\n❌ 修复失败")
        sys.exit(1)