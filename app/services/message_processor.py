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
            # 首先检查审核群是否已配置
            from app.services.config_manager import ConfigManager
            config_manager = ConfigManager()
            review_group = await config_manager.get_config('channels.review_group_id')
            
            if not review_group:
                logger.error("❌ 审核群未配置，阻止自动转发！所有消息必须经过审核群。")
                # 更新消息状态为错误状态
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Message).where(Message.id == message.id)
                    )
                    db_message = result.scalar_one()
                    db_message.status = "error"
                    db_message.reject_reason = "审核群未配置，自动转发被阻止"
                    await db.commit()
                return
            
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
            # 准备视觉哈希（如果有）
            visual_hashes = None
            if hasattr(message, 'visual_hash') and message.visual_hash:
                try:
                    visual_hashes = eval(message.visual_hash)
                except:
                    pass
            
            is_duplicate, orig_id, dup_type = await self.duplicate_detector.is_duplicate_message(
                source_channel=message.source_channel,
                media_hash=message.media_hash,
                combined_media_hash=message.combined_media_hash,
                content=message.content,
                message_time=message.created_at,
                message_id=message.id,
                visual_hashes=visual_hashes
            )
            
            if is_duplicate and orig_id:
                # 直接标记为重复并指向原始消息
                await self.duplicate_detector.mark_as_duplicate(
                    message_id=message.id,
                    original_message_id=orig_id
                )
                
                logger.info(f"消息 {message.id} 被检测为{dup_type}重复消息（原消息ID: {orig_id}），已自动过滤")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查重复消息时出错: {e}")
            return False
    
    async def process_new_message(self, message_data: dict) -> Optional[Message]:
        """
        处理新消息，包括重复检测
        
        Args:
            message_data: 消息数据字典
            
        Returns:
            处理后的消息对象，如果重复则返回None
        """
        try:
            # 先进行重复检测（在插入数据库之前）
            is_duplicate, original_msg_id, duplicate_type = await self.duplicate_detector.is_duplicate_message(
                source_channel=message_data.get('source_channel'),
                media_hash=message_data.get('media_hash'),
                combined_media_hash=message_data.get('combined_media_hash'),
                content=message_data.get('content'),
                message_time=message_data.get('created_at') or datetime.utcnow(),
                visual_hashes=message_data.get('visual_hash')
            )
            
            if is_duplicate:
                logger.info(f"检测到重复消息（{duplicate_type}），原始消息ID: {original_msg_id}，拒绝处理")
                return None
            
            # 非重复消息，检查数据库中是否已存在相同的source_channel+message_id
            async with AsyncSessionLocal() as db:
                from sqlalchemy import and_
                existing_result = await db.execute(
                    select(Message).where(and_(
                        Message.source_channel == message_data.get('source_channel'),
                        Message.message_id == message_data.get('message_id')
                    ))
                )
                existing_message = existing_result.scalar_one_or_none()
                
                if existing_message:
                    logger.info(f"消息已存在于数据库中：频道 {message_data.get('source_channel')}，消息ID {message_data.get('message_id')}")
                    return existing_message
                
                # 插入新消息
                message = Message(**message_data)
                db.add(message)
                await db.commit()
                await db.refresh(message)
                
                logger.info(f"新消息 {message.id} 成功保存到数据库")
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