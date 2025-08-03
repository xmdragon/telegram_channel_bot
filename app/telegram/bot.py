"""
Telegram客户端核心功能 - 使用Telethon
"""
import logging
import asyncio
from typing import List, Optional
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Message as TLMessage, PeerChannel, PeerUser
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.errors import FloodWaitError, ChannelPrivateError
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import db_settings
from app.core.database import AsyncSessionLocal, Message
from app.services.message_processor import MessageProcessor
from app.services.content_filter import ContentFilter
from app.telegram.auth import auth_manager

logger = logging.getLogger(__name__)

class TelegramClient:
    """Telegram客户端管理类"""
    
    def __init__(self):
        self.client = None
        self.message_processor = MessageProcessor()
        self.content_filter = ContentFilter()
        self.is_running = False
    
    async def start(self):
        """启动Telegram客户端"""
        try:
            # 首先尝试加载已保存的认证信息
            logger.info("尝试加载已保存的认证信息...")
            auth_loaded = await auth_manager.load_saved_auth()
            
            if auth_loaded:
                logger.info("成功加载已保存的认证信息")
            else:
                logger.info("未找到已保存的认证信息，等待用户通过Web界面完成认证...")
                return
            
            # 检查认证状态
            auth_status = await auth_manager.get_auth_status()
            if not auth_status["authorized"]:
                logger.info("等待用户通过Web界面完成认证...")
                return
            
            # 使用认证管理器中的客户端
            self.client = auth_manager.client
            if not self.client:
                logger.error("认证客户端不可用")
                return
            
            logger.info("Telegram客户端已启动并授权")
            
            # 注册事件处理器
            self.register_handlers()
            
            # 启动事件循环
            self.is_running = True
            asyncio.create_task(self.run_client())
            
        except Exception as e:
            logger.error(f"启动Telegram客户端时出错: {e}")
    
    def register_handlers(self):
        """注册事件处理器"""
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            await self.handle_message(event)
        
        @self.client.on(events.CallbackQuery)
        async def handle_callback(event):
            await self.handle_callback(event)
    
    async def run_client(self):
        """运行客户端事件循环"""
        try:
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"客户端运行出错: {e}")
        finally:
            self.is_running = False
    
    async def stop(self):
        """停止客户端"""
        self.is_running = False
        if self.client:
            await self.client.disconnect()
            logger.info("Telegram客户端已停止")
    
    async def handle_message(self, event):
        """处理接收到的消息"""
        try:
            message = event.message
            if not message:
                return
            
            # 获取聊天信息
            chat = await event.get_chat()
            chat_id = str(chat.id)
            
            # 获取配置
            source_channels = await db_settings.get_source_channels()
            review_group_id = await db_settings.get_review_group_id()
            
            # 检查是否来自源频道
            if chat_id in source_channels:
                await self.process_source_message(message, chat)
            
            # 检查是否来自审核群
            elif chat_id == review_group_id:
                await self.process_review_message(message, chat)
                
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    async def process_source_message(self, message: TLMessage, chat):
        """处理源频道消息"""
        try:
            # 提取消息内容
            content = message.text or message.raw_text or ""
            media_type = None
            media_url = None
            
            # 处理媒体消息
            if message.media:
                if hasattr(message.media, 'photo'):
                    media_type = "photo"
                    media_url = str(message.media.photo.id)
                elif hasattr(message.media, 'document'):
                    media_type = "document"
                    media_url = str(message.media.document.id)
            
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
                    source_channel=str(chat.id),
                    message_id=message.id,
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
            # 获取配置
            review_group_id = await db_settings.get_review_group_id()
            auto_forward_delay = await db_settings.get_auto_forward_delay()
            
            if not review_group_id:
                logger.error("未配置审核群ID")
                return
            
            # 构建审核消息
            review_text = f"""
📨 新消息待审核

🔗 来源: {db_message.source_channel}
📝 内容: {db_message.filtered_content[:200]}...
🏷️ 类型: {db_message.media_type or '文本'}
🚨 广告检测: {'是' if db_message.is_ad else '否'}

⏰ 将在 {auto_forward_delay // 60} 分钟后自动转发

操作:
✅ 通过: /approve_{db_message.id}
❌ 拒绝: /reject_{db_message.id}
🔄 编辑: /edit_{db_message.id}
📊 详情: /detail_{db_message.id}
            """
            
            # 发送到审核群
            await self.client.send_message(
                entity=int(review_group_id),
                message=review_text
            )
            
            # 更新数据库记录
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(Message.id == db_message.id)
                )
                message = result.scalar_one()
                message.review_message_id = db_message.id  # 简化处理
                await db.commit()
                
        except Exception as e:
            logger.error(f"转发到审核群时出错: {e}")
    
    async def handle_callback(self, event):
        """处理回调按钮"""
        try:
            data = event.data.decode()
            action, message_id = data.split('_', 1)
            message_id = int(message_id)
            
            if action == "approve":
                await self.approve_message(message_id, event.sender.username)
            elif action == "reject":
                await self.reject_message(message_id, event.sender.username)
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
    
    async def process_review_message(self, message: TLMessage, chat):
        """处理审核群中的消息"""
        try:
            text = message.text or ""
            
            # 处理命令
            if text.startswith('/approve_'):
                message_id = int(text.split('_')[1])
                await self.approve_message(message_id, message.sender.username)
            elif text.startswith('/reject_'):
                message_id = int(text.split('_')[1])
                await self.reject_message(message_id, message.sender.username)
            elif text.startswith('/edit_'):
                message_id = int(text.split('_')[1])
                await self.edit_message(message_id)
            elif text.startswith('/detail_'):
                message_id = int(text.split('_')[1])
                await self.show_message_detail(message_id)
                
        except Exception as e:
            logger.error(f"处理审核群消息时出错: {e}")
    
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
            
            if not target_channel_id:
                logger.error("未配置目标频道ID")
                return
            
            # 发送到目标频道
            await self.client.send_message(
                entity=int(target_channel_id),
                message=message.filtered_content
            )
            
            # 更新数据库
            message.target_message_id = message.id  # 简化处理
            message.forwarded_time = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"转发到目标频道时出错: {e}")
    
    async def get_chat_info(self, chat_id: str):
        """获取聊天信息"""
        try:
            chat = await self.client.get_entity(int(chat_id))
            return chat
        except Exception as e:
            logger.error(f"获取聊天信息时出错: {e}")
            return None