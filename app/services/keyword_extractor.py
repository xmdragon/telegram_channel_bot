"""
关键词提取器 - 使用jieba分词
用于从文本中提取潜在的广告关键词

Author: Claude
Created: 2025-09-12
"""

import logging
import json
from typing import List, Set, Tuple
from pathlib import Path

import jieba
import jieba.analyse

from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class AdKeywordExtractor:
    """广告关键词提取器"""
    
    def __init__(self):
        # 加载已有关键词
        self.keywords_file = PathConfig.DATA_DIR / "config" / "ad_keywords.json"
        self.existing_keywords: Set[str] = set()
        self.load_existing_keywords()
        
        # 设置jieba参数
        jieba.setLogLevel(logging.INFO)
        
        # 常见停用词（不提取的词）
        self.stop_words = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
            '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
            '自己', '这', '那', '些', '什么', '他', '她', '它', '们', '我们', '你们', '他们',
            '这个', '那个', '吗', '吧', '啊', '呢', '呀', '啦', '哦', '哈', '嗯', '哇', '呃',
            '可以', '能', '得', '过', '给', '对', '将', '把', '被', '让', '使', '用', '从',
            '为', '以', '于', '与', '及', '其', '或', '如', '等', '当', '但', '而', '后',
            '前', '下', '里', '内', '外', '中', '间', '之', '又', '已', '才', '只', '还',
            '就是', '可是', '如果', '因为', '所以', '虽然', '但是', '不过', '现在', '这样',
            '那样', '这里', '那里', '这么', '那么', '怎么', '什么样', '为什么', '没有'
        }
        
        # 数字、英文等模式（不作为关键词）
        self.ignore_patterns = [
            r'^\d+$',  # 纯数字
            r'^[a-zA-Z]+$',  # 纯英文
            r'^\W+$',  # 纯符号
        ]
    
    def load_existing_keywords(self) -> None:
        """加载已存在的关键词"""
        try:
            if self.keywords_file.exists():
                with open(self.keywords_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.existing_keywords = set(data.get('keywords', {}).keys())
                logger.info(f"加载已有关键词: {len(self.existing_keywords)}个")
        except Exception as e:
            logger.error(f"加载已有关键词失败: {e}")
            self.existing_keywords = set()
    
    def extract_keywords(self, text: str, top_k: int = 20) -> List[Tuple[str, float]]:
        """
        提取关键词（过滤已存在的）
        
        Args:
            text: 要提取的文本
            top_k: 提取前K个关键词
            
        Returns:
            [(关键词, TF-IDF分数), ...]
        """
        if not text:
            return []
        
        try:
            # 使用TF-IDF提取关键词
            keywords_with_weight = jieba.analyse.extract_tags(
                text, 
                topK=top_k * 2,  # 多提取一些，后面会过滤
                withWeight=True
            )
            
            # 过滤结果
            filtered_keywords = []
            for keyword, weight in keywords_with_weight:
                # 跳过已存在的关键词
                if keyword in self.existing_keywords:
                    continue
                
                # 跳过停用词
                if keyword in self.stop_words:
                    continue
                
                # 跳过太短的词（单字符）
                if len(keyword) < 2:
                    continue
                
                # 跳过纯数字、纯英文等
                import re
                skip = False
                for pattern in self.ignore_patterns:
                    if re.match(pattern, keyword):
                        skip = True
                        break
                if skip:
                    continue
                
                filtered_keywords.append((keyword, round(weight, 3)))
                
                # 达到需要的数量就停止
                if len(filtered_keywords) >= top_k:
                    break
            
            return filtered_keywords
            
        except Exception as e:
            logger.error(f"提取关键词失败: {e}")
            return []
    
    def extract_new_keywords(self, text: str, min_freq: int = 2) -> List[str]:
        """
        提取新关键词（基于词频）
        
        Args:
            text: 要提取的文本
            min_freq: 最小出现频率
            
        Returns:
            新关键词列表
        """
        if not text:
            return []
        
        try:
            # 分词
            words = jieba.cut(text)
            
            # 统计词频
            word_freq = {}
            for word in words:
                # 跳过已存在的关键词
                if word in self.existing_keywords:
                    continue
                
                # 跳过停用词
                if word in self.stop_words:
                    continue
                
                # 跳过太短的词
                if len(word) < 2:
                    continue
                
                # 统计频率
                word_freq[word] = word_freq.get(word, 0) + 1
            
            # 筛选高频词
            new_keywords = [
                word for word, freq in word_freq.items() 
                if freq >= min_freq
            ]
            
            # 按频率排序
            new_keywords.sort(key=lambda w: word_freq[w], reverse=True)
            
            return new_keywords[:10]  # 最多返回10个
            
        except Exception as e:
            logger.error(f"提取新关键词失败: {e}")
            return []
    
    def suggest_keywords_with_weight(self, text: str) -> List[Tuple[str, float]]:
        """
        建议关键词及其推荐权重
        
        Args:
            text: 要分析的文本
            
        Returns:
            [(关键词, 推荐权重), ...]
        """
        # 提取关键词
        keywords = self.extract_keywords(text, top_k=15)
        
        suggested = []
        for keyword, tfidf_score in keywords:
            # 根据TF-IDF分数推荐权重
            if tfidf_score > 0.3:
                weight = 3  # 高重要性
            elif tfidf_score > 0.15:
                weight = 2  # 中等重要性
            else:
                weight = 1  # 低重要性
            
            # 特殊关键词加权
            if any(k in keyword for k in ['娱乐城', '赌', '博彩', 'USDT', '出款']):
                weight = min(weight + 2, 5)  # 最高权重5
            elif any(k in keyword for k in ['充值', '会员', '优惠', '活动']):
                weight = min(weight + 1, 3)
            
            suggested.append((keyword, weight))
        
        return suggested


# 全局实例
_extractor_instance = None


def get_keyword_extractor() -> AdKeywordExtractor:
    """获取关键词提取器实例（单例）"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = AdKeywordExtractor()
    return _extractor_instance