#!/usr/bin/env python3
"""
补抓最近的缺失媒体文件
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.core.database import get_db, Message
from app.services.media_handler import MediaHandler
from sqlalchemy import select, and_, or_
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def find_recent_missing_media(hours=24):
    """查找最近N小时内媒体文件缺失的消息"""
    missing_messages = []
    
    async for db in get_db():
        # 计算时间范围
        since = datetime.now() - timedelta(hours=hours)
        
        # 查询最近的有媒体URL的消息
        result = await db.execute(
            select(Message).where(
                and_(
                    Message.created_at >= since,
                    or_(
                        Message.media_url.isnot(None),
                        Message.media_group.isnot(None)
                    )
                )
            ).order_by(Message.id.desc())
        )
        messages = result.scalars().all()
        
        for msg in messages:
            has_missing = False
            
            # 检查主媒体文件
            if msg.media_url:
                if not os.path.exists(msg.media_url):
                    has_missing = True
            
            # 检查媒体组
            if msg.media_group:
                for item in msg.media_group:
                    file_path = item.get('file_path')
                    if file_path and not os.path.exists(file_path):
                        has_missing = True
                        break
            
            if has_missing:
                missing_messages.append(msg)
        
        break
    
    return missing_messages


async def refetch_media(message, media_handler):
    """重新下载消息的媒体文件"""
    try:
        logger.info(f"开始补抓消息 #{message.id} 的媒体")
        
        # 获取Telegram消息
        from app.telegram.bot import telegram_bot
        if not telegram_bot.client:
            logger.error("Telegram客户端未连接")
            return False
        
        # 获取源消息
        try:
            channel_entity = await telegram_bot.client.get_entity(int(message.source_channel))
            tg_message = await telegram_bot.client.get_messages(
                channel_entity,
                ids=message.message_id
            )
        except Exception as e:
            logger.error(f"获取Telegram消息失败: {e}")
            return False
        
        if not tg_message:
            logger.warning(f"未找到Telegram消息 {message.message_id}")
            return False
        
        # 重新下载媒体
        if tg_message.media:
            media_url = await media_handler.download_media(
                tg_message,
                message.source_channel,
                message.message_id
            )
            
            if media_url:
                # 更新数据库
                async for db in get_db():
                    message.media_url = media_url
                    await db.commit()
                    logger.info(f"成功补抓消息 #{message.id} 的媒体: {media_url}")
                    break
                return True
            else:
                logger.error(f"下载媒体失败: 消息 #{message.id}")
                return False
        else:
            logger.warning(f"消息 #{message.id} 在Telegram中没有媒体")
            return False
            
    except Exception as e:
        logger.error(f"补抓消息 #{message.id} 媒体失败: {e}")
        return False


async def main():
    """主函数"""
    print("=" * 60)
    print("补抓最近缺失的媒体文件")
    print("=" * 60)
    
    # 查找最近24小时缺失媒体的消息
    print("\n正在查找最近24小时内媒体缺失的消息...")
    missing_messages = await find_recent_missing_media(hours=24)
    
    if not missing_messages:
        print("✅ 没有发现最近24小时内媒体缺失的消息")
        return
    
    print(f"\n发现 {len(missing_messages)} 条最近消息的媒体文件缺失")
    
    # 显示详情
    print("\n缺失媒体的消息列表:")
    print("-" * 60)
    for msg in missing_messages:
        created_time = msg.created_at.strftime("%m-%d %H:%M")
        print(f"ID: {msg.id}, 时间: {created_time}, 状态: {msg.status}, 媒体: {msg.media_type}")
        if msg.media_url:
            print(f"  缺失文件: {msg.media_url}")
    
    print("\n" + "=" * 60)
    
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
    print(f"\n开始批量补抓 {len(missing_messages)} 条消息...")
    success_count = 0
    fail_count = 0
    
    for i, msg in enumerate(missing_messages, 1):
        print(f"\n[{i}/{len(missing_messages)}] 处理消息 #{msg.id} (状态: {msg.status})")
        
        success = await refetch_media(msg, media_handler)
        if success:
            success_count += 1
            print(f"  ✅ 成功")
        else:
            fail_count += 1
            print(f"  ❌ 失败")
        
        # 每处理5条消息暂停一下，避免请求过快
        if i % 5 == 0:
            await asyncio.sleep(1)
    
    # 显示结果
    print("\n" + "=" * 60)
    print("批量补抓完成")
    print(f"成功: {success_count} 条")
    print(f"失败: {fail_count} 条")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())