#!/usr/bin/env python3
"""
批量对现有未审核消息应用语义尾部过滤策略
"""
import asyncio
import sys
import os
import json
from datetime import datetime

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import init_db, AsyncSessionLocal, Message
from app.services.semantic_tail_filter import semantic_tail_filter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


async def batch_filter_messages():
    """批量过滤现有未审核消息"""
    print("🚀 开始批量过滤现有未审核消息...")
    
    # 初始化数据库
    await init_db()
    
    try:
        async with AsyncSessionLocal() as session:
            # 获取所有未审核的消息
            result = await session.execute(
                select(Message).where(Message.status == 'pending')
            )
            messages = result.scalars().all()
            
            if not messages:
                print("📭 没有找到未审核的消息")
                return
            
            print(f"📊 找到 {len(messages)} 条未审核消息，开始应用语义尾部过滤...")
            
            filtered_count = 0
            processed_count = 0
            
            for message in messages:
                try:
                    if not message.content:
                        continue
                    
                    # 应用语义尾部过滤
                    has_media = bool(message.media_type or message.media_url or (message.combined_messages and any(m.get('media_type') for m in message.combined_messages)))
                    filtered_content, was_filtered, removed_tail, analysis = semantic_tail_filter.filter_message(
                        message.content, has_media
                    )
                    
                    # 更新数据库中的过滤后内容
                    await session.execute(
                        update(Message)
                        .where(Message.id == message.id)
                        .values(filtered_content=filtered_content)
                    )
                    
                    processed_count += 1
                    
                    if was_filtered:
                        filtered_count += 1
                        print(f"🔧 消息 {message.id}: 过滤 {len(message.content)} → {len(filtered_content)} 字符")
                    else:
                        print(f"✅ 消息 {message.id}: 无需过滤 ({len(message.content)} 字符)")
                        
                except Exception as e:
                    print(f"❌ 处理消息 {message.id} 时出错: {str(e)}")
                    continue
            
            # 提交更改
            await session.commit()
            
            print(f"\n🎉 批量过滤完成!")
            print(f"📊 处理统计:")
            print(f"   - 处理消息数: {processed_count}")
            print(f"   - 过滤消息数: {filtered_count}")
            print(f"   - 保持原样数: {processed_count - filtered_count}")
            if processed_count > 0:
                print(f"   - 过滤率: {(filtered_count/processed_count*100):.1f}%")
            else:
                print("   - 过滤率: 0.0%")
            
    except Exception as e:
        print(f"❌ 批量过滤失败: {str(e)}")
        raise
    finally:
        pass


async def show_filter_statistics():
    """显示过滤统计信息"""
    print("\n📊 过滤效果统计...")
    
    await init_db()
    
    try:
        async with AsyncSessionLocal() as session:
            # 获取所有有过滤后内容的消息
            result = await session.execute(
                select(Message).where(Message.filtered_content.isnot(None))
            )
            messages = result.scalars().all()
            
            if not messages:
                print("📭 没有找到过滤数据")
                return
            
            total_messages = len(messages)
            filtered_messages = 0
            total_original_length = 0
            total_filtered_length = 0
            
            for message in messages:
                try:
                    if message.content and message.filtered_content:
                        original_len = len(message.content)
                        filtered_len = len(message.filtered_content)
                        
                        total_original_length += original_len
                        total_filtered_length += filtered_len
                        
                        # 如果过滤后的内容比原始内容短，说明被过滤了
                        if filtered_len < original_len:
                            filtered_messages += 1
                            
                except Exception as e:
                    continue
            
            print(f"📈 过滤统计结果:")
            print(f"   - 总消息数: {total_messages}")
            print(f"   - 被过滤消息数: {filtered_messages}")
            if total_messages > 0:
                print(f"   - 过滤率: {(filtered_messages/total_messages*100):.1f}%")
            else:
                print("   - 过滤率: 0.0%")
            print(f"   - 原始总长度: {total_original_length} 字符")
            print(f"   - 过滤后总长度: {total_filtered_length} 字符")
            if total_original_length > 0:
                print(f"   - 内容保留率: {(total_filtered_length/total_original_length*100):.1f}%")
            else:
                print("   - 内容保留率: 100.0%")
            
    except Exception as e:
        print(f"❌ 统计失败: {str(e)}")
    finally:
        pass


async def main():
    """主函数"""
    if len(sys.argv) > 1 and sys.argv[1] == '--stats':
        await show_filter_statistics()
    else:
        await batch_filter_messages()
        await show_filter_statistics()


if __name__ == "__main__":
    asyncio.run(main())