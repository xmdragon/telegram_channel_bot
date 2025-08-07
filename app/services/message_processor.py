"""
消息处理服务
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal, Message
from app.core.config import db_settings
from .duplicate_detector import DuplicateDetector

logger = logging.getLogger(__name__)

class MessageProcessor:
    """消息处理器"""
    
    def __init__(self):
        self.duplicate_detector = DuplicateDetector()
    
    async def get_pending_messages(self) -> List[Message]:
        """获取待审核的消息"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Message).where(Message.status == "pending")
            )
            return result.scalars().all()
    
    async def get_auto_forward_messages(self) -> List[Message]:
        """获取需要自动转发的消息"""
        auto_forward_delay = await db_settings.get_auto_forward_delay()
        cutoff_time = datetime.utcnow() - timedelta(seconds=auto_forward_delay)
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Message).where(
                    and_(
                        Message.status == "pending",
                        Message.created_at <= cutoff_time,
                        Message.is_ad == False  # 非广告消息才自动转发
                    )
                )
            )
            return result.scalars().all()
    
    async def auto_forward_message(self, message: Message):
        """自动转发消息"""
        try:
            # 这里应该调用Telegram API转发消息
            # 为了简化，这里只更新状态
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(Message.id == message.id)
                )
                db_message = result.scalar_one()
                db_message.status = "auto_forwarded"
                db_message.forwarded_time = datetime.utcnow()
                await db.commit()
                
            logger.info(f"自动转发消息 ID: {message.id}")
            
        except Exception as e:
            logger.error(f"自动转发消息失败: {e}")
    
    async def check_and_filter_duplicates(self, message: Message) -> bool:
        """
        检查并过滤重复消息
        
        Args:
            message: 要检查的消息
            
        Returns:
            True如果是重复消息，False如果不重复
        """
        try:
            is_duplicate = await self.duplicate_detector.is_duplicate_message(
                source_channel=message.source_channel,
                media_hash=message.media_hash,
                combined_media_hash=message.combined_media_hash,
                content=message.content
            )
            
            if is_duplicate:
                # 获取相似的历史消息
                similar_messages = await self.duplicate_detector.get_similar_messages(
                    source_channel=message.source_channel,
                    media_hash=message.media_hash or message.combined_media_hash
                )
                
                if similar_messages:
                    # 标记为重复并指向原始消息
                    await self.duplicate_detector.mark_as_duplicate(
                        message_id=message.id,
                        original_message_id=similar_messages[0].id
                    )
                    
                    logger.info(f"消息 {message.id} 被检测为重复消息，已自动过滤")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查重复消息时出错: {e}")
            return False
    
    async def process_new_message(self, message_data: dict) -> Message:
        """
        处理新消息，包括重复检测
        
        Args:
            message_data: 消息数据字典
            
        Returns:
            处理后的消息对象
        """
        try:
            async with AsyncSessionLocal() as db:
                # 创建消息对象
                message = Message(**message_data)
                db.add(message)
                await db.commit()
                await db.refresh(message)
                
                # 检查是否为重复消息
                is_duplicate = await self.check_and_filter_duplicates(message)
                
                if is_duplicate:
                    logger.info(f"新消息 {message.id} 被标记为重复，已过滤")
                else:
                    logger.info(f"新消息 {message.id} 通过重复检测")
                
                return message
                
        except Exception as e:
            logger.error(f"处理新消息时出错: {e}")
            raise
    
    async def get_message_stats(self) -> dict:
        """获取消息统计信息"""
        async with AsyncSessionLocal() as db:
            # 导入Channel模型
            from app.core.database import Channel
            
            # 总消息数
            total_result = await db.execute(select(Message))
            total_count = len(total_result.scalars().all())
            
            # 待审核消息数
            pending_result = await db.execute(
                select(Message).where(Message.status == "pending")
            )
            pending_count = len(pending_result.scalars().all())
            
            # 已批准消息数
            approved_result = await db.execute(
                select(Message).where(Message.status == "approved")
            )
            approved_count = len(approved_result.scalars().all())
            
            # 被拒绝消息数
            rejected_result = await db.execute(
                select(Message).where(Message.status == "rejected")
            )
            rejected_count = len(rejected_result.scalars().all())
            
            # 广告消息数
            ad_result = await db.execute(
                select(Message).where(Message.is_ad == True)
            )
            ad_count = len(ad_result.scalars().all())
            
            # 重复消息数（通过filtered_content判断）
            duplicate_result = await db.execute(
                select(Message).where(Message.filtered_content.like("%重复消息%"))
            )
            duplicate_count = len(duplicate_result.scalars().all())
            
            # 源频道数量
            channel_result = await db.execute(
                select(Channel).where(Channel.channel_type == "source")
            )
            channel_count = len(channel_result.scalars().all())
            
            return {
                "total": total_count,
                "pending": pending_count,
                "approved": approved_count,
                "rejected": rejected_count,
                "ads": ad_count,
                "duplicates": duplicate_count,
                "channels": channel_count,
                "auto_forwarded": total_count - pending_count - approved_count - rejected_count
            }