"""
消息组合处理器 - 处理Telegram的消息组合功能
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from app.utils.timezone import get_current_time
from app.storage.redis_manager import redis_manager

logger = logging.getLogger(__name__)

class MessageGrouper:
    """消息组合处理器"""
    
    def __init__(self):
        self.processed_groups: Dict[str, str] = {}  # 已处理的组合消息ID {grouped_id: combined_message_id}
        self.telegram_client = None  # Telegram客户端，用于主动获取完整组
        self.completed_groups: Dict[str, Dict] = {}  # 已完成处理的组合消息数据
        self.group_locks: Dict[str, asyncio.Lock] = {}  # 组合消息并发锁 {group_key: lock}
    
    def _deduplicate_content(self, texts: List[str]) -> List[str]:
        """去重文本内容 - 移除重复的段落"""
        if not texts:
            return texts
        
        # 如果只有一条消息，检查内容是否内部重复
        if len(texts) == 1:
            content = texts[0].strip()
            if not content:
                return texts
            
            # 检查是否整体重复（被双换行分割成相等的两半）
            parts = content.split('\n\n')
            
            # 情况1: 简单的两部分重复
            if len(parts) == 2 and parts[0].strip() == parts[1].strip():
                logger.warning(f"检测到单条消息内部重复(简单两部分)，移除重复部分: {len(parts[0])}字符")
                return [parts[0].strip()]
            
            # 情况2: 复杂重复 - 检查是否前一半和后一半相同
            elif len(parts) > 2 and len(parts) % 2 == 0:
                mid = len(parts) // 2
                first_half = '\n\n'.join(parts[:mid])
                second_half = '\n\n'.join(parts[mid:])
                
                if first_half.strip() == second_half.strip():
                    logger.warning(f"检测到单条消息内部重复(复杂模式)，移除重复部分: {len(first_half)}字符")
                    return [first_half.strip()]
            
            return texts
        
        # 多条消息去重
        unique_texts = []
        seen_content = set()
        
        for text in texts:
            text_stripped = text.strip()
            if text_stripped and text_stripped not in seen_content:
                unique_texts.append(text)
                seen_content.add(text_stripped)
            elif text_stripped in seen_content:
                logger.debug(f"跳过重复内容: {len(text_stripped)}字符")
        
        return unique_texts
    
    async def process_message(self, message, channel_id: str, media_info: Optional[Dict] = None, filtered_content: Optional[str] = None, is_ad: bool = False, is_batch: bool = False) -> Optional[Dict]:
        """
        处理消息，检查是否需要与其他消息组合
        返回完整的组合消息或None（如果消息还在等待组合）
        
        Args:
            is_batch: 是否为批量处理模式（如历史消息采集），批量模式下会立即处理完整个组
        """
        try:
            # 提取消息基本信息
            # 🔧 修复：改进文本内容提取，确保不丢失caption
            original_content = ""
            
            # 1. 优先使用传入的filtered_content（来自上游处理器）
            if filtered_content is not None and filtered_content.strip():
                original_content = filtered_content
                logger.debug(f"使用上游过滤后内容: {len(original_content)}字符")
            else:
                # 2. 如果没有传入有效的filtered_content，直接从消息提取
                # 按Telegram官方优先级提取，与message_receiver.py保持一致
                # 不拼接多个字段，避免重复 - 修复消息#2261重复显示问题
                # 优先级：message → raw_text → text → caption
                if hasattr(message, 'message') and message.message:
                    original_content = message.message.strip()
                    logger.debug(f"组合器使用message字段: {len(original_content)}字符")
                elif hasattr(message, 'raw_text') and message.raw_text:
                    original_content = message.raw_text.strip()
                    logger.debug(f"组合器使用raw_text字段: {len(original_content)}字符")
                elif hasattr(message, 'text') and message.text:
                    original_content = message.text.strip()
                    logger.debug(f"组合器使用text字段: {len(original_content)}字符")
                elif hasattr(message, 'caption') and message.caption:
                    original_content = message.caption.strip()
                    logger.debug(f"组合器使用caption字段: {len(original_content)}字符")
                else:
                    original_content = ""
                    logger.debug("组合器未找到有效文本内容")
                
                logger.debug(f"组合器提取原始内容: {len(original_content)}字符")
            
            message_data = {
                'message_id': message.id,
                'content': original_content,  # 使用提取或传入的内容
                'filtered_content': await self._ensure_filtered_content(original_content, filtered_content),
                'is_ad': is_ad,
                'media_info': media_info,
                'date': message.date or get_current_time(),
                'grouped_id': str(getattr(message, 'grouped_id', None)) if getattr(message, 'grouped_id', None) else None
            }
            
            # 如果没有grouped_id，说明是独立消息
            if not message_data['grouped_id']:
                return await self._create_single_message(message_data, channel_id)
            
            # 有grouped_id，使用主动获取完整组
            return await self._handle_grouped_message_active(message_data, channel_id, is_batch)
            
        except Exception as e:
            logger.error(f"处理消息组合时出错: {e}")
            # 出错时返回单独消息
            fallback_content = ""
            if filtered_content is not None:
                fallback_content = filtered_content
            elif hasattr(message, 'message') and message.message:
                fallback_content = message.message
            elif hasattr(message, 'raw_text') and message.raw_text:
                fallback_content = message.raw_text
            elif hasattr(message, 'text') and message.text:
                fallback_content = message.text
            elif hasattr(message, 'caption') and message.caption:
                fallback_content = message.caption
            
            return await self._create_single_message(message_data if 'message_data' in locals() else {
                'message_id': message.id,
                'content': fallback_content,
                'filtered_content': filtered_content,
                'is_ad': is_ad,
                'media_info': media_info,
                'date': message.date or get_current_time(),
                'grouped_id': None
            }, channel_id)
    
    async def _create_single_message(self, message_data: Dict, channel_id: str) -> Dict:
        """创建单独消息"""
        # 如果有媒体信息，转换为web可访问URL
        media_url = None
        if message_data.get('media_info') and message_data['media_info'].get('file_path'):
            from app.services.media_handler import media_handler
            media_url = await media_handler.get_media_url(message_data['media_info']['file_path'])
        
        return {
            'message_id': message_data['message_id'],
            'content': message_data.get('content', ''),
            'filtered_content': message_data.get('filtered_content', message_data.get('content', '')),
            'is_ad': message_data.get('is_ad', False),
            'media_type': message_data['media_info']['media_type'] if message_data.get('media_info') else None,
            'media_url': media_url,
            'grouped_id': str(message_data.get('grouped_id')) if message_data.get('grouped_id') else None,
            'is_combined': False,
            'combined_messages': None,
            'media_group': None,
            'date': message_data.get('date', get_current_time())
        }
    
    async def _handle_grouped_message_active(self, message_data: Dict, channel_id: str, is_batch: bool = False) -> Optional[Dict]:
        """主动获取完整消息组处理 - 并发安全版本"""
        grouped_id = str(message_data['grouped_id']) if message_data.get('grouped_id') else None
        if not grouped_id:
            return await self._create_single_message(message_data, channel_id)
            
        group_key = f"{channel_id}_{grouped_id}"
        
        # 🔧 并发控制：获取或创建该组的专用锁
        if group_key not in self.group_locks:
            self.group_locks[group_key] = asyncio.Lock()
        
        # 使用专用锁确保同一组只被处理一次
        async with self.group_locks[group_key]:
            # 再次检查是否已经处理过这个消息组（双重检查锁定模式）
            if group_key in self.processed_groups:
                logger.debug(f"消息组 {grouped_id} 已被标记为已处理，跳过")
                return None
                
            existing_combined = await self._get_existing_combined_message(channel_id, grouped_id)
            if existing_combined:
                logger.debug(f"消息组 {grouped_id} 已存在，跳过处理")
                # 标记为已处理，避免后续检查
                self.processed_groups[group_key] = str(existing_combined.get('message_id', 'existing'))
                return None
            
            # 标记为正在处理，避免重复处理
            self.processed_groups[group_key] = "processing"
            
            try:
                # 直接获取完整组 - 不要猜测，直接获取完整数据
                complete_group = await self._fetch_complete_group(channel_id, grouped_id, message_data['message_id'])
                
                if not complete_group:
                    logger.warning(f"无法获取完整消息组 {grouped_id}，作为单独消息处理")
                    del self.processed_groups[group_key]
                    return await self._create_single_message(message_data, channel_id)
                
                # 立即处理完整组
                combined_message = await self._create_combined_message(complete_group, channel_id)
                processed_data = await self._save_combined_message(combined_message, channel_id)
                
                if processed_data:
                    self.completed_groups[group_key] = processed_data
                    self.processed_groups[group_key] = processed_data['message_id']
                    
                    # 保存到Redis - 增加错误处理
                    await self._save_to_redis_safe(processed_data, combined_message, channel_id)
                    
                    logger.info(f"✅ 处理完成：消息组 {grouped_id} 包含 {len(complete_group)} 条消息")
                    return processed_data
                else:
                    logger.error(f"处理组合消息数据失败: {group_key}")
                    del self.processed_groups[group_key]
                    return None
                    
            except Exception as e:
                logger.error(f"主动获取消息组失败 {group_key}: {e}")
                if group_key in self.processed_groups:
                    del self.processed_groups[group_key]
                return await self._create_single_message(message_data, channel_id)
    
    async def _fetch_complete_group(self, channel_id: str, grouped_id: str, sample_message_id: int) -> List[Dict]:
        """获取完整消息组 - 不要猜测，直接获取完整数据"""
        try:
            # 检查客户端状态（可能由bot_manager设置，也可能需要自己初始化）
            if not self.telegram_client:
                logger.info(f"📱 组合器客户端未设置，尝试自行初始化: grouped_id={grouped_id}")
                await self._init_telegram_client()
                
            if not self.telegram_client:
                logger.error(f"❌ Telegram客户端初始化失败，组合消息将拆分处理: grouped_id={grouped_id}")
                return None
            
            # 验证客户端连接状态
            try:
                if not self.telegram_client.is_connected():
                    logger.warning("Telegram客户端未连接，尝试重新连接")
                    await self.telegram_client.connect()
            except Exception as conn_e:
                logger.error(f"Telegram客户端连接检查失败: {conn_e}")
                return None
            
            # 使用sample_message_id作为参考点，获取周围的消息
            # Telegram媒体组通常在相近的ID范围内
            start_id = max(1, sample_message_id - 20)
            end_id = sample_message_id + 20
            
            # 从配置中获取频道用户名
            from app.storage.json_store import get_json_channel_store
            channel_store = get_json_channel_store()
            
            channel_username = None
            # 直接通过channel_id获取频道信息
            channel_info = channel_store.get_channel(channel_id)
            if channel_info:
                username = channel_info.get('username') or ''
                if username and username.startswith('@'):
                    channel_username = username[1:]  # 移除@前缀
                elif username:
                    channel_username = username
            
            if not channel_username:
                # 统一配置读取：从配置文件动态获取所有频道映射
                try:
                    all_channels = channel_store.get_all_channels()
                    for ch in all_channels:
                        if str(ch.get('channel_id')) == str(channel_id):
                            ch_name = ch.get('channel_name', '')
                            if ch_name:
                                # 处理各种格式：@username, username, https://t.me/username
                                if ch_name.startswith('@'):
                                    channel_username = ch_name[1:]
                                elif ch_name.startswith('https://t.me/'):
                                    channel_username = ch_name.replace('https://t.me/', '')
                                else:
                                    channel_username = ch_name
                                break
                    
                    if channel_username:
                        logger.info(f"✅ 从配置文件获取频道映射: {channel_id} -> {channel_username}")
                except Exception as e:
                    logger.warning(f"从配置读取频道映射失败: {e}")
                    channel_username = None
                
                if not channel_username:
                    logger.error(f"无法找到频道 {channel_id} 的用户名")
                    return None
                    
                logger.info(f"使用已知频道映射: {channel_id} -> {channel_username}")
            
            # 获取附近的消息
            nearby_messages = await self.telegram_client.get_messages(
                channel_username,
                min_id=start_id,
                max_id=end_id,
                limit=100
            )
            
            if not nearby_messages:
                logger.warning(f"⚠️ 未获取到附近消息: {channel_username}:{start_id}-{end_id} | grouped_id={grouped_id}")
                return None
            
            logger.debug(f"🔍 搜索范围: {channel_username}:{start_id}-{end_id}, 获取到 {len(nearby_messages)} 条消息")
            
            # 过滤出同一组的消息
            group_messages = []
            for msg in nearby_messages:
                if hasattr(msg, 'grouped_id') and str(msg.grouped_id) == grouped_id:
                    group_messages.append(msg)
                    logger.debug(f"✓ 找到组消息: #{msg.id} (grouped_id: {msg.grouped_id})")
            
            if not group_messages:
                logger.error(f"❌ 未找到任何组合消息: grouped_id={grouped_id} | 搜索范围: {start_id}-{end_id} | 频道: {channel_username}")
                # 输出调试信息
                logger.debug(f"调试信息: 附近消息ID列表: {[msg.id for msg in nearby_messages[:10]]}")
                grouped_ids = [str(msg.grouped_id) for msg in nearby_messages if hasattr(msg, 'grouped_id') and msg.grouped_id]
                if grouped_ids:
                    logger.debug(f"调试信息: 发现的其他grouped_id: {list(set(grouped_ids))}")
                return None
            
            # 按ID排序
            group_messages.sort(key=lambda x: x.id)
            
            logger.info(f"🎯 获取成功: grouped_id={grouped_id} 找到 {len(group_messages)} 条消息")
            
            # 转换为内部格式，包含媒体下载
            converted_messages = []
            for msg in group_messages:
                converted_msg = await self._convert_telegram_message(msg, channel_id)
                if converted_msg:
                    converted_messages.append(converted_msg)
            
            return converted_messages
            
        except Exception as e:
            logger.error(f"获取完整消息组失败: {e}")
            return None
    
    async def _init_telegram_client(self):
        """初始化Telegram客户端（后备方案，优先使用由bot_manager设置的客户端）"""
        try:
            # 检查是否已经由外部（bot_manager）设置了客户端
            if self.telegram_client:
                logger.debug("✅ 使用外部设置的Telegram客户端")
                return
            
            logger.warning("⚠️ 使用后备方案初始化独立的Telegram客户端")
            
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            import json
            import os
            
            # 从配置文件读取Telegram设置
            config_file = os.path.join(os.path.dirname(__file__), '../../data/config/system.json')
            if not os.path.exists(config_file):
                logger.error("配置文件不存在，无法初始化客户端")
                return
                
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            api_id = int(config_data.get('telegram.api_id', {}).get('value', '0'))
            api_hash = config_data.get('telegram.api_hash', {}).get('value', '')
            session_string = config_data.get('telegram.listener_session', {}).get('value', '')
            
            if not api_id or not api_hash or not session_string:
                logger.error("🔧 Telegram配置不完整，无法初始化独立客户端。请确保bot_manager正确设置了message_grouper的客户端")
                return
            
            logger.info(f"🔄 创建独立Telegram客户端连接...")
            self.telegram_client = TelegramClient(
                StringSession(session_string),
                api_id,
                api_hash,
                connection_retries=3,
                retry_delay=2,
                auto_reconnect=True
            )
            
            await self.telegram_client.connect()
            
            if not await self.telegram_client.is_user_authorized():
                logger.error("❌ Telegram会话未授权，无法处理组合消息")
                self.telegram_client = None
                return
            
            logger.info("✅ 独立Telegram客户端初始化成功（不推荐，建议使用共享客户端）")
            
        except Exception as e:
            logger.error(f"❌ 初始化独立Telegram客户端失败: {e}")
            self.telegram_client = None
    
    async def _convert_telegram_message(self, telegram_msg, channel_id: str) -> Optional[Dict]:
        """将Telegram消息转换为内部格式，包含媒体下载"""
        try:
            # 提取文本内容
            content = ""
            if hasattr(telegram_msg, 'message') and telegram_msg.message:
                content = telegram_msg.message.strip()
            elif hasattr(telegram_msg, 'raw_text') and telegram_msg.raw_text:
                content = telegram_msg.raw_text.strip()
            elif hasattr(telegram_msg, 'text') and telegram_msg.text:
                content = telegram_msg.text.strip()
            elif hasattr(telegram_msg, 'caption') and telegram_msg.caption:
                content = telegram_msg.caption.strip()
            
            # 下载或获取媒体信息（不再硬编码None）
            media_info = None
            if telegram_msg.media:
                from app.services.media_manager import media_manager
                media_info = await media_manager.get_or_download_media(
                    telegram_msg.id, 
                    telegram_msg, 
                    channel_id
                )
                
                if not media_info:
                    # 如果媒体下载失败，创建基本信息结构
                    media_info = {
                        'media_type': 'photo' if hasattr(telegram_msg.media, 'photo') else 'document',
                        'file_path': None,
                        'file_size': 0,
                        'mime_type': getattr(telegram_msg.media, 'mime_type', 'unknown'),
                        'download_failed': True,
                        'error': '媒体下载失败'
                    }
            
            return {
                'message_id': telegram_msg.id,
                'content': content,
                'filtered_content': content,  # 稍后会被过滤
                'is_ad': False,  # 稍后会被检测
                'media_info': media_info,
                'date': telegram_msg.date or get_current_time(),
                'grouped_id': str(telegram_msg.grouped_id) if telegram_msg.grouped_id else None
            }
            
        except Exception as e:
            logger.error(f"转换Telegram消息失败: {e}")
            return None
    
    async def _save_to_redis(self, processed_data: Dict, combined_message: Dict, channel_id: str):
        """保存组合消息到Redis"""
        try:
            from app.services.message_processor import MessageProcessor
            processor = MessageProcessor()
            
            # 检查是否需要人工审核
            from app.services.config_manager import config_manager
            require_approval = await config_manager.get_config('review.require_approval', True)
            
            # 准备保存数据
            save_data = {
                'source_channel': channel_id,
                'message_id': processed_data['message_id'],
                'content': processed_data['content'],
                'filtered_content': processed_data.get('filtered_content'),
                'media_hash': processed_data.get('combined_media_hash'),
                'visual_hash': processed_data.get('visual_hash'),
                'grouped_id': processed_data.get('grouped_id'),
                'is_combined': True,
                'status': 'pending' if require_approval else 'approved',
                'is_ad': processed_data.get('is_ad', False),
                'combined_messages': processed_data.get('combined_messages'),
                'media_group': processed_data.get('media_group'),
                'created_at': processed_data.get('date', combined_message.get('date'))
            }
            
            if not require_approval:
                logger.info(f"人工审核已关闭，组合消息 {channel_id}:{processed_data['message_id']} 自动批准")
            
            # 保存到Redis - ：提供详细失败原因
            try:
                logger.debug(f"🔄 准备保存组合消息: {channel_id}:{processed_data['message_id']}")
                logger.debug(f"保存数据详情: {save_data}")
                
                saved_message = await processor.process_new_message(save_data)
                if saved_message:
                    logger.info(f"✅ 组合消息已保存到Redis: {channel_id}:{processed_data['message_id']}")
                    
                    # 如果组合消息已自动批准（人工审核关闭），等待scheduler自动转发
                    if saved_message.get('status') == 'approved':
                        message_id_str = f"{channel_id}:{processed_data['message_id']}"
                        logger.info(f"人工审核已关闭，组合消息 {message_id_str} 保持approved状态，等待自动转发")
                    
                    # 通知前端组合消息已创建
                    await self._notify_combined_message_created(saved_message)
                else:
                    # 获取详细失败原因 - 减少重复日志
                    failure_count = getattr(self, '_failure_count', 0)
                    self._failure_count = failure_count + 1
                    
                    # 只在前5次失败时记录详细错误，避免日志泛滥
                    if failure_count < 5:
                        from app.storage.redis_manager import redis_manager
                        if redis_manager is None:
                            failure_reason = "Redis存储未初始化"
                        else:
                            # 检查具体可能的原因
                            try:
                                redis_manager.ping()
                                # 检查数据有效性
                                if not save_data.get('content'):
                                    failure_reason = "消息内容为空"
                                elif len(save_data.get('content', '')) < 10:
                                    failure_reason = "消息内容过短，可能被过度过滤"
                                else:
                                    failure_reason = "消息处理器返回None - 可能数据格式不匹配或过滤条件不满足"
                            except Exception as redis_error:
                                failure_reason = f"Redis连接失败: {redis_error}"
                        
                        logger.error(f"❌ 组合消息保存失败: {channel_id}:{processed_data['message_id']} - 原因: {failure_reason}")
                        logger.error(f"保存数据概况: content={len(save_data.get('content', ''))}字符, "
                                   f"status={save_data.get('status')}, "
                                   f"media={bool(save_data.get('media_hash'))}")
                    elif failure_count == 5:
                        logger.warning(f"⚠️ 组合消息保存持续失败，已记录5次详细错误，后续仅记录概要")
                    
                    # 总是记录失败概要（但更简洁）
                    if failure_count >= 5:
                        logger.warning(f"组合消息保存失败: {channel_id}:{processed_data['message_id']} (累计{failure_count+1}次)")
            except Exception as process_error:
                logger.error(f"❌ 组合消息保存过程异常: {channel_id}:{processed_data['message_id']} - 错误: {process_error}")
                
        except Exception as save_error:
            logger.error(f"保存组合消息到Redis时出错: {save_error}")
    
    async def _save_to_redis_safe(self, processed_data: Dict, combined_message: Dict, channel_id: str):
        """安全保存组合消息到Redis - 处理重复保存情况"""
        try:
            from app.services.message_processor import MessageProcessor
            from app.storage.redis_manager import redis_manager
            
            # 🔧 优化：先检查是否已存在，避免重复检测器误报
            message_id = processed_data['message_id']
            existing_message = None
            
            if hasattr(self, 'redis_store') and self.redis_store:
                try:
                    existing_message = self.redis_store.get_message(channel_id, int(message_id), silent=True)
                except Exception:
                    pass
            
            # 如果消息已存在，直接返回成功
            if existing_message:
                logger.info(f"✅ 组合消息已存在于Redis，跳过保存: {channel_id}:{message_id}")
                # 通知前端组合消息已创建（如果还没有通知过）
                try:
                    await self._notify_combined_message_created(existing_message)
                except Exception:
                    pass  # 通知失败不影响主流程
                return
            
            # 消息不存在，正常保存
            await self._save_to_redis(processed_data, combined_message, channel_id)
            
        except Exception as safe_error:
            logger.error(f"安全保存组合消息时出错: {safe_error}")
            # 如果安全保存失败，回退到原始保存方法
            try:
                await self._save_to_redis(processed_data, combined_message, channel_id)
            except Exception:
                pass  # 最终失败时静默处理，错误已在_save_to_redis中记录
    
    async def _create_combined_message(self, messages: List[Dict], channel_id: str) -> Dict:
        """创建组合消息 - 修改为组合后统一过滤"""
        # 按时间排序
        messages.sort(key=lambda x: x['date'])
        
        # 🔧 修复：收集所有原始内容（子消息已跳过过滤）
        all_texts = []
        text_message_count = 0  # 记录有文本的消息数量
        
        for i, msg in enumerate(messages):
            content = msg.get('content') or ''
            
            # 记录文本内容存在性
            has_content = bool(content.strip())
            
            if has_content:
                text_message_count += 1
                all_texts.append(content.strip())
                logger.debug(f"消息{i+1}原始内容: {len(content)}字符")
        
        # 去重并合并原始文本内容
        deduplicated_texts = self._deduplicate_content(all_texts)
        combined_content = '\n\n'.join(deduplicated_texts) if deduplicated_texts else ""
        
        if len(deduplicated_texts) < len(all_texts):
            logger.info(f"🧹 内容去重：原始 {len(all_texts)} 条 → {len(deduplicated_texts)} 条")
        
        # 🚀 关键修复：组合完成后，对整体内容进行统一过滤
        main_message_id = messages[0]['message_id'] if messages else None
        combined_filtered_content = await self._ensure_filtered_content(
            combined_content, 
            channel_id,
            main_message_id
        )
        
        # 检测组合后的内容是否为广告
        from app.services.unified_filter_engine import unified_filter_engine
        is_ad, _, filter_reason = await unified_filter_engine.detect_advertisement(
            combined_filtered_content,
            channel_id=channel_id
        )
        
        if is_ad:
            logger.info(f"🚫 组合消息被检测为广告: {filter_reason}")
        
        # 记录文本合并结果
        logger.info(f"组合消息统一处理: {len(messages)}条消息, {text_message_count}条有文本, "
                   f"原始{len(combined_content)}字符, 过滤后{len(combined_filtered_content)}字符, 广告={is_ad}")
        
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
                    'error': media_info.get('error'),
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
        
        # 🔧 修复：查找有文字内容的消息作为主消息，如果没有则使用第一个
        main_message = None
        for msg in messages:
            if msg.get('content') and msg.get('content').strip():
                main_message = msg
                break
        
        # 如果没有找到有文字的消息，使用第一个消息
        if not main_message:
            main_message = messages[0]
        
        # 🔧 改进组合消息的占位符说明，更清晰且保持顺序
        placeholder_text = ""
        if media_group:
            # 按原始顺序生成媒体描述
            media_descriptions = []
            for i, media in enumerate(media_group, 1):
                media_type = media.get('media_type', 'unknown')
                type_name = {
                    'photo': '图片',
                    'video': '视频', 
                    'document': '文件',
                    'animation': '动图',
                    'audio': '音频'
                }.get(media_type, media_type)
                
                # 添加下载状态信息
                status_info = ""
                if media.get('download_failed'):
                    status_info = "[下载失败]"
                elif not media.get('file_path'):
                    status_info = "[无文件]"
                
                media_descriptions.append(f"{type_name}{i}{status_info}")
            
            # 生成统计信息
            media_count_by_type = {}
            available_count = 0
            for media in media_group:
                media_type = media.get('media_type', 'unknown')
                media_count_by_type[media_type] = media_count_by_type.get(media_type, 0) + 1
                if not media.get('download_failed') and media.get('file_path'):
                    available_count += 1
            
            # 生成摘要描述
            summary_parts = []
            for media_type, count in media_count_by_type.items():
                type_name = {
                    'photo': '图片',
                    'video': '视频', 
                    'document': '文件',
                    'animation': '动图',
                    'audio': '音频'
                }.get(media_type, media_type)
                summary_parts.append(f"{count}个{type_name}")
            
            message_ids = [str(msg['message_id']) for msg in messages]
            
            # 🚀 改进：将媒体组信息从内容中分离，消除特殊情况
            media_group_info = {
                'summary': ' + '.join(summary_parts),
                'available_count': available_count,
                'total_count': len(media_group),
                'message_ids': message_ids,
                'display_text': f"[📎 媒体组: {' + '.join(summary_parts)} | 可用: {available_count}/{len(media_group)} | ID: {', '.join(message_ids)}]"
            }
        
        # 内容保持纯净，不混入元数据
        final_content = combined_content
        final_filtered_content = combined_filtered_content
        
        # 为组合消息保存主媒体文件路径
        main_media_url = None
        if media_group:
            # 转换为web可访问URL
            from app.services.media_handler import media_handler
            main_media_url = await media_handler.get_media_url(media_group[0]['file_path']) if media_group[0].get('file_path') else None
        
        return {
            'message_id': main_message['message_id'],
            'content': final_content,
            'filtered_content': final_filtered_content,
            'is_ad': is_ad,
            'media_type': 'grouped_media' if media_group else main_media_type,  # 🔧 明确标记为组合媒体
            'media_url': main_media_url,
            'grouped_id': str(main_message['grouped_id']) if main_message.get('grouped_id') else None,
            'is_combined': True,
            'media_group_info': media_group_info if media_group else None,  # 🆕 新增媒体组信息字段
            'combined_messages': [
                {
                    'message_id': msg['message_id'],
                    'content': msg['content'],
                    'media_info': msg.get('media_info')
                }
                for msg in messages
            ],
            'media_group': media_group if media_group else None,
            'date': main_message['date']
        }
    
    async def _ensure_filtered_content(self, original_content: str, channel_id: str, message_id: int = None) -> str:
        """确保内容经过过滤处理 - 优化版本
        
        对组合后的内容进行统一过滤，使用正确的频道ID和消息上下文
        """
        if not original_content:
            return ""
        
        try:
            # 使用统一的过滤引擎处理内容
            from app.services.unified_filter_engine import unified_filter_engine
            from app.services.filters.base import FilterContext
            
            # 🔧 修复：创建过滤上下文 - 使用真实的频道ID和消息ID
            context = FilterContext(
                message_id=message_id if message_id else 0,
                channel_id=channel_id  # 使用真实频道ID，而不是"grouper"
            )
            
            # 添加元数据标记这是组合消息的统一过滤
            context.add_metadata('is_combined_filtering', True)
            context.add_metadata('source_type', 'combined_message')
            
            # 执行过滤
            result = await unified_filter_engine.filter_pipeline.process(original_content, context)
            
            if result.final_content != original_content:
                logger.info(f"组合消息统一过滤: {len(original_content)} -> {len(result.final_content)} 字符 (频道: {channel_id})")
            
            return result.final_content
            
        except Exception as e:
            logger.error(f"组合消息统一过滤失败，使用原始内容: {e}")
            return original_content
    
    async def _save_combined_message(self, combined_message: Dict, channel_id: str):
        """准备组合消息数据（不再直接保存）"""
        try:
            # 返回处理后的组合消息数据
            processed_data = await self._trigger_combined_message_event(combined_message, channel_id)
            
            # 🔥 修复：组消息保存后立即更新checkpoint
            if processed_data:
                await self._update_group_checkpoint(combined_message, channel_id)
            
            return processed_data
            
        except Exception as e:
            logger.error(f"准备组合消息数据时出错: {e}")
            return None
    
    async def _update_group_checkpoint(self, combined_message: Dict, channel_id: str):
        """更新组消息checkpoint到组内最大消息ID"""
        try:
            from app.storage.channel_store import RedisChannelStore
            from app.storage.redis_manager import redis_manager
            
            # 获取组内所有消息ID
            message_ids = []
            for msg in combined_message.get('messages', []):
                msg_id = msg.get('message_id')
                if msg_id:
                    message_ids.append(int(msg_id))
            
            if message_ids:
                max_msg_id = max(message_ids)
                channel_store = RedisChannelStore(redis_manager.client)
                success = channel_store.set_checkpoint(channel_id, max_msg_id)
                
                if success:
                    logger.info(f"✅ 组消息checkpoint更新: {channel_id} -> {max_msg_id}")
                else:
                    logger.warning(f"⚠️ 组消息checkpoint更新失败: {channel_id} -> {max_msg_id}")
                    
        except Exception as e:
            logger.error(f"更新组消息checkpoint失败: {e}")
    
    async def _trigger_combined_message_event(self, combined_message: Dict, channel_id: str):
        """返回组合消息数据（不再直接保存）"""
        try:
            from datetime import datetime
            
            # 使用已经过滤的内容（在创建组合消息时已经处理）
            is_ad = combined_message.get('is_ad', False)
            filtered_content = combined_message.get('filtered_content', combined_message['content'])
            
            # 🚀 性能优化：根据配置决定是否删除单独消息
            await self._cleanup_individual_messages_if_enabled(channel_id, combined_message)
            
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
            
            visual_hash = None
            
            # 计算组合媒体哈希
            combined_media_hash = None
            if clean_media_group:
                import hashlib
                hashes = []
                for media_item in clean_media_group:
                    if media_item.get('hash'):
                        hashes.append(media_item['hash'])
                if hashes:
                    combined_media_hash = hashlib.sha256(''.join(sorted(hashes)).encode()).hexdigest()
            
            # 返回处理后的消息数据，由统一处理器保存
            logger.info(f"组合消息准备完成: grouped_id={combined_message['grouped_id']}, 包含 {len(combined_message.get('combined_messages', []))} 条消息")
            
            return {
                'message_id': combined_message['message_id'],
                'content': combined_message['content'],
                'filtered_content': filtered_content,
                'is_ad': is_ad,
                'media_type': combined_message['media_type'],
                'media_url': combined_message['media_url'],
                'grouped_id': combined_message.get('grouped_id'),
                'is_combined': True,
                'combined_messages': clean_combined_messages,
                'media_group': clean_media_group,
                'visual_hash': visual_hash,
                'combined_media_hash': combined_media_hash,
                'date': combined_message.get('date', get_current_time())
            }
                
        except Exception as e:
            logger.error(f"处理组合消息数据时出错: {e}")
            return None
    
    
    async def _get_existing_combined_message(self, channel_id: str, grouped_id: str) -> Optional[Dict]:
        """检查是否已存在组合消息"""
        try:
            redis_store = redis_manager
            
            # 改进：使用组合消息的索引来查找，而不是遍历所有消息
            # 查询指定频道最近的消息（限制数量）
            messages = redis_manager.get_messages_by_channel(channel_id, limit=100)
            
            # 查找已存在的组合消息
            for message in messages:
                if (message.get('grouped_id') == grouped_id and 
                    message.get('is_combined') == True):
                    logger.debug(f"找到现有组合消息: grouped_id={grouped_id}")
                    return message
                    
            return None
            
        except Exception as e:
            logger.error(f"检查现有组合消息时出错: {e}")
            return None
    
    async def _get_existing_single_message(self, channel_id: str, message_id: int) -> Optional[Dict]:
        """检查是否已存在单独消息"""
        try:
            redis_store = redis_manager
            
            # 直接尝试获取消息，避免遍历（静默模式，避免产生不必要的警告）
            # 首先尝试根据message_id直接查找
            existing_message = redis_manager.get_message(channel_id, message_id, silent=True)
            if existing_message and existing_message.get('telegram_message_id') == message_id:
                logger.debug(f"找到现有单独消息: message_id={message_id}")
                return existing_message
            
            # 如果直接查找失败，再查询最近的消息（限制数量）
            messages = redis_manager.get_messages_by_channel(channel_id, limit=100)
            
            # 查找已存在的单独消息
            for message in messages:
                if message.get('telegram_message_id') == message_id:
                    logger.debug(f"在最近消息中找到现有单独消息: message_id={message_id}")
                    return message
                    
            return None
            
        except Exception as e:
            logger.error(f"检查现有单独消息时出错: {e}")
            return None
    
    async def _cleanup_individual_messages(self, channel_id: str, combined_message: Dict):
        """清理已经被组合的单独消息"""
        try:
            if not combined_message.get('combined_messages'):
                return
            
            redis_store = redis_manager
            
            # 获取所有相关的单独消息ID
            message_ids = [msg['message_id'] for msg in combined_message['combined_messages']]
            
            # 查询指定频道的所有消息
            messages = redis_manager.get_messages_by_channel(channel_id)
            
            # 查找需要删除的单独消息
            messages_to_delete = []
            for message in messages:
                if (message.get('telegram_message_id') in message_ids and 
                    not message.get('is_combined', False)):
                    messages_to_delete.append(message)
            
            # 删除这些单独消息
            delete_count = 0
            for msg in messages_to_delete:
                msg_id = msg.get('message_id')
                if msg_id:
                    success = redis_manager.delete_message(channel_id, msg_id)
                    if success:
                        delete_count += 1
                        logger.info(f"删除已被组合的单独消息: Redis ID={msg_id}, telegram_id={msg.get('telegram_message_id')}")
            
            if delete_count > 0:
                logger.info(f"已清理 {delete_count} 条被组合的单独消息")
                
        except Exception as e:
            logger.error(f"清理单独消息时出错: {e}")
    
    async def cleanup_expired_groups(self):
        """清理过期的消息组 - 后无需此功能"""
        try:
            logger.debug("设计：无需清理过期组，所有组均即时处理")
            # 设计：没有待处理的组，所以也没有过期的组
                
        except Exception as e:
            logger.error(f"清理过期消息组时出错: {e}")
    
    async def _notify_combined_message_created(self, saved_message):
        """通知前端组合消息已创建"""
        try:
            from app.api.websocket import websocket_manager
            from app.utils.timezone import format_for_api
            
            # 准备消息数据
            message_data = {
                "id": saved_message.get('id'),
                "message_id": saved_message.get('message_id'),
                "source_channel": saved_message.get('source_channel'),
                "content": saved_message.get('content'),
                "filtered_content": saved_message.get('filtered_content'),
                "media_type": saved_message.get('media_type'),
                "media_url": saved_message.get('media_url'),
                "is_ad": saved_message.get('is_ad'),
                "is_combined": saved_message.get('is_combined'),
                "grouped_id": saved_message.get('grouped_id'),
                "status": saved_message.get('status'),
                "created_at": self._safe_format_time(saved_message.get('created_at')),
                "media_group_display": self._prepare_media_group_display(saved_message),
                "media_group": saved_message.get('media_group'),
                "combined_messages": saved_message.get('combined_messages')
            }
            
            # 广播到所有WebSocket客户端
            await websocket_manager.broadcast_new_message(message_data)
            logger.info(f"✅ 成功通知前端组合消息创建: ID:{saved_message.get('id')}")
            
        except ImportError as e:
            logger.warning(f"WebSocket管理器未可用: {e}")
        except Exception as e:
            logger.error(f"通知前端组合消息创建失败: {e}")
    
    def _safe_format_time(self, time_value):
        """安全的时间格式化方法"""
        try:
            from app.utils.timezone import format_for_api
            from datetime import datetime
            
            if time_value is None:
                return None
            
            # 如果已经是字符串，直接返回
            if isinstance(time_value, str):
                return time_value
            
            # 如果是datetime对象，使用format_for_api格式化
            if isinstance(time_value, datetime):
                return format_for_api(time_value)
            
            # 其他情况，转换为字符串
            return str(time_value)
        
        except Exception as e:
            logger.warning(f"时间格式化失败: {e}, 使用原始值: {time_value}")
            return str(time_value) if time_value is not None else None
    
    def _prepare_media_group_display(self, db_message):
        """准备媒体组显示数据"""
        try:
            if not db_message.get('is_combined') or not db_message.get('media_group'):
                return None
                
            media_display = []
            for media_item in db_message.get('media_group', []):
                # 转换本地文件路径为web访问路径
                file_path = media_item.get('file_path') or ''
                
                # 跳过空文件路径
                if not file_path:
                    continue
                
                # 检查文件是否存在
                import os
                if not os.path.exists(file_path):
                    logger.warning(f"媒体文件不存在，跳过: {file_path}")
                    continue
                    
                from app.core.path_config import PathConfig
                temp_media_local = f"./{PathConfig.TEMP_MEDIA_DIR.name}/"
                temp_media_web = f"/{PathConfig.TEMP_MEDIA_DIR.name}/"
                if file_path and file_path.startswith(temp_media_local):
                    web_path = file_path.replace(temp_media_local, temp_media_web)
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

    async def _cleanup_individual_messages_if_enabled(self, channel_id: str, combined_message: Dict):
        """🚀 根据配置决定是否清理已经被组合的单独消息"""
        try:
            # 检查配置开关
            from app.services.config_manager import config_manager
            delete_enabled = await config_manager.get_config('storage.delete_single_messages', False)
            
            if not delete_enabled:
                logger.debug(f"单独消息删除功能已禁用，跳过清理: grouped_id={combined_message.get('grouped_id')}")
                return
            
            # 启用了删除功能，执行清理
            logger.info(f"🗑️ 开始清理单独消息: grouped_id={combined_message.get('grouped_id')}")
            await self._cleanup_individual_messages(channel_id, combined_message)
            
        except Exception as e:
            logger.error(f"检查配置并清理单独消息时出错: {e}")
    
    async def disconnect_telegram_client(self):
        """断开Telegram客户端连接"""
        try:
            if self.telegram_client:
                await self.telegram_client.disconnect()
                self.telegram_client = None
                logger.info("👋 Telegram客户端已断开")
        except Exception as e:
            logger.error(f"断开Telegram客户端时出错: {e}")

# 全局消息组合器实例
message_grouper = MessageGrouper()