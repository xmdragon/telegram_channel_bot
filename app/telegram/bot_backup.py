"""
Telegram客户端核心功能 - 使用Telethon
重构版本 - 参考bot_v3.py的成功模式
"""
import logging
import asyncio
import os
from typing import List, Optional
from datetime import datetime, timezone
from telethon import TelegramClient, events
from telethon.sessions import StringSession
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
from app.services.system_monitor import system_monitor
from app.services.history_collector import history_collector
from app.services.media_handler import media_handler
from app.services.message_grouper import message_grouper
from app.services.config_manager import ConfigManager
from app.telegram.process_lock import telegram_lock

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram机器人管理类"""
    
    def __init__(self):
        self.client = None
        self.message_processor = MessageProcessor()
        self.content_filter = ContentFilter()
        self.is_running = False
        self.monitor_task = None
        self.auto_collection_done = False
        self.config_manager = ConfigManager()
        self.event_loop_task = None
    
    async def start(self):
        """启动Telegram客户端和监控"""
        # 启动系统监控
        await system_monitor.start()
        logger.info("系统监控已启动")
        
        # 启动客户端监控循环
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        
    async def _monitoring_loop(self):
        """监控循环 - 持续检查系统状态并尝试连接"""
        while True:
            try:
                if not self.is_running:
                    await self._start_telegram_client()
                await asyncio.sleep(30)  # 30秒检查一次
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                await asyncio.sleep(10)
    
    async def _start_telegram_client(self):
        """启动Telegram客户端（参考bot_v3.py的模式）"""
        try:
            # 获取认证信息
            api_id = await self.config_manager.get_config("telegram.api_id")
            api_hash = await self.config_manager.get_config("telegram.api_hash")
            session_string = await self.config_manager.get_config("telegram.session")
            
            if not all([api_id, api_hash, session_string]):
                logger.warning("缺少Telegram认证信息，等待用户认证")
                return
            
            logger.info(f"API ID: {api_id}")
            logger.info("准备创建Telegram客户端...")
            
            # 获取进程锁
            if not await telegram_lock.acquire(timeout=30):
                logger.error("无法获取Telegram进程锁，可能有其他进程正在使用")
                return
            
            try:
                # 创建客户端（直接在这里创建，不依赖auth_manager）
                self.client = TelegramClient(
                    StringSession(session_string),
                    int(api_id),
                    api_hash
                )
                
                # 启动客户端
                logger.info("启动Telegram客户端...")
                await self.client.start()
                
                # 验证连接
                me = await self.client.get_me()
                logger.info(f"✅ 客户端已成功连接，登录用户: {me.first_name} (@{me.username})")
                
                # 更新 auth_manager 的客户端实例，让系统监控器能正确检测状态
                from app.telegram.auth import auth_manager
                auth_manager.client = self.client
                
                # 启动媒体处理器
                await media_handler.start()
                
                # 在同一个函数内注册事件处理器（这是关键！）
                await self._register_event_handlers()
                
                # 解析缺失的频道ID
                await self._resolve_missing_channel_ids()
                
                # 首次连接时进行历史消息采集
                if not self.auto_collection_done:
                    await self._auto_collect_history()
                    self.auto_collection_done = True
                
                # 设置运行状态
                self.is_running = True
                
                # 创建并启动事件循环任务
                logger.info("启动事件循环...")
                self.event_loop_task = asyncio.create_task(self._run_event_loop())
                
            except Exception as e:
                logger.error(f"启动客户端失败: {e}")
                await telegram_lock.release()
                raise
                
        except Exception as e:
            logger.error(f"创建Telegram客户端时出错: {e}")
    
    async def _register_event_handlers(self):
        """注册事件处理器（在客户端启动后立即注册）"""
        logger.info("注册事件处理器...")
        
        # 定义消息处理器（参考bot_v3.py的模式）
        @self.client.on(events.NewMessage())
        async def handle_new_message(event):
            """处理新消息事件"""
            logger.info("[事件触发] 收到新消息！")
            try:
                chat = await event.get_chat()
                chat_id = str(chat.id)
                chat_title = getattr(chat, 'title', 'Unknown')
                message_text = event.message.text or "(无文本)"
                
                logger.info(f"频道: {chat_title} (ID: {chat_id})")
                logger.info(f"消息: {message_text[:100]}")
                
                # 调用消息处理逻辑
                await self._handle_message(event)
                
            except Exception as e:
                logger.error(f"处理消息失败: {e}")
        
        @self.client.on(events.CallbackQuery)
        async def handle_callback(event):
            """处理回调查询"""
            await self._handle_callback(event)
        
        # 验证事件处理器已注册
        handlers = self.client.list_event_handlers()
        logger.info(f"✅ 事件处理器注册完成，共 {len(handlers)} 个处理器")
    
    async def _run_event_loop(self):
        """运行客户端事件循环"""
        try:
            logger.info("开始监听消息...")
            await self.client.run_until_disconnected()
            logger.info("客户端事件循环已结束")
        except Exception as e:
            logger.error(f"客户端运行出错: {e}")
        finally:
            self.is_running = False
            await telegram_lock.release()
    
    async def _handle_message(self, event):
        """处理接收到的消息"""
        try:
            message = event.message
            if not message:
                return
            
            # 获取聊天信息
            chat = await event.get_chat()
            
            # 处理频道ID格式
            # Telegram频道ID可能以不同格式出现：
            # - 正数ID (如 2829999238)
            # - 负数ID (如 -1002829999238)
            # 统一转换为带-100前缀的格式用于匹配
            raw_chat_id = chat.id
            if raw_chat_id > 0:
                # 如果是正数，加上-100前缀
                chat_id = f"-100{raw_chat_id}"
            else:
                # 如果是负数，直接转为字符串
                chat_id = str(raw_chat_id)
            
            chat_title = getattr(chat, 'title', 'Unknown')
            
            # 获取配置
            source_channels = await db_settings.get_source_channels()
            
            # 记录消息处理
            logger.info(f"处理消息 - 频道: {chat_title} (原始ID: {raw_chat_id}, 格式化ID: {chat_id})")
            
            # 获取有效的审核群ID
            from app.services.telegram_link_resolver import link_resolver
            review_group_id = await link_resolver.get_effective_group_id()
            
            # 检查是否来自源频道
            if chat_id in source_channels:
                logger.info(f"消息来自监听的源频道: {chat_title}")
                await self.process_source_message(message, chat)
            
            # 检查是否来自审核群
            elif review_group_id and chat_id == review_group_id:
                logger.info(f"消息来自审核群: {chat_title}")
                await self.process_review_message(message, chat)
            else:
                logger.debug(f"消息来自未监听的频道/群组: {chat_title} (ID: {chat_id})")
                
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    async def process_source_message(self, message: TLMessage, chat):
        """处理源频道消息"""
        try:
            # 提取消息内容
            content = message.text or message.raw_text or ""
            media_type = None
            media_url = None
            media_info = None
            
            # 处理媒体消息 - 下载到本地
            if message.media:
                if hasattr(message.media, 'photo'):
                    media_type = "photo"
                elif hasattr(message.media, 'document'):
                    media_type = "document"
                    
                # 下载媒体文件
                media_info = await media_handler.download_media(self.client, message, message.id)
                if media_info:
                    media_type = media_info['media_type']
                    media_url = media_info['file_path']
                elif message.media and hasattr(message.media, 'document'):
                    # media_info 为 None 表示文件被拒绝（可能是危险文件）
                    logger.warning(f"🚫 消息包含危险文件，自动过滤")
                    return
            
            # 内容过滤（包含智能去尾部）
            logger.info(f"📝 开始内容过滤，原始内容长度: {len(content)} 字符")
            is_ad, filtered_content = await self.content_filter.filter_message(content)
            
            # 记录过滤结果
            if len(filtered_content) < len(content):
                logger.info(f"📝 内容过滤完成，过滤后长度: {len(filtered_content)} 字符，减少: {len(content) - len(filtered_content)} 字符")
            else:
                logger.info(f"📝 内容过滤完成，长度无变化: {len(filtered_content)} 字符")
            
            # 检查是否为纯广告（无新闻价值）
            if self.content_filter.is_pure_advertisement(content):
                logger.warning(f"🚫 检测到纯广告，自动拒绝: {content[:50]}...")
                if media_info:
                    await media_handler.cleanup_file(media_info['file_path'])
                return
            
            # 如果是广告且配置了自动过滤，则跳过
            auto_filter_ads = await db_settings.get_auto_filter_ads()
            if is_ad and auto_filter_ads:
                logger.info(f"自动过滤广告消息: {content[:50]}...")
                if media_info:
                    await media_handler.cleanup_file(media_info['file_path'])
                return
            
            # 保存到数据库 - 使用统一的ID格式
            raw_chat_id = chat.id
            if raw_chat_id > 0:
                channel_id = f"-100{raw_chat_id}"
            else:
                channel_id = str(raw_chat_id)
            
            # 使用message_grouper处理可能的组合消息
            combined_message = await message_grouper.process_message(
                message, channel_id, media_info, 
                filtered_content=filtered_content, 
                is_ad=is_ad
            )
            
            # 如果返回None，说明消息还在等待组合，暂时不处理
            if combined_message is None:
                logger.info(f"消息 {message.id} 正在等待组合...")
                return
            
            # 如果是组合消息，message_grouper已经处理了保存和转发
            if combined_message.get('is_combined'):
                logger.info(f"组合消息 {combined_message['grouped_id']} 已由message_grouper处理")
                return
            
            # 处理单独消息
            async with AsyncSessionLocal() as db:
                db_message = Message(
                    source_channel=channel_id,
                    message_id=message.id,
                    content=content,
                    media_type=media_type,
                    media_url=media_url,
                    is_ad=is_ad,
                    filtered_content=filtered_content,
                    grouped_id=str(message.grouped_id) if hasattr(message, 'grouped_id') and message.grouped_id else None,
                    is_combined=False
                )
                db.add(db_message)
                await db.commit()
                await db.refresh(db_message)
                
                # 转发到审核群
                await self.forward_to_review(db_message)
                
                # 广播新消息到WebSocket客户端
                await self._broadcast_new_message(db_message)
                
        except Exception as e:
            logger.error(f"处理源频道消息时出错: {e}")
    
    async def forward_to_review(self, db_message: Message):
        """转发消息到审核群（包含媒体）"""
        try:
            # 获取有效的审核群ID
            from app.services.telegram_link_resolver import link_resolver
            review_group_id = await link_resolver.get_effective_group_id()
            
            if not review_group_id:
                logger.error("未配置审核群ID或无法解析审核群链接")
                return
            
            sent_message = None
            
            # 准备消息内容（使用过滤后的内容）
            message_text = db_message.filtered_content or db_message.content
            
            # 记录智能去尾部效果
            if db_message.filtered_content and len(db_message.filtered_content) < len(db_message.content or ""):
                removed_chars = len(db_message.content) - len(db_message.filtered_content)
                logger.info(f"📤 转发到审核群，智能去尾部已生效，减少 {removed_chars} 字符")
            
            # 在转发时添加频道落款
            message_text = await self.content_filter.add_channel_signature(message_text)
            
            # 检查是否为组合消息
            if db_message.is_combined and db_message.media_group:
                # 发送组合消息到审核群
                sent_message = await self._send_combined_message_to_review(review_group_id, db_message, message_text)
            elif db_message.media_type and db_message.media_url and os.path.exists(db_message.media_url):
                # 发送单个媒体消息到审核群
                sent_message = await self._send_single_media_to_review(review_group_id, db_message, message_text)
            else:
                # 发送纯文本消息到审核群
                sent_message = await self.client.send_message(
                    entity=int(review_group_id),
                    message=message_text
                )
            
            # 更新数据库记录
            if sent_message:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Message).where(Message.id == db_message.id)
                    )
                    message = result.scalar_one()
                    if isinstance(sent_message, list):
                        # 组合消息返回列表，保存第一个消息的ID
                        message.review_message_id = sent_message[0].id
                    else:
                        message.review_message_id = sent_message.id
                    await db.commit()
                    
                logger.info(f"消息已转发到审核群: {db_message.id} -> {message.review_message_id}")
                
        except Exception as e:
            logger.error(f"转发到审核群时出错: {e}")
    
    async def _send_combined_message_to_review(self, review_group_id: str, message: Message, caption: str):
        """发送组合消息到审核群"""
        try:
            media_files = []
            
            # 准备媒体文件列表
            for media_item in message.media_group:
                file_path = media_item['file_path']
                if os.path.exists(file_path):
                    media_files.append(file_path)
            
            if not media_files:
                # 没有媒体文件，发送纯文本
                return await self.client.send_message(
                    entity=int(review_group_id),
                    message=caption
                )
            
            # 发送媒体组
            if len(media_files) == 1:
                # 只有一个文件
                return await self.client.send_file(
                    entity=int(review_group_id),
                    file=media_files[0],
                    caption=caption
                )
            else:
                # 多个文件
                return await self.client.send_file(
                    entity=int(review_group_id),
                    file=media_files,
                    caption=caption
                )
                
        except Exception as e:
            logger.error(f"发送组合消息到审核群失败: {e}")
            # 失败时尝试发送纯文本
            return await self.client.send_message(
                entity=int(review_group_id),
                message=caption
            )
    
    async def _send_single_media_to_review(self, review_group_id: str, message: Message, caption: str):
        """发送单个媒体消息到审核群"""
        try:
            return await self.client.send_file(
                entity=int(review_group_id),
                file=message.media_url,
                caption=caption
            )
        except Exception as e:
            logger.error(f"发送媒体消息到审核群失败: {e}")
            # 失败时尝试发送纯文本
            return await self.client.send_message(
                entity=int(review_group_id),
                message=caption
            )
    
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
    
    async def _handle_callback(self, event):
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
                message.review_time = datetime.now()
                
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
                
                # 删除审核群的消息
                if message.review_message_id:
                    await self.delete_review_message(message.review_message_id)
                
                # 更新状态
                message.status = "rejected"
                message.reviewed_by = reviewer
                message.review_time = datetime.now()
                
                await db.commit()
                
                # 清理媒体文件
                await self._cleanup_message_files(message)
                
        except Exception as e:
            logger.error(f"拒绝消息时出错: {e}")
    
    async def edit_message(self, message_id: int):
        """编辑消息（预留功能）"""
        pass
    
    async def show_message_detail(self, message_id: int):
        """显示消息详情（预留功能）"""
        pass
    
    async def forward_to_target(self, message: Message):
        """重新发布到目标频道"""
        try:
            # 获取目标频道配置
            target_channel_id = await db_settings.get_target_channel_id()
            
            if not target_channel_id:
                logger.error("未配置目标频道ID")
                return
            
            sent_message = None
            
            # 检查是否为组合消息
            if message.is_combined and message.media_group:
                # 发送组合消息（媒体组）
                sent_message = await self._send_combined_message(target_channel_id, message)
            elif message.media_type and message.media_url and os.path.exists(message.media_url):
                # 发送单个媒体消息
                sent_message = await self._send_single_media_message(target_channel_id, message)
            else:
                # 发送纯文本消息
                sent_message = await self.client.send_message(
                    entity=int(target_channel_id),
                    message=message.filtered_content or message.content
                )
            
            # 更新数据库
            if sent_message:
                if isinstance(sent_message, list):
                    message.target_message_id = sent_message[0].id
                else:
                    message.target_message_id = sent_message.id
            message.forwarded_time = datetime.now()
            
            logger.info(f"消息重新发布成功: {message.id} -> {message.target_message_id}")
            
            # 清理本地文件
            await self._cleanup_message_files(message)
            
        except Exception as e:
            logger.error(f"重新发布到目标频道时出错: {e}")
            await self._cleanup_message_files(message)
    
    async def _send_combined_message(self, target_channel_id: str, message: Message):
        """发送组合消息（媒体组）"""
        try:
            media_files = []
            caption_text = message.filtered_content or message.content
            
            # 准备媒体文件列表
            for media_item in message.media_group:
                file_path = media_item['file_path']
                if os.path.exists(file_path):
                    media_files.append(file_path)
            
            if not media_files:
                logger.warning("组合消息中没有可用的媒体文件，发送纯文本")
                return await self.client.send_message(
                    entity=int(target_channel_id),
                    message=caption_text
                )
            
            # 发送媒体组
            if len(media_files) == 1:
                return await self.client.send_file(
                    entity=int(target_channel_id),
                    file=media_files[0],
                    caption=caption_text
                )
            else:
                return await self.client.send_file(
                    entity=int(target_channel_id),
                    file=media_files,
                    caption=caption_text
                )
                
        except Exception as e:
            logger.error(f"发送组合消息失败: {e}")
            return await self.client.send_message(
                entity=int(target_channel_id),
                message=message.filtered_content or message.content
            )
    
    async def _send_single_media_message(self, target_channel_id: str, message: Message):
        """发送单个媒体消息"""
        try:
            return await self.client.send_file(
                entity=int(target_channel_id),
                file=message.media_url,
                caption=message.filtered_content or message.content
            )
        except Exception as e:
            logger.error(f"发送媒体消息失败: {e}")
            return await self.client.send_message(
                entity=int(target_channel_id),
                message=message.filtered_content or message.content
            )
    
    async def _cleanup_message_files(self, message: Message):
        """清理消息相关的媒体文件"""
        try:
            if message.is_combined and message.media_group:
                # 清理组合消息的所有媒体文件
                for media_item in message.media_group:
                    file_path = media_item['file_path']
                    if os.path.exists(file_path):
                        await media_handler.cleanup_file(file_path)
            elif message.media_url and os.path.exists(message.media_url):
                # 清理单个媒体文件
                await media_handler.cleanup_file(message.media_url)
        except Exception as e:
            logger.error(f"清理消息文件时出错: {e}")
    
    async def update_review_message(self, message: Message):
        """更新审核群中的消息内容"""
        try:
            if not message.review_message_id:
                logger.warning("消息没有审核群消息ID，无法更新")
                return
            
            # 获取审核群ID
            from app.services.telegram_link_resolver import link_resolver
            review_group_id = await link_resolver.get_effective_group_id()
            
            if not review_group_id:
                logger.error("未配置审核群ID或无法解析审核群链接")
                return
            
            # 准备更新后的消息内容
            # 注意：落款已经在API层面添加并保存到filtered_content中，这里直接使用
            updated_content = message.filtered_content or message.content
            
            # 检查消息是否包含媒体
            has_media = (message.media_type and message.media_url) or (message.is_combined and message.media_group)
            
            if has_media:
                # 对于带媒体的消息，需要删除旧消息并重新发送
                logger.info(f"消息包含媒体，需要重新发送到审核群")
                
                # 1. 删除旧的审核群消息
                await self.delete_review_message(message.review_message_id)
                
                # 2. 重新发送到审核群
                sent_message = None
                
                # 检查是否为组合消息
                if message.is_combined and message.media_group:
                    # 发送组合消息到审核群
                    sent_message = await self._send_combined_message_to_review(review_group_id, message, updated_content)
                elif message.media_type and message.media_url and os.path.exists(message.media_url):
                    # 发送单个媒体消息到审核群
                    sent_message = await self._send_single_media_to_review(review_group_id, message, updated_content)
                else:
                    # 媒体文件不存在，只发送文本
                    logger.warning(f"媒体文件不存在: {message.media_url}")
                    sent_message = await self.client.send_message(
                        entity=int(review_group_id),
                        message=updated_content
                    )
                
                # 3. 更新数据库中的review_message_id
                if sent_message:
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(
                            select(Message).where(Message.id == message.id)
                        )
                        db_message = result.scalar_one()
                        if isinstance(sent_message, list):
                            # 组合消息返回列表，保存第一个消息的ID
                            db_message.review_message_id = sent_message[0].id
                        else:
                            db_message.review_message_id = sent_message.id
                        await db.commit()
                        logger.info(f"已更新审核群消息ID: {message.id} -> {db_message.review_message_id}")
            else:
                # 纯文本消息，直接编辑
                await self.client.edit_message(
                    entity=int(review_group_id),
                    message=message.review_message_id,
                    text=updated_content
                )
                logger.info(f"已更新审核群消息: {message.review_message_id}")
            
        except Exception as e:
            logger.error(f"更新审核群消息失败: {e}")
    
    async def delete_review_message(self, review_message_id: int):
        """删除审核群的消息"""
        try:
            # 获取审核群ID
            from app.services.telegram_link_resolver import link_resolver
            review_group_id = await link_resolver.get_effective_group_id()
            
            if not review_group_id:
                return
            
            # 删除消息
            await self.client.delete_messages(
                entity=int(review_group_id),
                message_ids=[review_message_id]
            )
            
            logger.info(f"已删除审核群消息: {review_message_id}")
            
        except Exception as e:
            logger.error(f"删除审核群消息失败: {e}")
    
    async def _broadcast_new_message(self, db_message: Message):
        """广播新消息到WebSocket客户端"""
        try:
            from app.api.websocket import websocket_manager
            
            # 准备消息数据
            message_data = {
                "id": db_message.id,
                "source_channel": db_message.source_channel,
                "content": db_message.content,
                "filtered_content": db_message.filtered_content,
                "media_type": db_message.media_type,
                "media_url": db_message.media_url,
                "is_ad": db_message.is_ad,
                "status": db_message.status,
                "created_at": db_message.created_at.isoformat() if db_message.created_at else None,
                "is_combined": db_message.is_combined,
                "media_group_display": self._prepare_media_group_display(db_message)
            }
            
            # 广播到所有WebSocket客户端
            await websocket_manager.broadcast_new_message(message_data)
            
        except Exception as e:
            logger.error(f"广播新消息到WebSocket时出错: {e}")
    
    def _prepare_media_group_display(self, db_message: Message):
        """准备媒体组显示数据"""
        try:
            if not db_message.is_combined or not db_message.media_group:
                return None
                
            media_display = []
            for media_item in db_message.media_group:
                # 转换本地文件路径为web访问路径
                file_path = media_item.get('file_path', '')
                if file_path.startswith('./temp_media/'):
                    web_path = file_path.replace('./temp_media/', '/media/')
                else:
                    web_path = file_path
                    
                media_display.append({
                    'media_type': media_item.get('media_type'),
                    'url': web_path,
                    'file_size': media_item.get('file_size'),
                    'mime_type': media_item.get('mime_type')
                })
            
            return media_display
            
        except Exception as e:
            logger.error(f"准备媒体组显示数据时出错: {e}")
            return None
    
    async def _resolve_missing_channel_ids(self):
        """解析缺失的频道ID"""
        try:
            logger.info("检查并解析缺失的频道ID...")
            from app.services.channel_manager import channel_manager
            resolved_count = await channel_manager.resolve_missing_channel_ids()
            if resolved_count > 0:
                logger.info(f"成功解析 {resolved_count} 个频道ID")
            else:
                logger.info("所有频道ID都已解析或无需解析")
        except Exception as e:
            logger.error(f"解析频道ID失败: {e}")
    
    async def _auto_collect_history(self):
        """自动采集频道历史消息"""
        try:
            logger.info("开始采集频道历史消息...")
            await self._collect_channel_history()
        except Exception as e:
            logger.error(f"自动采集历史消息失败: {e}")
    
    async def _collect_channel_history(self):
        """采集所有监听频道的历史消息"""
        try:
            # 获取历史消息采集配置
            history_limit = await self.config_manager.get_config("channels.history_message_limit", 50)
            
            if history_limit <= 0:
                logger.info("历史消息采集已禁用")
                return
            
            # 获取所有源频道
            async with AsyncSessionLocal() as db:
                from app.core.database import Channel
                from sqlalchemy import select
                result = await db.execute(
                    select(Channel).where(
                        Channel.channel_type == 'source',
                        Channel.is_active == True
                    )
                )
                channels = result.scalars().all()
            
            if not channels:
                logger.warning("未找到活跃的源频道")
                return
                
            logger.info(f"找到 {len(channels)} 个源频道，开始采集历史消息")
            
            # 为每个频道采集历史消息
            for channel in channels:
                try:
                    await self._collect_single_channel_history(channel, history_limit)
                    await asyncio.sleep(2)  # 避免频率限制
                except Exception as e:
                    logger.error(f"采集频道 {channel.channel_name} 历史消息失败: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"采集频道历史消息失败: {e}")
    
    async def _collect_single_channel_history(self, channel, limit: int):
        """采集单个频道的历史消息"""
        try:
            # 检查现有消息数量
            async with AsyncSessionLocal() as db:
                from sqlalchemy import func
                result = await db.execute(
                    select(func.count(Message.id)).where(Message.source_channel == channel.channel_id)
                )
                existing_count = result.scalar()
                
            if existing_count >= limit:
                logger.info(f"频道 {channel.channel_name} 已有 {existing_count} 条消息，跳过采集")
                return
                
            need_collect = limit - existing_count
            logger.info(f"频道 {channel.channel_name} 需要采集 {need_collect} 条历史消息")
            
            # 获取频道实体
            try:
                entity = await self.client.get_entity(int(channel.channel_id))
                logger.info(f"开始采集频道 {entity.title} 的历史消息")
            except Exception as e:
                logger.error(f"获取频道 {channel.channel_name} 实体失败: {e}")
                return
            
            # 采集历史消息 - 先收集到列表，然后按时间顺序处理
            collected_messages = []
            async for message in self.client.iter_messages(entity, limit=need_collect):
                try:
                    # 修复：与实时监听保持一致，处理所有消息（包括纯媒体）
                    if not message:
                        continue
                        
                    # 检查消息是否已存在
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(
                            select(Message).where(
                                Message.source_channel == channel.channel_id,
                                Message.message_id == message.id
                            )
                        )
                        if result.scalar_one_or_none():
                            continue  # 消息已存在，跳过
                    
                    collected_messages.append(message)
                    
                    if len(collected_messages) >= need_collect:
                        break
                        
                except Exception as e:
                    logger.error(f"收集历史消息失败: {e}")
                    continue
            
            # 按时间顺序（旧的在前）处理消息，这样媒体组能正确组合
            collected_messages.reverse()
            logger.info(f"收集到 {len(collected_messages)} 条历史消息，开始处理...")
            
            # 处理收集到的消息
            collected = 0
            for message in collected_messages:
                try:
                    # 处理消息（包括媒体下载）
                    await self._process_and_save_message(message, channel.channel_id, is_history=True)
                    collected += 1
                    
                    if collected % 10 == 0:
                        logger.info(f"已处理 {collected}/{len(collected_messages)} 条历史消息...")
                        
                except Exception as e:
                    logger.error(f"处理历史消息失败: {e}")
                    continue
                    
            # 等待一小段时间，确保所有媒体组都处理完成
            await asyncio.sleep(1)
            logger.info(f"频道 {channel.channel_name} 历史消息采集完成，共处理 {collected} 条")
            
        except Exception as e:
            logger.error(f"采集频道 {channel.channel_name} 历史消息失败: {e}")
    
    async def _process_and_save_message(self, message, channel_id: str, is_history: bool = False):
        """处理并保存消息（包括媒体处理和消息组合）"""
        try:
            # 获取消息文本
            content = message.text or message.message or ''
            
            # 先进行内容过滤（历史消息也需要过滤）
            is_ad, filtered_content = await self.content_filter.filter_message(content)
            
            logger.info(f"📝 历史消息过滤: 原始长度={len(content)}, 过滤后长度={len(filtered_content)}, 是否广告={is_ad}")
            
            # 检查是否为纯广告（与实时监听保持一致）
            if content and self.content_filter.is_pure_advertisement(content):
                logger.warning(f"🚫 历史消息检测到纯广告，跳过: {content[:50]}...")
                return
            
            # 下载媒体文件（如果有）
            media_info = None
            if message.media:
                try:
                    media_info = await media_handler.download_media(self.client, message, message.id)
                    if media_info:
                        logger.debug(f"媒体文件已下载: {media_info['file_path']}")
                    elif message.media:
                        # media_info 为 None 表示文件被拒绝（可能是危险文件）
                        logger.warning(f"🚫 历史消息包含危险文件，跳过")
                        return
                except Exception as e:
                    logger.error(f"下载媒体文件失败: {e}")
            
            # 使用消息组合器处理消息，传递过滤后的内容
            # 历史消息采集使用批量模式
            combined_message = await message_grouper.process_message(
                message, channel_id, media_info,
                filtered_content=filtered_content,
                is_ad=is_ad,
                is_batch=is_history  # 历史消息使用批量模式
            )
            
            # 如果返回None，说明消息正在等待组合，暂时不处理
            if combined_message is None:
                logger.debug(f"消息 {message.id} 正在等待组合")
                return
            
            # 处理完整的消息（单独消息或组合消息）
            await self._save_processed_message(combined_message, channel_id, is_history)
                    
        except Exception as e:
            logger.error(f"处理并保存消息失败: {e}")
            # 出错时清理媒体文件
            if media_info:
                await media_handler.cleanup_file(media_info['file_path'])
    
    async def _save_processed_message(self, message_data: dict, channel_id: str, is_history: bool = False):
        """保存处理后的消息"""
        try:
            # 检查是否已经有过滤后的内容（从message_grouper传递过来的）
            if 'filtered_content' in message_data:
                # 已经过滤过了，直接使用
                filtered_content = message_data['filtered_content']
                is_ad = message_data.get('is_ad', False)
                logger.info(f"📝 使用预过滤内容，长度: {len(filtered_content)} 字符")
            else:
                # 未过滤，进行过滤（兼容旧的调用方式）
                logger.info(f"📝 开始内容过滤，原始内容长度: {len(message_data.get('content', ''))} 字符")
                if message_data.get('content'):
                    logger.info(f"📝 内容预览: {message_data['content'][:100]}...")
                
                # 内容过滤
                is_ad, filtered_content = await self.content_filter.filter_message(message_data['content'])
                
                # 对于组合消息，如果文本被判定为广告，保留原始内容供审核
                # 避免出现只有媒体没有文本的情况
                if message_data.get('is_combined') and is_ad and not filtered_content:
                    logger.info(f"📝 组合消息被判定为广告，保留原始文本供审核")
                    filtered_content = message_data['content']  # 保留原始内容
                
                # 添加过滤后的日志
                if message_data.get('content') != filtered_content:
                    logger.info(f"📝 内容过滤完成，长度变化: {len(message_data.get('content', ''))} -> {len(filtered_content)} 字符")
                else:
                    logger.info(f"📝 内容过滤完成，长度无变化: {len(filtered_content)} 字符")
            
            # 初始化媒体哈希变量
            media_hash = None
            combined_media_hash = None
            
            # 如果是广告且配置了自动过滤，则跳过
            auto_filter_ads = await db_settings.get_auto_filter_ads()
            if is_ad and auto_filter_ads:
                logger.info(f"{'历史' if is_history else '实时'}消息：自动过滤广告消息: {message_data.get('content', '')[:50]}...")
                
                # 清理已下载的媒体文件
                if message_data.get('media_url') and os.path.exists(message_data['media_url']):
                    await media_handler.cleanup_file(message_data['media_url'])
                
                # 对于组合消息，清理所有媒体文件
                if message_data.get('is_combined') and message_data.get('combined_messages'):
                    for msg in message_data['combined_messages']:
                        if msg.get('media_info') and msg['media_info'].get('file_path'):
                            if os.path.exists(msg['media_info']['file_path']):
                                await media_handler.cleanup_file(msg['media_info']['file_path'])
                
                # 对于媒体组，清理所有媒体文件
                if message_data.get('media_group'):
                    for media_item in message_data['media_group']:
                        if media_item.get('file_path') and os.path.exists(media_item['file_path']):
                            await media_handler.cleanup_file(media_item['file_path'])
                
                return
            
            # 计算媒体哈希（先计算，再检查重复）
            logger.info(f"📊 开始计算媒体哈希: is_combined={message_data.get('is_combined')}, media_type={message_data.get('media_type')}, media_url={message_data.get('media_url')}")
            
            # 单个媒体哈希
            if message_data.get('media_type') and message_data.get('media_url'):
                # 从文件计算哈希
                media_hash = await media_handler._calculate_file_hash(message_data['media_url'])
                logger.info(f"📊 单个媒体哈希计算完成: {media_hash}")
            
            # 组合媒体哈希
            if message_data.get('is_combined'):
                combined_media_list = []
                
                # 优先从media_group获取（新格式）
                if message_data.get('media_group'):
                    logger.info(f"📊 处理媒体组: {len(message_data['media_group'])} 个文件")
                    for i, media_item in enumerate(message_data['media_group']):
                        if media_item.get('file_path'):
                            # 计算每个媒体文件的哈希
                            file_hash = await media_handler._calculate_file_hash(media_item['file_path'])
                            logger.info(f"📊 媒体{i+1}哈希: {file_hash} (文件: {media_item.get('file_path')})")
                            if file_hash:
                                combined_media_list.append({
                                    'hash': file_hash,
                                    'message_id': media_item.get('message_id', 0)
                                })
                # 兼容旧格式combined_messages
                elif message_data.get('combined_messages'):
                    logger.info(f"📊 处理旧格式组合消息: {len(message_data['combined_messages'])} 个")
                    for msg in message_data['combined_messages']:
                        if msg.get('media_info') and msg['media_info'].get('file_path'):
                            # 计算每个媒体文件的哈希
                            file_hash = await media_handler._calculate_file_hash(msg['media_info']['file_path'])
                            if file_hash:
                                combined_media_list.append({
                                    'hash': file_hash,
                                    'message_id': msg.get('message_id', 0)
                                })
                
                if combined_media_list:
                    combined_media_hash = await media_handler.process_media_group(combined_media_list)
                    logger.info(f"📊 组合媒体哈希计算完成: {combined_media_hash}")
                else:
                    logger.warning("📊 没有有效的媒体文件用于计算组合哈希")
            
            # 使用整合的重复检测器（历史消息和实时消息都需要检测重复）
            from app.services.duplicate_detector import DuplicateDetector
            duplicate_detector = DuplicateDetector()
            
            async with AsyncSessionLocal() as check_db:
                # 执行整合的重复检测
                is_duplicate, original_msg_id, duplicate_type = await duplicate_detector.is_duplicate_message(
                    source_channel=channel_id,
                    media_hash=media_hash,
                    combined_media_hash=combined_media_hash,
                    content=message_data.get('content'),
                    message_time=message_data.get('date') or datetime.now(),
                    db=check_db
                )
                
                if is_duplicate:
                    logger.info(f"{'历史' if is_history else '实时'}消息：发现重复消息（{duplicate_type}），原始消息ID: {original_msg_id}，跳过处理")
                    # 清理已下载的媒体文件
                    if message_data.get('media_url') and os.path.exists(message_data['media_url']):
                        await media_handler.cleanup_file(message_data['media_url'])
                    # 清理组合消息的媒体文件
                    if message_data.get('media_group'):
                        for media_item in message_data['media_group']:
                            if media_item.get('file_path') and os.path.exists(media_item['file_path']):
                                await media_handler.cleanup_file(media_item['file_path'])
                    return
            
            # 保存到数据库
            async with AsyncSessionLocal() as db:
                db_message = Message(
                    source_channel=channel_id,
                    message_id=message_data['message_id'],
                    content=message_data['content'],
                    media_type=message_data.get('media_type'),
                    media_url=message_data.get('media_url'),
                    grouped_id=str(message_data.get('grouped_id')) if message_data.get('grouped_id') else None,
                    is_combined=message_data.get('is_combined', False),
                    combined_messages=message_data.get('combined_messages'),
                    # 添加媒体哈希字段
                    media_hash=media_hash,
                    combined_media_hash=combined_media_hash,
                    media_group=message_data.get('media_group'),
                    is_ad=is_ad,
                    filtered_content=filtered_content,
                    status='pending' if not is_history else 'auto_forwarded',
                    created_at=message_data.get('date').replace(tzinfo=None) if message_data.get('date') and hasattr(message_data.get('date'), 'tzinfo') else (message_data.get('date') or datetime.now())
                )
                db.add(db_message)
                await db.commit()
                await db.refresh(db_message)
                
                # 如果不是历史消息，转发到审核群
                if not is_history:
                    await self.forward_to_review(db_message)
                    
                    # 广播新消息到WebSocket客户端
                    await self._broadcast_new_message(db_message)
                    
        except Exception as e:
            logger.error(f"保存处理后的消息失败: {e}")
            # 出错时清理媒体文件
            if message_data.get('media_url') and os.path.exists(message_data['media_url']):
                await media_handler.cleanup_file(message_data['media_url'])
    
    async def stop(self):
        """停止客户端"""
        self.is_running = False
        
        # 停止监控任务
        if self.monitor_task:
            self.monitor_task.cancel()
        
        # 停止事件循环任务
        if self.event_loop_task:
            self.event_loop_task.cancel()
            
        # 停止系统监控
        await system_monitor.stop()
        
        # 停止历史采集
        await history_collector.stop_all_collections()
        
        # 停止媒体处理器
        await media_handler.stop()
        
        if self.client:
            await self.client.disconnect()
            logger.info("Telegram客户端已停止")
        
        # 释放进程锁
        await telegram_lock.release()
    
    async def get_chat_info(self, chat_id: str):
        """获取聊天信息"""
        try:
            chat = await self.client.get_entity(int(chat_id))
            return chat
        except Exception as e:
            logger.error(f"获取聊天信息时出错: {e}")
            return None

# 全局bot实例，供其他模块使用
telegram_bot = None