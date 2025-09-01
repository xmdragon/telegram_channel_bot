#!/usr/bin/env python3
"""
批量补抓缺失媒体文件
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_manager import redis_manager
from app.services.media_handler import MediaHandler

# 直接使用Redis URL，避免复杂的配置依赖
REDIS_URL = "redis://localhost:6379"
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def find_missing_media():
    """查找所有媒体文件缺失的消息"""
    missing_messages = []
    
    # 初始化Redis存储
    init_redis_stores(REDIS_URL)
    redis_store = redis_manager
    
    # 获取所有有媒体的消息
    all_messages = redis_manager.get_all_messages(limit=5000)
    
    for msg in all_messages:
        has_missing = False
        
        # 检查主媒体文件
        media_url = msg.get('media_url')
        if media_url:
            if not os.path.exists(media_url):
                has_missing = True
        
        # 检查媒体组
        media_group = msg.get('media_group')
        if media_group:
            for item in media_group:
                file_path = item.get('file_path')
                if file_path and not os.path.exists(file_path):
                    has_missing = True
                    break
        
        if has_missing:
            missing_messages.append(msg)
    
    return missing_messages


async def refetch_media(message, media_handler):
    """重新下载消息的媒体文件"""
    try:
        channel_id = message['channel_id']
        message_id = message['message_id']
        
        logger.info(f"开始补抓消息 {channel_id}:{message_id} 的媒体")
        
        # 获取Telegram消息
        from app.telegram.bot import telegram_bot
        if not telegram_bot.client:
            logger.error("Telegram客户端未连接")
            return False
        
        # 获取源消息
        channel_entity = await telegram_bot.client.get_entity(int(channel_id))
        tg_message = await telegram_bot.client.get_messages(
            channel_entity,
            ids=int(message_id)
        )
        
        if not tg_message:
            logger.warning(f"未找到Telegram消息 {message_id}")
            return False
        
        # 重新下载媒体
        if tg_message.media:
            media_url = await media_handler.download_media(
                tg_message,
                channel_id,
                message_id
            )
            
            if media_url:
                # 更新Redis存储
                init_redis_stores(settings.redis_url)
                redis_store = redis_manager
                
                # 获取完整消息数据并更新
                full_msg = redis_manager.get_message(str(channel_id), int(message_id))
                if full_msg:
                    full_msg['media_url'] = media_url
                    redis_manager.save_message(str(channel_id), int(message_id), full_msg)
                    logger.info(f"成功补抓消息 {channel_id}:{message_id} 的媒体: {media_url}")
                return True
            else:
                logger.error(f"下载媒体失败: 消息 {channel_id}:{message_id}")
                return False
        else:
            logger.warning(f"消息 {channel_id}:{message_id} 在Telegram中没有媒体")
            return False
            
    except Exception as e:
        logger.error(f"补抓消息 {message.get('channel_id')}:{message.get('message_id')} 媒体失败: {e}")
        return False


async def main():
    """主函数"""
    print("=" * 60)
    print("批量补抓缺失媒体文件")
    print("=" * 60)
    
    # 查找缺失媒体的消息
    print("\n正在查找媒体缺失的消息...")
    missing_messages = await find_missing_media()
    
    if not missing_messages:
        print("✅ 没有发现媒体缺失的消息")
        return
    
    print(f"\n发现 {len(missing_messages)} 条消息的媒体文件缺失")
    
    # 显示详情
    print("\n缺失媒体的消息列表:")
    print("-" * 60)
    for msg in missing_messages[:10]:  # 只显示前10条
        channel_id = msg.get('channel_id')
        message_id = msg.get('message_id')
        media_type = msg.get('media_type')
        print(f"ID: {channel_id}:{message_id}, 媒体类型: {media_type}")
        media_url = msg.get('media_url')
        if media_url:
            print(f"  缺失文件: {media_url}")
    
    if len(missing_messages) > 10:
        print(f"  ... 还有 {len(missing_messages) - 10} 条消息")
    
    # 询问是否继续
    print("\n" + "=" * 60)
    response = input(f"是否开始批量补抓这 {len(missing_messages)} 条消息的媒体？(y/n): ")
    if response.lower() != 'y':
        print("已取消")
        return
    
    # 初始化媒体处理器
    media_handler = MediaHandler()
    
    # 确保Telegram客户端已连接
    from app.telegram.bot import telegram_bot
    if not telegram_bot.client:
        print("\n正在连接Telegram...")
        await telegram_bot.initialize()
        if not telegram_bot.client:
            print("❌ 无法连接到Telegram，请先完成认证")
            return
    
    # 批量补抓
    print("\n开始批量补抓...")
    success_count = 0
    fail_count = 0
    
    for i, msg in enumerate(missing_messages, 1):
        channel_id = msg.get('channel_id')
        message_id = msg.get('message_id')
        print(f"\n[{i}/{len(missing_messages)}] 处理消息 {channel_id}:{message_id}")
        
        success = await refetch_media(msg, media_handler)
        if success:
            success_count += 1
            print(f"  ✅ 成功")
        else:
            fail_count += 1
            print(f"  ❌ 失败")
        
        # 每处理10条消息暂停一下，避免请求过快
        if i % 10 == 0:
            await asyncio.sleep(2)
    
    # 显示结果
    print("\n" + "=" * 60)
    print("批量补抓完成")
    print(f"成功: {success_count} 条")
    print(f"失败: {fail_count} 条")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())