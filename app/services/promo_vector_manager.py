"""
推广样本向量管理器
基于TailVectorManager架构，管理推广链接过滤的向量数据
"""
import numpy as np
import json
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from sentence_transformers import SentenceTransformer

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)

class PromoVectorManager:
    """推广样本向量管理器"""
    
    def __init__(self):
        self.model_name = "all-MiniLM-L6-v2"  # 轻量级模型，384维向量
        self.model = None
        self.vector_cache_file = PathConfig.PROMO_TRAINING_DIR / "vector_cache.json"
        self.vector_data_file = PathConfig.PROMO_TRAINING_DIR / "vectors.npy"
        
        # 确保目录存在
        PathConfig.PROMO_TRAINING_DIR.mkdir(parents=True, exist_ok=True)
        
        self._vector_cache = {}  # 文本hash -> 向量索引映射
        self._vectors = None     # numpy数组存储所有向量
        self._texts = []         # 对应的文本列表
        
        self._initialize()
    
    def _initialize(self):
        """初始化向量管理器"""
        try:
            # 延迟加载模型
            self._load_model()
            
            # 加载现有向量数据
            self._load_vectors()
            
            logger.info(f"推广向量管理器初始化完成，已缓存 {len(self._texts)} 个向量")
            
        except Exception as e:
            logger.error(f"推广向量管理器初始化失败: {e}")
    
    def _load_model(self):
        """延迟加载SentenceTransformer模型"""
        if self.model is None:
            try:
                self.model = SentenceTransformer(self.model_name)
                logger.info(f"加载向量模型成功: {self.model_name}")
            except Exception as e:
                logger.error(f"加载向量模型失败: {e}")
                raise
    
    def _load_vectors(self):
        """从文件加载向量缓存"""
        try:
            # 加载向量缓存映射
            if self.vector_cache_file.exists():
                cache_data = SafeFileOperation.read_json_safe(self.vector_cache_file)
                if cache_data:
                    self._vector_cache = cache_data.get('cache', {})
                    self._texts = cache_data.get('texts', [])
            
            # 加载向量数据
            if self.vector_data_file.exists():
                self._vectors = np.load(str(self.vector_data_file))
                
            # 验证数据一致性
            if len(self._texts) != (self._vectors.shape[0] if self._vectors is not None else 0):
                logger.warning("向量缓存数据不一致，重新构建")
                self._rebuild_cache()
                
        except Exception as e:
            logger.error(f"加载向量缓存失败: {e}")
            self._vector_cache = {}
            self._vectors = None
            self._texts = []
    
    def _save_vectors(self):
        """保存向量缓存到文件"""
        try:
            # 保存缓存映射
            cache_data = {
                'cache': self._vector_cache,
                'texts': self._texts
            }
            SafeFileOperation.write_json_safe(self.vector_cache_file, cache_data)
            
            # 保存向量数据
            if self._vectors is not None:
                np.save(str(self.vector_data_file), self._vectors)
                
            logger.debug(f"向量缓存保存成功，共 {len(self._texts)} 个向量")
            
        except Exception as e:
            logger.error(f"保存向量缓存失败: {e}")
    
    def _rebuild_cache(self):
        """重新构建向量缓存"""
        try:
            # 从推广样本文件重新构建
            from app.routers.training.base import load_promo_samples
            samples = load_promo_samples()
            
            if not samples:
                logger.info("没有推广样本，清空向量缓存")
                self._vector_cache = {}
                self._vectors = None
                self._texts = []
                return
            
            # 提取所有文本
            texts = []
            for sample in samples:
                if sample.get('content'):
                    texts.append(sample['content'].strip())
            
            if not texts:
                logger.info("推广样本中没有有效文本内容")
                return
            
            # 重新计算向量
            logger.info(f"重新构建推广向量缓存，处理 {len(texts)} 个文本")
            self._encode_texts(texts, rebuild=True)
            
        except Exception as e:
            logger.error(f"重新构建向量缓存失败: {e}")
    
    def _get_text_hash(self, text: str) -> str:
        """获取文本的hash值"""
        import hashlib
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _encode_texts(self, texts: List[str], rebuild: bool = False):
        """编码文本为向量"""
        if not texts:
            return
            
        try:
            self._load_model()
            
            if rebuild:
                # 完全重建
                self._vector_cache = {}
                self._texts = []
                self._vectors = None
            
            # 找出需要编码的新文本
            new_texts = []
            for text in texts:
                text_hash = self._get_text_hash(text)
                if text_hash not in self._vector_cache:
                    new_texts.append(text)
            
            if not new_texts:
                return  # 没有新文本需要编码
                
            # 编码新文本
            logger.info(f"编码 {len(new_texts)} 个新推广文本")
            new_vectors = self.model.encode(new_texts, normalize_embeddings=True)
            
            # 更新缓存
            start_idx = len(self._texts)
            for i, text in enumerate(new_texts):
                text_hash = self._get_text_hash(text)
                self._vector_cache[text_hash] = start_idx + i
                self._texts.append(text)
            
            # 合并向量
            if self._vectors is None:
                self._vectors = new_vectors
            else:
                self._vectors = np.vstack([self._vectors, new_vectors])
            
            # 保存到文件
            self._save_vectors()
            
            logger.info(f"推广向量缓存更新完成，总计 {len(self._texts)} 个向量")
            
        except Exception as e:
            logger.error(f"编码推广文本失败: {e}")
    
    def add_sample_vector(self, content: str):
        """添加单个推广样本的向量"""
        if not content or not content.strip():
            return
            
        content = content.strip()
        text_hash = self._get_text_hash(content)
        
        # 检查是否已存在
        if text_hash in self._vector_cache:
            return
            
        # 编码新样本
        self._encode_texts([content])
    
    def remove_sample_vector(self, content: str):
        """移除推广样本的向量"""
        if not content:
            return
            
        text_hash = self._get_text_hash(content.strip())
        if text_hash not in self._vector_cache:
            return
            
        try:
            # 获取要删除的索引
            remove_idx = self._vector_cache[text_hash]
            
            # 从缓存中移除
            del self._vector_cache[text_hash]
            
            # 从文本列表中移除
            self._texts.pop(remove_idx)
            
            # 从向量数组中移除
            if self._vectors is not None:
                self._vectors = np.delete(self._vectors, remove_idx, axis=0)
            
            # 更新后续索引
            for key, idx in self._vector_cache.items():
                if idx > remove_idx:
                    self._vector_cache[key] = idx - 1
            
            # 保存更新
            self._save_vectors()
            
            logger.info(f"移除推广向量成功，剩余 {len(self._texts)} 个向量")
            
        except Exception as e:
            logger.error(f"移除推广向量失败: {e}")
    
    def update_cache(self):
        """更新向量缓存（同步推广样本）"""
        try:
            from app.routers.training.base import load_promo_samples
            samples = load_promo_samples()
            
            # 提取现有样本的内容
            current_contents = set()
            for sample in samples:
                if sample.get('content'):
                    current_contents.add(sample['content'].strip())
            
            # 找出缓存中多余的向量（样本已删除）
            cached_contents = set(self._texts)
            to_remove = cached_contents - current_contents
            
            # 移除多余的向量
            for content in to_remove:
                self.remove_sample_vector(content)
            
            # 添加新的向量
            to_add = current_contents - set(self._texts)
            if to_add:
                self._encode_texts(list(to_add))
            
            logger.info(f"推广向量缓存同步完成，现有 {len(self._texts)} 个向量")
            
        except Exception as e:
            logger.error(f"更新推广向量缓存失败: {e}")
    
    def find_similar_samples(
        self, 
        query_text: str, 
        threshold: float = 0.85, 
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        查找相似的推广样本
        
        Args:
            query_text: 查询文本
            threshold: 相似度阈值
            top_k: 返回最相似的k个样本
            
        Returns:
            [(样本文本, 相似度分数), ...]
        """
        if not query_text or not query_text.strip():
            return []
            
        if self._vectors is None or len(self._texts) == 0:
            return []
            
        try:
            self._load_model()
            
            # 编码查询文本
            query_vector = self.model.encode([query_text.strip()], normalize_embeddings=True)
            
            # 计算余弦相似度
            similarities = np.dot(self._vectors, query_vector.T).flatten()
            
            # 找到超过阈值的样本
            valid_indices = np.where(similarities >= threshold)[0]
            
            if len(valid_indices) == 0:
                return []
            
            # 按相似度排序
            valid_similarities = similarities[valid_indices]
            sorted_indices = valid_indices[np.argsort(valid_similarities)[::-1]]
            
            # 返回top-k结果
            results = []
            for idx in sorted_indices[:top_k]:
                results.append((self._texts[idx], float(similarities[idx])))
            
            return results
            
        except Exception as e:
            logger.error(f"查找相似推广样本失败: {e}")
            return []
    
    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        return {
            'total_vectors': len(self._texts),
            'cache_file_exists': self.vector_cache_file.exists(),
            'vector_file_exists': self.vector_data_file.exists(),
            'model_loaded': self.model is not None,
            'vector_dimension': self._vectors.shape[1] if self._vectors is not None else 0
        }
    
    def clear_cache(self):
        """清空向量缓存"""
        try:
            self._vector_cache = {}
            self._vectors = None
            self._texts = []
            
            # 删除缓存文件
            if self.vector_cache_file.exists():
                self.vector_cache_file.unlink()
            if self.vector_data_file.exists():
                self.vector_data_file.unlink()
                
            logger.info("推广向量缓存已清空")
            
        except Exception as e:
            logger.error(f"清空推广向量缓存失败: {e}")

# 全局实例
promo_vector_manager = PromoVectorManager()