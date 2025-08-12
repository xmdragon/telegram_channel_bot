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
            # 步骤1: 首先提取原始内容并保存
            original_content = await self._extract_original_content(message)
            
            # 步骤2: 通用处理（提取内容、下载媒体、过滤广告）
            processed_data = await self._common_message_processing(message, channel_id, is_history)
            if not processed_data:
                return None  # 消息被过滤
            
            # 确保原始内容被保留
            processed_data['original_content'] = original_content
            
            # 步骤3: 组合消息检测
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
            
            # 步骤4: 准备保存数据
            save_data = await self._prepare_save_data(
                combined_message, 
                channel_id, 
                processed_data,
                is_history
            )
            
            # 步骤5: 去重检测
            duplicate_info = await self._check_duplicate_with_details(save_data, channel_id)
            if duplicate_info:
                logger.info(f"{'历史' if is_history else '实时'}消息被去重检测拒绝: {duplicate_info['reason']}")
                # 保存被去重拒绝的消息到数据库，状态为rejected
                save_data['status'] = 'rejected'
                save_data['reject_reason'] = f"去重检测: {duplicate_info['reason']} (原消息ID: {duplicate_info.get('original_id', 'N/A')})"
                save_data['filter_reason'] = duplicate_info['reason']
                
                # 保存到数据库
                db_message = await self.message_processor.process_new_message(save_data)
                if db_message:
                    logger.info(f"去重拒绝的消息已保存到数据库，ID: {db_message.id}")
                
                # 清理媒体文件（如果不想保留的话）
                # await self._cleanup_media_files(save_data)
                return db_message
            
            # 步骤6: 保存到数据库
            db_message = await self.message_processor.process_new_message(save_data)
            
            if not db_message:
                logger.info(f"消息保存失败或被拒绝")
                await self._cleanup_media_files(save_data)
                return None
            
            # 步骤7: 转发到审核群（根据配置决定）
            if await self._should_forward_to_review(is_history):
                await self._forward_to_review(db_message)
            
            # 步骤8: 广播到WebSocket（所有新消息都广播，让web端能看到）
            # 不再区分是否历史消息，所有成功保存的消息都广播到web端
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
            if message.media:
                media_info = await self._process_media(message, channel_id)
            
            # 准备媒体文件列表用于OCR处理
            media_files = []
            if media_info and media_info.get('file_path'):
                media_files.append(media_info['file_path'])
            
            # 提取消息实体（包括隐藏链接）
            from app.services.structural_ad_detector import structural_detector
            entities = structural_detector.extract_entity_data(message)
            
            # 移除隐藏链接（根据配置）
            removed_hidden_links = []
            from app.services.config_manager import config_manager
            hidden_link_action = await config_manager.get_config('filter.hidden_link_action')
            if hidden_link_action == 'remove' or hidden_link_action is None:  # 默认移除
                clean_entities, removed_hidden_links = structural_detector.remove_hidden_links(message)
                if removed_hidden_links:
                    logger.info(f"🔗 移除了 {len(removed_hidden_links)} 个隐藏链接")
            
            # 内容过滤（智能去尾部 + 结构化广告检测 + AI广告检测 + OCR图片文字提取）
            is_ad, filtered_content, filter_reason, ocr_result = await self.content_filter.filter_message(
                content, 
                channel_id=channel_id,
                message_obj=message,  # 传递消息对象用于结构化检测
                media_files=media_files  # 传递媒体文件用于OCR处理
            )
            
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
                    # 清理媒体文件
                    if media_info and media_info.get('file_path'):
                        await media_handler.cleanup_file(media_info['file_path'])
                    return None
                
                # 如果配置了自动过滤广告，直接返回None
                if await db_settings.get_auto_filter_ads():
                    logger.info(f"自动过滤广告消息")
                    if media_info and media_info.get('file_path'):
                        await media_handler.cleanup_file(media_info['file_path'])
                    return None
            
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
                'ocr_result': ocr_result,  # 包含OCR提取结果
                'entities': entities,  # 所有实体信息
                'removed_hidden_links': removed_hidden_links  # 被移除的隐藏链接
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
            'media_type': message_data.get('media_type'),
            'media_url': message_data.get('media_url'),
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
        
        # 高危广告关键词
        HIGH_RISK_AD_KEYWORDS = [
            # 赌博相关
            r'[Yy]3.*(?:娱乐|娛樂|国际|國際)',
            r'(?:USDT|泰达币|虚拟币).*(?:娱乐城|娛樂城|平台)',
            r'(?:博彩|赌场|賭場|棋牌|体育|體育).*(?:平台|官网|官網)',
            r'(?:首充|首存).*(?:返水|优惠|優惠)',
            r'(?:日出|日入).*[0-9]+.*[uU]',
            r'(?:实力|實力).*(?:U盘|U盤|USDT)',
            r'(?:千万|千萬|巨款).*(?:无忧|無憂)',
            
            # 色情相关
            r'(?:上线|上線).*(?:福利|八大)',
            r'(?:永久|免费|免費).*(?:送|领取|領取)',
            r'(?:幸运|幸運).*(?:单|單).*(?:奖|獎)',
            
            # 诈骗相关
            r'(?:一个月|一個月).*(?:奔驰|奔馳|宝马|寶馬)',
            r'(?:三个月|三個月).*(?:套房|房子)',
            r'(?:汽车|汽車).*(?:违停|違停).*(?:拍照|一张|一張).*[0-9]+',
            r'(?:想功成名就|胆子大|膽子大).*(?:灰色|看我)',
        ]
        
        # 情况1：整条消息都是广告文本
        if "整条消息都是广告" in filter_reason:
            # 检查是否包含高危关键词
            for pattern in HIGH_RISK_AD_KEYWORDS:
                if re.search(pattern, content, re.IGNORECASE):
                    return True, "高风险纯广告（赌博/色情/诈骗）"
            
            # 如果有媒体文件
            if media_info:
                # 如果OCR结果显示媒体也包含广告内容
                if ocr_result and ocr_result.get('ad_score', 0) > 0.5:
                    return True, "纯广告消息（文本+媒体都是广告）"
                
                # 如果OCR提取到了类似的广告文字
                if ocr_result and ocr_result.get('ocr_text'):
                    ocr_text = ocr_result.get('ocr_text', '')
                    # 检查OCR文字是否包含高危关键词
                    for pattern in HIGH_RISK_AD_KEYWORDS:
                        if re.search(pattern, ocr_text, re.IGNORECASE):
                            return True, "纯广告消息（媒体含高危广告内容）"
            else:
                # 没有媒体，纯广告文本，直接拒绝
                return True, "纯广告文本（无媒体）"
        
        # 情况2：文本被完全过滤且有媒体
        if not filtered_content.strip() and media_info:
            # 检查原文本是否包含高危关键词
            for pattern in HIGH_RISK_AD_KEYWORDS:
                if re.search(pattern, content, re.IGNORECASE):
                    return True, "高风险广告媒体（文本含高危内容）"
            
            # 检查OCR结果
            if ocr_result:
                # 高广告分数
                if ocr_result.get('ad_score', 0) > 0.7:
                    return True, "纯广告媒体（OCR检测高分）"
                
                # OCR文字包含高危关键词
                ocr_text = ocr_result.get('ocr_text', '')
                if ocr_text:
                    for pattern in HIGH_RISK_AD_KEYWORDS:
                        if re.search(pattern, ocr_text, re.IGNORECASE):
                            return True, "纯广告媒体（OCR含高危内容）"
            
            # 如果文本过滤掉了超过90%的内容，也视为纯广告
            if len(content) > 0 and len(filtered_content) < len(content) * 0.1:
                return True, "疑似纯广告（文本过滤超90%）"
        
        return False, ""
    
    async def _broadcast_new_message(self, db_message: Message):
        """广播新消息到WebSocket客户端"""
        try:
            # 直接使用websocket_manager，避免依赖telegram_bot
            from app.api.websocket import websocket_manager
            
            # 准备消息数据（确保包含所有必要字段）
            message_data = {
                "id": db_message.id,
                "message_id": db_message.message_id,  # 添加message_id字段
                "source_channel": db_message.source_channel,
                "content": db_message.content,
                "filtered_content": db_message.filtered_content,
                "media_type": db_message.media_type,
                "media_url": db_message.media_url,
                "is_ad": db_message.is_ad,
                "status": db_message.status,
                "created_at": format_for_api(db_message.created_at),
                "is_combined": db_message.is_combined,
                "media_group": db_message.media_group if db_message.is_combined else None,
                "combined_messages": db_message.combined_messages if db_message.is_combined else None
            }
            
            # 广播消息
            await websocket_manager.broadcast_new_message(message_data)
            logger.info(f"✅ 成功广播新消息 ID:{db_message.id} 到 {len(websocket_manager.active_connections)} 个WebSocket连接")
            
        except ImportError as e:
            logger.error(f"导入WebSocket管理器失败: {e}")
        except Exception as e:
            logger.error(f"广播消息失败: {e}")

# 导入hashlib（用于组合媒体哈希）
import hashlib

# 全局实例
unified_processor = UnifiedMessageProcessor()