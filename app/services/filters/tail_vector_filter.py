"""
基于ONNX语义模型的尾部过滤器
使用真正的语义向量进行精确识别

Linus原则：消除所有不必要的复杂性
Author: Claude (ONNX重构)
Created: 2025-09-07
"""

import json
import numpy as np
import logging
import os
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from sklearn.metrics.pairwise import cosine_similarity

from app.core.path_config import PathConfig
from app.services.semantic_extractor import SemanticExtractor

logger = logging.getLogger(__name__)


class TailVectorFilter:
    """基于ONNX语义模型的尾部过滤器
    
    核心思路：
    1. 使用ONNX语义模型生成768维向量
    2. 与尾部样本语义向量计算相似度
    3. 纯语义判断，无复杂逻辑
    """
    
    def __init__(self):
        """初始化语义向量过滤器"""
        self.semantic_extractor = None
        self.tail_embeddings = None
        self.tail_samples = []
        self.threshold = None
        self.is_initialized = False
        
        self._initialize()
    
    def _initialize(self):
        """初始化过滤器 - 🚫 临时禁用避免内存泄漏"""
        logger.info("🚫 临时禁用ONNX语义尾部过滤器（避免内存泄漏）")
        
        # 🚫 临时禁用所有初始化，避免ONNX模型加载导致内存泄漏
        self.is_initialized = False
        self.semantic_extractor = None
        self.tail_embeddings = None
        self.tail_samples = []
        self.threshold = 0.7
    
    def _load_threshold(self) -> float:
        """从统一配置文件加载阈值"""
        threshold_file = os.path.join(PathConfig.CONFIG_DIR, 'thresholds.json')
        
        if not os.path.exists(threshold_file):
            logger.warning("阈值配置文件不存在，使用默认值0.7")
            return 0.7
        
        try:
            with open(threshold_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('tail_filter', {}).get('semantic', {}).get('current', 0.7)
        except Exception as e:
            logger.warning(f"加载阈值配置失败: {e}，使用默认值0.7")
            return 0.7
    
    def _load_tail_embeddings(self):
        """加载尾部样本的语义向量"""
        embeddings_file = os.path.join(PathConfig.TAIL_TRAINING_DIR, 'tail_embeddings.npz')
        samples_file = os.path.join(PathConfig.TAIL_TRAINING_DIR, 'tail_filter_samples.json')
        
        if os.path.exists(embeddings_file):
            try:
                data = np.load(embeddings_file)
                self.tail_embeddings = data['embeddings']
                self.tail_samples = data['samples'].tolist()
                logger.info(f"📂 加载现有语义向量缓存: {len(self.tail_samples)} 个样本")
                return
            except Exception as e:
                logger.warning(f"加载语义向量缓存失败: {e}")
        
        logger.info("🔨 生成新的语义向量...")
        self._build_embeddings(samples_file, embeddings_file)
    
    def _build_embeddings(self, samples_file: str, embeddings_file: str):
        """构建尾部样本的语义向量 - 改进：拆分为单行向量并去重"""
        if not os.path.exists(samples_file):
            raise FileNotFoundError(f"训练样本文件不存在: {samples_file}")
        
        with open(samples_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        if not samples:
            raise ValueError("没有找到训练样本")
        
        # 🚀 改进：拆分多行样本为单行并去重
        unique_lines = set()  # 用于去重
        self.tail_samples = []
        
        logger.info(f"📝 拆分 {len(samples)} 个多行样本为单行并去重...")
        
        for sample in samples:
            if 'tail_part' in sample:
                tail_text = sample['tail_part'].strip()
                if not tail_text:
                    continue
                
                # 按行拆分
                lines = tail_text.split('\n')
                
                for line in lines:
                    line = line.strip()
                    # 过滤条件：非空、长度>=10、未重复
                    if line and len(line) >= 10 and line not in unique_lines:
                        unique_lines.add(line)
                        self.tail_samples.append(line)
        
        if not self.tail_samples:
            raise ValueError("没有有效的尾部文本行")
        
        logger.info(f"✅ 去重后得到 {len(self.tail_samples)} 个独立行样本")
        
        # 生成向量
        embeddings = []
        failed_count = 0
        
        for i, text in enumerate(self.tail_samples):
            if (i + 1) % 50 == 0:
                logger.info(f"   处理进度: {i + 1}/{len(self.tail_samples)}")
            
            vector = self.semantic_extractor.extract_vector(text)
            if vector:
                embeddings.append(vector)
            else:
                logger.warning(f"无法提取向量: {text[:50]}...")
                # 使用零向量作为占位符
                embeddings.append([0.0] * 768)
                failed_count += 1
        
        self.tail_embeddings = np.array(embeddings)
        
        os.makedirs(os.path.dirname(embeddings_file), exist_ok=True)
        np.savez_compressed(embeddings_file, 
                          embeddings=self.tail_embeddings,
                          samples=np.array(self.tail_samples))
        
        logger.info(f"💾 单行向量已保存到: {embeddings_file}")
        logger.info(f"📊 成功生成: {len(embeddings) - failed_count} 个向量, 失败: {failed_count} 个")
    
    def is_tail_content(self, text: str) -> Tuple[bool, float]:
        """
        判断文本是否为尾部内容
        
        Args:
            text: 要判断的文本
            
        Returns:
            (是否为尾部内容, 最大相似度)
        """
        if not self.is_initialized or self.tail_embeddings is None:
            return False, 0.0
        
        if not text.strip():
            return False, 0.0
        
        try:
            text_vector = self.semantic_extractor.extract_vector(text)
            if not text_vector:
                return False, 0.0
            text_embedding = np.array(text_vector).reshape(1, -1)
            
            similarities = cosine_similarity(text_embedding, self.tail_embeddings)[0]
            max_similarity = float(np.max(similarities))
            
            is_tail = max_similarity > self.threshold
            
            if is_tail:
                logger.debug(f"检测到尾部内容 (相似度: {max_similarity:.3f}): {text[:50]}...")
            
            return is_tail, max_similarity
            
        except Exception as e:
            logger.error(f"语义相似度计算失败: {e}")
            return False, 0.0
    
    def add_tail_sample(self, text: str) -> bool:
        """
        添加新的尾部样本并重建向量
        
        Args:
            text: 新的尾部样本文本
            
        Returns:
            是否成功添加
        """
        if not self.is_initialized:
            return False
        
        text = text.strip()
        if not text or text in self.tail_samples:
            return False
        
        try:
            new_vector = self.semantic_extractor.extract_vector(text)
            if not new_vector:
                logger.error(f"无法提取向量: {text[:50]}...")
                return False
            new_embedding = np.array(new_vector).reshape(1, -1)
            
            self.tail_samples.append(text)
            
            if self.tail_embeddings is None:
                self.tail_embeddings = new_embedding
            else:
                self.tail_embeddings = np.vstack([self.tail_embeddings, new_embedding])
            
            embeddings_file = os.path.join(PathConfig.TAIL_TRAINING_DIR, 'tail_embeddings.npz')
            np.savez_compressed(embeddings_file,
                              embeddings=self.tail_embeddings,
                              samples=np.array(self.tail_samples))
            
            logger.info(f"✅ 添加新尾部样本: {text[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"添加尾部样本失败: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            'initialized': self.is_initialized,
            'sample_count': len(self.tail_samples),
            'threshold': self.threshold,
            'vector_dimension': self.tail_embeddings.shape[1] if self.tail_embeddings is not None else 0,
            'model_type': 'ONNX_Semantic'
        }


_tail_vector_filter_instance = None


def get_tail_vector_filter() -> TailVectorFilter:
    """获取尾部向量过滤器单例"""
    global _tail_vector_filter_instance
    if _tail_vector_filter_instance is None:
        _tail_vector_filter_instance = TailVectorFilter()
    return _tail_vector_filter_instance