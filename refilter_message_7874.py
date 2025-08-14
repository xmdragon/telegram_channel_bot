#!/usr/bin/env python3
"""
重新过滤消息#7874
"""
import asyncio
import logging
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def refilter_message():
    """重新过滤指定消息"""
    try:
        from app.core.database import AsyncSessionLocal, Message
        from sqlalchemy import select
        from app.services.content_filter import ContentFilter
        
        # 创建内容过滤器
        content_filter = ContentFilter()
        
        async with AsyncSessionLocal() as db:
            # 查询消息
            result = await db.execute(
                select(Message).where(Message.id == 7874)
            )
            msg = result.scalar_one_or_none()
            
            if not msg:
                logger.error("未找到消息 #7874")
                return
            
            logger.info(f"找到消息 #7874")
            logger.info(f"源频道: {msg.source_channel}")
            logger.info(f"创建时间: {msg.created_at}")
            
            # 显示原始内容
            print("\n" + "="*60)
            print("原始内容:")
            print("-"*60)
            print(msg.content if msg.content else "[无内容]")
            
            # 显示当前过滤后内容
            print("\n" + "="*60)
            print("当前过滤后内容:")
            print("-"*60)
            print(msg.filtered_content if msg.filtered_content else "[无内容]")
            
            # 重新过滤
            logger.info("\n正在重新过滤...")
            
            # 准备媒体文件列表（如果有）
            media_files = []
            if msg.media_url and Path(msg.media_url).exists():
                media_files.append(msg.media_url)
            
            # 执行过滤
            is_ad, filtered_content, filter_reason, ocr_result = await content_filter.filter_message(
                msg.content,
                channel_id=msg.source_channel,
                media_files=media_files
            )
            
            # 显示新的过滤结果
            print("\n" + "="*60)
            print("重新过滤后的内容:")
            print("-"*60)
            print(filtered_content if filtered_content else "[无内容]")
            
            # 比较结果
            print("\n" + "="*60)
            print("过滤结果对比:")
            print(f"原始长度: {len(msg.content) if msg.content else 0} 字符")
            print(f"之前过滤后: {len(msg.filtered_content) if msg.filtered_content else 0} 字符")
            print(f"重新过滤后: {len(filtered_content) if filtered_content else 0} 字符")
            
            if msg.content:
                old_removed = len(msg.content) - (len(msg.filtered_content) if msg.filtered_content else 0)
                new_removed = len(msg.content) - (len(filtered_content) if filtered_content else 0)
                print(f"之前过滤掉: {old_removed} 字符 ({old_removed/len(msg.content)*100:.1f}%)")
                print(f"现在过滤掉: {new_removed} 字符 ({new_removed/len(msg.content)*100:.1f}%)")
            
            print(f"\n广告检测: {is_ad}")
            if filter_reason:
                print(f"过滤原因: {filter_reason}")
            
            # 询问是否更新
            print("\n" + "="*60)
            response = input("是否更新数据库中的过滤后内容？(y/n): ")
            
            if response.lower() == 'y':
                msg.filtered_content = filtered_content
                msg.is_ad = is_ad
                await db.commit()
                logger.info("✅ 已更新消息的过滤后内容")
            else:
                logger.info("未更新消息内容")
                
    except Exception as e:
        logger.error(f"处理失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(refilter_message())