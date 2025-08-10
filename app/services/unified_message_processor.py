"""
统一的消息处理器
将实时消息和历史消息的处理流程统一，确保一致性和可维护性
"""
import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime
from telethon.tl.types import Message as TLMessage

from app.core.database import AsyncSessionLocal, Message
from app.services.content_filter import ContentFilter
from app.services.media_handler import media_handler
from app.services.message_grouper import message_grouper
from app.services.duplicate_detector import DuplicateDetector
from app.services.message_processor import MessageProcessor
from app.core.config import db_settings

logger = logging.getLogger(__name__)

class UnifiedMessageProcessor:
    """统一的消息处理器 - 处理所有来源的消息"""
    
    def __init__(self):
        self.content_filter = ContentFilter()
        self.duplicate_detector = DuplicateDetector()
        self.message_processor = MessageProcessor()
        
    async def process_telegram_message(
        self, 
        message: TLMessage, 
        channel_id: str, 
        is_history: bool = False
    ) -> Optional[Message]:
        """
        统一的消息处理入口
        
        Args:
            message: Telegram消息对象
            channel_id: 频道ID（已格式化）
            is_history: 是否为历史消息
            
        Returns:
            处理后的数据库消息对象，如果消息被过滤则返回None
        """
        try:
            # 步骤1: 通用处理（提取内容、下载媒体、过滤广告）
            processed_data = await self._common_message_processing(message, channel_id, is_history)
            if not processed_data:
                return None  # 消息被过滤
            
            # 步骤2: 组合消息检测
            combined_message = await message_grouper.process_message(
                message, 
                channel_id, 
                processed_data.get('media_info'),
                filtered_content=processed_data['filtered_content'],
                is_ad=processed_data['is_ad'],
                is_batch=is_history  # 历史消息使用批量模式
            )
            
            # 如果返回None，说明消息正在等待组合
            if combined_message is None:
                logger.debug(f"消息 {message.id} 正在等待组合")
                return None
            
            # 步骤3: 准备保存数据
            save_data = await self._prepare_save_data(
                combined_message, 
                channel_id, 
                processed_data,
                is_history
            )
            
            # 步骤4: 去重检测
            if await self._is_duplicate(save_data, channel_id):
                logger.info(f"{'历史' if is_history else '实时'}消息被去重检测拒绝")
                await self._cleanup_media_files(save_data)
                return None
            
            # 步骤5: 保存到数据库
            db_message = await self.message_processor.process_new_message(save_data)
            
            if not db_message:
                logger.info(f"消息保存失败或被拒绝")
                await self._cleanup_media_files(save_data)
                return None
            
            # 步骤6: 转发到审核群（仅实时消息或配置了历史消息转发）
            if not is_history or await self._should_forward_history():
                await self._forward_to_review(db_message)
            
            # 步骤7: 广播到WebSocket（仅实时消息）
            if not is_history:
                await self._broadcast_new_message(db_message)
            
            return db_message
            
        except Exception as e:
            logger.error(f"统一消息处理失败: {e}")
            # 清理可能已下载的媒体
            if 'processed_data' in locals() and processed_data:
                media_info = processed_data.get('media_info')
                if media_info and media_info.get('file_path'):
                    await media_handler.cleanup_file(media_info['file_path'])
            return None
    
    async def _common_message_processing(
        self, 
        message: TLMessage, 
        channel_id: str, 
        is_history: bool
    ) -> Optional[Dict[str, Any]]:
        """
        通用消息处理逻辑
        提取内容、下载媒体、过滤广告
        """
        try:
            # 提取消息内容
            content = message.text or message.raw_text or message.message or ""
            
            # 对于媒体消息，检查是否有caption
            if not content and message.media:
                if hasattr(message, 'caption'):
                    content = message.caption or ""
                elif hasattr(message, 'raw_text'):
                    content = message.raw_text or ""
            
            # 再次尝试获取
            if not content and hasattr(message, 'message') and message.message:
                content = message.message
                logger.debug(f"📝 从message属性提取到内容")
            
            # 记录内容提取结果
            if content:
                logger.info(f"📝 提取到消息内容: {content[:100]}...")
            else:
                logger.debug(f"📝 消息无文本内容（纯媒体）")
            
            # 处理媒体
            media_info = None
            if message.media:
                media_info = await self._process_media(message, channel_id)
            
            # 内容过滤（智能去尾部 + 广告检测）
            is_ad, filtered_content, filter_reason = self.content_filter.filter_message(
                content, 
                channel_id=channel_id
            )
            
            # 记录过滤效果
            if content != filtered_content:
                original_len = len(content)
                filtered_len = len(filtered_content)
                logger.info(f"📝 内容过滤: {original_len} -> {filtered_len} 字符 (减少 {original_len - filtered_len})")
            
            if is_ad:
                logger.info(f"🚫 检测到广告: {filter_reason}")
                # 如果配置了自动过滤广告，直接返回None
                if await db_settings.get_auto_filter_ads():
                    logger.info(f"自动过滤广告消息")
                    if media_info and media_info.get('file_path'):
                        await media_handler.cleanup_file(media_info['file_path'])
                    return None
            
            return {
                'content': content,
                'filtered_content': filtered_content,
                'is_ad': is_ad,
                'filter_reason': filter_reason,
                'media_info': media_info
            }
            
        except Exception as e:
            logger.error(f"通用消息处理失败: {e}")
            return None
    
    async def _process_media(self, message: TLMessage, channel_id: str) -> Optional[Dict]:
        """处理媒体下载"""
        try:
            media_type = None
            if hasattr(message.media, 'photo'):
                media_type = "photo"
                timeout = 30.0
            elif hasattr(message.media, 'document'):
                media_type = "document"
                document = message.media.document
                mime_type = document.mime_type or ""
                timeout = 120.0 if mime_type.startswith("video/") else 60.0
            else:
                return None
            
            # 获取Telegram客户端
            from app.telegram.bot import telegram_bot
            if not telegram_bot or not telegram_bot.client:
                logger.warning("Telegram客户端未连接，无法下载媒体")
                return None
            
            # 下载媒体（需要传递client和message_id）
            media_info = await media_handler.download_media(
                telegram_bot.client,
                message, 
                message.id,
                timeout=timeout
            )
            
            if not media_info or not media_info.get('file_path'):
                logger.warning(f"媒体下载失败或超时")
                return None
            
            # 返回媒体信息（media_handler已经计算了哈希和视觉哈希）
            return media_info
            
        except Exception as e:
            logger.error(f"媒体处理失败: {e}")
            return None
    
    async def _prepare_save_data(
        self, 
        message_data: dict, 
        channel_id: str,
        processed_data: dict,
        is_history: bool
    ) -> dict:
        """准备保存到数据库的数据"""
        # 提取媒体哈希
        media_hash = None
        combined_media_hash = None
        visual_hash = None
        
        if message_data.get('is_combined'):
            # 组合消息的哈希处理
            if message_data.get('media_group'):
                hashes = []
                visual_hashes = []
                for media_item in message_data['media_group']:
                    if media_item.get('hash'):
                        hashes.append(media_item['hash'])
                    if media_item.get('visual_hashes'):
                        visual_hashes.append(media_item['visual_hashes'])
                
                if hashes:
                    combined_media_hash = hashlib.sha256(''.join(sorted(hashes)).encode()).hexdigest()
                if visual_hashes:
                    visual_hash = str(visual_hashes)
        else:
            # 单独消息的哈希
            media_info = processed_data.get('media_info')
            if media_info:
                media_hash = media_info.get('hash')
                if media_info.get('visual_hashes'):
                    visual_hash = str(media_info['visual_hashes'])
        
        # 处理时间戳，确保是无时区的datetime
        created_at = message_data.get('date', datetime.now())
        if hasattr(created_at, 'tzinfo') and created_at.tzinfo is not None:
            # 如果有时区信息，转换为无时区的UTC时间
            created_at = created_at.replace(tzinfo=None)
        
        return {
            'source_channel': channel_id,
            'message_id': message_data.get('message_id', message_data.get('id')),
            'content': message_data.get('content', processed_data['content']),
            'filtered_content': message_data.get('filtered_content', processed_data['filtered_content']),
            'is_ad': message_data.get('is_ad', processed_data['is_ad']),
            'media_type': message_data.get('media_type'),
            'media_url': message_data.get('media_url'),
            'media_hash': media_hash,
            'combined_media_hash': combined_media_hash,
            'visual_hash': visual_hash,
            'grouped_id': str(message_data.get('grouped_id')) if message_data.get('grouped_id') else None,
            'is_combined': message_data.get('is_combined', False),
            'combined_messages': message_data.get('combined_messages'),
            'media_group': message_data.get('media_group'),
            'status': 'pending',  # 所有消息都先设为pending状态，等待审核
            'created_at': created_at
        }
    
    async def _is_duplicate(self, save_data: dict, channel_id: str) -> bool:
        """检查是否为重复消息"""
        try:
            # 解析视觉哈希
            visual_hashes = None
            if save_data.get('visual_hash'):
                try:
                    visual_hashes = eval(save_data['visual_hash'])
                    if isinstance(visual_hashes, list) and visual_hashes:
                        visual_hashes = visual_hashes[0]
                except:
                    pass
            
            is_duplicate, orig_id, dup_type = await self.duplicate_detector.is_duplicate_message(
                source_channel=channel_id,
                media_hash=save_data.get('media_hash'),
                combined_media_hash=save_data.get('combined_media_hash'),
                content=save_data.get('content'),
                message_time=save_data.get('created_at'),
                visual_hashes=visual_hashes
            )
            
            if is_duplicate:
                logger.info(f"检测到重复消息（{dup_type}），原始消息ID: {orig_id}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"重复检测失败: {e}")
            return False
    
    async def _cleanup_media_files(self, save_data: dict):
        """清理媒体文件"""
        try:
            # 清理单个媒体文件
            if save_data.get('media_url') and os.path.exists(save_data['media_url']):
                await media_handler.cleanup_file(save_data['media_url'])
            
            # 清理组合消息的媒体文件
            if save_data.get('media_group'):
                for media_item in save_data['media_group']:
                    file_path = media_item.get('file_path')
                    if file_path and os.path.exists(file_path):
                        await media_handler.cleanup_file(file_path)
                        
        except Exception as e:
            logger.error(f"清理媒体文件失败: {e}")
    
    async def _should_forward_history(self) -> bool:
        """检查是否应该转发历史消息到审核群"""
        # 可以添加配置项控制历史消息是否需要审核
        return False  # 默认历史消息不转发到审核群
    
    async def _forward_to_review(self, db_message: Message):
        """转发消息到审核群"""
        try:
            # 延迟导入避免循环引用
            from app.telegram.message_forwarder import message_forwarder
            from app.telegram.bot import telegram_bot
            
            if telegram_bot and telegram_bot.client:
                await message_forwarder.forward_to_review(telegram_bot.client, db_message)
            else:
                logger.warning("Telegram客户端未连接，无法转发到审核群")
                
        except Exception as e:
            logger.error(f"转发到审核群失败: {e}")
    
    async def _broadcast_new_message(self, db_message: Message):
        """广播新消息到WebSocket客户端"""
        try:
            # 延迟导入避免循环引用
            from app.telegram.bot import telegram_bot
            
            if telegram_bot and hasattr(telegram_bot, '_broadcast_new_message'):
                await telegram_bot._broadcast_new_message(db_message)
            else:
                logger.debug("无法广播到WebSocket")
                
        except Exception as e:
            logger.error(f"广播消息失败: {e}")

# 导入hashlib（用于组合媒体哈希）
import hashlib

# 全局实例
unified_processor = UnifiedMessageProcessor()