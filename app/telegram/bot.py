"""
Telegram机器人核心功能
"""
import logging
from typing import List, Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import db_settings
from app.core.database import AsyncSessionLocal, Message
from app.services.message_processor import MessageProcessor
from app.services.content_filter import ContentFilter

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram机器人管理类"""
    
    def __init__(self):
        self.application = None
        self.message_processor = MessageProcessor()
        self.content_filter = ContentFilter()
    
    async def start(self):
        """启动机器人"""
        bot_token = await db_settings.get_telegram_bot_token()
        if not bot_token:
            logger.error("未配置Telegram机器人Token")
            return
            
        self.application = Application.builder().token(bot_token).build()
        
        # 注册处理器
        self.application.add_handler(
            MessageHandler(filters.ALL, self.handle_message)
        )
        self.application.add_handler(
            CallbackQueryHandler(self.handle_callback)
        )
        
        # 启动机器人
        await self.application.initialize()
        await self.application.start()
        logger.info("Telegram机器人已启动")
    
    async def stop(self):
        """停止机器人"""
        if self.application:
            await self.application.stop()
            logger.info("Telegram机器人已停止")
    
    async def handle_message(self, update: Update, context):
        """处理接收到的消息"""
        try:
            message = update.message
            if not message:
                return
            
            chat_id = str(message.chat.id)
            
            # 获取配置
            source_channels = await db_settings.get_source_channels()
            review_group_id = await db_settings.get_review_group_id()
            
            # 检查是否来自源频道
            if chat_id in source_channels:
                await self.process_source_message(message)
            
            # 检查是否来自审核群
            elif chat_id == review_group_id:
                await self.process_review_message(message)
                
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    async def process_source_message(self, message):
        """处理源频道消息"""
        try:
            # 提取消息内容
            content = message.text or message.caption or ""
            media_type = None
            media_url = None
            
            # 处理媒体消息
            if message.photo:
                media_type = "photo"
                media_url = message.photo[-1].file_id
            elif message.video:
                media_type = "video"
                media_url = message.video.file_id
            elif message.document:
                media_type = "document"
                media_url = message.document.file_id
            
            # 内容过滤
            is_ad, filtered_content = await self.content_filter.filter_message(content)
            
            # 如果是广告且配置了自动过滤，则跳过
            auto_filter_ads = await db_settings.get_auto_filter_ads()
            if is_ad and auto_filter_ads:
                logger.info(f"自动过滤广告消息: {content[:50]}...")
                return
            
            # 保存到数据库
            async with AsyncSessionLocal() as db:
                db_message = Message(
                    source_channel=str(message.chat.id),
                    message_id=message.message_id,
                    content=content,
                    media_type=media_type,
                    media_url=media_url,
                    is_ad=is_ad,
                    filtered_content=filtered_content
                )
                db.add(db_message)
                await db.commit()
                await db.refresh(db_message)
                
                # 转发到审核群
                await self.forward_to_review(db_message)
                
        except Exception as e:
            logger.error(f"处理源频道消息时出错: {e}")
    
    async def forward_to_review(self, db_message: Message):
        """转发消息到审核群"""
        try:
            # 创建审核按钮
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ 通过", callback_data=f"approve_{db_message.id}"),
                    InlineKeyboardButton("❌ 拒绝", callback_data=f"reject_{db_message.id}")
                ],
                [
                    InlineKeyboardButton("🔄 编辑", callback_data=f"edit_{db_message.id}"),
                    InlineKeyboardButton("📊 详情", callback_data=f"detail_{db_message.id}")
                ]
            ])
            
            # 获取配置
            auto_forward_delay = await db_settings.get_auto_forward_delay()
            review_group_id = await db_settings.get_review_group_id()
            
            # 构建审核消息
            review_text = f"""
📨 新消息待审核

🔗 来源: {db_message.source_channel}
📝 内容: {db_message.filtered_content[:200]}...
🏷️ 类型: {db_message.media_type or '文本'}
🚨 广告检测: {'是' if db_message.is_ad else '否'}

⏰ 将在 {auto_forward_delay // 60} 分钟后自动转发
            """
            
            # 发送到审核群
            sent_message = await self.application.bot.send_message(
                chat_id=review_group_id,
                text=review_text,
                reply_markup=keyboard
            )
            
            # 更新数据库记录
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(Message.id == db_message.id)
                )
                message = result.scalar_one()
                message.review_message_id = sent_message.message_id
                await db.commit()
                
        except Exception as e:
            logger.error(f"转发到审核群时出错: {e}")
    
    async def handle_callback(self, update: Update, context):
        """处理回调按钮"""
        try:
            query = update.callback_query
            await query.answer()
            
            data = query.data
            action, message_id = data.split('_', 1)
            message_id = int(message_id)
            
            if action == "approve":
                await self.approve_message(message_id, query.from_user.username)
            elif action == "reject":
                await self.reject_message(message_id, query.from_user.username)
            elif action == "edit":
                await self.edit_message(message_id)
            elif action == "detail":
                await self.show_message_detail(message_id)
                
        except Exception as e:
            logger.error(f"处理回调时出错: {e}")
    
    async def approve_message(self, message_id: int, reviewer: str):
        """批准消息"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(Message.id == message_id)
                )
                message = result.scalar_one()
                
                # 更新状态
                message.status = "approved"
                message.reviewed_by = reviewer
                message.review_time = datetime.utcnow()
                
                # 转发到目标频道
                await self.forward_to_target(message)
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"批准消息时出错: {e}")
    
    async def reject_message(self, message_id: int, reviewer: str):
        """拒绝消息"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(Message.id == message_id)
                )
                message = result.scalar_one()
                
                # 更新状态
                message.status = "rejected"
                message.reviewed_by = reviewer
                message.review_time = datetime.utcnow()
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"拒绝消息时出错: {e}")
    
    async def process_review_message(self, message):
        """处理审核群中的消息"""
        # 这里可以处理审核群中的其他消息，比如管理员的指令
        pass
    
    async def edit_message(self, message_id: int):
        """编辑消息（预留功能）"""
        # 这里可以实现消息编辑功能
        pass
    
    async def show_message_detail(self, message_id: int):
        """显示消息详情（预留功能）"""
        # 这里可以实现显示详细信息
        pass
    
    async def forward_to_target(self, message: Message):
        """转发到目标频道"""
        try:
            # 获取目标频道配置
            target_channel_id = await db_settings.get_target_channel_id()
            
            # 发送到目标频道
            sent_message = await self.application.bot.send_message(
                chat_id=target_channel_id,
                text=message.filtered_content
            )
            
            # 更新数据库
            message.target_message_id = sent_message.message_id
            message.forwarded_time = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"转发到目标频道时出错: {e}")