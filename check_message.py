#!/usr/bin/env python3
"""
检查特定消息的过滤情况
"""
import asyncio
import logging
from sqlalchemy import select, and_, or_
from app.core.database import AsyncSessionLocal, Message, Channel
from app.services.ai_filter import ai_filter
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_message_4315():
    """检查消息 #4315 的情况"""
    
    # 加载AI模式
    try:
        ai_filter.load_patterns("data/ai_filter_patterns.json")
        logger.info(f"✅ 已加载 {len(ai_filter.channel_patterns)} 个频道的尾部模式")
    except Exception as e:
        logger.error(f"加载模式失败: {e}")
        return
    
    async with AsyncSessionLocal() as db:
        # 查找频道信息
        channel_result = await db.execute(
            select(Channel).where(
                or_(
                    Channel.channel_name == '@yyds518899',
                    Channel.channel_name == 'yyds518899'
                )
            )
        )
        channel = channel_result.scalar_one_or_none()
        
        if channel:
            logger.info(f"\n📱 频道信息:")
            logger.info(f"  - 频道名: {channel.channel_name}")
            logger.info(f"  - 频道ID: {channel.channel_id}")
            logger.info(f"  - 频道标题: {channel.channel_title}")
            
            # 检查AI模式中是否有该频道
            if channel.channel_id in ai_filter.channel_patterns:
                pattern = ai_filter.channel_patterns[channel.channel_id]
                logger.info(f"\n🤖 AI模式信息:")
                logger.info(f"  - 已学习该频道的尾部模式")
                logger.info(f"  - 学习时间: {pattern.get('learned_at', 'Unknown')}")
                logger.info(f"  - 样本数量: {pattern.get('sample_count', 0)}")
                logger.info(f"  - 相似度阈值: {pattern.get('threshold', 0.75)}")
            else:
                logger.warning(f"  ⚠️ AI模式中未找到该频道的尾部模式")
        else:
            logger.warning("未找到频道 @yyds518899")
        
        # 查找消息 #4315
        # 先尝试通过ID查找
        msg_result = await db.execute(
            select(Message).where(Message.id == 4315)
        )
        msg = msg_result.scalar_one_or_none()
        
        if not msg:
            # 尝试通过消息序号查找
            logger.info("\n通过ID未找到，尝试其他方式...")
            msg_result = await db.execute(
                select(Message).where(
                    Message.source_channel == channel.channel_id if channel else None
                ).order_by(Message.created_at.desc()).limit(100)
            )
            messages = msg_result.scalars().all()
            logger.info(f"找到该频道最近 {len(messages)} 条消息")
            
            # 查找可能包含尾部的消息
            for m in messages[:10]:
                if m.content and ('报名入群' in m.content or '跑分担保' in m.content or '免费报名' in m.content):
                    msg = m
                    break
        
        if msg:
            logger.info(f"\n📨 消息信息:")
            logger.info(f"  - 消息ID: {msg.id}")
            logger.info(f"  - 来源频道: {msg.source_channel}")
            logger.info(f"  - 创建时间: {msg.created_at}")
            logger.info(f"  - 原始内容长度: {len(msg.content) if msg.content else 0}")
            logger.info(f"  - 过滤内容长度: {len(msg.filtered_content) if msg.filtered_content else 0}")
            
            if msg.content:
                logger.info(f"\n📝 原始内容:")
                logger.info("-" * 60)
                logger.info(msg.content[:500])
                if len(msg.content) > 500:
                    logger.info("... (内容过长，已截断)")
                logger.info("-" * 60)
                
                # 尝试应用AI过滤
                if msg.source_channel and msg.source_channel in ai_filter.channel_patterns:
                    logger.info(f"\n🔧 尝试应用AI过滤...")
                    filtered = ai_filter.filter_channel_tail(msg.source_channel, msg.content)
                    
                    logger.info(f"  - 过滤前: {len(msg.content)} 字符")
                    logger.info(f"  - 过滤后: {len(filtered)} 字符")
                    logger.info(f"  - 删除了: {len(msg.content) - len(filtered)} 字符")
                    
                    if len(filtered) < len(msg.content):
                        logger.info(f"\n✂️ 被过滤的尾部内容:")
                        logger.info("-" * 60)
                        removed_tail = msg.content[len(filtered):]
                        logger.info(removed_tail)
                        logger.info("-" * 60)
                        
                        # 分析为什么没有被过滤
                        logger.info(f"\n🔍 尾部分析:")
                        lines = msg.content.split('\n')
                        for i in range(len(lines) - 1, max(0, len(lines) - 10), -1):
                            test_tail = '\n'.join(lines[i:])
                            is_tail, score = ai_filter.is_channel_tail(msg.source_channel, test_tail)
                            logger.info(f"  行 {i}: 相似度 {score:.3f} {'✅' if is_tail else '❌'}")
                    else:
                        logger.info("\n❌ AI过滤器未检测到尾部")
                        
                        # 检查尾部内容
                        lines = msg.content.split('\n')
                        logger.info(f"\n📋 消息最后10行:")
                        for i, line in enumerate(lines[-10:], start=len(lines)-10+1):
                            logger.info(f"  {i}: {line}")
                else:
                    logger.warning(f"\n⚠️ 该频道未在AI模式中，无法过滤")
                    
                if msg.filtered_content:
                    logger.info(f"\n📝 数据库中的过滤内容:")
                    logger.info("-" * 60)
                    logger.info(msg.filtered_content[:500])
                    if len(msg.filtered_content) > 500:
                        logger.info("... (内容过长，已截断)")
                    logger.info("-" * 60)
                    
                    # 检查过滤内容是否仍有尾部
                    if '报名入群' in msg.filtered_content or '跑分担保' in msg.filtered_content:
                        logger.warning("\n⚠️ 过滤后的内容仍包含推广信息！")
                        # 显示尾部
                        lines = msg.filtered_content.split('\n')
                        logger.info(f"过滤内容的最后5行:")
                        for line in lines[-5:]:
                            if line.strip():
                                logger.info(f"  {line}")
        else:
            logger.error("未找到消息 #4315")

