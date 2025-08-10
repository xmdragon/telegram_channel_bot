#!/usr/bin/env python3
"""
测试AI尾部过滤效果
从数据库读取原始消息，应用AI过滤器，比较过滤前后的差异
"""
import asyncio
import logging
from sqlalchemy import select, and_, func
from app.core.database import AsyncSessionLocal, Message
from app.services.ai_filter import ai_filter
from datetime import datetime, timedelta
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_tail_filtering():
    """测试尾部过滤效果"""
    
    # 确保AI过滤器已加载模式
    if not ai_filter.initialized:
        logger.error("AI过滤器未初始化")
        return
    
    # 加载已保存的模式
    try:
        ai_filter.load_patterns("data/ai_filter_patterns.json")
        logger.info(f"✅ 已加载 {len(ai_filter.channel_patterns)} 个频道的尾部模式")
    except Exception as e:
        logger.error(f"加载模式失败: {e}")
        return
    
    async with AsyncSessionLocal() as db:
        # 获取最近的消息（有原始内容的）
        result = await db.execute(
            select(Message).where(
                and_(
                    Message.content.isnot(None),
                    Message.source_channel.isnot(None)
                )
            ).order_by(Message.created_at.desc()).limit(500)
        )
        messages = result.scalars().all()
        
        logger.info(f"\n📊 开始测试 {len(messages)} 条消息的尾部过滤效果\n")
        
        # 统计数据
        total_processed = 0
        total_filtered = 0
        total_chars_removed = 0
        channel_stats = {}
        
        # 示例展示
        examples = []
        
        for msg in messages:
            if not msg.content or not msg.source_channel:
                continue
                
            total_processed += 1
            original_content = msg.content
            channel_id = msg.source_channel
            
            # 应用AI尾部过滤
            filtered_content = ai_filter.filter_channel_tail(channel_id, original_content)
            
            # 计算差异
            chars_removed = len(original_content) - len(filtered_content)
            
            if chars_removed > 0:
                total_filtered += 1
                total_chars_removed += chars_removed
                
                # 统计每个频道的过滤情况
                if channel_id not in channel_stats:
                    channel_stats[channel_id] = {
                        'total': 0,
                        'filtered': 0,
                        'chars_removed': 0,
                        'channel_name': f"频道{channel_id}"
                    }
                
                channel_stats[channel_id]['total'] += 1
                channel_stats[channel_id]['filtered'] += 1
                channel_stats[channel_id]['chars_removed'] += chars_removed
                
                # 收集示例（前5个）
                if len(examples) < 5:
                    # 提取被过滤的尾部
                    removed_tail = original_content[len(filtered_content):]
                    examples.append({
                        'channel': f"频道{channel_id}",
                        'original_len': len(original_content),
                        'filtered_len': len(filtered_content),
                        'removed_chars': chars_removed,
                        'removed_tail': removed_tail[:200] + '...' if len(removed_tail) > 200 else removed_tail,
                        'percentage': round(chars_removed / len(original_content) * 100, 1)
                    })
            elif channel_id in channel_stats:
                channel_stats[channel_id]['total'] += 1
        
        # 输出统计报告
        logger.info("\n" + "="*60)
        logger.info("📈 尾部过滤效果测试报告")
        logger.info("="*60)
        
        logger.info(f"\n📊 整体统计:")
        logger.info(f"  - 处理消息数: {total_processed}")
        logger.info(f"  - 过滤消息数: {total_filtered} ({total_filtered/total_processed*100:.1f}%)")
        logger.info(f"  - 平均每条删除: {total_chars_removed/total_filtered:.0f} 字符" if total_filtered > 0 else "  - 平均每条删除: 0 字符")
        logger.info(f"  - 总计删除: {total_chars_removed} 字符")
        
        if channel_stats:
            logger.info(f"\n📱 各频道过滤情况:")
            for channel_id, stats in sorted(channel_stats.items(), key=lambda x: x[1]['filtered'], reverse=True)[:10]:
                if stats['filtered'] > 0:
                    avg_removed = stats['chars_removed'] / stats['filtered']
                    logger.info(f"  {stats['channel_name']}:")
                    logger.info(f"    - 消息数: {stats['total']}, 过滤: {stats['filtered']} ({stats['filtered']/stats['total']*100:.0f}%)")
                    logger.info(f"    - 平均删除: {avg_removed:.0f} 字符")
        
        if examples:
            logger.info(f"\n🔍 过滤示例:")
            for i, example in enumerate(examples, 1):
                logger.info(f"\n  示例 {i} - {example['channel']}:")
                logger.info(f"    原始长度: {example['original_len']} 字符")
                logger.info(f"    过滤后: {example['filtered_len']} 字符")
                logger.info(f"    删除比例: {example['percentage']}%")
                logger.info(f"    被过滤的尾部:")
                for line in example['removed_tail'].split('\n')[:5]:
                    if line.strip():
                        logger.info(f"      {line}")
        
        # 检查是否需要更新数据库
        logger.info(f"\n💡 建议:")
        if total_filtered > 0:
            logger.info(f"  ✅ AI尾部过滤效果良好，成功过滤 {total_filtered} 条消息")
            logger.info(f"  💾 可以考虑将过滤结果更新到数据库的 filtered_content 字段")
        else:
            logger.info(f"  ℹ️ 未发现需要过滤的尾部内容")
            logger.info(f"  🔍 可能需要检查训练数据或重新训练")
        
        # 询问是否更新数据库
        if total_filtered > 0:
            logger.info(f"\n❓ 是否要将过滤结果更新到数据库？")
            logger.info(f"   这将更新 {total_filtered} 条消息的 filtered_content 字段")
            logger.info(f"   (运行 python3 test_tail_filter.py --update 来执行更新)")

