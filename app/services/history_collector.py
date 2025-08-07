"""
历史消息采集服务
采集频道的历史消息
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from telethon.errors import FloodWaitError, ChannelPrivateError
from sqlalchemy import select, and_
from sqlalchemy.orm import sessionmaker

from app.core.database import AsyncSessionLocal, Message
from app.core.config import db_settings
from app.services.content_filter import ContentFilter
from app.services.channel_manager import ChannelManager
# 移除这行，改为在需要时导入telegram_bot

logger = logging.getLogger(__name__)

@dataclass
class CollectionProgress:
    """采集进度"""
    channel_id: str
    channel_name: str
    total_messages: int
    collected_messages: int
    status: str  # 'running', 'completed', 'error', 'paused'
    start_time: datetime
    end_time: Optional[datetime]
    error_message: Optional[str]

class HistoryCollector:
    """历史消息采集器"""
    
    def __init__(self):
        self.content_filter = ContentFilter()
        self.channel_manager = ChannelManager()
        self.collection_tasks = {}  # channel_id -> task
        self.collection_progress = {}  # channel_id -> CollectionProgress
        
    async def start_collection(self, channel_id: str, limit: int = 100) -> bool:
        """
        开始采集频道历史消息
        
        Args:
            channel_id: 频道ID
            limit: 采集消息数量限制
        """
        try:
            # 检查是否已经在采集
            if channel_id in self.collection_tasks:
                task = self.collection_tasks[channel_id]
                if not task.done():
                    logger.info(f"频道 {channel_id} 已在采集中")
                    return False
                    
            # 验证频道是否存在且可访问
            if not await self._verify_channel_access(channel_id):
                logger.error(f"频道 {channel_id} 不可访问")
                return False
                
            # 获取频道信息
            channel_info = await self._get_channel_info(channel_id)
            if not channel_info:
                logger.error(f"无法获取频道 {channel_id} 信息")
                return False
                
            # 初始化进度
            progress = CollectionProgress(
                channel_id=channel_id,
                channel_name=channel_info.get('title', 'Unknown'),
                total_messages=0,
                collected_messages=0,
                status='running',
                start_time=datetime.utcnow(),
                end_time=None,
                error_message=None
            )
            self.collection_progress[channel_id] = progress
            
            # 启动采集任务
            task = asyncio.create_task(
                self._collect_channel_history(channel_id, limit, progress)
            )
            self.collection_tasks[channel_id] = task
            
            logger.info(f"开始采集频道 {channel_id} 的历史消息，限制 {limit} 条")
            return True
            
        except Exception as e:
            logger.error(f"启动历史消息采集失败: {e}")
            return False
            
    async def stop_collection(self, channel_id: str) -> bool:
        """停止采集特定频道"""
        try:
            if channel_id in self.collection_tasks:
                task = self.collection_tasks[channel_id]
                if not task.done():
                    task.cancel()
                    if channel_id in self.collection_progress:
                        self.collection_progress[channel_id].status = 'paused'
                    logger.info(f"已停止频道 {channel_id} 的历史消息采集")
                    return True
            return False
        except Exception as e:
            logger.error(f"停止历史消息采集失败: {e}")
            return False
            
    async def stop_all_collections(self):
        """停止所有采集任务"""
        for channel_id in list(self.collection_tasks.keys()):
            await self.stop_collection(channel_id)
            
    async def get_collection_progress(self, channel_id: str) -> Optional[CollectionProgress]:
        """获取采集进度"""
        return self.collection_progress.get(channel_id)
        
    async def get_all_progress(self) -> Dict[str, CollectionProgress]:
        """获取所有采集进度"""
        return self.collection_progress.copy()
        
    async def _verify_channel_access(self, channel_id: str) -> bool:
        """验证频道访问权限"""
        try:
            from app.telegram.bot import telegram_bot
            
            if not telegram_bot or not telegram_bot.client:
                logger.error("Telegram bot未连接")
                return False
                
            entity = await telegram_bot.client.get_entity(int(channel_id))
            return True
        except Exception as e:
            logger.error(f"验证频道 {channel_id} 访问权限失败: {e}")
            return False
            
    async def _get_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """获取频道信息"""
        try:
            from app.telegram.bot import telegram_bot
            
            if not telegram_bot or not telegram_bot.client:
                logger.error("Telegram bot未连接")
                return None
                
            entity = await telegram_bot.client.get_entity(int(channel_id))
            return {
                'id': entity.id,
                'title': getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Unknown'),
                'participants_count': getattr(entity, 'participants_count', 0)
            }
        except Exception as e:
            logger.error(f"获取频道 {channel_id} 信息失败: {e}")
            return None
            
    async def _collect_channel_history(self, channel_id: str, limit: int, progress: CollectionProgress):
        """采集频道历史消息"""
        try:
            from app.telegram.bot import telegram_bot
            
            if not telegram_bot or not telegram_bot.client:
                progress.status = 'error'
                progress.error_message = 'Telegram客户端未连接'
                return
                
            # 检查是否已采集过该频道的消息
            existing_count = await self._get_existing_message_count(channel_id)
            if existing_count > 0:
                logger.info(f"频道 {channel_id} 已有 {existing_count} 条消息，跳过历史采集")
                progress.status = 'completed'
                progress.collected_messages = existing_count
                progress.end_time = datetime.utcnow()
                return
                
            # 处理频道ID格式，去掉-100前缀来获取实体
            # channel_id 格式为 -1002829999238
            # 需要转换为整数 ID 用于 Telegram API
            entity_id = int(channel_id)
            
            # 获取频道实体
            entity = await telegram_bot.client.get_entity(entity_id)
            
            collected = 0
            batch_size = 20  # 每批采集数量
            
            logger.info(f"开始采集频道 {channel_id} 历史消息，目标 {limit} 条")
            
            async for message in telegram_bot.client.iter_messages(entity, limit=limit):
                try:
                    # 检查任务是否被取消
                    if asyncio.current_task().cancelled():
                        progress.status = 'paused'
                        return
                        
                    # 处理消息
                    await self._process_history_message(message, channel_id)
                    collected += 1
                    progress.collected_messages = collected
                    
                    # 每采集一批休息一下，避免被限制
                    if collected % batch_size == 0:
                        logger.info(f"频道 {channel_id} 已采集 {collected}/{limit} 条消息")
                        await asyncio.sleep(1)  # 1秒间隔
                        
                except FloodWaitError as e:
                    logger.warning(f"遇到频率限制，等待 {e.seconds} 秒")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.error(f"处理消息时出错: {e}")
                    continue
                    
            # 采集完成
            progress.status = 'completed'
            progress.end_time = datetime.utcnow()
            progress.total_messages = collected
            
            logger.info(f"频道 {channel_id} 历史消息采集完成，共采集 {collected} 条")
            
        except ChannelPrivateError:
            progress.status = 'error'
            progress.error_message = '频道为私有或无访问权限'
            logger.error(f"频道 {channel_id} 为私有或无访问权限")
        except Exception as e:
            progress.status = 'error'
            progress.error_message = str(e)
            logger.error(f"采集频道 {channel_id} 历史消息失败: {e}")
        finally:
            progress.end_time = datetime.utcnow()
            
    async def _get_existing_message_count(self, channel_id: str) -> int:
        """获取已存在的消息数量"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(Message.source_channel == channel_id)
                )
                messages = result.scalars().all()
                return len(messages)
        except Exception as e:
            logger.error(f"获取现有消息数量失败: {e}")
            return 0
            
    async def _process_history_message(self, tl_message, channel_id: str):
        """处理历史消息 - 使用与实时消息相同的流程"""
        try:
            # 检查消息是否已存在
            if await self._message_exists(channel_id, tl_message.id):
                return
            
            # 获取bot实例来使用相同的处理流程
            from app.telegram.bot import telegram_bot
            
            # 确保bot已连接
            if not telegram_bot or not telegram_bot.client:
                logger.error("Telegram bot未连接，无法处理历史消息")
                return
            
            # 获取频道实体（用于传递给process_source_message）
            try:
                # channel_id 格式: "-1002829999238"
                entity_id = int(channel_id)
                entity = await telegram_bot.client.get_entity(entity_id)
            except Exception as e:
                logger.warning(f"获取频道实体失败: {e}，创建临时实体")
                # 如果获取失败，创建一个简单的对象
                # 需要处理ID格式：如果是-100开头的负数，转换为正数
                class SimpleChat:
                    def __init__(self, id):
                        self.id = id
                
                # 从 "-1002829999238" 提取 "2829999238"
                if channel_id.startswith('-100'):
                    chat_id = int(channel_id[4:])  # 去掉 "-100" 前缀
                else:
                    chat_id = abs(int(channel_id))  # 其他负数直接取绝对值
                    
                entity = SimpleChat(chat_id)
            
            # 使用实时消息相同的处理流程
            # process_source_message会：
            # 1. 下载媒体文件
            # 2. 过滤内容
            # 3. 保存到数据库（状态为pending）
            # 4. 转发到审核群
            # 5. 广播WebSocket更新
            await telegram_bot.process_source_message(tl_message, entity)
            
            logger.debug(f"历史消息 {tl_message.id} 已通过标准流程处理")
                
        except Exception as e:
            logger.error(f"处理历史消息失败: {e}")
            
    async def _message_exists(self, channel_id: str, message_id: int) -> bool:
        """检查消息是否已存在"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(
                        and_(
                            Message.source_channel == channel_id,
                            Message.message_id == message_id
                        )
                    )
                )
                return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"检查消息是否存在失败: {e}")
            return False
            
    async def auto_collect_for_new_channels(self):
        """为新添加的频道自动采集历史消息"""
        try:
            # 获取历史消息采集配置
            history_limit = await db_settings.get_history_limit()
            if history_limit <= 0:
                return
                
            # 获取所有源频道
            channels = await self.channel_manager.get_channels_by_type('source')
            
            for channel in channels:
                channel_id = channel.telegram_id
                
                # 检查是否已采集过
                existing_count = await self._get_existing_message_count(channel_id)
                if existing_count == 0:
                    logger.info(f"为新频道 {channel_id} 启动历史消息采集")
                    await self.start_collection(channel_id, history_limit)
                    
        except Exception as e:
            logger.error(f"自动采集新频道历史消息失败: {e}")

# 全局历史采集器实例
history_collector = HistoryCollector()