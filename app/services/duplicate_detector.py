"""
整合的消息重复检测服务
优先媒体哈希跨频道检测，其次jieba文本相似度检测
"""
import warnings
# 抑制jieba的pkg_resources弃用警告
warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import hashlib
import re
import logging
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import jieba
from app.storage.redis_store import get_redis_message_store

# 导入视觉相似度检测器
try:
    from app.services.visual_similarity import visual_detector
except ImportError:
    visual_detector = None

logger = logging.getLogger(__name__)

class DuplicateDetector:
    """整合的消息重复检测器：媒体哈希 + jieba文本相似度"""
    
    def __init__(self):
        # 媒体检测参数（增加检测窗口）
        self.media_cache_hours = 72  # 媒体检测72小时窗口
        
        # 文本检测参数（调整相似度阈值和时间窗口）
        self.text_similarity_threshold = 0.75  # 75%相似度阈值（更严格避免误判）
        self.text_time_window_minutes = 2880  # 48小时时间窗口 (2880分钟)
        
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
    
    def calculate_media_hash(self, media_data: bytes) -> str:
        """计算媒体文件的哈希值"""
        return hashlib.sha256(media_data).hexdigest()
    
    def calculate_combined_hash(self, media_list: List[Dict]) -> str:
        """计算组合媒体的哈希值"""
        # 将所有媒体的哈希值组合起来
        combined = ""
        for media in sorted(media_list, key=lambda x: x.get('index', 0)):
            if media.get('hash'):
                combined += media['hash']
        
        if combined:
            return hashlib.sha256(combined.encode()).hexdigest()
        return None
    
    async def is_duplicate_message(self, 
                                  source_channel: str,
                                  media_hash: Optional[str] = None, 
                                  combined_media_hash: Optional[str] = None,
                                  content: Optional[str] = None,
                                  message_time: Optional[datetime] = None,
                                  message_id: Optional[int] = None,
                                  media_data: Optional[bytes] = None,
                                  visual_hashes: Optional[dict] = None,
                                  db=None) -> Tuple[bool, Optional[int], str]:
        """
        整合的重复消息检测：优先视觉相似度，其次媒体哈希，最后jieba文本相似度
        
        Args:
            source_channel: 源频道
            media_hash: 单个媒体的哈希值
            combined_media_hash: 组合媒体的哈希值
            content: 消息文本内容
            message_time: 消息时间
            message_id: 消息ID
            media_data: 媒体文件的二进制数据（用于视觉相似度检测）
            visual_hashes: 预计算的视觉哈希值
            db: 数据库会话
            
        Returns:
            (is_duplicate, original_message_id, duplicate_type)
        """
        if message_time is None:
            message_time = datetime.utcnow()
        # 确保时间没有时区信息（naive datetime）
        if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
            message_time = message_time.replace(tzinfo=None)
        
        # 最优先进行视觉相似度检测（如果有图片数据）
        if visual_detector and (media_data or visual_hashes):
            logger.debug(f"开始视觉相似度检测，检测窗口: 96小时")
            is_visual_dup, orig_id, similarity = await self._check_visual_duplicate(
                media_data, visual_hashes, message_time, message_id, db
            )
            if is_visual_dup:
                logger.info(f"✅ 检测到视觉相似图片，相似度: {similarity:.1f}%，原消息ID: {orig_id}")
                return True, orig_id, "visual"
            else:
                logger.debug(f"视觉相似度检测未发现重复")
            
        # 其次进行媒体哈希检测（跨频道）
        if media_hash or combined_media_hash:
            logger.debug(f"开始媒体哈希检测，检测窗口: {self.media_cache_hours}小时")
            is_media_dup, orig_id = await self._check_media_duplicate(
                media_hash, combined_media_hash, message_time, message_id, db
            )
            if is_media_dup:
                logger.info(f"✅ 检测到媒体哈希重复，原消息ID: {orig_id}")
                return True, orig_id, "media"
            else:
                logger.debug(f"媒体哈希检测未发现重复")
        
        # 其次进行文本相似度检测（跨频道）
        if content and content.strip():
            logger.debug(f"开始文本相似度检测，阈值: {self.text_similarity_threshold:.0%}，检测窗口: {self.text_time_window_minutes//60}小时")
            is_text_dup, orig_id = await self._check_text_duplicate(
                content, source_channel, message_time, message_id, db
            )
            if is_text_dup:
                logger.info(f"✅ 检测到文本相似重复，原消息ID: {orig_id}")
                return True, orig_id, "text"
            else:
                logger.debug(f"文本相似度检测未发现重复（检查了{len(content.strip())}字符的内容）")
        
        logger.debug(f"✅ 去重检测完成，未发现重复")
        return False, None, "none"
        
        # 如果没有传入db会话，创建一个
        use_external_db = db is not None
        if not use_external_db:
            db = AsyncSessionLocal()
        
        try:
            result = await self.is_duplicate_message(
                source_channel, media_hash, combined_media_hash, content, message_time, db
            )
            return result[0]  # 只返回是否重复
        except Exception as e:
            logger.error(f"检测重复消息时出错: {e}")
            return False
        finally:
            if not use_external_db:
                await db.close()
    
    async def _check_visual_duplicate(self, media_data: Optional[bytes],
                                     visual_hashes: Optional[dict],
                                     message_time: datetime,
                                     message_id: Optional[int] = None,
                                     db: Optional[AsyncSession] = None) -> Tuple[bool, Optional[int], float]:
        """
        检查视觉相似度重复
        
        Args:
            media_data: 媒体文件数据
            visual_hashes: 预计算的视觉哈希
            message_time: 消息时间
            message_id: 当前消息ID
            db: 数据库会话
            
        Returns:
            (是否重复, 原始消息ID, 相似度分数)
        """
        if not visual_detector:
            return False, None, 0.0
        
        # 如果有媒体数据但没有视觉哈希，先计算
        if media_data and not visual_hashes:
            visual_hashes = visual_detector.calculate_perceptual_hashes(media_data)
        
        if not visual_hashes:
            return False, None, 0.0
        
        use_external_db = db is not None
        if not use_external_db:
            db = AsyncSessionLocal()
        
        try:
            # 确保时间没有时区信息
            if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
                message_time = message_time.replace(tzinfo=None)
            
            # 查询时间范围内的消息（扩大视觉相似度检测窗口）
            time_threshold = message_time - timedelta(hours=96)  # 96小时窗口
            
            conditions = [
                Message.created_at >= time_threshold,
                Message.status != "rejected",
                Message.visual_hash.isnot(None)  # 只查询有视觉哈希的消息
            ]
            
            # 排除当前消息
            if message_id is not None:
                conditions.append(Message.id != message_id)
            
            result = await db.execute(
                select(Message).where(and_(*conditions)).order_by(Message.created_at.desc())
            )
            messages = result.scalars().all()
            
            # 检查每个历史消息的视觉相似度
            for msg in messages:
                try:
                    stored_hashes = eval(msg.visual_hash)  # 将字符串转换回字典
                    is_similar, similarity = visual_detector.is_visually_similar(visual_hashes, stored_hashes)
                    if is_similar:
                        logger.info(f"发现视觉相似图片，消息ID: {msg.id}, 相似度: {similarity:.1f}%")
                        return True, msg.id, similarity
                except Exception as e:
                    logger.debug(f"比较视觉哈希时出错: {e}")
            
            return False, None, 0.0
            
        except Exception as e:
            logger.error(f"检查视觉重复时出错: {e}")
            return False, None, 0.0
        finally:
            if not use_external_db:
                await db.close()
    
    async def _check_media_duplicate(self, media_hash: Optional[str], 
                                    combined_media_hash: Optional[str],
                                    message_time: datetime,
                                    message_id: Optional[int] = None,
                                    db: Optional[AsyncSession] = None) -> Tuple[bool, Optional[int]]:
        """检查媒体重复（跨频道）"""
        if not media_hash and not combined_media_hash:
            return False, None
            
        use_external_db = db is not None
        if not use_external_db:
            db = AsyncSessionLocal()
            
        try:
            # 确保时间没有时区信息
            if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
                message_time = message_time.replace(tzinfo=None)
            
            # 查询时间范围（跨所有频道）
            time_threshold = message_time - timedelta(hours=self.media_cache_hours)
            
            # 构建查询条件
            conditions = [
                Message.created_at >= time_threshold,
                Message.status != "rejected"  # 不考虑已拒绝的消息
            ]
            
            # 排除当前消息本身
            if message_id is not None:
                conditions.append(Message.id != message_id)
            
            # 媒体哈希匹配条件
            hash_conditions = []
            if media_hash:
                hash_conditions.append(Message.media_hash == media_hash)
            if combined_media_hash:
                hash_conditions.append(Message.combined_media_hash == combined_media_hash)
            
            if hash_conditions:
                conditions.append(or_(*hash_conditions))
            
            # 执行查询
            result = await db.execute(
                select(Message).where(and_(*conditions))
            )
            existing_messages = result.scalars().all()
            
            if existing_messages:
                logger.info(f"检测到媒体重复: 与消息ID {existing_messages[0].id} 的媒体相同")
                return True, existing_messages[0].id
                
            return False, None
            
        except Exception as e:
            logger.error(f"检查媒体重复时出错: {e}")
            return False, None
        finally:
            if not use_external_db:
                await db.close()
    
    async def _check_text_duplicate(self, content: str, source_channel: str,
                                   message_time: datetime,
                                   message_id: Optional[int] = None,
                                   db: Optional[AsyncSession] = None) -> Tuple[bool, Optional[int]]:
        """检查文本重复（跨频道，使用jieba分词）"""
        use_external_db = db is not None
        if not use_external_db:
            db = AsyncSessionLocal()
            
        try:
            # 确保时间没有时区信息
            if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
                message_time = message_time.replace(tzinfo=None)
            
            # 设置时间窗口
            time_start = message_time - timedelta(minutes=self.text_time_window_minutes)
            time_end = message_time + timedelta(minutes=self.text_time_window_minutes)
            
            # 构建查询条件
            conditions = [
                Message.created_at >= time_start,
                Message.created_at <= time_end,
                Message.content.isnot(None),  # 有文本内容
                Message.status != "rejected"  # 非拒绝消息
            ]
            
            # 排除当前消息本身
            if message_id is not None:
                conditions.append(Message.id != message_id)
            
            # 查询时间窗口内的所有消息（包括同频道）
            result = await db.execute(
                select(Message).where(and_(*conditions)).order_by(Message.created_at.desc())
            )
            recent_messages = result.scalars().all()
            
            # 检查相似度
            for msg in recent_messages:
                if not msg.content:
                    continue
                
                # 计算多种相似度
                text_similarity = self._calculate_text_similarity(content, msg.content)
                jieba_similarity = self._calculate_jieba_similarity(content, msg.content)
                
                # 取最高相似度
                max_similarity = max(text_similarity, jieba_similarity)
                
                logger.debug(f"相似度检查: {max_similarity:.2f} (文本: {text_similarity:.2f}, jieba: {jieba_similarity:.2f})")
                
                if max_similarity >= self.text_similarity_threshold:
                    logger.info(f"发现文本重复消息，相似度: {max_similarity:.2f}")
                    return True, msg.id
            
            return False, None
            
        except Exception as e:
            logger.error(f"检查文本重复时出错: {e}")
            return False, None
        finally:
            if not use_external_db:
                await db.close()
    
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
    
    def _is_text_similar(self, text1: Optional[str], text2: Optional[str], threshold: float = 0.8) -> bool:
        """简单的文本相似度检查（兼容性方法）"""
        if not text1 or not text2:
            # 如果都为空，认为相似
            return not text1 and not text2
        
        # 简单的相似度计算：基于共同字符的比例
        text1 = text1.strip().lower()
        text2 = text2.strip().lower()
        
        if text1 == text2:
            return True
        
        # 使用新的jieba相似度算法
        jieba_sim = self._calculate_jieba_similarity(text1, text2)
        text_sim = self._calculate_text_similarity(text1, text2)
        return max(jieba_sim, text_sim) >= threshold
    
    async def get_similar_messages(self, 
                                  source_channel: str,
                                  media_hash: Optional[str] = None,
                                  content: Optional[str] = None,
                                  hours: int = 24) -> List[Message]:
        """
        获取相似的历史消息（支持媒体和文本检索）
        
        Args:
            source_channel: 源频道
            media_hash: 媒体哈希值
            content: 文本内容
            hours: 查询多少小时内的消息
            
        Returns:
            相似消息列表
        """
        if not media_hash and not content:
            return []
        
        try:
            async with AsyncSessionLocal() as db:
                time_threshold = datetime.utcnow() - timedelta(hours=hours)
                
                # 构建查询条件
                conditions = [
                    Message.created_at >= time_threshold,
                    Message.status != "rejected"
                ]
                
                # 添加媒体或文本条件
                search_conditions = []
                if media_hash:
                    search_conditions.extend([
                        Message.media_hash == media_hash,
                        Message.combined_media_hash == media_hash
                    ])
                
                if search_conditions:
                    conditions.append(or_(*search_conditions))
                
                result = await db.execute(
                    select(Message).where(and_(*conditions)).order_by(Message.created_at.desc())
                )
                
                messages = result.scalars().all()
                
                # 如果有文本内容，进一步过滤相似文本
                if content and not media_hash:
                    similar_messages = []
                    for msg in messages:
                        if msg.content:
                            similarity = max(
                                self._calculate_text_similarity(content, msg.content),
                                self._calculate_jieba_similarity(content, msg.content)
                            )
                            if similarity >= 0.5:  # 50%以上相似度
                                similar_messages.append(msg)
                    return similar_messages
                
                return messages
                
        except Exception as e:
            logger.error(f"获取相似消息时出错: {e}")
            return []
    
    async def mark_as_duplicate(self, message_id: int, original_message_id: int):
        """
        将消息标记为重复
        
        Args:
            message_id: 重复消息的ID
            original_message_id: 原始消息的ID
        """
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(Message.id == message_id)
                )
                message = result.scalar_one_or_none()
                
                if message:
                    message.status = "rejected"
                    # 重要：去重不意味着是广告，不要改变is_ad状态
                    message.filtered_content = f"[重复消息，原消息ID: {original_message_id}]"
                    message.review_time = datetime.utcnow()
                    message.reviewed_by = "DuplicateDetector"
                    
                    await db.commit()
                    logger.info(f"消息 {message_id} 已被标记为重复")
                    
        except Exception as e:
            logger.error(f"标记重复消息时出错: {e}")