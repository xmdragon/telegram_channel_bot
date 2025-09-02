"""
AI语义提取器 - 广告向量化专用
基于现有的轻量级相似度模块，专门为广告检测优化

Author: Claude
Created: 2025-08-31
"""

import logging
import numpy as np
from typing import List, Optional, Dict, Any
import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
import pickle
import os
from datetime import datetime

from app.services.lightweight_similarity import LightweightTextSimilarity
from app.core.ai_config import get_ai_config

logger = logging.getLogger(__name__)


class SemanticExtractor:
    """AI语义提取器 - Linus式简洁设计"""
    
    def __init__(self, vector_dim: int = 128):
        """
        初始化语义提取器
        
        Args:
            vector_dim: 输出向量维度
        """
        self.vector_dim = vector_dim
        self.lightweight_similarity = None
        self.vectorizer = None
        self.svd = None
        self.initialized = False
        
        # AI配置检查
        self.ai_config = get_ai_config()
        
        logger.info(f"语义提取器初始化 - 向量维度: {vector_dim}")
    
    def _get_ad_stopwords(self) -> List[str]:
        """获取广告检测专用的停用词"""
        return [
            '的', '是', '在', '了', '和', '有', '个', '就', '都', '会', 
            '可以', '不是', '这个', '那个', '什么', '怎么', '为什么',
            '我们', '你们', '他们', '自己', '一下', '一些', '所有',
            # 广告常用但不重要的词
            '限时', '特价', '优惠', '活动', '立即', '马上', '赶快',
            '点击', '联系', '扫码', '加群', '关注'
        ]
    
    def _preprocess_ad_text(self, text: str) -> str:
        """
        针对广告文本的预处理
        
        Args:
            text: 原始文本
            
        Returns:
            预处理后的文本
        """
        if not text:
            return ""
        
        # 清理文本
        text = text.strip().replace('\n', ' ').replace('\t', ' ')
        
        # 中文分词
        words = list(jieba.cut(text))
        
        # 过滤条件：
        # 1. 长度大于1
        # 2. 不是纯数字和特殊字符
        # 3. 不在停用词中
        stopwords = set(self._get_ad_stopwords())
        filtered_words = []
        
        for word in words:
            word = word.strip()
            if (len(word) > 1 and 
                not word.isdigit() and
                not all(c in '!@#$%^&*()_+-={}[]|\\:";\'<>?,./' for c in word) and
                word.lower() not in stopwords):
                filtered_words.append(word)
        
        result = " ".join(filtered_words)
        logger.debug(f"文本预处理: {len(text)} → {len(result)} 字符")
        
        return result
    
    def _initialize_models(self, sample_texts: List[str] = None) -> bool:
        """初始化模型（如果需要训练）"""
        if self.initialized:
            return True
        
        try:
            # 检查是否有足够的样本进行训练
            if sample_texts and len(sample_texts) >= 5:
                logger.info("使用提供的样本训练语义模型")
                
                # 预处理文本
                processed_texts = [self._preprocess_ad_text(text) for text in sample_texts]
                processed_texts = [t for t in processed_texts if len(t) > 5]  # 过滤过短文本
                
                if len(processed_texts) < 3:
                    logger.warning("有效训练样本不足，使用默认模型")
                    return self._use_default_model()
                
                # 创建TF-IDF向量化器
                self.vectorizer = TfidfVectorizer(
                    max_features=min(2000, len(processed_texts) * 100),  # 动态特征数量
                    ngram_range=(1, 3),  # 1-3元语法，适合中文广告检测
                    min_df=1,
                    max_df=0.9,
                    tokenizer=lambda x: x.split(),  # 已经分词
                    lowercase=False  # 保持中文大小写
                )
                
                # 训练TF-IDF
                tfidf_matrix = self.vectorizer.fit_transform(processed_texts)
                logger.info(f"TF-IDF矩阵: {tfidf_matrix.shape}")
                
                # SVD降维
                n_components = min(self.vector_dim, tfidf_matrix.shape[1], tfidf_matrix.shape[0])
                self.svd = TruncatedSVD(n_components=n_components, random_state=42)
                self.svd.fit(tfidf_matrix)
                
                logger.info(f"SVD降维: {tfidf_matrix.shape[1]} → {n_components}")
                
                self.initialized = True
                return True
            else:
                logger.info("样本不足，使用默认模型")
                return self._use_default_model()
                
        except Exception as e:
            logger.error(f"初始化模型失败: {e}")
            return self._use_default_model()
    
    def _use_default_model(self) -> bool:
        """使用默认的简单模型"""
        try:
            # 创建简单的字符级向量化器
            logger.info("使用默认的轻量级模型")
            
            # 默认的广告关键词特征
            default_features = [
                '微信', 'QQ', '群', '联系', '客服', '优惠', '特价', '限时',
                '首存', '充值', '提现', '赚钱', '兼职', '代理', '加盟',
                '注册', '下载', '安装', '点击', '扫码', '关注', '转发',
                '红包', '奖金', '返利', '佣金', '免费', '送', '领取',
                'http', 'www', 'com', 't.me', '链接', '网址'
            ]
            
            self.default_features = default_features
            self.initialized = True
            return True
            
        except Exception as e:
            logger.error(f"使用默认模型失败: {e}", exc_info=True)
            # 即使异常也要设置基础属性，确保系统可用
            try:
                self.default_features = ['微信', 'QQ', '群', '联系', '客服']  # 最基础的特征
                self.initialized = True
                logger.error(f"异常恢复成功，设置了{len(self.default_features)}个基础特征")
                return True
            except Exception as e2:
                logger.error(f"异常恢复也失败: {e2}", exc_info=True)
                return False
    
    def extract_vector(self, text: str) -> Optional[List[float]]:
        """
        从文本中提取语义向量
        
        Args:
            text: 输入文本
            
        Returns:
            语义向量，如果失败返回None
        """
        result = self.extract_vector_with_info(text)
        return result['vector'] if result['success'] else None
    
    def extract_vector_with_info(self, text: str) -> Dict[str, Any]:
        """
        从文本中提取语义向量（带详细信息）
        
        Args:
            text: 输入文本
            
        Returns:
            包含向量和状态信息的字典: {
                'success': bool,
                'vector': List[float] | None,
                'error_type': 'none' | 'invalid_text' | 'technical_error',
                'error_message': str,
                'processed_text': str
            }
        """
        if not text:
            return {
                'success': False,
                'vector': None,
                'error_type': 'invalid_text',
                'error_message': '输入文本为空',
                'processed_text': ''
            }
        
        try:
            # 确保模型已初始化
            if not self.initialized:
                self._initialize_models()
            
            # 预处理文本
            processed_text = self._preprocess_ad_text(text)
            if not processed_text:
                return {
                    'success': False,
                    'vector': None,
                    'error_type': 'invalid_text',
                    'error_message': '文本预处理后为空（可能全为停用词、数字或特殊字符）',
                    'processed_text': processed_text
                }
            
            # 提取向量
            if self.vectorizer and self.svd:
                # 使用训练的TF-IDF + SVD模型
                tfidf_vector = self.vectorizer.transform([processed_text])
                semantic_vector = self.svd.transform(tfidf_vector)
                result = semantic_vector[0].tolist()
                
                # 补齐到目标维度
                if len(result) < self.vector_dim:
                    result.extend([0.0] * (self.vector_dim - len(result)))
                else:
                    result = result[:self.vector_dim]
                
                return {
                    'success': True,
                    'vector': result,
                    'error_type': 'none',
                    'error_message': '',
                    'processed_text': processed_text
                }
            else:
                # 使用默认特征向量
                result = self._extract_default_vector(processed_text)
                return {
                    'success': True,
                    'vector': result,
                    'error_type': 'none',
                    'error_message': '',
                    'processed_text': processed_text
                }
                
        except Exception as e:
            logger.error(f"提取语义向量失败: {e}")
            return {
                'success': False,
                'vector': None,
                'error_type': 'technical_error',
                'error_message': str(e),
                'processed_text': processed_text if 'processed_text' in locals() else ''
            }
    
    def _extract_default_vector(self, text: str) -> List[float]:
        """使用默认方法提取向量"""
        try:
            vector = [0.0] * self.vector_dim
            
            if not hasattr(self, 'default_features'):
                return vector
            
            # 基于关键词匹配的简单向量
            words = set(jieba.cut(text.lower()))
            
            for i, feature in enumerate(self.default_features):
                if i >= self.vector_dim:
                    break
                
                # 特征权重计算
                weight = 0.0
                if feature in text.lower():
                    weight = 1.0
                    # 考虑词频
                    weight += text.lower().count(feature) * 0.1
                
                # 考虑相关词
                if feature == '微信' and any(w in text for w in ['wx', 'wechat', '薇信']):
                    weight += 0.5
                elif feature == 'QQ' and any(w in text for w in ['qq', 'q群', '扣扣']):
                    weight += 0.5
                
                vector[i] = min(weight, 2.0)  # 限制最大权重
            
            # 归一化
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = [x / norm for x in vector]
            
            return vector
            
        except Exception as e:
            logger.error(f"默认向量提取失败: {e}")
            return [0.0] * self.vector_dim
    
    def batch_extract(self, texts: List[str]) -> Dict[str, List[float]]:
        """
        批量提取向量
        
        Args:
            texts: 文本列表
            
        Returns:
            文本到向量的映射
        """
        results = {}
        
        for i, text in enumerate(texts):
            vector = self.extract_vector(text)
            if vector:
                results[f"text_{i}"] = vector
            
            if (i + 1) % 100 == 0:
                logger.info(f"批量提取进度: {i + 1}/{len(texts)}")
        
        logger.info(f"批量提取完成: {len(results)}/{len(texts)}")
        return results
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            'initialized': self.initialized,
            'vector_dim': self.vector_dim,
            'has_tfidf': self.vectorizer is not None,
            'has_svd': self.svd is not None,
            'tfidf_features': self.vectorizer.get_feature_names_out().tolist() if self.vectorizer else [],
            'svd_components': self.svd.n_components if self.svd else 0,
            'default_features': getattr(self, 'default_features', [])[:10]  # 只显示前10个
        }


# 全局语义提取器实例
_semantic_extractor = None

def get_semantic_extractor(vector_dim: int = 128) -> SemanticExtractor:
    """获取语义提取器实例（单例模式）"""
    global _semantic_extractor
    if _semantic_extractor is None:
        _semantic_extractor = SemanticExtractor(vector_dim)
    return _semantic_extractor