async def update_database_with_filtered():
    """将过滤结果更新到数据库"""
    logger.info("🔄 开始更新数据库中的过滤内容...")
    
    # 确保AI过滤器已加载模式
    if not ai_filter.initialized:
        logger.error("AI过滤器未初始化")
        return
    
    # 加载已保存的模式
    try:
        ai_filter.load_patterns("data/ai_filter_patterns.json")
        logger.info(f"✅ 已加载 {len(ai_filter.channel_patterns)} 个频道的尾部模式")
    except Exception as e:
        logger.error(f"加载模式失败: {e}")
        return
    
    async with AsyncSessionLocal() as db:
        # 批量处理所有消息，限制数量避免超时
        result = await db.execute(
            select(Message).where(
                and_(
                    Message.content.isnot(None),
                    Message.source_channel.isnot(None)
                )
            ).order_by(Message.created_at.desc()).limit(1000)  # 限制处理数量
        )
        messages = result.scalars().all()
        
        logger.info(f"准备处理 {len(messages)} 条消息...")
        
        updated_count = 0
        processed_count = 0
        for msg in messages:
            if not msg.content or not msg.source_channel:
                continue
            
            processed_count += 1
            if processed_count % 100 == 0:
                logger.info(f"已处理 {processed_count} 条消息...")
            
            # 应用AI尾部过滤
            filtered_content = ai_filter.filter_channel_tail(msg.source_channel, msg.content)
            
            # 如果有变化，更新数据库
            if len(filtered_content) < len(msg.content):
                msg.filtered_content = filtered_content
                updated_count += 1
        
        # 提交更改
        if updated_count > 0:
            await db.commit()
            logger.info(f"✅ 成功更新 {updated_count} 条消息的过滤内容")
        else:
            logger.info("ℹ️ 没有需要更新的消息")

async def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--update':
        # 更新数据库模式
        await update_database_with_filtered()
    else:
        # 测试模式
        await test_tail_filtering()

if __name__ == "__main__":
    asyncio.run(main())