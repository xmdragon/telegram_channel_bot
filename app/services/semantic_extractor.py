"""
真正的AI语义提取器 - 基于text2vec的广告检测
消除TF-IDF垃圾算法，使用现代语义理解模型

Linus原则：简洁、实用、无特殊情况
Author: Claude (Linus式重构)
Created: 2025-09-03
"""

import logging
import numpy as np
from typing import List, Optional, Dict, Any
from text2vec import SentenceModel

logger = logging.getLogger(__name__)


class SemanticExtractor:
    """真正的AI语义提取器 - Linus式极简设计"""
    
    def __init__(self, vector_dim: int = 768):
        """
        初始化text2vec语义提取器
        
        Args:
            vector_dim: text2vec固定768维
        """
        self.vector_dim = vector_dim
        self.model = None
        self.initialized = False
        
        logger.info(f"text2vec语义提取器初始化 - 维度: {vector_dim}")
    
    def _initialize_model(self):
        """延迟初始化text2vec模型"""
        if self.initialized:
            return True
            
        try:
            logger.info("正在加载text2vec中文语义模型...")
            self.model = SentenceModel('shibing624/text2vec-base-chinese')
            self.initialized = True
            logger.info("✅ text2vec模型加载成功")
            return True
        except Exception as e:
            logger.error(f"text2vec模型加载失败: {e}")
            return False
    
    def extract_vector(self, text: str) -> Optional[List[float]]:
        """
        从文本提取768维语义向量 - Linus式简洁实现
        
        Args:
            text: 原始文本
            
        Returns:
            768维语义向量，失败返回None
        """
        if not text or not text.strip():
            return None
            
        # 确保模型已初始化
        if not self._initialize_model():
            return None
            
        try:
            # text2vec直接提取语义向量 - 无需预处理！
            vectors = self.model.encode([text.strip()])
            return vectors[0].tolist()
        except Exception as e:
            logger.error(f"语义向量提取失败: {e}")
            return None
    
    def extract_vector_with_info(self, text: str) -> Dict[str, Any]:
        """
        提取向量并返回详细信息 - 向后兼容接口
        
        Args:
            text: 输入文本
            
        Returns:
            包含向量和状态信息的字典
        """
        if not text or not text.strip():
            return {
                'success': False,
                'vector': None,
                'error_type': 'invalid_text',
                'error_message': '输入文本为空',
                'processed_text': ''
            }
        
        vector = self.extract_vector(text)
        if vector:
            return {
                'success': True,
                'vector': vector,
                'error_type': 'none',
                'error_message': '',
                'processed_text': text.strip()
            }
        else:
            return {
                'success': False,
                'vector': None,
                'error_type': 'technical_error',
                'error_message': '向量提取失败',
                'processed_text': text.strip()
            }
    
    def batch_extract(self, texts: List[str]) -> Dict[str, List[float]]:
        """
        批量提取向量
        
        Args:
            texts: 文本列表
            
        Returns:
            文本到向量的映射
        """
        results = {}
        
        # 确保模型已初始化
        if not self._initialize_model():
            return results
        
        try:
            # text2vec支持批量处理，更高效
            clean_texts = [text.strip() for text in texts if text and text.strip()]
            if not clean_texts:
                return results
            
            vectors = self.model.encode(clean_texts)
            
            for i, vector in enumerate(vectors):
                results[f"text_{i}"] = vector.tolist()
                
            logger.info(f"批量提取完成: {len(results)}/{len(texts)}")
            return results
            
        except Exception as e:
            logger.error(f"批量向量提取失败: {e}")
            return results
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            'initialized': self.initialized,
            'vector_dim': self.vector_dim,
            'model_name': 'shibing624/text2vec-base-chinese',
            'model_type': 'text2vec',
            'semantic_model': True,
            'supports_batch': True
        }


# 全局语义提取器实例
_semantic_extractor = None

def get_semantic_extractor(vector_dim: int = 768) -> SemanticExtractor:
    """获取语义提取器实例（单例模式）"""
    global _semantic_extractor
    if _semantic_extractor is None:
        _semantic_extractor = SemanticExtractor(vector_dim)
    return _semantic_extractor