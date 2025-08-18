"""
轻量级文本相似度计算模块
替代sentence_transformers的轻量化解决方案
使用TF-IDF + SVD降维实现语义相似度计算
"""
import logging
import numpy as np
from typing import List, Tuple, Optional, Dict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import DBSCAN
import jieba
import pickle
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class LightweightTextSimilarity:
    """轻量级文本相似度计算器"""
    
    def __init__(self, n_components: int = 100, max_features: int = 5000):
        """
        初始化轻量级相似度计算器
        
        Args:
            n_components: SVD降维后的特征数量
            max_features: TF-IDF最大特征数量
        """
        self.n_components = n_components
        self.max_features = max_features
        self.vectorizer = None
        self.svd = None
        self.initialized = False
        
        # 缓存已训练的模型
        from app.core.path_config import PathConfig
        self.cache_file = str(PathConfig.LIGHTWEIGHT_SIMILARITY_CACHE_FILE)
        
        logger.info("✅ 轻量级文本相似度计算器初始化")
    
    def _preprocess_text(self, text: str) -> str:
        """
        预处理文本
        
        Args:
            text: 原始文本
            
        Returns:
            预处理后的文本
        """
        if not text:
            return ""
        
        # 中文分词
        words = jieba.cut(text.strip())
        
        # 过滤单字符和空字符
        words = [w for w in words if len(w) > 1]
        
        return " ".join(words)
    
    def fit(self, texts: List[str]) -> bool:
        """
        训练模型
        
        Args:
            texts: 训练文本列表
            
        Returns:
            是否训练成功
        """
        if not texts or len(texts) < 2:
            logger.warning("训练文本不足，至少需要2个样本")
            return False
        
        try:
            logger.info(f"开始训练轻量级相似度模型，样本数：{len(texts)}")
            
            # 预处理文本
            processed_texts = [self._preprocess_text(text) for text in texts]
            processed_texts = [t for t in processed_texts if t]  # 过滤空文本
            
            if len(processed_texts) < 2:
                logger.warning("预处理后有效文本不足")
                return False
            
            # TF-IDF向量化
            self.vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                stop_words=None,  # 中文没有标准停用词
                ngram_range=(1, 2),  # 使用1-2元语法
                min_df=1,  # 最小文档频率
                max_df=0.95  # 最大文档频率
            )
            
            tfidf_matrix = self.vectorizer.fit_transform(processed_texts)
            logger.info(f"TF-IDF矩阵形状：{tfidf_matrix.shape}")
            
            # SVD降维
            if tfidf_matrix.shape[1] > self.n_components:
                self.svd = TruncatedSVD(
                    n_components=min(self.n_components, tfidf_matrix.shape[1] - 1),
                    random_state=42
                )
                self.svd.fit(tfidf_matrix)
                logger.info(f"SVD降维到 {self.svd.n_components} 维")
            else:
                logger.info("特征数少于目标维度，跳过SVD降维")
            
            self.initialized = True
            
            # 保存模型到缓存
            self._save_cache()
            
            logger.info("✅ 轻量级相似度模型训练完成")
            return True
            
        except Exception as e:
            logger.error(f"训练轻量级相似度模型失败：{e}")
            return False
    
    def encode(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        将文本编码为向量
        
        Args:
            texts: 文本列表
            
        Returns:
            编码后的向量矩阵
        """
        if not self.initialized:
            logger.warning("模型未初始化")
            return None
        
        try:
            # 预处理文本
            processed_texts = [self._preprocess_text(text) for text in texts]
            
            # TF-IDF向量化
            tfidf_matrix = self.vectorizer.transform(processed_texts)
            
            # SVD降维
            if self.svd is not None:
                vectors = self.svd.transform(tfidf_matrix)
            else:
                vectors = tfidf_matrix.toarray()
            
            return vectors
            
        except Exception as e:
            logger.error(f"文本编码失败：{e}")
            return None
    
    def similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度分数 (0-1)
        """
        if not self.initialized:
            return 0.0
        
        try:
            vectors = self.encode([text1, text2])
            if vectors is None or len(vectors) != 2:
                return 0.0
            
            sim = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]
            return float(sim)
            
        except Exception as e:
            logger.error(f"相似度计算失败：{e}")
            return 0.0
    
    def find_similar(self, query_text: str, candidate_texts: List[str], 
                    threshold: float = 0.5, top_k: int = 5) -> List[Tuple[int, float]]:
        """
        在候选文本中找到与查询文本最相似的
        
        Args:
            query_text: 查询文本
            candidate_texts: 候选文本列表
            threshold: 相似度阈值
            top_k: 返回前k个结果
            
        Returns:
            (索引, 相似度)列表
        """
        if not self.initialized or not candidate_texts:
            return []
        
        try:
            all_texts = [query_text] + candidate_texts
            vectors = self.encode(all_texts)
            
            if vectors is None or len(vectors) < 2:
                return []
            
            query_vector = vectors[0:1]
            candidate_vectors = vectors[1:]
            
            similarities = cosine_similarity(query_vector, candidate_vectors)[0]
            
            # 过滤低于阈值的结果
            results = []
            for i, sim in enumerate(similarities):
                if sim >= threshold:
                    results.append((i, float(sim)))
            
            # 按相似度排序
            results.sort(key=lambda x: x[1], reverse=True)
            
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"相似文本查找失败：{e}")
            return []
    
    def cluster(self, texts: List[str], eps: float = 0.3, min_samples: int = 2) -> List[int]:
        """
        文本聚类
        
        Args:
            texts: 文本列表
            eps: DBSCAN的邻域半径
            min_samples: 最小样本数
            
        Returns:
            聚类标签列表
        """
        if not self.initialized or len(texts) < min_samples:
            return [-1] * len(texts)
        
        try:
            vectors = self.encode(texts)
            if vectors is None:
                return [-1] * len(texts)
            
            clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
            labels = clustering.fit_predict(vectors)
            
            return labels.tolist()
            
        except Exception as e:
            logger.error(f"文本聚类失败：{e}")
            return [-1] * len(texts)
    
    def _save_cache(self):
        """保存模型到缓存文件"""
        try:
            cache_data = {
                'vectorizer': self.vectorizer,
                'svd': self.svd,
                'n_components': self.n_components,
                'max_features': self.max_features,
                'initialized': self.initialized,
                'cached_at': datetime.now().isoformat()
            }
            
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
                
            logger.info(f"模型已缓存到 {self.cache_file}")
            
        except Exception as e:
            logger.error(f"保存模型缓存失败：{e}")
    
    def load_cache(self) -> bool:
        """从缓存文件加载模型"""
        try:
            if not os.path.exists(self.cache_file):
                return False
            
            with open(self.cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            
            self.vectorizer = cache_data['vectorizer']
            self.svd = cache_data['svd']
            self.n_components = cache_data['n_components']
            self.max_features = cache_data['max_features']
            self.initialized = cache_data['initialized']
            
            logger.info(f"✅ 从缓存加载轻量级相似度模型：{self.cache_file}")
            return True
            
        except Exception as e:
            logger.error(f"加载模型缓存失败：{e}")
            return False


class LightweightAIFilter:
    """轻量级AI过滤器，使用TF-IDF替代sentence_transformers"""
    
    def __init__(self):
        self.similarity_engine = LightweightTextSimilarity()
        self.channel_patterns = {}  # 频道尾部模式
        self.ad_vectors = None  # 广告样本向量
        self.normal_vectors = None  # 正常内容向量
        self.ad_texts = []  # 广告样本文本
        self.normal_texts = []  # 正常内容文本
        
        # 尝试加载缓存的模型
        if self.similarity_engine.load_cache():
            logger.info("✅ 轻量级AI过滤器初始化完成（使用缓存）")
        else:
            logger.info("🔄 轻量级AI过滤器初始化（需要训练）")
    
    def train_with_samples(self, ad_samples: List[str], normal_samples: List[str]) -> bool:
        """
        使用样本数据训练模型
        
        Args:
            ad_samples: 广告样本
            normal_samples: 正常内容样本
            
        Returns:
            是否训练成功
        """
        try:
            all_samples = ad_samples + normal_samples
            if len(all_samples) < 5:
                logger.warning("训练样本不足，至少需要5个样本")
                return False
            
            # 训练相似度引擎
            if not self.similarity_engine.fit(all_samples):
                return False
            
            # 保存样本
            self.ad_texts = ad_samples.copy()
            self.normal_texts = normal_samples.copy()
            
            # 计算样本向量
            if ad_samples:
                self.ad_vectors = self.similarity_engine.encode(ad_samples)
            if normal_samples:
                self.normal_vectors = self.similarity_engine.encode(normal_samples)
            
            logger.info(f"✅ 轻量级AI过滤器训练完成：{len(ad_samples)}个广告样本，{len(normal_samples)}个正常样本")
            return True
            
        except Exception as e:
            logger.error(f"轻量级AI过滤器训练失败：{e}")
            return False
    
    def is_advertisement(self, text: str, threshold: float = 0.6) -> Tuple[bool, float]:
        """
        判断文本是否为广告
        
        Args:
            text: 待检测文本
            threshold: 判定阈值
            
        Returns:
            (是否为广告, 置信度)
        """
        if not self.similarity_engine.initialized:
            return False, 0.0
        
        try:
            # 计算与广告样本的最大相似度
            ad_similarity = 0.0
            if self.ad_texts:
                ad_results = self.similarity_engine.find_similar(
                    text, self.ad_texts, threshold=0.0, top_k=1
                )
                if ad_results:
                    ad_similarity = ad_results[0][1]
            
            # 计算与正常内容的最大相似度  
            normal_similarity = 0.0
            if self.normal_texts:
                normal_results = self.similarity_engine.find_similar(
                    text, self.normal_texts, threshold=0.0, top_k=1
                )
                if normal_results:
                    normal_similarity = normal_results[0][1]
            
            # 判断逻辑
            if ad_similarity > normal_similarity and ad_similarity > threshold:
                return True, ad_similarity
            else:
                return False, 1 - ad_similarity
                
        except Exception as e:
            logger.error(f"广告检测失败：{e}")
            return False, 0.0
    
    def learn_channel_pattern(self, channel_id: str, messages: List[str]) -> bool:
        """
        学习频道尾部模式
        
        Args:
            channel_id: 频道ID
            messages: 消息列表
            
        Returns:
            是否学习成功
        """
        if not self.similarity_engine.initialized or len(messages) < 3:
            return False
        
        try:
            # 提取尾部内容
            tails = []
            for msg in messages:
                tail = self._extract_tail(msg)
                if tail and len(tail) > 20:
                    tails.append(tail)
            
            if len(tails) < 3:
                logger.info(f"频道 {channel_id} 尾部样本不足")
                return False
            
            # 聚类找出重复模式
            labels = self.similarity_engine.cluster(tails, eps=0.4, min_samples=2)
            
            # 找最大聚类
            from collections import Counter
            label_counts = Counter(l for l in labels if l != -1)
            
            if not label_counts:
                logger.info(f"频道 {channel_id} 没有发现重复尾部模式")
                return False
            
            # 获取最常见的尾部模式
            main_label = label_counts.most_common(1)[0][0]
            pattern_texts = [tails[i] for i, l in enumerate(labels) if l == main_label]
            
            # 存储模式
            self.channel_patterns[channel_id] = {
                'samples': pattern_texts[:5],  # 保存前5个样本
                'threshold': 0.7,
                'learned_at': datetime.now().isoformat(),
                'sample_count': len(pattern_texts)
            }
            
            logger.info(f"✅ 频道 {channel_id} 尾部模式学习完成：{len(pattern_texts)}个样本")
            return True
            
        except Exception as e:
            logger.error(f"学习频道模式失败：{e}")
            return False
    
    def is_channel_tail(self, channel_id: str, text: str) -> Tuple[bool, float]:
        """
        判断文本是否为频道尾部
        
        Args:
            channel_id: 频道ID  
            text: 待检测文本
            
        Returns:
            (是否为尾部, 相似度)
        """
        if channel_id not in self.channel_patterns:
            return False, 0.0
        
        try:
            pattern = self.channel_patterns[channel_id]
            sample_texts = pattern['samples']
            threshold = pattern['threshold']
            
            # 计算与样本的最大相似度
            results = self.similarity_engine.find_similar(
                text, sample_texts, threshold=0.0, top_k=1
            )
            
            if not results:
                return False, 0.0
            
            max_similarity = results[0][1]
            is_tail = max_similarity >= threshold
            
            return is_tail, max_similarity
            
        except Exception as e:
            logger.error(f"尾部检测失败：{e}")
            return False, 0.0
    
    def _extract_tail(self, content: str) -> str:
        """提取消息尾部内容"""
        import re
        lines = content.split('\n')
        
        if len(lines) < 3:
            return ""
        
        # 寻找推广标志
        promo_patterns = [
            r'https?://',
            r't\.me/',
            r'@[a-zA-Z]\w{4,}',
            r'(?:订阅|關注|投稿|商务|联系)',
        ]
        
        # 从后向前找推广内容起始位置
        for i in range(len(lines) - 1, max(0, len(lines) - 10), -1):
            line = lines[i]
            promo_count = sum(1 for p in promo_patterns if re.search(p, line, re.IGNORECASE))
            
            if promo_count >= 1:  # 包含推广特征
                tail = '\n'.join(lines[i:])
                if len(tail) > 20:  # 尾部长度合理
                    return tail.strip()
        
        return ""


# 全局实例
_lightweight_filter = None

def get_lightweight_filter() -> LightweightAIFilter:
    """获取轻量级过滤器实例"""
    global _lightweight_filter
    if _lightweight_filter is None:
        _lightweight_filter = LightweightAIFilter()
    return _lightweight_filter