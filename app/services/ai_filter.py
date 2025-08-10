"""
AI智能过滤模块
使用句子嵌入和机器学习技术实现智能的广告检测和尾部过滤
"""
import logging
import json
import numpy as np
from typing import Dict, List, Tuple, Optional
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import DBSCAN
from collections import defaultdict
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class IntelligentFilter:
    """智能过滤器 - 基于AI的内容过滤"""
    
    def __init__(self):
        self.model = None
        self.channel_patterns = {}  # 存储每个频道的尾部模式
        self.ad_embeddings = []  # 广告样本的嵌入向量
        self.normal_embeddings = []  # 正常内容的嵌入向量
        self.initialized = False
        
        # 尝试加载模型
        self._initialize()
        
        # 尝试加载已保存的模式
        if self.initialized:
            try:
                import os
                patterns_file = "data/ai_filter_patterns.json"
                if os.path.exists(patterns_file):
                    self.load_patterns(patterns_file)
                    logger.info(f"✅ 从 {patterns_file} 加载了AI过滤模式")
            except Exception as e:
                logger.error(f"加载AI过滤模式失败: {e}")
    
    def _initialize(self):
        """初始化模型"""
        try:
            from sentence_transformers import SentenceTransformer
            # 使用多语言模型，支持中文
            self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            self.initialized = True
            logger.info("✅ AI过滤器初始化成功")
        except ImportError:
            logger.warning("⚠️ sentence-transformers 未安装，AI过滤功能暂不可用")
        except Exception as e:
            logger.error(f"AI过滤器初始化失败: {e}")
    
    async def learn_channel_pattern(self, channel_id: str, messages: List[str]) -> bool:
        """
        学习特定频道的尾部模式
        
        Args:
            channel_id: 频道ID
            messages: 该频道的历史消息列表
            
        Returns:
            是否学习成功
        """
        if not self.initialized or not messages:
            return False
        
        try:
            # 提取每条消息的尾部（最后5行）
            tails = []
            for msg in messages:
                lines = msg.split('\n')
                if len(lines) > 3:
                    tail = '\n'.join(lines[-5:])
                    tails.append(tail)
            
            # 动态判断样本数量 - 不再固定要求10个
            min_samples = min(5, len(tails))  # 最少5个样本，或者所有可用样本
            if len(tails) < min_samples:
                logger.info(f"频道 {channel_id} 样本不足（{len(tails)}个），跳过学习")
                return False
            
            # 计算尾部的嵌入向量
            logger.info(f"正在学习频道 {channel_id} 的尾部模式...")
            tail_embeddings = self.model.encode(tails)
            
            # 使用DBSCAN聚类找出重复的模式
            # 动态调整聚类参数：样本少时降低要求
            min_cluster_size = max(2, len(tails) // 5)  # 至少占20%的样本
            clustering = DBSCAN(eps=0.3, min_samples=min_cluster_size, metric='cosine')
            labels = clustering.fit_predict(tail_embeddings)
            
            # 找出最大的聚类（最常见的尾部模式）
            label_counts = defaultdict(int)
            for label in labels:
                if label != -1:  # -1 表示噪声点
                    label_counts[label] += 1
            
            if not label_counts:
                logger.info(f"频道 {channel_id} 没有发现重复的尾部模式（可能无固定尾部）")
                return False
            
            # 获取最大聚类的中心向量
            max_label = max(label_counts, key=label_counts.get)
            cluster_indices = [i for i, l in enumerate(labels) if l == max_label]
            cluster_embeddings = tail_embeddings[cluster_indices]
            
            # 存储该频道的尾部模式（使用聚类中心）
            self.channel_patterns[channel_id] = {
                'centroid': np.mean(cluster_embeddings, axis=0),
                'samples': cluster_embeddings[:5],  # 保存几个样本用于验证
                'threshold': 0.75,  # 相似度阈值
                'learned_at': datetime.now().isoformat(),
                'sample_count': len(cluster_indices)
            }
            
            logger.info(f"✅ 频道 {channel_id} 尾部模式学习完成，发现 {len(cluster_indices)} 个相似样本")
            return True
            
        except Exception as e:
            logger.error(f"学习频道 {channel_id} 模式失败: {e}")
            return False
    
    def is_channel_tail(self, channel_id: str, text: str) -> Tuple[bool, float]:
        """
        判断文本是否为特定频道的尾部内容
        
        Args:
            channel_id: 频道ID
            text: 要检查的文本
            
        Returns:
            (是否为尾部, 相似度分数)
        """
        if not self.initialized or channel_id not in self.channel_patterns:
            return False, 0.0
        
        try:
            pattern = self.channel_patterns[channel_id]
            text_embedding = self.model.encode([text])[0]
            
            # 计算与频道尾部模式的相似度
            similarity = cosine_similarity(
                text_embedding.reshape(1, -1),
                pattern['centroid'].reshape(1, -1)
            )[0][0]
            
            is_tail = similarity >= pattern['threshold']
            return is_tail, float(similarity)
            
        except Exception as e:
            logger.error(f"检查尾部内容失败: {e}")
            return False, 0.0
    
    def filter_channel_tail(self, channel_id: str, content: str) -> str:
        """
        过滤掉频道特定的尾部内容
        
        Args:
            channel_id: 频道ID
            content: 原始内容
            
        Returns:
            过滤后的内容
        """
        if not self.initialized or channel_id not in self.channel_patterns:
            return content
        
        lines = content.split('\n')
        if len(lines) <= 3:
            return content
        
        # 从后往前检查，找到尾部开始的位置
        tail_start = len(lines)
        for i in range(len(lines) - 1, max(0, len(lines) - 10), -1):
            # 检查从第i行到结尾的内容是否为尾部
            test_tail = '\n'.join(lines[i:])
            is_tail, score = self.is_channel_tail(channel_id, test_tail)
            
            if is_tail and score > 0.8:
                tail_start = min(tail_start, i)  # 记录最早的尾部开始位置
                # 继续向前检查，不要break
        
        if tail_start < len(lines):
            filtered = '\n'.join(lines[:tail_start])
            logger.info(f"过滤频道 {channel_id} 尾部: {len(content)} -> {len(filtered)} 字符")
            return filtered.strip()
        
        return content
    
    async def train_ad_classifier(self, ad_samples: List[str], normal_samples: List[str]):
        """
        训练广告分类器
        
        Args:
            ad_samples: 广告样本列表
            normal_samples: 正常内容样本列表
        """
        if not self.initialized:
            logger.warning("AI过滤器未初始化，无法训练")
            return
        
        try:
            logger.info(f"开始训练广告分类器: {len(ad_samples)} 个广告样本, {len(normal_samples)} 个正常样本")
            
            # 计算嵌入向量
            if ad_samples:
                self.ad_embeddings = self.model.encode(ad_samples)
            if normal_samples:
                self.normal_embeddings = self.model.encode(normal_samples)
            
            logger.info("✅ 广告分类器训练完成")
            
        except Exception as e:
            logger.error(f"训练广告分类器失败: {e}")
    
    def is_advertisement(self, text: str) -> Tuple[bool, float]:
        """
        判断文本是否为广告
        
        Args:
            text: 要检查的文本
            
        Returns:
            (是否为广告, 置信度)
        """
        if not self.initialized or (len(self.ad_embeddings) == 0 and len(self.normal_embeddings) == 0):
            return False, 0.0
        
        try:
            text_embedding = self.model.encode([text])[0].reshape(1, -1)
            
            # 计算与广告样本的相似度
            ad_similarity = 0.0
            if len(self.ad_embeddings) > 0:
                ad_similarities = cosine_similarity(text_embedding, self.ad_embeddings)
                ad_similarity = np.max(ad_similarities)
            
            # 计算与正常内容的相似度
            normal_similarity = 0.0
            if len(self.normal_embeddings) > 0:
                normal_similarities = cosine_similarity(text_embedding, self.normal_embeddings)
                normal_similarity = np.max(normal_similarities)
            
            # 如果更像广告，则判定为广告
            is_ad = ad_similarity > normal_similarity and ad_similarity > 0.7
            confidence = float(ad_similarity) if is_ad else float(1 - ad_similarity)
            
            return is_ad, confidence
            
        except Exception as e:
            logger.error(f"广告检测失败: {e}")
            return False, 0.0
    
    def save_patterns(self, filepath: str):
        """保存学习的模式到文件"""
        try:
            data = {
                'channel_patterns': {},
                'ad_sample_count': len(self.ad_embeddings),
                'normal_sample_count': len(self.normal_embeddings),
                'saved_at': datetime.now().isoformat()
            }
            
            # 转换numpy数组为列表以便JSON序列化
            for channel_id, pattern in self.channel_patterns.items():
                data['channel_patterns'][channel_id] = {
                    'centroid': pattern['centroid'].tolist(),
                    'threshold': pattern['threshold'],
                    'learned_at': pattern['learned_at'],
                    'sample_count': pattern['sample_count']
                }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"模式已保存到 {filepath}")
            
        except Exception as e:
            logger.error(f"保存模式失败: {e}")
    
    def load_patterns(self, filepath: str):
        """从文件加载学习的模式"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 恢复numpy数组
            for channel_id, pattern_data in data['channel_patterns'].items():
                self.channel_patterns[channel_id] = {
                    'centroid': np.array(pattern_data['centroid']),
                    'threshold': pattern_data['threshold'],
                    'learned_at': pattern_data['learned_at'],
                    'sample_count': pattern_data['sample_count'],
                    'samples': []  # 加载时不恢复样本
                }
            
            logger.info(f"从 {filepath} 加载了 {len(self.channel_patterns)} 个频道模式")
            
        except Exception as e:
            logger.error(f"加载模式失败: {e}")


# 全局实例
ai_filter = IntelligentFilter()