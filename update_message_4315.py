#!/usr/bin/env python3
"""
更新消息的过滤内容（通用版本）
"""
import asyncio
import logging
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.storage.redis_store import init_redis_stores, get_redis_message_store
from app.services.content_filter import content_filter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def update_specific_message(message_id: str = "4315"):
    """更新特定消息的过滤内容"""
    
    try:
        # 初始化Redis存储
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        if not init_redis_stores(redis_url):
            logger.error("❌ Redis连接失败")
            return
        
        store = get_redis_message_store()
        
        # 解析消息ID
        if ':' in str(message_id):
            channel_id, msg_id = str(message_id).split(':', 1)
            msg_id = int(msg_id)
        else:
            # 搜索所有频道中的消息
            msg_id = int(message_id)
            channel_id = None
            
            # 尝试从所有消息中查找
            all_messages = store.get_all_messages(limit=1000)
            target_msg = None
            for msg in all_messages:
                if msg.get('message_id') == msg_id:
                    target_msg = msg
                    channel_id = msg.get('channel_id')
                    break
            
            if not target_msg:
                logger.error(f"❌ 未找到消息 #{msg_id}")
                return
        
        # 获取消息数据
        msg_data = store.get_message(channel_id, msg_id)
        
        if not msg_data:
            logger.error(f"❌ 未找到消息 {channel_id}:{msg_id}")
            return
        
        content = msg_data.get('content', '')
        if not content:
            logger.error(f"❌ 消息 {channel_id}:{msg_id} 内容为空")
            return
        
        logger.info(f"\n📨 找到消息 {channel_id}:{msg_id}")
        logger.info(f"  来源频道: {channel_id}")
        logger.info(f"  原始内容长度: {len(content)} 字符")
        
        current_filtered = msg_data.get('filtered_content', '')
        logger.info(f"  当前过滤内容长度: {len(current_filtered)} 字符")
        
        # 显示原始内容预览
        content_preview = content[:200].replace('\n', ' ')
        logger.info(f"  内容预览: {content_preview}...")
        
        # 应用内容过滤
        logger.info(f"\n🔧 正在应用内容过滤...")
        
        try:
            filtered_content = content_filter.filter_promotional_content(
                content, 
                channel_id=channel_id
            )
            
            logger.info(f"\n📊 过滤结果:")
            logger.info(f"  过滤后长度: {len(filtered_content)} 字符")
            logger.info(f"  删除字符数: {len(content) - len(filtered_content)}")
            
            if len(filtered_content) < len(content):
                # 显示被过滤的内容
                if content.startswith(filtered_content):
                    removed = content[len(filtered_content):]
                    logger.info(f"\n🗑️ 被过滤的尾部内容:")
                    logger.info("-" * 50)
                    logger.info(removed[:300] + ("..." if len(removed) > 300 else ""))
                    logger.info("-" * 50)
                else:
                    logger.info(f"\n🗑️ 过滤内容分布在各个位置")
                
                # 询问是否更新
                try:
                    response = input(f"\n是否更新消息 {channel_id}:{msg_id} 的过滤内容？(y/n): ")
                except EOFError:
                    # 非交互环境，默认更新
                    response = 'y'
                    logger.info("非交互环境，自动更新")
                
                if response.lower() == 'y':
                    # 更新消息数据
                    msg_data['filtered_content'] = filtered_content
                    success = store.save_message(channel_id, msg_id, msg_data)
                    
                    if success:
                        logger.info(f"\n✅ 成功更新消息 {channel_id}:{msg_id} 的过滤内容")
                    else:
                        logger.error(f"\n❌ 更新失败")
                else:
                    logger.info(f"\n⚠️ 未更新消息内容")
                    
            else:
                logger.info(f"\n⚠️ 没有检测到需要过滤的内容")
                
                # 检查是否需要强制重新过滤
                if current_filtered and len(current_filtered) != len(content):
                    logger.info(f"当前已有过滤内容，可能需要重新评估")
                    
                    try:
                        response = input("是否强制使用新的过滤结果？(y/n): ")
                    except EOFError:
                        response = 'n'
                        logger.info("非交互环境，保持现状")
                    
                    if response.lower() == 'y':
                        msg_data['filtered_content'] = filtered_content
                        success = store.save_message(channel_id, msg_id, msg_data)
                        
                        if success:
                            logger.info(f"\n✅ 已强制更新消息 {channel_id}:{msg_id}")
                        else:
                            logger.error(f"\n❌ 强制更新失败")
                            
        except Exception as e:
            logger.error(f"❌ 内容过滤失败: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        logger.error(f"❌ 更新消息失败: {e}")
        import traceback
        traceback.print_exc()

async def batch_update_messages(channel_id: str = None, status: str = None, limit: int = 10):
    """批量更新消息的过滤内容"""
    
    try:
        # 初始化Redis存储
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        if not init_redis_stores(redis_url):
            logger.error("❌ Redis连接失败")
            return
        
        store = get_redis_message_store()
        
        # 获取消息列表
        if status:
            messages = store.get_messages_by_status(status, limit)
            logger.info(f"📋 获取到 {len(messages)} 条 {status} 状态的消息")
        elif channel_id:
            messages = store.get_messages_by_channel(channel_id, limit)
            logger.info(f"📋 获取到频道 {channel_id} 的 {len(messages)} 条消息")
        else:
            messages = store.get_all_messages(limit)
            logger.info(f"📋 获取到 {len(messages)} 条消息")
        
        if not messages:
            logger.warning("⚠️ 未找到消息")
            return
        
        # 批量处理
        updated_count = 0
        for i, msg_data in enumerate(messages, 1):
            msg_channel_id = msg_data.get('channel_id')
            msg_id = msg_data.get('message_id')
            content = msg_data.get('content', '')
            current_filtered = msg_data.get('filtered_content', '')
            
            if not content:
                continue
            
            logger.info(f"\n🔄 处理消息 {i}/{len(messages)}: {msg_channel_id}:{msg_id}")
            
            try:
                # 重新过滤
                filtered_content = content_filter.filter_promotional_content(
                    content, 
                    channel_id=msg_channel_id
                )
                
                # 如果过滤结果不同，则更新
                if filtered_content != current_filtered:
                    msg_data['filtered_content'] = filtered_content
                    success = store.save_message(msg_channel_id, msg_id, msg_data)
                    
                    if success:
                        updated_count += 1
                        removed_chars = len(content) - len(filtered_content)
                        logger.info(f"  ✅ 已更新，删除 {removed_chars} 字符")
                    else:
                        logger.error(f"  ❌ 更新失败")
                else:
                    logger.info(f"  ⚠️ 过滤结果相同，跳过")
                    
            except Exception as e:
                logger.error(f"  ❌ 过滤失败: {e}")
        
        logger.info(f"\n🎯 批量更新完成，更新了 {updated_count} 条消息")
        
    except Exception as e:
        logger.error(f"❌ 批量更新失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='更新消息过滤内容')
    parser.add_argument('message_id', nargs='?', help='要更新的消息ID (格式: channel_id:message_id 或 message_id)')
    parser.add_argument('--batch', action='store_true', help='批量更新模式')
    parser.add_argument('--channel', help='指定频道ID（批量模式）')
    parser.add_argument('--status', choices=['pending', 'approved', 'rejected'], help='指定状态（批量模式）')
    parser.add_argument('--limit', type=int, default=10, help='限制数量（批量模式，默认10）')
    
    args = parser.parse_args()
    
    if args.batch:
        await batch_update_messages(args.channel, args.status, args.limit)
    elif args.message_id:
        await update_specific_message(args.message_id)
    else:
        # 默认更新消息4315（保持向后兼容）
        await update_specific_message("4315")

if __name__ == "__main__":
    asyncio.run(main())