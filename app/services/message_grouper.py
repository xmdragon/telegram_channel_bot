"""
消息组合处理器 - 处理Telegram的消息组合功能
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, Message

logger = logging.getLogger(__name__)

class MessageGrouper:
    """消息组合处理器"""
    
    def __init__(self):
        self.pending_groups: Dict[str, List[Dict]] = {}  # 待处理的消息组
        self.group_timers: Dict[str, asyncio.Task] = {}  # 组合超时定时器
        self.group_timeout = 10  # 消息组合超时时间（秒）- 统一使用10秒
        self.telegram_messages: Dict[str, Any] = {}  # 保存原始Telegram消息对象，用于异步下载
    
    async def process_message(self, message, channel_id: str, media_info: Optional[Dict] = None, filtered_content: Optional[str] = None, is_ad: bool = False, is_batch: bool = False) -> Optional[Dict]:
        """
        处理消息，检查是否需要与其他消息组合
        返回完整的组合消息或None（如果消息还在等待组合）
        
        Args:
            is_batch: 是否为批量处理模式（如历史消息采集），批量模式下会立即处理完整个组
        """
        try:
            # 提取消息基本信息
            message_data = {
                'message_id': message.id,
                'content': message.text or message.raw_text or "",
                'filtered_content': filtered_content,
                'is_ad': is_ad,
                'media_info': media_info,
                'date': message.date or datetime.now(),
                'grouped_id': str(getattr(message, 'grouped_id', None)) if getattr(message, 'grouped_id', None) else None
            }
            
            # 如果没有grouped_id，说明是独立消息
            if not message_data['grouped_id']:
                return await self._create_single_message(message_data, channel_id)
            
            # 有grouped_id，需要处理消息组合
            if is_batch:
                # 批量模式，使用更短的超时或立即处理
                return await self._handle_grouped_message_batch(message_data, channel_id)
            else:
                # 实时模式，使用正常的超时机制
                return await self._handle_grouped_message(message_data, channel_id)
            
        except Exception as e:
            logger.error(f"处理消息组合时出错: {e}")
            # 出错时返回单独消息
            return await self._create_single_message(message_data if 'message_data' in locals() else {
                'message_id': message.id,
                'content': message.text or "",
                'media_info': media_info,
                'date': message.date or datetime.now(),
                'grouped_id': None
            }, channel_id)
    
    async def _create_single_message(self, message_data: Dict, channel_id: str) -> Dict:
        """创建单独消息"""
        # 如果有媒体信息，保存本地文件路径
        media_url = None
        if message_data.get('media_info'):
            media_url = message_data['media_info']['file_path']
        
        return {
            'message_id': message_data['message_id'],
            'content': message_data['content'],
            'media_type': message_data['media_info']['media_type'] if message_data.get('media_info') else None,
            'media_url': media_url,
            'grouped_id': str(message_data.get('grouped_id')) if message_data.get('grouped_id') else None,
            'is_combined': False,
            'combined_messages': None,
            'media_group': None,
            'date': message_data['date']
        }
    
    async def _handle_grouped_message_batch(self, message_data: Dict, channel_id: str) -> Optional[Dict]:
        """批量模式下处理组合消息（用于历史消息采集）"""
        grouped_id = str(message_data['grouped_id']) if message_data.get('grouped_id') else None
        if not grouped_id:
            return await self._create_single_message(message_data, channel_id)
            
        group_key = f"{channel_id}_{grouped_id}"
        
        # 检查是否已经处理过这个消息组
        existing_combined = await self._get_existing_combined_message(channel_id, grouped_id)
        if existing_combined:
            logger.debug(f"消息组 {grouped_id} 已存在，跳过处理")
            return None
        
        # 将消息添加到待处理组
        if group_key not in self.pending_groups:
            self.pending_groups[group_key] = []
            # 批量模式下，使用统一的超时时间
            asyncio.create_task(self._process_batch_group_after_timeout(group_key, channel_id, self.group_timeout))
        
        self.pending_groups[group_key].append(message_data)
        logger.debug(f"批量模式：消息组 {grouped_id} 当前有 {len(self.pending_groups[group_key])} 条消息")
        
        # 批量模式下返回None，等待超时后处理
        return None
    
    async def _process_batch_group_after_timeout(self, group_key: str, channel_id: str, timeout: float):
        """批量模式下的超时处理"""
        try:
            await asyncio.sleep(timeout)
            
            if group_key not in self.pending_groups:
                return
            
            messages = self.pending_groups[group_key]
            if not messages:
                return
            
            logger.info(f"批量处理消息组 {group_key}，共 {len(messages)} 条消息")
            
            # 创建组合消息
            combined_message = await self._create_combined_message(messages, channel_id)
            
            # 保存组合消息到数据库
            await self._save_combined_message(combined_message, channel_id)
            
            # 清理
            del self.pending_groups[group_key]
                
        except Exception as e:
            logger.error(f"批量处理消息组 {group_key} 时出错: {e}")
    
    async def _handle_grouped_message(self, message_data: Dict, channel_id: str) -> Optional[Dict]:
        """处理组合消息"""
        grouped_id = str(message_data['grouped_id']) if message_data.get('grouped_id') else None
        if not grouped_id:
            return await self._create_single_message(message_data, channel_id)
            
        group_key = f"{channel_id}_{grouped_id}"
        
        # 检查是否已经处理过这个消息组
        existing_combined = await self._get_existing_combined_message(channel_id, grouped_id)
        if existing_combined:
            logger.info(f"消息组 {grouped_id} 已存在，跳过处理")
            return None
        
        # 检查这条消息是否已经被作为单独消息保存过
        existing_single = await self._get_existing_single_message(channel_id, message_data['message_id'])
        if existing_single:
            logger.info(f"消息 {message_data['message_id']} 已作为单独消息存在，跳过处理")
            return None
        
        # 将消息添加到待处理组
        if group_key not in self.pending_groups:
            self.pending_groups[group_key] = []
        
        self.pending_groups[group_key].append(message_data)
        
        # 取消之前的定时器
        if group_key in self.group_timers:
            self.group_timers[group_key].cancel()
        
        # 设置新的定时器
        self.group_timers[group_key] = asyncio.create_task(
            self._process_group_after_timeout(group_key, channel_id)
        )
        
        logger.info(f"消息组 {grouped_id} 当前有 {len(self.pending_groups[group_key])} 条消息")
        
        # 暂时返回None，等待超时后处理
        return None
    
    async def _process_group_after_timeout(self, group_key: str, channel_id: str):
        """超时后处理消息组"""
        try:
            await asyncio.sleep(self.group_timeout)
            
            if group_key not in self.pending_groups:
                return
            
            messages = self.pending_groups[group_key]
            if not messages:
                return
            
            logger.info(f"处理消息组 {group_key}，共 {len(messages)} 条消息")
            
            # 创建组合消息
            combined_message = await self._create_combined_message(messages, channel_id)
            
            # 保存组合消息到数据库
            await self._save_combined_message(combined_message, channel_id)
            
            # 清理
            del self.pending_groups[group_key]
            if group_key in self.group_timers:
                del self.group_timers[group_key]
                
        except Exception as e:
            logger.error(f"处理消息组超时时出错: {e}")
            # 清理资源
            if group_key in self.pending_groups:
                del self.pending_groups[group_key]
            if group_key in self.group_timers:
                del self.group_timers[group_key]
    
    async def _create_combined_message(self, messages: List[Dict], channel_id: str) -> Dict:
        """创建组合消息"""
        # 按时间排序
        messages.sort(key=lambda x: x['date'])
        
        # 提取所有文本内容（优先使用过滤后的内容）
        all_texts = []
        all_filtered_texts = []
        is_ad = False
        
        for msg in messages:
            content = msg.get('content') or ''
            filtered_content = msg.get('filtered_content')
            
            # 始终保存原始内容
            if content.strip():
                all_texts.append(content)
            
            # 如果有过滤后的内容，使用过滤后的；否则使用原始内容
            if filtered_content and filtered_content.strip():
                all_filtered_texts.append(filtered_content)
            elif content.strip():
                all_filtered_texts.append(content)
            
            # 如果组内任何一条消息被判定为广告，整组都标记为广告
            if msg.get('is_ad'):
                is_ad = True
                logger.info(f"🚫 消息组中检测到广告，整组标记为广告")
        
        combined_content = '\n'.join(all_texts) if all_texts else ""
        combined_filtered_content = '\n'.join(all_filtered_texts) if all_filtered_texts else ""
        
        # 提取所有媒体信息
        media_group = []
        media_types = set()
        
        for msg in messages:
            if msg.get('media_info'):
                media_info = msg['media_info']
                media_group.append({
                    'message_id': msg['message_id'],
                    'media_type': media_info['media_type'],
                    'file_path': media_info.get('file_path'),  # 可能为None（下载失败）
                    'file_size': media_info.get('file_size'),
                    'mime_type': media_info.get('mime_type'),
                    'download_failed': media_info.get('download_failed', False),
                    'error': media_info.get('error')
                })
                # 只有成功下载的媒体才计入类型统计
                if not media_info.get('download_failed'):
                    media_types.add(media_info['media_type'])
        
        # 确定主要媒体类型
        if len(media_types) == 1:
            main_media_type = list(media_types)[0]
        elif 'photo' in media_types:
            main_media_type = 'photo'
        elif 'video' in media_types:
            main_media_type = 'video'
        else:
            main_media_type = 'mixed'
        
        # 使用第一个消息的信息作为主消息
        first_message = messages[0]
        
        # 为组合消息保存主媒体文件路径
        main_media_url = None
        if media_group:
            main_media_url = media_group[0]['file_path']
        
        return {
            'message_id': first_message['message_id'],
            'content': combined_content,
            'filtered_content': combined_filtered_content,
            'is_ad': is_ad,
            'media_type': main_media_type if media_group else None,
            'media_url': main_media_url,
            'grouped_id': str(first_message['grouped_id']) if first_message.get('grouped_id') else None,
            'is_combined': True,
            'combined_messages': [
                {
                    'message_id': msg['message_id'],
                    'content': msg['content'],
                    'media_info': msg.get('media_info')
                }
                for msg in messages
            ],
            'media_group': media_group if media_group else None,
            'date': first_message['date']
        }
    
    async def _save_combined_message(self, combined_message: Dict, channel_id: str):
        """保存组合消息到数据库"""
        try:
            # 这里只创建消息数据，实际保存由调用方处理
            # 因为需要配合现有的过滤和审核流程
            
            # 触发组合消息处理事件
            await self._trigger_combined_message_event(combined_message, channel_id)
            
        except Exception as e:
            logger.error(f"保存组合消息时出错: {e}")
    
    async def _trigger_combined_message_event(self, combined_message: Dict, channel_id: str):
        """触发组合消息处理事件"""
        try:
            # 导入并调用消息处理器
            from app.services.message_processor import MessageProcessor
            import json
            from datetime import datetime
            
            processor = MessageProcessor()
            
            # 使用已经过滤的内容（在创建组合消息时已经处理）
            is_ad = combined_message.get('is_ad', False)
            filtered_content = combined_message.get('filtered_content', combined_message['content'])
            
            # 首先删除已经单独保存的组内消息（如果有的话）
            await self._cleanup_individual_messages(channel_id, combined_message)
            
            # 处理JSON序列化 - 清理包含datetime的对象
            def serialize_for_json(obj):
                """递归处理对象，将datetime转换为字符串"""
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: serialize_for_json(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize_for_json(item) for item in obj]
                else:
                    return obj
            
            # 清理combined_messages和media_group中的datetime对象
            clean_combined_messages = serialize_for_json(combined_message.get('combined_messages'))
            clean_media_group = serialize_for_json(combined_message.get('media_group'))
            
            # 保存到数据库
            async with AsyncSessionLocal() as db:
                db_message = Message(
                    source_channel=channel_id,
                    message_id=combined_message['message_id'],
                    content=combined_message['content'],
                    media_type=combined_message['media_type'],
                    media_url=combined_message['media_url'],
                    grouped_id=str(combined_message['grouped_id']) if combined_message.get('grouped_id') else None,
                    is_combined=combined_message['is_combined'],
                    combined_messages=clean_combined_messages,
                    media_group=clean_media_group,
                    is_ad=is_ad,
                    filtered_content=filtered_content,
                    created_at=datetime.now()  # 使用当前时间，避免时区问题
                )
                db.add(db_message)
                await db.commit()
                await db.refresh(db_message)
                
                logger.info(f"组合消息已保存: ID={db_message.id}, grouped_id={combined_message['grouped_id']}, 包含 {len(combined_message.get('combined_messages', []))} 条消息")
                
                # 媒体已经同步下载完成，无需额外处理
                
                # 转发到审核群（延迟导入避免循环引用）
                try:
                    from app.telegram.bot import telegram_bot
                    if telegram_bot and hasattr(telegram_bot, 'forward_to_review'):
                        await telegram_bot.forward_to_review(db_message)
                        
                    # 广播新消息到WebSocket客户端
                    if telegram_bot and hasattr(telegram_bot, '_broadcast_new_message'):
                        await telegram_bot._broadcast_new_message(db_message)
                        
                except ImportError:
                    logger.warning("无法导入telegram_bot，跳过转发到审核群和WebSocket广播")
                
        except Exception as e:
            logger.error(f"触发组合消息事件时出错: {e}")
    
    async def _get_existing_combined_message(self, channel_id: str, grouped_id: str) -> Optional[Message]:
        """检查是否已存在组合消息"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(
                        Message.source_channel == channel_id,
                        Message.grouped_id == grouped_id,
                        Message.is_combined == True
                    )
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"检查现有组合消息时出错: {e}")
            return None
    
    async def _get_existing_single_message(self, channel_id: str, message_id: int) -> Optional[Message]:
        """检查是否已存在单独消息"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(
                        Message.source_channel == channel_id,
                        Message.message_id == message_id
                    )
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"检查现有单独消息时出错: {e}")
            return None
    
    async def _cleanup_individual_messages(self, channel_id: str, combined_message: Dict):
        """清理已经被组合的单独消息"""
        try:
            if not combined_message.get('combined_messages'):
                return
            
            async with AsyncSessionLocal() as db:
                # 获取所有相关的单独消息ID
                message_ids = [msg['message_id'] for msg in combined_message['combined_messages']]
                
                # 查找并删除这些单独消息
                result = await db.execute(
                    select(Message).where(
                        Message.source_channel == channel_id,
                        Message.message_id.in_(message_ids),
                        Message.is_combined == False  # 只删除单独消息，不删除组合消息
                    )
                )
                
                messages_to_delete = result.scalars().all()
                
                if messages_to_delete:
                    for msg in messages_to_delete:
                        logger.info(f"删除已被组合的单独消息: ID={msg.id}, message_id={msg.message_id}")
                        await db.delete(msg)
                    
                    await db.commit()
                    logger.info(f"已清理 {len(messages_to_delete)} 条被组合的单独消息")
                
        except Exception as e:
            logger.error(f"清理单独消息时出错: {e}")
    
    async def cleanup_expired_groups(self):
        """清理过期的消息组"""
        try:
            expired_keys = []
            current_time = datetime.now()
            
            for group_key, messages in self.pending_groups.items():
                if not messages:
                    expired_keys.append(group_key)
                    continue
                
                # 检查最旧消息的时间
                oldest_time = min(msg['date'] for msg in messages)
                if current_time - oldest_time > timedelta(minutes=5):  # 5分钟超时
                    expired_keys.append(group_key)
            
            for key in expired_keys:
                if key in self.pending_groups:
                    del self.pending_groups[key]
                if key in self.group_timers:
                    self.group_timers[key].cancel()
                    del self.group_timers[key]
                    
            if expired_keys:
                logger.info(f"清理了 {len(expired_keys)} 个过期消息组")
                
        except Exception as e:
            logger.error(f"清理过期消息组时出错: {e}")

# 全局消息组合器实例
message_grouper = MessageGrouper()