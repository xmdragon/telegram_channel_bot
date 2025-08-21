"""
消息组合处理器 - 处理Telegram的消息组合功能
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from app.utils.timezone import get_current_time
from app.storage.redis_store import get_redis_message_store

logger = logging.getLogger(__name__)

class MessageGrouper:
    """消息组合处理器"""
    
    def __init__(self):
        self.pending_groups: Dict[str, List[Dict]] = {}  # 待处理的消息组
        self.completed_groups: Dict[str, Dict] = {}  # 已完成的组合消息数据
        self.group_timers: Dict[str, asyncio.Task] = {}  # 组合超时定时器
        self.group_timeout = 30  # Linus式修复：增加到30秒，减少网络延迟导致的丢失
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
            # 🔧 修复：改进文本内容提取，确保不丢失caption
            original_content = ""
            
            # 1. 优先使用传入的filtered_content（来自上游处理器）
            if filtered_content is not None and filtered_content.strip():
                original_content = filtered_content
                logger.debug(f"使用上游过滤后内容: {len(original_content)}字符")
            else:
                # 2. 如果没有传入有效的filtered_content，直接从消息提取
                # 按优先级提取：text -> raw_text -> message -> caption
                if hasattr(message, 'text') and message.text:
                    original_content = message.text
                elif hasattr(message, 'raw_text') and message.raw_text:
                    original_content = message.raw_text
                elif hasattr(message, 'message') and message.message:
                    original_content = message.message
                
                # 3. 🔧 重要：无论是否已有文本，都检查caption
                caption = ""
                if hasattr(message, 'caption') and message.caption:
                    caption = message.caption
                
                # 4. 组合文本和caption
                if original_content and caption:
                    original_content = f"{original_content}\n\n{caption}"
                    logger.debug(f"组合器中合并文本和caption: text={len(message.text if hasattr(message, 'text') else '')}字符, caption={len(caption)}字符")
                elif not original_content and caption:
                    original_content = caption
                    logger.debug(f"组合器中使用caption: {len(caption)}字符")
                
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
                'content': filtered_content if filtered_content is not None else (message.text or message.caption if hasattr(message, 'caption') else ""),
                'filtered_content': filtered_content,
                'is_ad': is_ad,
                'media_info': media_info,
                'date': message.date or get_current_time(),
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
        
        # 批量模式下等待组合完成，不立即返回单独消息
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
            
            # 使用统一的处理逻辑
            await self._complete_group_processing(group_key, channel_id, messages)
                
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
        
        # Linus式改进：检查消息组是否可能已完整，避免不必要的等待
        current_messages = self.pending_groups[group_key]
        is_likely_complete = await self._is_group_likely_complete(current_messages)
        
        # 取消之前的定时器
        if group_key in self.group_timers:
            self.group_timers[group_key].cancel()
        
        if is_likely_complete:
            # 如果检测到组可能已完整，缩短等待时间到5秒
            timeout = 5
            logger.info(f"消息组 {grouped_id} 检测到可能已完整（{len(current_messages)}条消息），使用短超时{timeout}秒")
        else:
            # 否则使用正常超时
            timeout = self.group_timeout
            logger.info(f"消息组 {grouped_id} 当前有 {len(current_messages)} 条消息，使用正常超时{timeout}秒")
        
        # 设置动态超时的定时器
        self.group_timers[group_key] = asyncio.create_task(
            self._process_group_after_dynamic_timeout(group_key, channel_id, timeout)
        )
        
        # 等待组合完成，不立即返回单独消息
        return None
    
    async def _is_group_likely_complete(self, messages: List[Dict]) -> bool:
        """
        Linus式简单判断：检查消息组是否可能已完整
        不需要复杂的算法，用简单的启发式规则
        """
        if len(messages) < 2:
            return False
            
        # 提取消息ID并排序
        message_ids = [msg['message_id'] for msg in messages if msg.get('message_id')]
        if len(message_ids) < 2:
            return False
            
        message_ids.sort()
        
        # 检查消息ID是否连续（允许有1-2个间隔）
        max_gap = 0
        for i in range(1, len(message_ids)):
            gap = message_ids[i] - message_ids[i-1]
            max_gap = max(max_gap, gap)
        
        # 如果最大间隔超过3，可能还有消息在传输中
        if max_gap > 3:
            return False
            
        # 如果已有4个或更多消息，很可能已经完整
        if len(messages) >= 4:
            return True
            
        return False
    
    async def _process_group_after_dynamic_timeout(self, group_key: str, channel_id: str, timeout: float):
        """动态超时处理"""
        try:
            await asyncio.sleep(timeout)
            
            if group_key not in self.pending_groups:
                return
            
            messages = self.pending_groups[group_key]
            if not messages:
                return
            
            logger.info(f"处理消息组 {group_key}，共 {len(messages)} 条消息（超时{timeout}秒）")
            
            # 其余逻辑与原来的_process_group_after_timeout相同
            await self._complete_group_processing(group_key, channel_id, messages)
            
        except asyncio.CancelledError:
            logger.debug(f"消息组 {group_key} 的定时器被取消")
        except Exception as e:
            logger.error(f"处理消息组 {group_key} 超时时发生错误: {e}")
    
    
    async def _create_combined_message(self, messages: List[Dict], channel_id: str) -> Dict:
        """创建组合消息"""
        # 按时间排序
        messages.sort(key=lambda x: x['date'])
        
        # 🔧 改进文本内容提取和合并逻辑
        all_texts = []
        all_filtered_texts = []
        is_ad = False
        text_message_count = 0  # 记录有文本的消息数量
        
        for i, msg in enumerate(messages):
            content = msg.get('content') or ''
            filtered_content = msg.get('filtered_content')
            
            # 记录文本内容存在性
            has_content = bool(content.strip())
            has_filtered = bool(filtered_content and filtered_content.strip())
            
            if has_content:
                text_message_count += 1
            
            # 始终保存原始内容（即使为空，保持消息顺序）
            if content.strip():
                all_texts.append(content.strip())
                logger.debug(f"消息{i+1}原始内容: {len(content)}字符")
            
            # 过滤后内容处理
            if has_filtered:
                all_filtered_texts.append(filtered_content.strip())
                logger.debug(f"消息{i+1}过滤后内容: {len(filtered_content)}字符")
            elif has_content:
                # 如果没有过滤后内容但有原始内容，使用原始内容
                all_filtered_texts.append(content.strip())
                logger.debug(f"消息{i+1}使用原始内容作为过滤后内容: {len(content)}字符")
            
            # 如果组内任何一条消息被判定为广告，整组都标记为广告
            if msg.get('is_ad'):
                is_ad = True
                logger.info(f"🚫 消息组中检测到广告，整组标记为广告")
        
        # 合并文本内容
        combined_content = '\n\n'.join(all_texts) if all_texts else ""
        combined_filtered_content = '\n\n'.join(all_filtered_texts) if all_filtered_texts else ""
        
        # 记录文本合并结果
        logger.info(f"组合消息文本合并: {len(messages)}条消息, {text_message_count}条有文本, 原始{len(combined_content)}字符, 过滤后{len(combined_filtered_content)}字符")
        
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
                    'visual_hashes': media_info.get('visual_hashes')  # 保留视觉哈希
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
            placeholder_text = f"\n\n[📎 媒体组: {' + '.join(summary_parts)} | 可用: {available_count}/{len(media_group)} | ID: {', '.join(message_ids)}]"
        
        # 合并内容和占位符
        final_content = combined_content + placeholder_text
        final_filtered_content = combined_filtered_content + placeholder_text
        
        # 为组合消息保存主媒体文件路径
        main_media_url = None
        if media_group:
            main_media_url = media_group[0]['file_path']
        
        return {
            'message_id': main_message['message_id'],
            'content': final_content,
            'filtered_content': final_filtered_content,
            'is_ad': is_ad,
            'media_type': 'grouped_media' if media_group else main_media_type,  # 🔧 明确标记为组合媒体
            'media_url': main_media_url,
            'grouped_id': str(main_message['grouped_id']) if main_message.get('grouped_id') else None,
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
            'date': main_message['date']
        }
    
    async def _ensure_filtered_content(self, original_content: str, filtered_content: Optional[str]) -> str:
        """确保内容经过过滤处理
        
        如果没有提供filtered_content，则通过过滤管道处理原始内容
        这样确保组合消息和单独消息使用相同的过滤逻辑
        """
        if filtered_content is not None:
            return filtered_content
            
        if not original_content:
            return ""
        
        try:
            # 使用统一的过滤引擎处理内容
            from app.services.unified_filter_engine import unified_filter_engine
            from app.services.filters.base import FilterContext
            
            # 创建过滤上下文
            context = FilterContext(
                message_id=0,  # 组合消息的临时ID
                channel_id="grouper"
            )
            
            # 执行过滤
            result = await unified_filter_engine.filter_pipeline.process(original_content, context)
            
            if result.final_content != original_content:
                logger.info(f"组合消息内容过滤: {len(original_content)} -> {len(result.final_content)} 字符")
            
            return result.final_content
            
        except Exception as e:
            logger.error(f"组合消息过滤失败，使用原始内容: {e}")
            return original_content
    
    async def _save_combined_message(self, combined_message: Dict, channel_id: str):
        """准备组合消息数据（不再直接保存）"""
        try:
            # 返回处理后的组合消息数据
            return await self._trigger_combined_message_event(combined_message, channel_id)
            
        except Exception as e:
            logger.error(f"准备组合消息数据时出错: {e}")
            return None
    
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
            
            # 提取组合消息的视觉哈希
            combined_visual_hashes = []
            if clean_media_group:
                for media_item in clean_media_group:
                    if media_item.get('visual_hashes'):
                        combined_visual_hashes.append(media_item['visual_hashes'])
            
            # 如果有视觉哈希，存储为JSON字符串
            import json
            visual_hash = json.dumps(combined_visual_hashes) if combined_visual_hashes else None
            
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
    
    async def force_complete_all_groups(self):
        """强制完成所有待处理的消息组（用于历史采集结束时）"""
        try:
            logger.info(f"强制完成所有待处理的消息组，当前有 {len(self.pending_groups)} 个组")
            
            # 取消所有定时器
            for timer in self.group_timers.values():
                timer.cancel()
            self.group_timers.clear()
            
            # 处理所有待处理的组
            groups_to_process = list(self.pending_groups.keys())
            for group_key in groups_to_process:
                messages = self.pending_groups.get(group_key, [])
                if messages:
                    # 从group_key中提取channel_id
                    # group_key格式: channel_id_grouped_id
                    # channel_id可能是负数，如 -1001969693044
                    last_underscore = group_key.rfind('_')
                    if last_underscore > 0:
                        channel_id = group_key[:last_underscore]
                    else:
                        # 如果找不到下划线，整个key就是channel_id
                        channel_id = group_key
                    
                    logger.info(f"强制处理消息组 {group_key}，共 {len(messages)} 条消息")
                    
                    # 使用统一的处理逻辑
                    await self._complete_group_processing(group_key, channel_id, messages)
            
            # 清理所有待处理的组
            self.pending_groups.clear()
            
            logger.info("所有待处理的消息组已完成")
            
        except Exception as e:
            logger.error(f"强制完成消息组时出错: {e}")
    
    async def _get_existing_combined_message(self, channel_id: str, grouped_id: str) -> Optional[Dict]:
        """检查是否已存在组合消息"""
        try:
            redis_store = get_redis_message_store()
            
            # 改进：使用组合消息的索引来查找，而不是遍历所有消息
            # 查询指定频道最近的消息（限制数量）
            messages = redis_store.get_messages_by_channel(channel_id, limit=100)
            
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
            redis_store = get_redis_message_store()
            
            # 直接尝试获取消息，避免遍历（静默模式，避免产生不必要的警告）
            # 首先尝试根据message_id直接查找
            existing_message = redis_store.get_message(channel_id, message_id, silent=True)
            if existing_message and existing_message.get('telegram_message_id') == message_id:
                logger.debug(f"找到现有单独消息: message_id={message_id}")
                return existing_message
            
            # 如果直接查找失败，再查询最近的消息（限制数量）
            messages = redis_store.get_messages_by_channel(channel_id, limit=100)
            
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
            
            redis_store = get_redis_message_store()
            
            # 获取所有相关的单独消息ID
            message_ids = [msg['message_id'] for msg in combined_message['combined_messages']]
            
            # 查询指定频道的所有消息
            messages = redis_store.get_messages_by_channel(channel_id)
            
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
                    success = redis_store.delete_message(channel_id, msg_id)
                    if success:
                        delete_count += 1
                        logger.info(f"删除已被组合的单独消息: Redis ID={msg_id}, telegram_id={msg.get('telegram_message_id')}")
            
            if delete_count > 0:
                logger.info(f"已清理 {delete_count} 条被组合的单独消息")
                
        except Exception as e:
            logger.error(f"清理单独消息时出错: {e}")
    
    async def cleanup_expired_groups(self):
        """清理过期的消息组"""
        try:
            expired_keys = []
            current_time = get_current_time()
            
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
    
    async def _notify_combined_message_created(self, saved_message):
        """通知前端组合消息已创建"""
        try:
            from app.api.websocket import websocket_manager
            from app.utils.timezone import format_for_api
            
            # 准备消息数据
            message_data = {
                "id": saved_message.id,
                "message_id": saved_message.message_id,
                "source_channel": saved_message.source_channel,
                "content": saved_message.content,
                "filtered_content": saved_message.filtered_content,
                "media_type": saved_message.media_type,
                "media_url": saved_message.media_url,
                "is_ad": saved_message.is_ad,
                "is_combined": saved_message.is_combined,
                "grouped_id": saved_message.grouped_id,
                "status": saved_message.status,
                "created_at": format_for_api(saved_message.created_at),
                "media_group_display": self._prepare_media_group_display(saved_message),
                "media_group": saved_message.media_group,
                "combined_messages": saved_message.combined_messages
            }
            
            # 广播到所有WebSocket客户端
            await websocket_manager.broadcast_new_message(message_data)
            logger.info(f"✅ 成功通知前端组合消息创建: ID:{saved_message.id}")
            
        except ImportError as e:
            logger.warning(f"WebSocket管理器未可用: {e}")
        except Exception as e:
            logger.error(f"通知前端组合消息创建失败: {e}")
    
    def _prepare_media_group_display(self, db_message):
        """准备媒体组显示数据"""
        try:
            if not db_message.is_combined or not db_message.media_group:
                return None
                
            media_display = []
            for media_item in db_message.media_group:
                # 转换本地文件路径为web访问路径
                file_path = media_item.get('file_path', '')
                from app.core.path_config import PathConfig
                temp_media_local = f"./{PathConfig.TEMP_MEDIA_DIR.name}/"
                temp_media_web = f"/{PathConfig.TEMP_MEDIA_DIR.name}/"
                if file_path.startswith(temp_media_local):
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
    
    async def _complete_group_processing(self, group_key: str, channel_id: str, messages: List[Dict]):
        """
        Linus式重构：统一的组处理完成逻辑，消除重复代码
        """
        try:
            # 创建组合消息
            combined_message = await self._create_combined_message(messages, channel_id)
            
            # 准备组合消息数据
            processed_data = await self._save_combined_message(combined_message, channel_id)
            
            # 将处理后的数据存储，供后续获取
            if processed_data:
                self.completed_groups[group_key] = processed_data
                
                # 调用message_processor保存到Redis
                try:
                    from app.services.message_processor import MessageProcessor
                    processor = MessageProcessor()
                    
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
                        'status': 'ads' if processed_data.get('is_ad') else 'pending',
                        'combined_messages': processed_data.get('combined_messages'),
                        'media_group': processed_data.get('media_group'),
                        'created_at': processed_data.get('date', combined_message.get('date'))
                    }
                    
                    # 保存到Redis
                    saved_message = await processor.process_new_message(save_data)
                    if saved_message:
                        logger.info(f"✅ 组合消息已保存到Redis: {channel_id}:{processed_data['message_id']}")
                        
                        # 通知前端组合消息已创建
                        await self._notify_combined_message_created(saved_message)
                    else:
                        logger.error(f"❌ 组合消息保存到Redis失败: {channel_id}:{processed_data['message_id']}")
                        
                except Exception as save_error:
                    logger.error(f"保存组合消息到Redis时出错: {save_error}")
            else:
                logger.warning(f"组合消息数据处理失败: {group_key}")
            
            # 清理完成的消息组
            if group_key in self.pending_groups:
                del self.pending_groups[group_key]
            if group_key in self.group_timers:
                del self.group_timers[group_key]
                
        except Exception as e:
            logger.error(f"完成组处理时发生错误: {e}")

# 全局消息组合器实例
message_grouper = MessageGrouper()