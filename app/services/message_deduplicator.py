"""
消息去重服务
使用多种算法智能识别和去除相似的重复消息
"""
import warnings
# 抑制jieba的pkg_resources弃用警告
warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import hashlib
import re
import logging
from typing import Tuple, Optional, List
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import jieba
from app.storage.redis_store import get_redis_message_store

logger = logging.getLogger(__name__)

class MessageDeduplicator:
    """消息去重器"""
    
    def __init__(self):
        # 相似度阈值
        self.similarity_threshold = 0.85  # 85%相似度
        self.time_window_minutes = 30  # 30分钟时间窗口
        
        # 需要过滤的常见广告标签和频道标记
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
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度"""
        if not text1 or not text2:
            return 0.0
        
        # 清理文本
        clean_text1 = self._clean_text(text1)
        clean_text2 = self._clean_text(text2)
        
        # 如果清理后的文本太短，使用原始文本的核心内容
        if len(clean_text1) < 20 or len(clean_text2) < 20:
            clean_text1 = self._extract_core_content(text1)
            clean_text2 = self._extract_core_content(text2)
            clean_text1 = self._clean_text(clean_text1)
            clean_text2 = self._clean_text(clean_text2)
        
        # 计算相似度
        return SequenceMatcher(None, clean_text1, clean_text2).ratio()
    
    def _calculate_hash_similarity(self, text1: str, text2: str) -> float:
        """使用分词和哈希计算相似度（对中文更友好）"""
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
    
    async def is_duplicate(self, content: str, source_channel: str, 
                          message_time: datetime) -> Tuple[bool, Optional[str]]:
        """
        检查消息是否为重复消息
        返回: (是否重复, 原始消息Key)
        """
        try:
            redis_store = get_redis_message_store()
            
            # 设置时间窗口
            time_start = message_time - timedelta(minutes=self.time_window_minutes)
            time_end = message_time + timedelta(minutes=self.time_window_minutes)
            
            # 获取所有消息进行筛选检查
            all_messages = redis_store.get_all_messages(limit=1000)  # 限制数量避免内存问题
            
            # 筛选时间窗口内的不同频道消息
            recent_messages = []
            for msg in all_messages:
                if not msg.get('content'):
                    continue
                    
                # 检查时间和频道
                msg_time_str = msg.get('created_at')
                msg_channel = msg.get('source_channel', '')
                
                if not msg_time_str or msg_channel == source_channel:
                    continue
                
                try:
                    msg_time = datetime.fromisoformat(msg_time_str.replace('Z', '+00:00'))
                    if time_start <= msg_time <= time_end:
                        recent_messages.append(msg)
                except Exception:
                    continue
            
            # 检查相似度
            for msg in recent_messages:
                msg_content = msg.get('content', '')
                
                # 计算多种相似度
                text_similarity = self._calculate_similarity(content, msg_content)
                hash_similarity = self._calculate_hash_similarity(content, msg_content)
                
                # 取最高相似度
                max_similarity = max(text_similarity, hash_similarity)
                
                logger.debug(f"相似度检查: {max_similarity:.2f} (文本: {text_similarity:.2f}, 哈希: {hash_similarity:.2f})")
                
                if max_similarity >= self.similarity_threshold:
                    msg_key = f"{msg.get('source_channel')}:{msg.get('message_id')}"
                    logger.info(f"发现重复消息，相似度: {max_similarity:.2f}")
                    return True, msg_key
            
            return False, None
            
        except Exception as e:
            logger.error(f"检查重复消息时出错: {e}")
            return False, None
    
    async def find_similar_messages(self, content: str, source_channel: str,
                                   message_time: datetime, limit: int = 5) -> List[dict]:
        """
        查找相似的消息
        返回相似消息列表，包含相似度信息
        """
        similar_messages = []
        
        try:
            redis_store = get_redis_message_store()
            
            # 扩大时间窗口用于分析
            time_start = message_time - timedelta(hours=2)
            time_end = message_time + timedelta(hours=2)
            
            # 获取所有消息进行筛选检查
            all_messages = redis_store.get_all_messages(limit=2000)  # 扩大查询范围
            
            # 筛选时间窗口内的不同频道消息
            filtered_messages = []
            for msg in all_messages:
                if not msg.get('content'):
                    continue
                    
                # 检查时间和频道
                msg_time_str = msg.get('created_at')
                msg_channel = msg.get('source_channel', '')
                
                if not msg_time_str or msg_channel == source_channel:
                    continue
                
                try:
                    msg_time = datetime.fromisoformat(msg_time_str.replace('Z', '+00:00'))
                    if time_start <= msg_time <= time_end:
                        filtered_messages.append(msg)
                except Exception:
                    continue
            
            # 计算相似度并排序
            for msg in filtered_messages:
                msg_content = msg.get('content', '')
                
                text_similarity = self._calculate_similarity(content, msg_content)
                hash_similarity = self._calculate_hash_similarity(content, msg_content)
                max_similarity = max(text_similarity, hash_similarity)
                
                if max_similarity >= 0.5:  # 50%以上的相似度才记录
                    similar_messages.append({
                        'message_key': f"{msg.get('source_channel')}:{msg.get('message_id')}",
                        'channel': msg.get('source_channel'),
                        'content': msg_content[:100] + '...' if len(msg_content) > 100 else msg_content,
                        'similarity': max_similarity,
                        'created_at': msg.get('created_at')
                    })
            
            # 按相似度排序
            similar_messages.sort(key=lambda x: x['similarity'], reverse=True)
            
            return similar_messages[:limit]
            
        except Exception as e:
            logger.error(f"查找相似消息时出错: {e}")
            return []

# 全局消息去重器实例
message_deduplicator = MessageDeduplicator()