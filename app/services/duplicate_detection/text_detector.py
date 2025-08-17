"""
文本重复检测器
使用jieba分词和文本相似度进行重复检测
"""
import warnings
# 抑制jieba的pkg_resources弃用警告
warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import hashlib
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from difflib import SequenceMatcher
import jieba

logger = logging.getLogger(__name__)


class TextDuplicateDetector:
    """文本重复检测器"""
    
    def __init__(self, redis_store=None, similarity_threshold: float = 0.75, 
                 time_window_minutes: int = 2880):
        self.redis_store = redis_store
        self.similarity_threshold = similarity_threshold
        self.time_window_minutes = time_window_minutes
        
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
    
    async def check_duplicate(self, content: str, source_channel: str,
                             message_time: datetime,
                             message_id: Optional[int] = None) -> Tuple[bool, Optional[int]]:
        """检查文本重复（跨频道，使用Redis）"""
        if not content or not content.strip():
            return False, None
            
        if not self.redis_store:
            return False, None
        
        try:
            # 确保时间没有时区信息
            if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
                message_time = message_time.replace(tzinfo=None)
            
            # 计算时间窗口
            time_start = message_time - timedelta(minutes=self.time_window_minutes)
            time_end = message_time + timedelta(minutes=5)  # 允许5分钟的未来时间差
            
            # 清理和提取核心内容
            cleaned_content = self._clean_text(content)
            core_content = self._extract_core_content(cleaned_content)
            
            if len(core_content) < 10:  # 忽略过短的内容
                return False, None
            
            # 获取时间窗口内的消息
            recent_messages = await self._get_recent_messages_with_content(
                time_start, time_end, message_id
            )
            
            # 检查每个历史消息的文本相似度
            for msg_data in recent_messages:
                try:
                    stored_content = msg_data.get('content', '')
                    if not stored_content:
                        continue
                    
                    # 计算相似度
                    similarity = self._calculate_text_similarity(core_content, stored_content)
                    
                    if similarity >= self.similarity_threshold:
                        orig_msg_id = msg_data.get('message_id')
                        logger.info(f"发现文本相似重复，相似度: {similarity:.1%}，原消息ID: {orig_msg_id}")
                        return True, orig_msg_id
                        
                except Exception as e:
                    logger.debug(f"比较文本相似度时出错: {e}")
                    continue
            
            return False, None
            
        except Exception as e:
            logger.error(f"检查文本重复时出错: {e}")
            return False, None
    
    def _clean_text(self, text: str) -> str:
        """清理文本，移除标签、链接等"""
        if not text:
            return ""
        
        cleaned = text
        for pattern in self.tag_patterns:
            cleaned = pattern.sub(' ', cleaned)
        
        # 移除多余的空白
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    
    def _extract_core_content(self, text: str) -> str:
        """提取核心内容"""
        if not text:
            return ""
        
        # 移除常见的推广后缀
        promo_suffixes = [
            r'订阅频道.*$',
            r'投稿爆料.*$',
            r'商务合作.*$',
            r'联系方式.*$',
            r'点击.*$',
            r'关注.*$',
        ]
        
        core = text
        for suffix in promo_suffixes:
            core = re.sub(suffix, '', core, flags=re.IGNORECASE)
        
        return core.strip()
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（使用jieba分词 + SequenceMatcher）"""
        if not text1 or not text2:
            return 0.0
        
        # 先用jieba计算
        jieba_sim = self._calculate_jieba_similarity(text1, text2)
        
        # 再用SequenceMatcher计算
        seq_sim = SequenceMatcher(None, text1, text2).ratio()
        
        # 取两者的最大值（更敏感）
        return max(jieba_sim, seq_sim)
    
    def _calculate_jieba_similarity(self, text1: str, text2: str) -> float:
        """使用jieba分词计算文本相似度"""
        try:
            # 分词
            words1 = set(jieba.cut(text1))
            words2 = set(jieba.cut(text2))
            
            # 移除过短的词
            words1 = {w for w in words1 if len(w.strip()) > 1}
            words2 = {w for w in words2 if len(w.strip()) > 1}
            
            if not words1 or not words2:
                return 0.0
            
            # 计算交集和并集
            intersection = len(words1 & words2)
            union = len(words1 | words2)
            
            if union == 0:
                return 0.0
            
            # Jaccard相似度
            return intersection / union
            
        except Exception as e:
            logger.debug(f"jieba相似度计算失败: {e}")
            return 0.0
    
    def calculate_text_hash(self, content: str) -> str:
        """计算文本哈希"""
        if not content:
            return ""
        return hashlib.md5(content.encode()).hexdigest()
    
    async def _get_recent_messages_with_content(self, time_start: datetime, time_end: datetime,
                                               exclude_message_id: Optional[int] = None) -> List:
        """获取指定时间范围内有内容的消息"""
        if not self.redis_store:
            return []
        
        try:
            # 格式化时间
            time_start_str = time_start.strftime('%Y-%m-%dT%H:%M:%S')
            time_end_str = time_end.strftime('%Y-%m-%dT%H:%M:%S')
            
            # 扫描所有消息键
            message_keys = self.redis_store.redis_client.keys("msg:*")
            
            messages_with_content = []
            for key in message_keys:
                try:
                    # 获取消息数据
                    message_data = self.redis_store.redis_client.hgetall(key)
                    if not message_data:
                        continue
                    
                    # 检查是否有内容
                    content = message_data.get('content', '')
                    if not content or len(content.strip()) < 10:
                        continue
                    
                    # 检查时间条件
                    created_at = message_data.get('created_at', '')
                    if not (time_start_str <= created_at <= time_end_str):
                        continue
                    
                    # 排除当前消息
                    msg_id = message_data.get('message_id')
                    if exclude_message_id and str(msg_id) == str(exclude_message_id):
                        continue
                    
                    # 排除被拒绝的消息
                    status = message_data.get('status', '')
                    if status == 'rejected':
                        continue
                    
                    messages_with_content.append(message_data)
                    
                except Exception as e:
                    logger.debug(f"处理消息键 {key} 时出错: {e}")
                    continue
            
            return messages_with_content[:50]  # 限制检查数量
            
        except Exception as e:
            logger.error(f"获取有内容的消息失败: {e}")
            return []