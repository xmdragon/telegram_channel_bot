"""
基于向量相似度的尾部过滤器
利用训练样本构建向量数据库，精确识别推广内容

Author: Claude  
Created: 2025-08-24
"""

import json
import numpy as np
import logging
import os
from typing import List, Tuple, Dict, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class TailVectorFilter:
    """基于向量相似度的尾部过滤器
    
    核心思路：
    1. 尾部内容模式有限，可以用向量完全学习
    2. 使用TF-IDF向量化训练样本
    3. 计算相似度精确识别推广内容
    """
    
    def __init__(self, similarity_threshold: float = 0.15):
        """初始化向量过滤器
        
        Args:
            similarity_threshold: 相似度阈值，超过此值认为是尾部内容
        """
        self.similarity_threshold = similarity_threshold
        self.vectorizer = None
        self.tail_vectors = None
        self.tail_samples = []
        self.is_initialized = False
        
        # 尝试加载向量数据库
        self._load_or_build_vectors()
    
    def _load_or_build_vectors(self):
        """加载现有向量或重新构建"""
        logger.info("🚀 初始化尾部向量过滤器...")
        logger.info(f"   相似度阈值: {self.similarity_threshold}")
        
        try:
            # 先尝试加载现有向量
            logger.info("📂 尝试加载现有向量数据库...")
            if self._load_existing_vectors():
                logger.info("✅ 成功加载现有尾部向量数据库")
                logger.info(f"   样本数量: {len(self.tail_samples)}")
                logger.info(f"   向量维度: {self.tail_vectors.shape}")
                logger.info(f"   词汇表大小: {len(self.vectorizer.vocabulary_)}")
                self.is_initialized = True
                return
        except Exception as e:
            logger.warning(f"⚠️ 加载现有向量失败: {e}")
            import traceback
            logger.debug(f"详细错误: {traceback.format_exc()}")
        
        # 重新构建向量数据库
        try:
            logger.info("🔨 重新构建向量数据库...")
            self._build_vector_database()
            logger.info("✅ 成功构建新的尾部向量数据库")
            logger.info(f"   样本数量: {len(self.tail_samples)}")
            logger.info(f"   向量维度: {self.tail_vectors.shape}")
            self.is_initialized = True
        except Exception as e:
            logger.error(f"❌ 构建向量数据库失败: {e}")
            logger.error(f"   错误类型: {type(e).__name__}")
            import traceback
            logger.error(f"   完整错误堆栈:\n{traceback.format_exc()}")
            self.is_initialized = False
            
            # 保存错误信息用于调试
            self.init_error = str(e)
    
    def _load_existing_vectors(self) -> bool:
        """加载现有的向量数据"""
        vector_file = os.path.join(PathConfig.TAIL_TRAINING_DIR, 'tail_vectors.npz')
        samples_file = os.path.join(PathConfig.TAIL_TRAINING_DIR, 'tail_filter_samples.json')
        
        if not (os.path.exists(vector_file) and os.path.exists(samples_file)):
            return False
        
        # 加载训练样本
        with open(samples_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
            self.tail_samples = [sample['tail_part'] for sample in samples if 'tail_part' in sample]
        
        if not self.tail_samples:
            return False
        
        # 重新构建向量化器（因为TF-IDF需要重新fit）
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 3),
            max_features=1000,
            stop_words=None,  # 中文没有标准stop words
            token_pattern=r'[\u4e00-\u9fff]+|@\w+|[a-zA-Z0-9]+',  # 中文、用户名、英文数字
            min_df=1
        )
        
        # 重新训练向量化器并生成向量
        self.tail_vectors = self.vectorizer.fit_transform(self.tail_samples)
        
        logger.info(f"📊 加载了 {len(self.tail_samples)} 个尾部样本")
        return True
    
    def _build_vector_database(self):
        """从训练样本构建向量数据库"""
        samples_file = os.path.join(PathConfig.TAIL_TRAINING_DIR, 'tail_filter_samples.json')
        
        if not os.path.exists(samples_file):
            raise FileNotFoundError(f"训练样本文件不存在: {samples_file}")
        
        # 加载训练样本
        with open(samples_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        if not samples:
            raise ValueError("没有找到训练样本")
        
        # 提取尾部文本
        self.tail_samples = []
        for sample in samples:
            if 'tail_part' in sample:
                tail_text = sample['tail_part'].strip()
                if tail_text:
                    self.tail_samples.append(tail_text)
        
        if not self.tail_samples:
            raise ValueError("没有有效的尾部文本样本")
        
        logger.info(f"📝 提取了 {len(self.tail_samples)} 个尾部样本")
        
        # 构建TF-IDF向量化器
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 3),  # 1-3元组，能捕获"订阅频道"、"投稿爆料"等短语
            max_features=1000,   # 最大特征数
            token_pattern=r'[\u4e00-\u9fff]+|@\w+|[a-zA-Z0-9]+',  # 中文、用户名、英文数字
            min_df=1,  # 最小文档频率
            lowercase=True
        )
        
        # 训练向量化器并生成向量矩阵
        self.tail_vectors = self.vectorizer.fit_transform(self.tail_samples)
        
        logger.info(f"🔢 生成了 {self.tail_vectors.shape} 的向量矩阵")
        logger.info(f"📈 向量化器词汇表大小: {len(self.vectorizer.vocabulary_)}")
        
        # 保存向量数据（可选）
        self._save_vectors()
    
    def _save_vectors(self):
        """保存向量数据到文件"""
        try:
            vector_file = os.path.join(PathConfig.TAIL_TRAINING_DIR, 'tail_vectors.npz')
            np.savez_compressed(vector_file, 
                               vectors=self.tail_vectors.toarray(),
                               samples=np.array(self.tail_samples, dtype=object))
            logger.debug(f"💾 向量数据已保存到: {vector_file}")
        except Exception as e:
            logger.warning(f"⚠️ 保存向量数据失败: {e}")
    
    def is_tail_content(self, text: str) -> Tuple[bool, float]:
        """判断文本是否为尾部内容
        
        Args:
            text: 要检测的文本
            
        Returns:
            (是否为尾部, 最高相似度)
        """
        if not self.is_initialized or not text.strip():
            return False, 0.0
        
        try:
            # 向量化输入文本
            text_vector = self.vectorizer.transform([text])
            
            # 计算与所有尾部样本的相似度
            similarities = cosine_similarity(text_vector, self.tail_vectors)
            max_similarity = similarities.max()
            
            is_tail = max_similarity >= self.similarity_threshold
            
            if is_tail:
                # 找到最相似的样本用于调试
                best_match_idx = similarities.argmax()
                best_match_sample = self.tail_samples[best_match_idx]
                logger.debug(f"🎯 检测到尾部内容 (相似度: {max_similarity:.3f})")
                logger.debug(f"   输入: {text[:50]}{'...' if len(text) > 50 else ''}")
                logger.debug(f"   匹配: {best_match_sample[:50]}{'...' if len(best_match_sample) > 50 else ''}")
            
            return is_tail, max_similarity
            
        except Exception as e:
            logger.error(f"❌ 向量匹配失败: {e}")
            return False, 0.0
    
    def filter_lines(self, lines: List[str]) -> Tuple[List[str], List[str], List[float]]:
        """对多行文本进行过滤
        
        Args:
            lines: 文本行列表
            
        Returns:
            (保留的行, 过滤的行, 相似度列表)
        """
        if not self.is_initialized:
            return lines, [], []
        
        kept_lines = []
        filtered_lines = []
        similarities = []
        
        for line in lines:
            if not line.strip():
                # 空行保留
                kept_lines.append(line)
                similarities.append(0.0)
                continue
            
            is_tail, similarity = self.is_tail_content(line)
            similarities.append(similarity)
            
            if is_tail:
                filtered_lines.append(line)
                logger.debug(f"✂️ 过滤行 (相似度: {similarity:.3f}): {line}")
            else:
                kept_lines.append(line)
        
        return kept_lines, filtered_lines, similarities
    
    def find_semantic_boundary(self, content: str) -> Optional[int]:
        """找到语义边界位置
        
        Args:
            content: 完整内容
            
        Returns:
            边界行号，如果没有找到返回None
        """
        lines = content.split('\n')
        
        # 从后往前检查，寻找第一个可能的边界点
        for i in range(len(lines) - 1, 0, -1):
            current_line = lines[i].strip()
            prev_line = lines[i-1].strip() if i > 0 else ""
            
            if not current_line:
                continue
            
            # 检查是否有格式突变
            has_format_change = False
            
            # 1. 联系方式突然出现
            has_contact_current = '@' in current_line or 't.me/' in current_line
            has_contact_prev = '@' in prev_line or 't.me/' in prev_line if prev_line else False
            
            if has_contact_current and not has_contact_prev:
                has_format_change = True
            
            # 2. 特殊符号突然出现
            special_emojis = ['📣', '💬', '😍', '🔔', '⚡', '📱', '🔗']
            has_emoji_current = any(emoji in current_line for emoji in special_emojis)
            has_emoji_prev = any(emoji in prev_line for emoji in special_emojis) if prev_line else False
            
            if has_emoji_current and not has_emoji_prev:
                has_format_change = True
            
            # 3. 行动号召突然出现
            cta_words = ['订阅', '加入', '联系', '投稿', '爆料', '关注']
            has_cta_current = any(word in current_line for word in cta_words)
            has_cta_prev = any(word in prev_line for word in cta_words) if prev_line else False
            
            if has_cta_current and not has_cta_prev:
                has_format_change = True
            
            if has_format_change:
                logger.debug(f"🔍 检测到语义边界 - 第{i}行: {current_line[:30]}...")
                return i
        
        # 如果没有明显边界，检查最后几行是否都是推广内容
        for i in range(max(0, len(lines) - 5), len(lines)):
            if i < len(lines):
                line = lines[i].strip()
                if line:
                    is_tail, similarity = self.is_tail_content(line)
                    if is_tail:
                        logger.debug(f"🔍 基于向量检测到边界 - 第{i}行: {line[:30]}...")
                        return i
        
        return None
    
    def get_statistics(self) -> Dict:
        """获取过滤器统计信息"""
        if not self.is_initialized:
            return {"status": "未初始化"}
        
        return {
            "status": "已初始化",
            "samples_count": len(self.tail_samples),
            "vector_shape": self.tail_vectors.shape,
            "vocabulary_size": len(self.vectorizer.vocabulary_),
            "similarity_threshold": self.similarity_threshold,
            "sample_preview": self.tail_samples[:3] if self.tail_samples else []
        }


# 全局实例
_tail_vector_filter = None

def get_tail_vector_filter() -> TailVectorFilter:
    """获取全局尾部向量过滤器实例"""
    global _tail_vector_filter
    if _tail_vector_filter is None:
        _tail_vector_filter = TailVectorFilter()
    return _tail_vector_filter