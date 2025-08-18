"""
尾部特征提取器
自动分析尾部文本的各种特征，为AI过滤提供量化数据
"""
import re
import logging
from typing import Dict, List, Optional
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

class TailFeatureExtractor:
    """尾部文本特征提取器"""
    
    def __init__(self):
        # 动作词汇
        self.action_words = {
            '订阅', '加入', '关注', '点击', '扫码', '添加',
            '联系', '咨询', '合作', '对接', '投稿', '爆料', 
            '澄清', '举报', '提供', '进群', '下载', '获取',
            '领取', '免费', '报名', '申请', '注册'
        }
        
        # 商业词汇
        self.business_words = {
            '商务', '代理', '招商', '销售', '推广', '营销',
            '合作', '代理', '加盟', '投资', '赚钱', '盈利',
            '收益', '佣金', '提成', '分润', '返现'
        }
        
        # 联系方式模式
        self.contact_patterns = [
            r'@\w+',  # Telegram用户名
            r't\.me/\w+',  # Telegram链接
            r'https?://[^\s]+',  # 网址链接
            r'\+?\d{10,15}',  # 电话号码
            r'微信[：:]\s*\w+',  # 微信号
            r'QQ[：:]\s*\d+',  # QQ号
            r'邮箱[：:]\s*\w+@\w+\.\w+'  # 邮箱
        ]
        
        # 表情符号范围
        self.emoji_pattern = r'[😀-🙏🌀-🗿🚀-🛿🏴-🏿]|[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]'
        
        # 初始化AI模型（如果可用）
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """加载sentence-transformers模型"""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            logger.info("✅ 特征提取器AI模型加载成功")
        except Exception as e:
            logger.warning(f"⚠️ AI模型加载失败: {e}")
    
    def extract_features(self, text: str) -> Dict:
        """
        提取文本的所有特征
        
        Args:
            text: 尾部文本
            
        Returns:
            包含各种特征的字典
        """
        if not text:
            return self._empty_features()
        
        logger.debug(f"📊 提取特征 - 文本长度: {len(text)}")
        
        features = {
            # 基础特征
            "text_length": len(text),
            "line_count": text.count('\n') + 1,
            "word_count": len(text.split()),
            "char_count": len(text),
            
            # 链接和联系方式
            "has_telegram_link": self._has_telegram_link(text),
            "has_contact": self._has_contact_info(text),
            "link_count": self._count_links(text),
            "contact_count": self._count_contacts(text),
            
            # 动作和商业词汇
            "action_words": self._extract_action_words(text),
            "business_words": self._extract_business_words(text),
            "action_word_count": len(self._extract_action_words(text)),
            "business_word_count": len(self._extract_business_words(text)),
            
            # 表情符号
            "emoji_count": self._count_emojis(text),
            "emoji_density": self._calculate_emoji_density(text),
            
            # 结构特征
            "has_separators": self._has_separators(text),
            "bullet_points": self._count_bullet_points(text),
            "has_uppercase": any(c.isupper() for c in text),
            "uppercase_ratio": self._calculate_uppercase_ratio(text),
            
            # 特殊模式
            "has_channel_mention": bool(re.search(r'频道|channel', text, re.I)),
            "has_group_mention": bool(re.search(r'群|group|讨论', text, re.I)),
            "has_urgency": self._detect_urgency(text),
            
            # 语言特征
            "chinese_char_ratio": self._calculate_chinese_ratio(text),
            "punctuation_count": self._count_punctuation(text)
        }
        
        logger.debug(f"提取到 {len(features)} 个特征")
        return features
    
    def calculate_scores(self, text: str, features: Optional[Dict] = None) -> Dict:
        """
        计算语义得分
        
        Args:
            text: 文本内容
            features: 已提取的特征（可选）
            
        Returns:
            包含各种得分的字典
        """
        if features is None:
            features = self.extract_features(text)
        
        # 计算推广得分 (0-1)
        promotion_score = self._calculate_promotion_score(text, features)
        
        # 计算商业化得分 (0-1)
        commercial_score = self._calculate_commercial_score(text, features)
        
        # 计算相关性得分 (与正文的相关性，尾部通常较低)
        relevance_score = self._calculate_relevance_score(text, features)
        
        scores = {
            "promotion_score": round(promotion_score, 3),
            "commercial_score": round(commercial_score, 3),
            "relevance_score": round(relevance_score, 3),
            "overall_score": round((promotion_score + commercial_score) / 2, 3)
        }
        
        logger.debug(f"计算得分: {scores}")
        return scores
    
    def _empty_features(self) -> Dict:
        """返回空特征字典"""
        return {
            "text_length": 0,
            "line_count": 0,
            "word_count": 0,
            "char_count": 0,
            "has_telegram_link": False,
            "has_contact": False,
            "link_count": 0,
            "contact_count": 0,
            "action_words": [],
            "business_words": [],
            "action_word_count": 0,
            "business_word_count": 0,
            "emoji_count": 0,
            "emoji_density": 0.0,
            "has_separators": False,
            "bullet_points": 0,
            "has_uppercase": False,
            "uppercase_ratio": 0.0,
            "has_channel_mention": False,
            "has_group_mention": False,
            "has_urgency": False,
            "chinese_char_ratio": 0.0,
            "punctuation_count": 0
        }
    
    def _has_telegram_link(self, text: str) -> bool:
        """检测是否包含Telegram链接"""
        patterns = [r'@\w+', r't\.me/\w+', r'https://t\.me/']
        return any(re.search(pattern, text, re.I) for pattern in patterns)
    
    def _has_contact_info(self, text: str) -> bool:
        """检测是否包含联系方式"""
        return any(re.search(pattern, text, re.I) for pattern in self.contact_patterns)
    
    def _count_links(self, text: str) -> int:
        """统计链接数量"""
        count = 0
        for pattern in self.contact_patterns[:3]:  # 只统计链接类型的
            count += len(re.findall(pattern, text, re.I))
        return count
    
    def _count_contacts(self, text: str) -> int:
        """统计联系方式数量"""
        count = 0
        for pattern in self.contact_patterns:
            count += len(re.findall(pattern, text, re.I))
        return count
    
    def _extract_action_words(self, text: str) -> List[str]:
        """提取动作词汇"""
        found_words = []
        for word in self.action_words:
            if word in text:
                found_words.append(word)
        return found_words
    
    def _extract_business_words(self, text: str) -> List[str]:
        """提取商业词汇"""
        found_words = []
        for word in self.business_words:
            if word in text:
                found_words.append(word)
        return found_words
    
    def _count_emojis(self, text: str) -> int:
        """统计表情符号数量"""
        return len(re.findall(self.emoji_pattern, text))
    
    def _calculate_emoji_density(self, text: str) -> float:
        """计算表情符号密度"""
        if not text:
            return 0.0
        emoji_count = self._count_emojis(text)
        return emoji_count / len(text)
    
    def _has_separators(self, text: str) -> bool:
        """检测是否有分隔符"""
        separators = ['---', '———', '===', '***', '~~~', '▔' * 3]
        return any(sep in text for sep in separators)
    
    def _count_bullet_points(self, text: str) -> int:
        """统计项目符号数量"""
        patterns = [r'^[•·▪▫‣⁃]\s', r'^\d+\.\s', r'^[a-zA-Z]\.\s', r'^[-*]\s']
        count = 0
        for line in text.split('\n'):
            for pattern in patterns:
                if re.search(pattern, line.strip()):
                    count += 1
                    break
        return count
    
    def _calculate_uppercase_ratio(self, text: str) -> float:
        """计算大写字母比例"""
        if not text:
            return 0.0
        uppercase_count = sum(1 for c in text if c.isupper())
        letter_count = sum(1 for c in text if c.isalpha())
        return uppercase_count / letter_count if letter_count > 0 else 0.0
    
    def _detect_urgency(self, text: str) -> bool:
        """检测紧急性词汇"""
        urgency_words = ['紧急', '急', '火速', '立即', '马上', '快速', '限时', '抢先']
        return any(word in text for word in urgency_words)
    
    def _calculate_chinese_ratio(self, text: str) -> float:
        """计算中文字符比例"""
        if not text:
            return 0.0
        chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        return chinese_count / len(text)
    
    def _count_punctuation(self, text: str) -> int:
        """统计标点符号数量"""
        punctuation = '，。！？；：""''（）【】《》'
        return sum(text.count(p) for p in punctuation)
    
    def _calculate_promotion_score(self, text: str, features: Dict) -> float:
        """计算推广得分"""
        score = 0.0
        
        # 基于动作词汇 (权重0.3)
        action_score = min(features["action_word_count"] * 0.1, 0.3)
        score += action_score
        
        # 基于链接和联系方式 (权重0.4)
        if features["has_telegram_link"]:
            score += 0.2
        if features["link_count"] > 0:
            score += min(features["link_count"] * 0.1, 0.2)
        
        # 基于频道/群组提及 (权重0.2)
        if features["has_channel_mention"] or features["has_group_mention"]:
            score += 0.2
        
        # 基于表情符号密度 (权重0.1)
        if features["emoji_density"] > 0.05:
            score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_commercial_score(self, text: str, features: Dict) -> float:
        """计算商业化得分"""
        score = 0.0
        
        # 基于商业词汇 (权重0.4)
        business_score = min(features["business_word_count"] * 0.15, 0.4)
        score += business_score
        
        # 基于联系方式数量 (权重0.3)
        contact_score = min(features["contact_count"] * 0.1, 0.3)
        score += contact_score
        
        # 基于紧急性 (权重0.2)
        if features["has_urgency"]:
            score += 0.2
        
        # 基于大写字母比例 (权重0.1)
        if features["uppercase_ratio"] > 0.1:
            score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_relevance_score(self, text: str, features: Dict) -> float:
        """计算与正文的相关性得分（尾部通常相关性较低）"""
        # 尾部内容与正文相关性通常很低
        score = 0.1
        
        # 如果包含分隔符，相关性更低
        if features["has_separators"]:
            score = 0.05
        
        # 如果是纯链接或联系方式，相关性极低
        if features["link_count"] > 0 and features["word_count"] < 5:
            score = 0.0
        
        return score
    
    def should_filter(self, text: str, threshold: float = 0.7) -> bool:
        """
        判断是否应该过滤该尾部
        
        Args:
            text: 尾部文本
            threshold: 过滤阈值
            
        Returns:
            是否应该过滤
        """
        features = self.extract_features(text)
        scores = self.calculate_scores(text, features)
        
        # 使用综合得分判断
        return scores["overall_score"] >= threshold
    
    def analyze_text(self, text: str) -> Dict:
        """
        完整分析文本，返回所有信息
        
        Args:
            text: 要分析的文本
            
        Returns:
            完整的分析结果
        """
        features = self.extract_features(text)
        scores = self.calculate_scores(text, features)
        
        return {
            "text": text,
            "features": features,
            "scores": scores,
            "should_filter": self.should_filter(text),
            "analysis_time": datetime.now().isoformat()
        }


# 懒加载全局实例
_tail_feature_extractor_instance = None

def get_tail_feature_extractor():
    """获取尾部特征提取器实例（懒加载）"""
    global _tail_feature_extractor_instance
    if _tail_feature_extractor_instance is None:
        # 检查AI功能是否启用
        try:
            from app.core.ai_config import is_module_enabled
            if not is_module_enabled('semantic_tail_filter'):
                logger.info("🔒 尾部特征提取器已禁用，使用空实现")
                from app.services.dummy_implementations import DummyTailFeatureExtractor
                _tail_feature_extractor_instance = DummyTailFeatureExtractor()
                return _tail_feature_extractor_instance
        except ImportError:
            pass
        
        _tail_feature_extractor_instance = TailFeatureExtractor()
    return _tail_feature_extractor_instance

# 兼容性：保持tail_feature_extractor属性访问
class TailFeatureExtractorProxy:
    """尾部特征提取器代理，实现懒加载"""
    def __getattr__(self, name):
        return getattr(get_tail_feature_extractor(), name)
    
    def __setattr__(self, name, value):
        setattr(get_tail_feature_extractor(), name, value)

tail_feature_extractor = TailFeatureExtractorProxy()