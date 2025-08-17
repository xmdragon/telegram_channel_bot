"""
统一的消息处理器
将实时消息和历史消息的处理流程统一，确保一致性和可维护性
"""
import logging
import os
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from app.utils.timezone import get_current_time, parse_telegram_time, format_for_api
from telethon.tl.types import Message as TLMessage

from app.services.content_filter import ContentFilter
from app.services.media_handler import media_handler
from app.services.message_grouper import message_grouper
from app.services.duplicate_detector import DuplicateDetector
from app.services.message_processor import MessageProcessor
from app.storage.redis_store import get_redis_message_store
from app.services.filters.base import FilterContext
from app.services.unified_filter_engine import unified_filter_engine

logger = logging.getLogger(__name__)

class UnifiedMessageProcessor:
    """统一的消息处理器 - 处理所有来源的消息"""
    
    def __init__(self):
        self.content_filter = ContentFilter()
        self.duplicate_detector = DuplicateDetector()
        self.message_processor = MessageProcessor()
        self.filter_pipeline = unified_filter_engine.filter_pipeline
        
    async def process_telegram_message(
        self, 
        message: TLMessage, 
        channel_id: str, 
        is_history: bool = False
    ) -> Optional[Dict]:
        """
        统一的消息处理入口
        
        Args:
            message: Telegram消息对象
            channel_id: 频道ID（已格式化）
            is_history: 是否为历史消息
            
        Returns:
            处理后的消息数据字典，如果消息被过滤则返回None
        """
        try:
            # 步骤1: 首先提取原始内容并保存
            original_content = await self._extract_original_content(message)
            
            # 步骤2: 通用处理（提取内容、下载媒体、过滤广告）
            processed_data = await self._common_message_processing(message, channel_id, is_history)
            if not processed_data:
                logger.info(f"📭 消息 #{message.id} 在通用处理阶段被过滤")
                return None  # 消息被过滤
            
            # 检查是否为自动拒绝的消息
            if processed_data.get('_auto_rejected'):
                logger.warning(f"🚨 消息 #{message.id} 被自动拒绝: {processed_data.get('_reject_reason')}")
                
                # 为自动拒绝的消息创建保存数据
                rejected_save_data = {
                    'source_channel': channel_id,
                    'message_id': message.id,
                    'content': processed_data.get('content', ''),
                    'filtered_content': processed_data.get('filtered_content', ''),
                    'is_ad': processed_data.get('is_ad', True),
                    'media_type': None,
                    'media_url': None,
                    'media_hash': None,
                    'status': 'rejected',  # 直接设为rejected状态
                    'reject_reason': processed_data.get('_reject_reason', '自动拒绝'),
                    'filter_reason': processed_data.get('filter_reason', ''),
                    'created_at': parse_telegram_time(message.date)
                }
                
                # 处理媒体信息
                media_info = processed_data.get('media_info')
                if media_info:
                    rejected_save_data['media_type'] = media_info.get('media_type')
                    rejected_save_data['media_url'] = media_info.get('file_path')
                    rejected_save_data['media_hash'] = media_info.get('hash')
                
                # 处理OCR结果
                ocr_result = processed_data.get('ocr_result', {})
                if ocr_result:
                    import json
                    if ocr_result.get('texts'):
                        rejected_save_data['ocr_text'] = json.dumps(ocr_result['texts'], ensure_ascii=False)
                    if ocr_result.get('qr_codes'):
                        rejected_save_data['qr_codes'] = json.dumps(ocr_result['qr_codes'], ensure_ascii=False)
                    rejected_save_data['ocr_ad_score'] = int(ocr_result.get('ad_score', 0))
                    rejected_save_data['ocr_processed'] = bool(ocr_result.get('processed_files', 0) > 0)
                
                # 保存到Redis存储
                saved_rejected = await self.message_processor.process_new_message(rejected_save_data)
                
                if saved_rejected:
                    # 广播到WebSocket让前端能看到拒绝的消息
                    await self._broadcast_new_message(saved_rejected)
                    msg_id = saved_rejected.get('message_id', 'N/A')
                    logger.info(f"❌ 最终处理结果: 消息 #{message.id} -> Redis {channel_id}:{msg_id} [状态: rejected] [原因: 自动拒绝]")
                    
                    # 清理媒体文件（拒绝的消息不保留媒体）
                    if media_info and media_info.get('file_path'):
                        await media_handler.cleanup_file(media_info['file_path'])
                    
                    return saved_rejected
                else:
                    logger.error(f"💥 自动拒绝消息 #{message.id} 保存失败")
                    # 清理媒体文件
                    if media_info and media_info.get('file_path'):
                        await media_handler.cleanup_file(media_info['file_path'])
                    return None
            
            # 确保原始内容被保留
            processed_data['original_content'] = original_content
            
            # 🔧 修复：同时保存单独消息和组合消息
            grouped_id = str(getattr(message, 'grouped_id', None)) if getattr(message, 'grouped_id', None) else None
            
            # 步骤3a: 先保存单独消息（确保每条消息都被保存）
            individual_save_data = await self._prepare_individual_save_data(
                message, 
                channel_id, 
                processed_data,
                is_history,
                grouped_id
            )
            
            # 去重检测
            duplicate_info = await self._check_duplicate_with_details(individual_save_data, channel_id)
            if duplicate_info:
                logger.info(f"🔄 单独消息被去重检测拒绝: {duplicate_info['reason']}")
                individual_save_data['status'] = 'rejected'
                individual_save_data['reject_reason'] = f"去重检测: {duplicate_info['reason']}"
                # 🔧 新增：保存重复信息供前端对比显示
                individual_save_data['duplicate_original_id'] = duplicate_info['original_id']
                individual_save_data['duplicate_type'] = duplicate_info['type']
            
            # 保存单独消息到Redis
            saved_individual = await self.message_processor.process_new_message(individual_save_data)
            
            if not saved_individual:
                logger.error(f"💥 单独消息 #{message.id} 保存失败")
                await self._cleanup_media_files(individual_save_data)
                return None
            
            # 记录单独消息保存成功
            msg_id = saved_individual.get('message_id', 'N/A')
            status = saved_individual.get('status', 'unknown')
            logger.info(f"✅ 单独消息已保存: #{message.id} -> Redis {channel_id}:{msg_id} [状态: {status}]")
            
            # 步骤3b: 如果有组ID，处理组合消息（用于组图展示）
            if grouped_id:
                # 🔧 修复后：只需要注册消息到组合器，不需要再次保存单独消息
                # message_grouper 将返回单独消息（已在步骤3a保存）和可能的组合消息
                grouper_result = await message_grouper.process_message(
                    message, 
                    channel_id, 
                    processed_data.get('media_info'),
                    filtered_content=processed_data['filtered_content'],
                    is_ad=processed_data['is_ad'],
                    is_batch=is_history  # 历史消息使用批量模式
                )
                
                # grouper_result 现在始终返回单独消息，无需重复处理
                logger.debug(f"📦 消息已注册到组合器，单独消息已保存")
            
            # 使用已保存的单独消息作为最终结果
            saved_message = saved_individual
            
            # 步骤7: 转发到审核群（根据配置决定）
            if await self._should_forward_to_review(is_history):
                await self._forward_to_review(saved_message)
            
            # 记录成功处理
            logger.info(f"✅ 消息处理完成: #{message.id} -> {channel_id}:{saved_message.get('message_id')} [组ID: {grouped_id or 'N/A'}]")
            
            # 步骤8: 广播到WebSocket（所有新消息都广播，让web端能看到）
            # 不再区分是否历史消息，所有成功保存的消息都广播到web端
            await self._broadcast_new_message(saved_message)
            
            # 最终处理结果日志
            status_emoji = {
                'pending': '⏳',
                'approved': '✅', 
                'rejected': '❌',
                'auto_forwarded': '🤖'
            }.get(saved_message.get('status'), '❓')
            
            msg_id = saved_message.get('message_id', 'N/A')
            status = saved_message.get('status', 'unknown')
            is_ad = saved_message.get('is_ad', False)
            
            logger.info(f"{status_emoji} 最终处理结果: 消息 #{message.id} -> Redis {channel_id}:{msg_id} [状态: {status}] [广告: {'是' if is_ad else '否'}]")
            
            return saved_message
            
        except Exception as e:
            logger.error(f"统一消息处理失败 #{message.id}: {e}")
            # 清理可能已下载的媒体
            if 'processed_data' in locals() and processed_data:
                media_info = processed_data.get('media_info')
                if media_info and media_info.get('file_path'):
                    from app.services.media_handler import media_handler
                    await media_handler.cleanup_file(media_info['file_path'])
            return None
    
    async def _extract_original_content(self, message: TLMessage) -> str:
        """
        提取消息的原始内容，确保不丢失任何文本
        
        Args:
            message: Telegram消息对象
            
        Returns:
            原始内容字符串
        """
        # 尝试多种方式提取内容
        content = ""
        
        # 1. 优先使用text属性
        if hasattr(message, 'text') and message.text:
            content = message.text
        # 2. 尝试raw_text
        elif hasattr(message, 'raw_text') and message.raw_text:
            content = message.raw_text
        # 3. 尝试message属性
        elif hasattr(message, 'message') and message.message:
            content = message.message
        # 4. 对于媒体消息，尝试caption
        elif hasattr(message, 'media') and message.media:
            if hasattr(message, 'caption') and message.caption:
                content = message.caption
        
        # 记录原始内容提取情况
        if content:
            logger.info(f"📝 提取到原始内容: {len(content)} 字符")
            logger.debug(f"原始内容前100字符: {content[:100]}...")
        else:
            logger.debug(f"📝 消息无文本内容（纯媒体）")
        
        return content
    
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
            media_type_info = None
            if message.media:
                # 首先记录媒体类型信息（即使下载失败也要保留）
                media_type_info = {
                    'has_media': True,
                    'media_type': self._get_media_type(message.media),
                    'download_failed': False
                }
                
                # 尝试下载媒体
                media_info = await self._process_media(message, channel_id)
                
                # 如果下载失败，标记下载失败状态
                if not media_info:
                    media_type_info['download_failed'] = True
                    logger.warning(f"媒体下载失败，但已记录媒体类型: {media_type_info['media_type']}")
            
            # 准备媒体文件列表用于OCR处理
            media_files = []
            if media_info and media_info.get('file_path'):
                media_files.append(media_info['file_path'])
            
            # 提取消息实体（包括隐藏链接）
            from app.services.structural_ad_detector import structural_detector
            entities = structural_detector.extract_entity_data(message)
            
            # 移除隐藏链接（系统默认策略：始终移除）
            removed_hidden_links = []
            clean_entities, removed_hidden_links = structural_detector.remove_hidden_links(message)
            if removed_hidden_links:
                logger.info(f"🔗 移除了 {len(removed_hidden_links)} 个隐藏链接")
            
            # 使用新的过滤器管道进行内容过滤
            filter_context = FilterContext(
                message_id=message.id,
                channel_id=channel_id
            )
            # 添加历史消息标记和媒体文件信息到元数据
            filter_context.add_metadata('is_history', is_history)
            filter_context.add_metadata('media_files', media_files)
            filter_context.add_metadata('message_obj', message)
            
            # 执行过滤器管道
            pipeline_result = await self.filter_pipeline.process(content, filter_context)
            
            # 提取结果
            # 🔧 修改广告判断逻辑：支持AI检测器的仅检测模式
            ad_detection_result = filter_context.get_metadata('ad_detection_result')
            is_ad = (not pipeline_result.passed) or (ad_detection_result and ad_detection_result.get('is_ad', False))
            filtered_content = pipeline_result.final_content
            filter_reason = pipeline_result.overall_reason or ""
            
            # 如果是AI检测到的广告，更新过滤原因
            if ad_detection_result and ad_detection_result.get('is_ad', False):
                ai_reason = ad_detection_result.get('main_reason', 'AI检测')
                if not filter_reason:
                    filter_reason = f"AI检测到疑似广告: {ai_reason}"
                else:
                    filter_reason += f" + AI检测: {ai_reason}"
            
            # 提取OCR结果（如果有）
            ocr_result = {}
            if 'ad_detector' in pipeline_result.filter_results:
                ad_result = pipeline_result.filter_results['ad_detector']
                ocr_result = ad_result.details.get('ocr_result', {}) if ad_result.details else {}
            
            # 记录过滤效果
            if content != filtered_content:
                original_len = len(content)
                filtered_len = len(filtered_content)
                logger.info(f"📝 内容过滤: {original_len} -> {filtered_len} 字符 (减少 {original_len - filtered_len})")
            
            if is_ad:
                logger.info(f"🚫 检测到广告: {filter_reason}")
                
                # 检查是否应该完全拒绝纯广告消息
                should_reject, reject_reason = self._should_reject_pure_ad(
                    is_ad, filter_reason, filtered_content, content, media_info, ocr_result
                )
                
                if should_reject:
                    logger.warning(f"🚨 拒绝纯广告消息: {reject_reason}")
                    
                    # 保存被拒绝的OCR样本（如果有媒体文件）
                    if media_info and media_info.get('file_path') and ocr_result:
                        try:
                            from app.services.ocr_service import ocr_service
                            import hashlib
                            import asyncio
                            
                            # 计算文件哈希
                            with open(media_info['file_path'], 'rb') as f:
                                file_hash = hashlib.md5(f.read()).hexdigest()
                            
                            # 异步保存样本
                            asyncio.create_task(ocr_service._save_ocr_sample(
                                image_path=media_info['file_path'],
                                image_hash=file_hash,
                                texts=ocr_result.get('texts', []),
                                qr_codes=[qr.get('data', '') for qr in ocr_result.get('qr_codes', []) if qr.get('data')],
                                ad_score=ocr_result.get('ad_score', 0),
                                is_ad=True,
                                keywords_detected=ocr_result.get('ad_indicators', []),
                                auto_rejected=True,
                                rejection_reason=reject_reason
                            ))
                        except Exception as e:
                            logger.debug(f"保存拒绝样本失败: {e}")
                    
                    # 为被拒绝的消息创建保存数据，状态设为rejected
                    rejected_data = {
                        'content': content,
                        'filtered_content': filtered_content,
                        'is_ad': is_ad,
                        'filter_reason': filter_reason,
                        'media_info': media_info,
                        'media_type_info': media_type_info,  # 🔧 新增：媒体类型信息
                        'ocr_result': ocr_result,
                        'entities': [],
                        'removed_hidden_links': []
                    }
                    
                    # 返回拒绝数据，让上层处理保存逻辑
                    rejected_data['_auto_rejected'] = True
                    rejected_data['_reject_reason'] = reject_reason
                    return rejected_data
                
                # 检查是否配置了自动过滤广告
                try:
                    from app.services.config_manager import config_manager
                    auto_filter = await config_manager.get_config('filter.auto_filter_ads', False)
                    if auto_filter:
                        logger.info(f"🚫 自动过滤广告消息: {filter_reason}")
                        
                        # 为自动过滤的消息创建保存数据
                        filtered_data = {
                            'content': content,
                            'filtered_content': filtered_content,
                            'is_ad': is_ad,
                            'filter_reason': filter_reason,
                            'media_info': media_info,
                            'media_type_info': media_type_info,  # 🔧 新增：媒体类型信息
                            'ocr_result': ocr_result,
                            'entities': [],
                            'removed_hidden_links': []
                        }
                        
                        # 返回过滤数据，让上层处理保存逻辑
                        filtered_data['_auto_rejected'] = True
                        filtered_data['_reject_reason'] = f"配置自动过滤: {filter_reason}"
                        return filtered_data
                except Exception as e:
                    logger.debug(f"检查自动过滤配置失败: {e}")
            
            # 检查消息是否有有效内容
            # 如果既没有媒体，filtered_content又为空，则拒绝这条消息
            if not media_info and not filtered_content:
                logger.warning(f"❌ 消息既无媒体又无有效内容，拒绝处理 (原内容长度: {len(content)})")
                return None
            
            return {
                'content': content,
                'filtered_content': filtered_content,
                'is_ad': is_ad,
                'filter_reason': filter_reason,
                'media_info': media_info,
                'media_type_info': media_type_info,  # 🔧 新增：媒体类型信息
                'ocr_result': ocr_result,  # 包含OCR提取结果
                'entities': entities,  # 所有实体信息
                'removed_hidden_links': removed_hidden_links  # 被移除的隐藏链接
            }
            
        except Exception as e:
            logger.error(f"通用消息处理失败: {e}")
            return None
    
    def _get_media_type(self, media) -> str:
        """获取媒体类型"""
        try:
            from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
            from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio
            from telethon.tl.types import DocumentAttributeAnimated, DocumentAttributeSticker
            
            if isinstance(media, MessageMediaPhoto):
                return 'photo'
            elif isinstance(media, MessageMediaDocument):
                document = media.document
                if document and hasattr(document, 'attributes'):
                    for attr in document.attributes:
                        if isinstance(attr, DocumentAttributeVideo):
                            return 'animation' if attr.round_message else 'video'
                        elif isinstance(attr, DocumentAttributeAnimated):
                            return 'animation'
                        elif isinstance(attr, DocumentAttributeAudio):
                            return 'audio'
                        elif isinstance(attr, DocumentAttributeSticker):
                            return 'sticker'
                    # 如果没有特殊属性，判断MIME类型
                    if document.mime_type:
                        if document.mime_type.startswith('video/'):
                            return 'video'
                        elif document.mime_type.startswith('audio/'):
                            return 'audio'
                        elif document.mime_type.startswith('image/'):
                            return 'photo'
                return 'document'
            else:
                return 'unknown'
        except Exception as e:
            logger.debug(f"获取媒体类型失败: {e}")
            return 'unknown'

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
    
    async def _prepare_individual_save_data(
        self,
        message: TLMessage,
        channel_id: str,
        processed_data: dict,
        is_history: bool,
        grouped_id: Optional[str] = None
    ) -> dict:
        """准备单独消息的保存数据（确保每条消息都被保存）"""
        # 处理媒体哈希
        media_hash = None
        visual_hash = None
        
        media_info = processed_data.get('media_info')
        if media_info:
            media_hash = media_info.get('hash')
            if media_info.get('visual_hashes'):
                import json
                visual_hash = json.dumps(media_info['visual_hashes'])
        
        # 处理时间戳
        created_at = parse_telegram_time(message.date)
        
        # 处理OCR结果
        ocr_result = processed_data.get('ocr_result', {})
        ocr_text = None
        qr_codes = None
        ocr_ad_score = 0
        ocr_processed = False
        
        if ocr_result:
            if ocr_result.get('texts'):
                import json
                ocr_text = json.dumps(ocr_result['texts'], ensure_ascii=False)
            
            if ocr_result.get('qr_codes'):
                qr_codes = json.dumps(ocr_result['qr_codes'], ensure_ascii=False)
            
            ocr_ad_score = int(ocr_result.get('ad_score', 0))
            ocr_processed = bool(ocr_result.get('processed_files', 0) > 0)
        
        return {
            'source_channel': channel_id,
            'message_id': message.id,
            'content': processed_data.get('original_content', processed_data['content']),
            'filtered_content': processed_data['filtered_content'],
            'is_ad': processed_data['is_ad'],
            'media_type': self._determine_media_type({}, processed_data),
            'media_url': self._determine_media_url({}, processed_data),
            'media_hash': media_hash,
            'ocr_text': ocr_text,
            'qr_codes': qr_codes,
            'ocr_ad_score': ocr_ad_score,
            'ocr_processed': ocr_processed,
            'entities': processed_data.get('entities'),
            'removed_hidden_links': processed_data.get('removed_hidden_links'),
            'visual_hash': visual_hash,
            'grouped_id': grouped_id,
            'is_combined': False,  # 单独消息不是组合消息
            'status': 'pending',
            'created_at': created_at
        }
    
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
                    import json
                    visual_hash = json.dumps(visual_hashes)
        else:
            # 单独消息的哈希
            media_info = processed_data.get('media_info')
            if media_info:
                media_hash = media_info.get('hash')
                if media_info.get('visual_hashes'):
                    import json
                    visual_hash = json.dumps(media_info['visual_hashes'])
        
        # 处理时间戳，确保是无时区的UTC datetime
        created_at = parse_telegram_time(message_data.get('date'))
        
        # 处理OCR结果
        ocr_result = processed_data.get('ocr_result', {})
        ocr_text = None
        qr_codes = None
        ocr_ad_score = 0
        ocr_processed = False
        
        if ocr_result:
            # 将OCR文字转换为JSON字符串存储
            if ocr_result.get('texts'):
                import json
                ocr_text = json.dumps(ocr_result['texts'], ensure_ascii=False)
            
            # 将二维码信息转换为JSON字符串存储
            if ocr_result.get('qr_codes'):
                qr_codes = json.dumps(ocr_result['qr_codes'], ensure_ascii=False)
            
            ocr_ad_score = int(ocr_result.get('ad_score', 0))
            ocr_processed = bool(ocr_result.get('processed_files', 0) > 0)
        
        return {
            'source_channel': channel_id,
            'message_id': message_data.get('message_id', message_data.get('id')),
            'content': processed_data.get('original_content', message_data.get('content', processed_data['content'])),  # 优先使用原始内容
            'filtered_content': message_data.get('filtered_content', processed_data['filtered_content']),
            'is_ad': message_data.get('is_ad', processed_data['is_ad']),
            'media_type': self._determine_media_type(message_data, processed_data),
            'media_url': self._determine_media_url(message_data, processed_data),
            'media_hash': media_hash,
            # 新增OCR相关字段
            'ocr_text': ocr_text,
            'qr_codes': qr_codes,
            'ocr_ad_score': ocr_ad_score,
            'ocr_processed': ocr_processed,
            # 新增实体相关字段
            'entities': processed_data.get('entities'),
            'removed_hidden_links': processed_data.get('removed_hidden_links'),
            'combined_media_hash': combined_media_hash,
            'visual_hash': visual_hash,
            'grouped_id': str(message_data.get('grouped_id')) if message_data.get('grouped_id') else None,
            'is_combined': message_data.get('is_combined', False),
            'combined_messages': message_data.get('combined_messages'),
            'media_group': message_data.get('media_group'),
            'status': 'pending',  # 所有消息都先设为pending状态，等待审核
            'created_at': created_at
        }
    
    def _determine_media_type(self, message_data: dict, processed_data: dict) -> Optional[str]:
        """确定媒体类型（优先使用实际下载的，其次使用检测到的）"""
        # 1. 优先使用实际下载的媒体信息
        if message_data.get('media_type'):
            return message_data.get('media_type')
        
        # 2. 检查处理数据中的媒体信息
        media_info = processed_data.get('media_info')
        if media_info and media_info.get('media_type'):
            return media_info['media_type']
        
        # 3. 检查媒体类型信息（即使下载失败也有）
        media_type_info = processed_data.get('media_type_info')
        if media_type_info and media_type_info.get('media_type'):
            return media_type_info['media_type']
        
        return None
    
    def _determine_media_url(self, message_data: dict, processed_data: dict) -> Optional[str]:
        """确定媒体URL（如果下载失败，生成占位符）"""
        # 1. 优先使用实际下载的媒体文件
        if message_data.get('media_url'):
            return message_data.get('media_url')
        
        # 2. 检查处理数据中的媒体信息
        media_info = processed_data.get('media_info')
        if media_info and media_info.get('file_path'):
            return media_info['file_path']
        
        # 3. 如果有媒体但下载失败，生成占位符
        media_type_info = processed_data.get('media_type_info')
        if media_type_info and media_type_info.get('has_media') and media_type_info.get('download_failed'):
            media_type = media_type_info.get('media_type', 'media')
            media_type_name = {
                'photo': '图片',
                'video': '视频',
                'document': '文件',
                'animation': '动图',
                'audio': '音频',
                'sticker': '贴纸'
            }.get(media_type, '媒体')
            
            # 返回占位符标识，前端可以识别并显示
            return f"placeholder:{media_type_name}下载失败"
        
        return None
    
    async def _check_duplicate_with_details(self, save_data: dict, channel_id: str) -> Optional[dict]:
        """检查是否重复并返回详细信息"""
        try:
            # 提取视觉哈希（如果有）
            visual_hashes = None
            media_info = save_data.get('media_info')
            if media_info and media_info.get('visual_hashes'):
                visual_hashes = media_info['visual_hashes']
            else:
                # 兼容旧格式
                try:
                    import json
                    if save_data.get('visual_hash'):
                        visual_hashes = json.loads(save_data['visual_hash'])
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
                return {
                    'is_duplicate': True,
                    'original_id': orig_id,
                    'type': dup_type,
                    'reason': f"{dup_type}重复"
                }
                
            return None
            
        except Exception as e:
            logger.error(f"重复检测失败: {e}")
            return None
    
    async def _is_duplicate(self, save_data: dict, channel_id: str) -> bool:
        """检查是否为重复消息"""
        try:
            # 解析视觉哈希
            visual_hashes = None
            if save_data.get('visual_hash'):
                try:
                    # 解析JSON格式的visual_hash
                    import json
                    visual_hashes = json.loads(save_data['visual_hash'])
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
    
    async def _should_forward_to_review(self, is_history: bool) -> bool:
        """
        检查是否应该转发消息到审核群
        
        Args:
            is_history: 是否为历史消息
            
        Returns:
            是否应该转发到审核群
        """
        try:
            from app.services.config_manager import config_manager
            
            # 获取配置：是否启用审核群转发
            enable_review = await config_manager.get_config('review.enable_forward_to_group')
            if enable_review is False:
                return False
            
            # 对于实时消息，默认转发
            if not is_history:
                return True
            
            # 对于历史消息，检查专门的配置
            forward_history = await config_manager.get_config('review.forward_history_messages')
            return forward_history if forward_history is not None else False
            
        except Exception as e:
            logger.error(f"检查转发配置失败: {e}")
            # 出错时的默认行为：实时消息转发，历史消息不转发
            return not is_history
    
    async def _should_forward_history(self) -> bool:
        """检查是否应该转发历史消息到审核群（保留兼容性）"""
        return await self._should_forward_to_review(is_history=True)
    
    async def _forward_to_review(self, message_data: Dict):
        """转发消息到审核群"""
        try:
            # 延迟导入避免循环引用
            from app.telegram.message_forwarder import message_forwarder
            from app.telegram.bot import telegram_bot
            
            if telegram_bot and telegram_bot.client:
                # 创建临时的消息对象以兼容原有转发逻辑
                from app.services.duplicate_detector import MessageCompat
                temp_message = MessageCompat(message_data)
                temp_message.id = message_data.get('message_id')
                temp_message.source_channel = message_data.get('source_channel')
                temp_message.content = message_data.get('content')
                temp_message.filtered_content = message_data.get('filtered_content')
                temp_message.media_type = message_data.get('media_type')
                temp_message.media_url = message_data.get('media_url')
                temp_message.is_ad = message_data.get('is_ad')
                temp_message.status = message_data.get('status')
                
                await message_forwarder.forward_to_review(telegram_bot.client, temp_message)
            else:
                logger.warning("Telegram客户端未连接，无法转发到审核群")
                
        except Exception as e:
            logger.error(f"转发到审核群失败: {e}")
    
    def _should_reject_pure_ad(self, is_ad: bool, filter_reason: str, filtered_content: str, 
                              content: str, media_info: dict, ocr_result: dict) -> Tuple[bool, str]:
        """
        判断是否应该完全拒绝纯广告消息
        
        Args:
            is_ad: 是否被判定为广告
            filter_reason: 过滤原因
            filtered_content: 过滤后的内容
            content: 原始内容
            media_info: 媒体信息
            ocr_result: OCR识别结果
            
        Returns:
            (是否拒绝, 拒绝原因)
        """
        import re
        
        # 高危广告关键词（赌博、色情、诈骗）
        HIGH_RISK_AD_KEYWORDS = [
            # 赌博平台相关
            r'(?:铂莱|博莱|Y3|AG|BBIN).*(?:娱乐|娛樂|国际|國際|平台)',
            r'(?:USDT|泰达币|虚拟币|加密货币).*(?:娱乐城|娛樂城|平台|充值|提款)',
            r'(?:博彩|赌场|賭場|棋牌|体育|體育|真人|电子).*(?:平台|官网|官網|娱乐城)',
            r'(?:首充|首存|二存|三存).*(?:返水|优惠|優惠|赠送|贈送)',
            r'(?:日出|日入|月入|日赚|日賺).*[0-9]+.*[万萬uU]',
            r'(?:实力|實力|信誉|信譽).*(?:U盘|U盤|USDT|出款)',
            r'(?:千万|千萬|巨款|巨额|大额).*(?:无忧|無憂|秒到|提款)',
            r'777.*(?:老虎机|老虎機|slots|游戏|遊戲)',
            
            # 色情相关
            r'(?:上线|上線).*(?:福利|八大|妹妹)',
            r'(?:永久|免费|免費).*(?:送|领取|領取|看片)',
            r'(?:幸运|幸運).*(?:单|單).*(?:奖|獎)',
            
            # 诈骗相关
            r'(?:一个月|一個月).*(?:奔驰|奔馳|宝马|寶馬)',
            r'(?:三个月|三個月).*(?:套房|房子)',
            r'(?:汽车|汽車).*(?:违停|違停).*(?:拍照|一张|一張).*[0-9]+',
            r'(?:想功成名就|胆子大|膽子大).*(?:灰色|看我)',
            
            # 特定平台标识
            r'(?:官方|客服).*(?:QQ|qq|微信|WeChat|wechat).*[0-9]+',
            r'(?:注册|註冊|登录|登錄).*(?:就送|即送|立即送)',
        ]
        
        # 提取OCR文字内容
        ocr_texts = []
        if ocr_result:
            # 从OCR结果中提取所有文字
            if ocr_result.get('texts'):
                ocr_texts.extend(ocr_result['texts'])
            
            # 从二维码中提取文字内容  
            if ocr_result.get('qr_codes'):
                for qr in ocr_result['qr_codes']:
                    if qr.get('data'):
                        ocr_texts.append(qr['data'])
        
        # 合并所有需要检查的文本
        all_text_to_check = content
        if ocr_texts:
            all_text_to_check += " " + " ".join(ocr_texts)
        
        # 优先级1：OCR检测到高分广告内容 - 直接拒绝
        if ocr_result and ocr_result.get('ad_score', 0) >= 50:
            return True, f"图片广告内容自动拒绝（OCR分数:{ocr_result.get('ad_score', 0)}）"
        
        # 优先级2：检查是否包含高危赌博关键词
        for pattern in HIGH_RISK_AD_KEYWORDS:
            if re.search(pattern, all_text_to_check, re.IGNORECASE):
                # 如果还有媒体文件，更严格
                if media_info:
                    return True, "高风险广告自动拒绝（赌博/色情/诈骗+媒体）"
                # 仅文字也可能拒绝
                elif len(filtered_content.strip()) < 20:  # 过滤后内容很少
                    return True, "高风险广告自动拒绝（赌博/色情/诈骗内容）"
        
        # 优先级3：纯媒体消息且OCR检测到广告
        if not content.strip() and media_info and ocr_result:
            if ocr_result.get('ad_score', 0) >= 30:
                return True, "纯媒体广告自动拒绝（无文字内容，OCR检测为广告）"
        
        # 优先级4：文本被完全过滤且有媒体
        if not filtered_content.strip() and media_info:
            # 如果OCR也检测到广告内容
            if ocr_result and ocr_result.get('ad_score', 0) >= 30:
                return True, "纯广告媒体自动拒绝（文字+媒体都是广告）"
            
            # 如果原文本过滤掉了超过95%的内容
            if len(content) > 10 and len(filtered_content) < len(content) * 0.05:
                return True, "疑似纯广告自动拒绝（文本过滤超95%）"
        
        # 优先级5：整条消息都是广告文本的处理
        if "整条消息都是广告" in filter_reason or "高风险广告" in filter_reason:
            # 没有媒体的纯文字广告，直接拒绝
            if not media_info:
                return True, "纯文字广告自动拒绝"
            # 有媒体且OCR也是广告，拒绝
            elif ocr_result and ocr_result.get('ad_score', 0) >= 30:
                return True, "纯广告消息自动拒绝（文字+媒体都是广告）"
        
        return False, ""
    
    async def _broadcast_new_message(self, message_data: Dict):
        """广播新消息到WebSocket客户端"""
        try:
            # 直接使用websocket_manager，避免依赖telegram_bot
            from app.api.websocket import websocket_manager
            
            # 准备广播数据（确保包含所有必要字段）
            broadcast_data = {
                "id": message_data.get('message_id'),  # 使用message_id作为唯一标识
                "message_id": message_data.get('message_id'),
                "source_channel": message_data.get('source_channel'),
                "content": message_data.get('content'),
                "filtered_content": message_data.get('filtered_content'),
                "media_type": message_data.get('media_type'),
                "media_url": message_data.get('media_url'),
                "is_ad": message_data.get('is_ad'),
                "status": message_data.get('status'),
                "created_at": message_data.get('created_at'),
                "is_combined": message_data.get('is_combined'),
                "media_group": message_data.get('media_group') if message_data.get('is_combined') else None,
                "combined_messages": message_data.get('combined_messages') if message_data.get('is_combined') else None
            }
            
            # 广播消息
            await websocket_manager.broadcast_new_message(broadcast_data)
            msg_id = message_data.get('message_id', 'N/A')
            logger.info(f"✅ 成功广播新消息 ID:{msg_id} 到 {len(websocket_manager.active_connections)} 个WebSocket连接")
            
        except ImportError as e:
            logger.error(f"导入WebSocket管理器失败: {e}")
        except Exception as e:
            logger.error(f"广播消息失败: {e}")

# 导入hashlib（用于组合媒体哈希）
import hashlib

# 全局实例
unified_processor = UnifiedMessageProcessor()