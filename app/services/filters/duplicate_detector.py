"""
去重检测过滤器
基于BaseFilter接口，整合媒体哈希、文本相似度和视觉相似度检测
检测到重复时返回 should_early_stop=True

Author: Claude  
Created: 2025-08-15
"""

import hashlib
import re
import json
import logging
import time
import warnings
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# 抑制jieba的pkg_resources弃用警告
warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")
import jieba

from .base import BaseFilter, FilterContext, FilterResult
from app.storage.redis_store import get_redis_message_store

# 导入视觉相似度检测器
try:
    from app.services.visual_similarity import visual_detector
except ImportError:
    visual_detector = None

logger = logging.getLogger(__name__)


class MessageCompat:
    """消息兼容类 - 桥接Redis数据格式与原有SQLAlchemy格式"""
    
    def __init__(self, redis_data: dict):
        self.data = redis_data
    
    @property
    def id(self):
        return self.data.get('message_id')
    
    @property
    def content(self):
        return self.data.get('content')
    
    @property
    def visual_hash(self):
        return self.data.get('visual_hash')
    
    @property
    def created_at(self):
        created_at_str = self.data.get('created_at')
        if created_at_str:
            try:
                # 解析ISO格式时间字符串
                dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                # 返回无时区的UTC时间
                return dt.replace(tzinfo=None)
            except:
                pass
        return datetime.utcnow()
    
    @property
    def status(self):
        return self.data.get('status', 'pending')
    
    @property
    def media_hash(self):
        return self.data.get('media_hash')
    
    @property
    def combined_media_hash(self):
        return self.data.get('combined_media_hash')