async def analyze_channel_pattern():
    """分析频道的尾部模式"""
    async with AsyncSessionLocal() as db:
        # 查找频道
        channel_result = await db.execute(
            select(Channel).where(
                or_(
                    Channel.channel_name == '@yyds518899',
                    Channel.channel_name == 'yyds518899'
                )
            )
        )
        channel = channel_result.scalar_one_or_none()
        
        if not channel:
            logger.error("未找到频道")
            return
            
        # 获取该频道的消息
        msg_result = await db.execute(
            select(Message).where(
                Message.source_channel == channel.channel_id
            ).order_by(Message.created_at.desc()).limit(50)
        )
        messages = msg_result.scalars().all()
        
        logger.info(f"\n📊 分析频道 {channel.channel_name} 的尾部模式")
        logger.info(f"获取了 {len(messages)} 条消息")
        
        # 统计尾部内容
        tail_patterns = {}
        for msg in messages:
            if msg.content:
                lines = msg.content.split('\n')
                if len(lines) > 3:
                    # 提取最后5行作为尾部
                    tail = '\n'.join(lines[-5:])
                    # 简化尾部用于统计
                    simplified_tail = []
                    for line in lines[-5:]:
                        if '报名' in line or '入群' in line or '跑分' in line or '担保' in line or '微信' in line or 'QQ' in line:
                            simplified_tail.append(line.strip())
                    
                    if simplified_tail:
                        tail_key = '\n'.join(simplified_tail)
                        if tail_key not in tail_patterns:
                            tail_patterns[tail_key] = 0
                        tail_patterns[tail_key] += 1
        
        logger.info(f"\n🔍 发现的尾部模式:")
        for pattern, count in sorted(tail_patterns.items(), key=lambda x: x[1], reverse=True)[:5]:
            logger.info(f"\n出现 {count} 次:")
            for line in pattern.split('\n'):
                logger.info(f"  {line}")

async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("🔍 检查消息 #4315 的过滤情况")
    logger.info("=" * 60)
    
    await check_message_4315()
    await analyze_channel_pattern()

if __name__ == "__main__":
    asyncio.run(main())