"""
消息处理服务
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal, Message
from app.core.config import db_settings

logger = logging.getLogger(__name__)

class MessageProcessor:
    """消息处理器"""
    
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
    
    async def get_message_stats(self) -> dict:
        """获取消息统计信息"""
        async with AsyncSessionLocal() as db:
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
            
            return {
                "total": total_count,
                "pending": pending_count,
                "approved": approved_count,
                "rejected": rejected_count,
                "ads": ad_count,
                "auto_forwarded": total_count - pending_count - approved_count - rejected_count
            }