class DuplicateDetectorFilter(BaseFilter):
    """去重检测过滤器：媒体哈希 + 文本相似度 + 视觉相似度"""
    
    def __init__(self, config: Optional[Dict[str, any]] = None):
        super().__init__("duplicate_detector", config)
        
        # Redis存储实例（延迟初始化）
        self.redis_store = None
        
        # 媒体检测参数
        self.media_cache_hours = self.config.get('media_cache_hours', 72)
        
        # 文本检测参数
        self.text_similarity_threshold = self.config.get('text_similarity_threshold', 0.75)
        self.text_time_window_minutes = self.config.get('text_time_window_minutes', 2880)  # 48小时
        
        # 视觉相似度检测窗口
        self.visual_cache_hours = self.config.get('visual_cache_hours', 96)
        
        # 文本清理正则表达式
        self.common_tags = [
            r'#\w+',  # 标签
            r'@\w+',  # 用户名/频道名
            r'https?://[^\s]+',  # 链接
            r't\.me/[^\s]+',  # Telegram链接
            r'(?:^|\s)订阅.{0,20}(?:$|\s)',  # 订阅相关文字
            r'(?:^|\s)投稿.{0,20}(?:$|\s)',  # 投稿相关文字
            r'(?:^|\s)联系.{0,20}(?:$|\s)',  # 联系方式
            r'📢|📣|📡|🎁|💰|🔥|❤|😊|😍|👇',  # 常见表情
        ]
        
        # 编译正则表达式
        self.tag_patterns = [re.compile(pattern) for pattern in self.common_tags]
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """预检查是否需要进行重复检测"""
        # 延迟初始化Redis存储
        if self.redis_store is None:
            try:
                self.redis_store = get_redis_message_store()
            except RuntimeError:
                logger.debug("Redis存储未初始化，跳过重复检测")
                return False
        
        # 如果没有内容也没有媒体信息，跳过检测
        if not content and not context.get_metadata('media_hash') and not context.get_metadata('visual_hashes'):
            return False
        
        return True
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """执行重复检测"""
        start_time = time.time()
        
        result = FilterResult(
            filtered_content=content,
            passed=True,
            confidence=0.0,
            details={}
        )
        
        try:
            # 获取上下文信息
            message_time = datetime.fromtimestamp(context.timestamp)
            message_id = context.message_id
            channel_id = str(context.channel_id) if context.channel_id else None
            
            # 获取媒体相关信息
            media_hash = context.get_metadata('media_hash')
            combined_media_hash = context.get_metadata('combined_media_hash')
            visual_hashes = context.get_metadata('visual_hashes')
            media_data = context.get_metadata('media_data')
            
            # 执行重复检测
            is_duplicate, original_message_id, duplicate_type = await self._check_duplicate(
                channel_id=channel_id,
                media_hash=media_hash,
                combined_media_hash=combined_media_hash,
                content=content,
                message_time=message_time,
                message_id=message_id,
                media_data=media_data,
                visual_hashes=visual_hashes
            )
            
            if is_duplicate:
                result.passed = False
                result.should_early_stop = True  # 关键：设置早停标志
                result.reason = f"检测到重复内容 ({duplicate_type})"
                result.confidence = 0.95  # 高置信度
                result.filtered_content = f"[重复内容，原消息ID: {original_message_id}]"
                
                # 详细记录判定依据
                result.details = {
                    'duplicate_type': duplicate_type,
                    'original_message_id': original_message_id,
                    'detection_method': self._get_detection_method_details(duplicate_type),
                    'message_id': message_id,
                    'channel_id': channel_id
                }
                
                logger.info(f"✅ 重复检测: {duplicate_type} 重复，原消息ID: {original_message_id}")
            else:
                result.details = {
                    'checked_methods': self._get_checked_methods(media_hash, combined_media_hash, visual_hashes, content),
                    'no_duplicates_found': True
                }
                logger.debug("✅ 去重检测完成，未发现重复")
                
        except Exception as e:
            logger.error(f"重复检测失败: {e}", exc_info=True)
            # 异常时不影响消息处理，允许通过
            result.details['error'] = str(e)
        
        # 计算处理时间
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        return result
    
    async def _check_duplicate(self, 
                              channel_id: Optional[str] = None,
                              media_hash: Optional[str] = None, 
                              combined_media_hash: Optional[str] = None,
                              content: Optional[str] = None,
                              message_time: Optional[datetime] = None,
                              message_id: Optional[int] = None,
                              media_data: Optional[bytes] = None,
                              visual_hashes: Optional[dict] = None) -> Tuple[bool, Optional[int], str]:
        """
        整合的重复消息检测：优先视觉相似度，其次媒体哈希，最后文本相似度
        
        Returns:
            (is_duplicate, original_message_id, duplicate_type)
        """
        if message_time is None:
            message_time = datetime.utcnow()
        
        # 确保时间没有时区信息
        if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
            message_time = message_time.replace(tzinfo=None)
        
        # 1. 最优先进行视觉相似度检测
        if visual_detector and (media_data or visual_hashes):
            logger.debug(f"开始视觉相似度检测，检测窗口: {self.visual_cache_hours}小时")
            is_visual_dup, orig_id, similarity = await self._check_visual_duplicate(
                media_data, visual_hashes, message_time, message_id
            )
            if is_visual_dup:
                logger.info(f"✅ 检测到视觉相似图片，相似度: {similarity:.1f}%，原消息ID: {orig_id}")
                return True, orig_id, "visual"
        
        # 2. 其次进行媒体哈希检测（跨频道）
        if media_hash or combined_media_hash:
            logger.debug(f"开始媒体哈希检测，检测窗口: {self.media_cache_hours}小时")
            is_media_dup, orig_id = await self._check_media_duplicate(
                media_hash, combined_media_hash, message_time, message_id
            )
            if is_media_dup:
                logger.info(f"✅ 检测到媒体哈希重复，原消息ID: {orig_id}")
                return True, orig_id, "media"
        
        # 3. 最后进行文本相似度检测（跨频道）
        if content and content.strip():
            logger.debug(f"开始文本相似度检测，阈值: {self.text_similarity_threshold:.0%}，检测窗口: {self.text_time_window_minutes//60}小时")
            is_text_dup, orig_id = await self._check_text_duplicate(
                content, channel_id, message_time, message_id
            )
            if is_text_dup:
                logger.info(f"✅ 检测到文本相似重复，原消息ID: {orig_id}")
                return True, orig_id, "text"
        
        return False, None, "none"
    
    async def _check_visual_duplicate(self, media_data: Optional[bytes],
                                     visual_hashes: Optional[dict],
                                     message_time: datetime,
                                     message_id: Optional[int] = None) -> Tuple[bool, Optional[int], float]:
        """检查视觉相似度重复"""
        if not visual_detector:
            return False, None, 0.0
        
        # 如果有媒体数据但没有视觉哈希，先计算
        if media_data and not visual_hashes:
            visual_hashes = visual_detector.calculate_perceptual_hashes(media_data)
        
        if not visual_hashes:
            return False, None, 0.0
        
        try:
            # 确保时间没有时区信息
            if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
                message_time = message_time.replace(tzinfo=None)
            
            # 计算时间阈值
            time_threshold = message_time - timedelta(hours=self.visual_cache_hours)
            
            # 获取Redis中有视觉哈希的消息
            messages_to_check = await self._get_recent_messages_with_visual_hash(
                time_threshold, message_id
            )
            
            # 检查每个历史消息的视觉相似度
            for msg_data in messages_to_check:
                result = self._check_single_visual_similarity(msg_data, visual_hashes)
                if result[0]:  # is_similar
                    return result
            
            return False, None, 0.0
            
        except Exception as e:
            logger.error(f"检查视觉重复时出错: {e}")
            return False, None, 0.0
    
    def _check_single_visual_similarity(self, msg_data: dict, visual_hashes: dict) -> Tuple[bool, Optional[int], float]:
        """检查单个消息的视觉相似度 - 消除嵌套的辅助方法"""
        try:
            stored_visual_hash = msg_data.get('visual_hash')
            if not stored_visual_hash:
                return False, None, 0.0
            
            stored_hashes = self._parse_visual_hash(stored_visual_hash)
            if not stored_hashes:
                return False, None, 0.0
            
            is_similar, similarity = visual_detector.is_visually_similar(visual_hashes, stored_hashes)
            if is_similar:
                orig_msg_id = msg_data.get('message_id')
                logger.info(f"发现视觉相似图片，消息ID: {orig_msg_id}, 相似度: {similarity:.1f}%")
                return True, orig_msg_id, similarity
            
            return False, None, 0.0
                        
        except Exception as e:
            logger.debug(f"比较视觉哈希时出错: {e}")
            return False, None, 0.0
    
    def _parse_visual_hash(self, stored_visual_hash) -> Optional[dict]:
        """解析存储的视觉哈希 - 简化嵌套逻辑"""
        if isinstance(stored_visual_hash, str):
            try:
                return json.loads(stored_visual_hash)
            except:
                try:
                    return eval(stored_visual_hash)  # 兼容旧格式
                except:
                    return None
        return stored_visual_hash
    
    async def _check_media_duplicate(self, media_hash: Optional[str], 
                                    combined_media_hash: Optional[str],
                                    message_time: datetime,
                                    message_id: Optional[int] = None) -> Tuple[bool, Optional[int]]:
        """检查媒体重复（跨频道，使用Redis）"""
        if not media_hash and not combined_media_hash:
            return False, None
            
        try:
            # 确保时间没有时区信息
            if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
                message_time = message_time.replace(tzinfo=None)
            
            # 计算时间阈值
            time_threshold = message_time - timedelta(hours=self.media_cache_hours)
            
            # 检查媒体哈希重复
            duplicate_keys = []
            
            # 检查单个媒体哈希
            if media_hash:
                duplicates = self.redis_store.find_duplicate_by_hash(media_hash)
                duplicate_keys.extend(duplicates)
            
            # 检查组合媒体哈希
            if combined_media_hash:
                duplicates = self.redis_store.find_duplicate_by_hash(combined_media_hash)
                duplicate_keys.extend(duplicates)
            
            # 检查重复消息是否在时间窗口内且不是被拒绝的
            for dup_key in duplicate_keys:
                result = self._check_single_media_duplicate(
                    dup_key, message_id, time_threshold, media_hash, combined_media_hash
                )
                if result[0]:  # is_duplicate
                    return result
                
            return False, None
            
        except Exception as e:
            logger.error(f"检查媒体重复时出错: {e}")
            return False, None
    
    def _check_single_media_duplicate(self, dup_key: str, message_id: Optional[int], 
                                     time_threshold: datetime, media_hash: Optional[str], 
                                     combined_media_hash: Optional[str]) -> Tuple[bool, Optional[int]]:
        """检查单个媒体重复 - 消除嵌套的辅助方法"""
        try:
            if ':' not in dup_key:
                return False, None
            
            channel_id, dup_message_id = dup_key.split(':', 1)
            dup_message_id = int(dup_message_id)
            
            # 排除当前消息本身
            if message_id is not None and dup_message_id == message_id:
                return False, None
            
            # 获取重复消息的详细信息（静默模式，避免产生不必要的警告）
            dup_msg_data = self.redis_store.get_message(channel_id, dup_message_id, silent=True)
            if not dup_msg_data:
                # 消息不存在，从哈希索引中清理这个无效引用
                self._cleanup_invalid_hash_reference(dup_key, media_hash, combined_media_hash)
                return False, None
            
            # 检查状态（不考虑已拒绝的消息）
            if dup_msg_data.get('status') == 'rejected':
                return False, None
            
            # 检查时间是否在窗口内
            dup_msg = MessageCompat(dup_msg_data)
            if dup_msg.created_at >= time_threshold:
                logger.info(f"检测到媒体重复: 与消息ID {dup_message_id} 的媒体相同")
                return True, dup_message_id
            
            return False, None
                        
        except Exception as e:
            logger.debug(f"解析重复消息失败: {e}")
            return False, None
    
    def _cleanup_invalid_hash_reference(self, dup_key: str, media_hash: Optional[str], 
                                       combined_media_hash: Optional[str]):
        """清理无效哈希索引引用 - 分离清理逻辑"""
        logger.debug(f"清理无效哈希索引引用: {dup_key}")
        pipe = self.redis_store.redis.pipeline()
        if media_hash:
            pipe.srem(f"msg:hash:media:{media_hash}", dup_key)
        if combined_media_hash:
            pipe.srem(f"msg:hash:media:{combined_media_hash}", dup_key)
        pipe.execute()
    
    async def _check_text_duplicate(self, content: str, source_channel: Optional[str],
                                   message_time: datetime,
                                   message_id: Optional[int] = None) -> Tuple[bool, Optional[int]]:
        """检查文本重复（跨频道，使用jieba分词，基于Redis）"""
        try:
            # 确保时间没有时区信息
            if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
                message_time = message_time.replace(tzinfo=None)
            
            # 设置时间窗口
            time_start = message_time - timedelta(minutes=self.text_time_window_minutes)
            time_end = message_time + timedelta(minutes=self.text_time_window_minutes)
            
            # 获取时间窗口内的所有消息
            recent_messages = await self._get_recent_messages_with_content(
                time_start, time_end, message_id
            )
            
            # 检查相似度
            for msg_data in recent_messages:
                msg_content = msg_data.get('content')
                if not msg_content:
                    continue
                
                # 计算多种相似度
                text_similarity = self._calculate_text_similarity(content, msg_content)
                jieba_similarity = self._calculate_jieba_similarity(content, msg_content)
                
                # 取最高相似度
                max_similarity = max(text_similarity, jieba_similarity)
                
                logger.debug(f"相似度检查: {max_similarity:.2f} (文本: {text_similarity:.2f}, jieba: {jieba_similarity:.2f})")
                
                if max_similarity >= self.text_similarity_threshold:
                    orig_msg_id = msg_data.get('message_id')
                    logger.info(f"发现文本重复消息，相似度: {max_similarity:.2f}")
                    return True, orig_msg_id
            
            return False, None
            
        except Exception as e:
            logger.error(f"检查文本重复时出错: {e}")
            return False, None
    
    def _clean_text(self, text: str) -> str:
        """清理文本，去除标签、链接等干扰因素"""
        if not text:
            return ""
        
        cleaned = text
        
        # 移除所有标签和链接
        for pattern in self.tag_patterns:
            cleaned = pattern.sub(' ', cleaned)
        
        # 去除多余空白
        cleaned = ' '.join(cleaned.split())
        
        return cleaned.strip()
    
    def _extract_core_content(self, text: str) -> str:
        """提取核心内容（主要是新闻内容部分）"""
        if not text:
            return ""
        
        # 按行分割
        lines = text.split('\n')
        
        # 找到主要内容（通常是最长的段落）
        main_content = []
        for line in lines:
            line = line.strip()
            if len(line) > 50:  # 超过50个字符的行可能是主要内容
                main_content.append(line)
        
        # 如果没有长段落，使用前几行
        if not main_content:
            main_content = [line.strip() for line in lines[:5] if line.strip()]
        
        return '\n'.join(main_content)
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度（使用SequenceMatcher）"""
        if not text1 or not text2:
            return 0.0
        
        # 清理文本
        clean_text1 = self._clean_text(text1)
        clean_text2 = self._clean_text(text2)
        
        # 如果清理后的文本太短，使用原始文本的核心内容
        if len(clean_text1) < 20 or len(clean_text2) < 20:
            clean_text1 = self._clean_text(self._extract_core_content(text1))
            clean_text2 = self._clean_text(self._extract_core_content(text2))
        
        return SequenceMatcher(None, clean_text1, clean_text2).ratio()
    
    def _calculate_jieba_similarity(self, text1: str, text2: str) -> float:
        """使用jieba分词和哈希计算相似度（对中文更友好）"""
        if not text1 or not text2:
            return 0.0
        
        # 提取核心内容
        core1 = self._extract_core_content(text1)
        core2 = self._extract_core_content(text2)
        
        # 分词
        words1 = set(jieba.cut(self._clean_text(core1)))
        words2 = set(jieba.cut(self._clean_text(core2)))
        
        # 过滤停用词和短词
        words1 = {w for w in words1 if len(w) > 1}
        words2 = {w for w in words2 if len(w) > 1}
        
        if not words1 or not words2:
            return 0.0
        
        # 计算Jaccard相似度
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    async def _get_recent_messages_with_visual_hash(self, time_threshold: datetime, 
                                                   exclude_message_id: Optional[int] = None) -> List[Dict]:
        """获取有视觉哈希的最近消息"""
        try:
            messages = []
            
            # 获取所有频道
            from app.services.unified_channel_service import unified_channel_service
            channel_configs = await unified_channel_service.get_all_channels(active_only=True)
            
            for channel_config in channel_configs:
                channel_id = channel_config.get('channel_id')
                if not channel_id:
                    continue
                
                channel_messages = self._get_channel_visual_messages(
                    channel_id, time_threshold, exclude_message_id
                )
                messages.extend(channel_messages)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取视觉哈希消息失败: {e}")
            return []
    
    def _get_channel_visual_messages(self, channel_id: str, time_threshold: datetime, 
                                    exclude_message_id: Optional[int]) -> List[Dict]:
        """获取单个频道的视觉哈希消息 - 消除嵌套的辅助方法"""
        try:
            # 获取该频道最近的消息（限制数量以提高性能）
            channel_messages = self.redis_store.get_messages_by_channel(channel_id, limit=500)
            messages = []
            
            for msg_data in channel_messages:
                if self._is_valid_visual_message(msg_data, time_threshold, exclude_message_id):
                    messages.append(msg_data)
            
            return messages
                            
        except Exception as e:
            logger.debug(f"处理频道 {channel_id} 失败: {e}")
            return []
    
    def _is_valid_visual_message(self, msg_data: dict, time_threshold: datetime, 
                                exclude_message_id: Optional[int]) -> bool:
        """检查消息是否符合视觉检测条件 - 简化条件判断"""
        try:
            # 检查是否有视觉哈希
            if not msg_data.get('visual_hash'):
                return False
            
            # 检查状态
            if msg_data.get('status') == 'rejected':
                return False
            
            # 检查时间
            msg = MessageCompat(msg_data)
            if msg.created_at < time_threshold:
                return False
            
            # 排除当前消息
            if exclude_message_id and msg_data.get('telegram_message_id') == exclude_message_id:
                return False
            
            return True
                            
        except Exception as e:
            logger.debug(f"处理消息失败: {e}")
            return False
    
    async def _get_recent_messages_with_content(self, time_start: datetime, time_end: datetime,
                                               exclude_message_id: Optional[int] = None) -> List[Dict]:
        """获取有文本内容的最近消息"""
        try:
            messages = []
            
            # 由于Redis没有复杂时间范围查询，我们遍历最近的消息
            all_channels = self.redis_store.redis.keys("msg:idx:*")
            
            for channel_key in all_channels:
                if not self._is_valid_channel_key(channel_key):
                    continue
                    
                channel_id = channel_key.split(':', 2)[2]
                channel_messages = self._get_channel_content_messages(
                    channel_key, channel_id, time_start, time_end, exclude_message_id
                )
                messages.extend(channel_messages)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取文本消息失败: {e}")
            return []
    
    def _is_valid_channel_key(self, channel_key: str) -> bool:
        """检查是否是有效的频道键 - 消除特殊情况判断"""
        return (channel_key.startswith('msg:idx:') and 
                not ':' in channel_key.split(':', 2)[2])
    
    def _get_channel_content_messages(self, channel_key: str, channel_id: str,
                                     time_start: datetime, time_end: datetime,
                                     exclude_message_id: Optional[int]) -> List[Dict]:
        """获取单个频道的文本消息 - 消除嵌套的辅助方法"""
        messages = []
        
        # 获取最近200条消息（覆盖更大时间范围）
        recent_msg_ids = self.redis_store.redis.zrevrange(channel_key, 0, 199)
        
        for msg_id in recent_msg_ids:
            msg_data = self._get_and_validate_content_message(
                channel_id, int(msg_id), time_start, time_end, exclude_message_id
            )
            if msg_data:
                messages.append(msg_data)
        
        return messages
    
    def _get_and_validate_content_message(self, channel_id: str, msg_id: int,
                                         time_start: datetime, time_end: datetime,
                                         exclude_message_id: Optional[int]) -> Optional[Dict]:
        """获取并验证单个文本消息 - 简化验证逻辑"""
        try:
            msg_data = self.redis_store.get_message(channel_id, msg_id, silent=True)
            if not msg_data:
                return None
            
            # 检查是否有文本内容
            if not msg_data.get('content'):
                return None
            
            # 检查状态
            if msg_data.get('status') == 'rejected':
                return None
            
            # 检查时间范围
            msg = MessageCompat(msg_data)
            if not (time_start <= msg.created_at <= time_end):
                return None
            
            # 排除当前消息
            if exclude_message_id and msg_data.get('message_id') == exclude_message_id:
                return None
            
            return msg_data
                            
        except Exception as e:
            logger.debug(f"处理消息失败: {e}")
            return None
    
    def _get_detection_method_details(self, duplicate_type: str) -> Dict[str, any]:
        """获取检测方法的详细信息"""
        details = {
            'visual': {
                'method': '视觉相似度检测',
                'description': '使用感知哈希算法比较图像相似度',
                'window_hours': self.visual_cache_hours
            },
            'media': {
                'method': '媒体哈希检测', 
                'description': '比较媒体文件的SHA256哈希值',
                'window_hours': self.media_cache_hours
            },
            'text': {
                'method': '文本相似度检测',
                'description': 'jieba分词 + SequenceMatcher算法',
                'threshold': self.text_similarity_threshold,
                'window_hours': self.text_time_window_minutes / 60
            }
        }
        
        return details.get(duplicate_type, {'method': 'unknown', 'description': '未知检测方法'})
    
    def _get_checked_methods(self, media_hash: Optional[str], combined_media_hash: Optional[str],
                            visual_hashes: Optional[dict], content: Optional[str]) -> List[str]:
        """获取已检查的方法列表"""
        methods = []
        
        if visual_detector and visual_hashes:
            methods.append('visual_similarity')
        
        if media_hash or combined_media_hash:
            methods.append('media_hash')
        
        if content and content.strip():
            methods.append('text_similarity')
        
        return methods
    
    async def validate_config(self) -> bool:
        """验证配置是否有效"""
        try:
            # 检查基本配置参数
            if self.media_cache_hours <= 0:
                logger.error("media_cache_hours 必须大于0")
                return False
            
            if not (0.0 < self.text_similarity_threshold <= 1.0):
                logger.error("text_similarity_threshold 必须在 (0, 1] 范围内")
                return False
            
            if self.text_time_window_minutes <= 0:
                logger.error("text_time_window_minutes 必须大于0")
                return False
            
            return True
        except Exception as e:
            logger.error(f"验证配置失败: {e}")
            return False


# 创建默认实例
duplicate_detector_filter = DuplicateDetectorFilter()