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
        self.keywords_file = PathConfig.AD_KEYWORDS_FILE
        self.existing_keywords: Set[str] = set()
        self.load_existing_keywords()
        
        # 加载配置文件
        self.rules_file = PathConfig.DATA_DIR / "config" / "keyword_rules.json"
        self.stopwords_file = PathConfig.DATA_DIR / "config" / "stopwords.json"
        self.keyword_rules = {}
        self.stop_words = set()
        self.load_rules_config()
        self.load_stopwords()
        
        # 设置jieba参数
        jieba.setLogLevel(logging.INFO)
    
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
    
    def load_rules_config(self) -> None:
        """加载关键词规则配置"""
        try:
            if self.rules_file.exists():
                with open(self.rules_file, 'r', encoding='utf-8') as f:
                    self.keyword_rules = json.load(f)
                logger.info(f"加载关键词规则配置成功")
            else:
                logger.warning(f"关键词规则配置文件不存在: {self.rules_file}")
                self.keyword_rules = {}
        except Exception as e:
            logger.error(f"加载关键词规则配置失败: {e}")
            self.keyword_rules = {}
    
    def load_stopwords(self) -> None:
        """加载停用词表"""
        try:
            if self.stopwords_file.exists():
                with open(self.stopwords_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.stop_words = set(data.get('stopwords', []))
                logger.info(f"加载停用词: {len(self.stop_words)}个")
            else:
                logger.warning(f"停用词配置文件不存在: {self.stopwords_file}")
                self.stop_words = set()
        except Exception as e:
            logger.error(f"加载停用词失败: {e}")
            self.stop_words = set()
    
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
                
                # 跳过太短的词
                min_length = self.keyword_rules.get('extraction_config', {}).get('min_keyword_length', 2)
                if len(keyword) < min_length:
                    continue
                
                # 跳过纯数字、纯英文等
                import re
                skip = False
                ignore_patterns = self.keyword_rules.get('extraction_config', {}).get('ignore_patterns', [
                    r'^\d+$',  # 纯数字
                    r'^[a-zA-Z]+$',  # 纯英文
                    r'^\W+$',  # 纯符号
                ])
                for pattern in ignore_patterns:
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
                min_length = self.keyword_rules.get('extraction_config', {}).get('min_keyword_length', 2)
                if len(word) < min_length:
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
            # 根据TF-IDF分数规则计算基础权重
            weight = 1.0  # 默认权重
            tfidf_rules = self.keyword_rules.get('tfidf_weight_rules', [])
            for rule in tfidf_rules:
                if rule['min_score'] <= tfidf_score <= rule['max_score']:
                    weight = rule['base_weight']
                    break
            
            # 根据关键词分类调整权重
            categories = self.keyword_rules.get('keyword_categories', [])
            # 按优先级排序
            categories = sorted(categories, key=lambda x: x.get('priority', 999))
            
            for category in categories:
                if any(k in keyword for k in category.get('keywords', [])):
                    adjustment = category.get('weight_adjustment', 0)
                    max_weight = category.get('max_weight', 5.0)
                    weight = min(weight + adjustment, max_weight)
                    break  # 只应用第一个匹配的分类
            
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