#!/usr/bin/env python3
"""
修复缺少媒体占位符的消息
"""
import asyncio
import sys
import os
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_manager import redis_manager
from app.storage.json_store import init_json_stores

async def fix_missing_media_placeholders():
    """为缺少媒体占位符的消息添加占位符"""
    try:
        print("🔍 修复缺少媒体占位符的消息...")
        
        # 初始化存储层
        redis_manager.is_healthy()
        init_json_stores()
        
        redis_store = redis_manager
        if not redis_store:
            print("❌ 无法获取Redis存储")
            return False
        
        # 获取所有消息键
        pattern = "message:*"
        keys = redis_manager.client.keys(pattern)
        
        fixed_count = 0
        checked_count = 0
        
        print(f"📊 找到 {len(keys)} 条消息记录")
        
        for key in keys:
            # 转换键为字符串
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            
            # 跳过非消息键（如计数器、索引等）
            if ':count:' in key_str or ':idx:' in key_str or ':hash:' in key_str:
                continue
                
            try:
                # 获取消息数据
                msg_data = redis_manager.client.hgetall(key)
                if not msg_data:
                    continue
                
                checked_count += 1
                
                # 转换字节数据为字符串
                message = {}
                for k, v in msg_data.items():
                    if isinstance(k, bytes):
                        k = k.decode('utf-8')
                    if isinstance(v, bytes):
                        v = v.decode('utf-8')
                    message[k] = v
                
                # 检查是否需要修复
                content = message.get('content', '')
                media_type = message.get('media_type')
                media_url = message.get('media_url')
                
                # 如果消息内容很长但没有媒体信息，可能是有媒体但下载失败的
                # 或者如果内容中提到了图片、视频等媒体相关词汇
                needs_fix = False
                suggested_media_type = None
                
                # 简单的启发式检测
                if not media_type and not media_url:
                    if any(keyword in content for keyword in ['📷', '📸', '🎥', '🎬', '📹', '图片', '视频', '照片']):
                        needs_fix = True
                        suggested_media_type = 'photo'
                    elif len(content) > 500 and not content.startswith('[广告内容已过滤]'):
                        # 长内容但没有媒体信息，可能是媒体下载失败
                        needs_fix = True
                        suggested_media_type = 'unknown'
                
                if needs_fix:
                    # 解析键获取channel_id和message_id
                    if key_str.startswith('msg:'):
                        parts = key_str.split(':')
                        if len(parts) >= 3:
                            channel_id = parts[1]
                            message_id = parts[2]
                            
                            # 更新媒体信息
                            updates = {
                                'media_type': suggested_media_type,
                                'media_url': f'placeholder:{suggested_media_type or "媒体"}下载失败'
                            }
                            
                            for field, value in updates.items():
                                redis_manager.client.hset(key, field, value)
                            
                            print(f"✅ 修复消息 {channel_id}:{message_id} - 添加占位符: {suggested_media_type}")
                            fixed_count += 1
                
                # 每处理100条消息显示进度
                if checked_count % 100 == 0:
                    print(f"📊 已检查 {checked_count} 条消息，修复 {fixed_count} 条")
                    
            except Exception as e:
                print(f"❌ 处理消息失败 {key}: {e}")
                continue
        
        print(f"\n🎉 修复完成！")
        print(f"📊 总共检查: {checked_count} 条消息")
        print(f"✅ 修复数量: {fixed_count} 条消息")
        
        return True
            
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(fix_missing_media_placeholders())
    print(f"\n{'🎉 修复成功' if result else '❌ 修复失败'}")
    sys.exit(0 if result else 1)