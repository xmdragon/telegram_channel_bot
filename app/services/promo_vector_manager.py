"""
推广样本向量管理器
基于TailVectorManager架构，管理推广链接过滤的向量数据
⚠️ 注意：系统已切换到轻量级模式，不再依赖sentence_transformers
"""
import numpy as np
import json
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

# 🚀 Linus式简化：彻底移除sentence_transformers依赖
SENTENCE_TRANSFORMERS_AVAILABLE = False
SentenceTransformer = None

logger = logging.getLogger(__name__)

class PromoVectorManager:
    """推广样本向量管理器"""
    
    def __init__(self):
        # 🚀 Linus式简化：不再依赖重量级模型
        self.disabled = False
        self.model_name = "lightweight"  # 轻量级模型标识
        self.model = None  # 废弃，不再使用
        self.vector_cache_file = PathConfig.PROMO_TRAINING_DIR / "vector_cache.json"
        self.vector_data_file = PathConfig.PROMO_TRAINING_DIR / "vectors.npy"
        
        # 确保目录存在
        PathConfig.PROMO_TRAINING_DIR.mkdir(parents=True, exist_ok=True)
        
        self._vector_cache = {}  # 文本hash -> 向量索引映射
        self._vectors = None     # numpy数组存储所有向量（废弃）
        self._texts = []         # 对应的文本列表
        self._initialized = False  # 延迟初始化标记
        
        # 🎯 Linus式优化: 延迟初始化，按需加载轻量模型
        logger.debug("✅ 推广向量管理器实例化（轻量级模式）")
    
    def _ensure_initialized(self):
        """确保管理器已初始化（延迟加载）"""
        if self.disabled:
            return
        if not self._initialized:
            logger.info("🔄 首次使用，正在初始化推广向量管理器（轻量级模式）...")
            self._initialize()
            self._initialized = True
            logger.info("✅ 推广向量管理器初始化完成（轻量级模式）")
    
    def _initialize(self):
        """初始化向量管理器 - Linus式简化版本"""
        try:
            # 🚀 不再加载重量级模型，只加载文本数据
            self._load_vectors()
            
            logger.info(f"推广向量管理器初始化完成，已缓存 {len(self._texts)} 个文本样本")
            
        except Exception as e:
            logger.error(f"推广向量管理器初始化失败: {e}")
    
    def _load_model(self):
        """废弃方法 - 不再加载重量级模型"""
        logger.debug("_load_model 已废弃，使用轻量级方案")
        pass
    
    def _load_vectors(self):
        """从文件加载文本缓存 - Linus式简化版本"""
        try:
            # 🚀 只加载文本数据，不加载向量数据
            if self.vector_cache_file.exists():
                cache_data = SafeFileOperation.read_json_safe(self.vector_cache_file)
                if cache_data:
                    self._vector_cache = cache_data.get('cache', {})
                    self._texts = cache_data.get('texts', [])
            
            # 🔥 废弃向量数据加载，使用轻量级方案实时计算
            self._vectors = None  # 不再使用预计算向量
            
            logger.info(f"文本缓存加载成功，共 {len(self._texts)} 个样本")
                
        except Exception as e:
            logger.error(f"加载文本缓存失败: {e}")
            self._vector_cache = {}
            self._vectors = None
            self._texts = []
    
    def _save_vectors(self):
        """保存文本缓存到文件 - Linus式简化版本"""
        try:
            # 🚀 只保存文本数据，不保存向量数据
            cache_data = {
                'cache': self._vector_cache,
                'texts': self._texts
            }
            SafeFileOperation.write_json_safe(self.vector_cache_file, cache_data)
            
            # 🔥 不再保存向量数据，使用轻量级方案实时计算
                
            logger.debug(f"文本缓存保存成功，共 {len(self._texts)} 个文本样本")
            
        except Exception as e:
            logger.error(f"保存文本缓存失败: {e}")
    
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
        """编码文本到缓存 - Linus式简化版本（无需向量）"""
        if not texts:
            return
            
        try:
            if rebuild:
                # 完全重建
                self._vector_cache = {}
                self._texts = []
                self._vectors = None
            
            # 🚀 只需要添加文本，不需要计算向量
            new_texts = []
            for text in texts:
                text_hash = self._get_text_hash(text)
                if text_hash not in self._vector_cache:
                    new_texts.append(text)
            
            if not new_texts:
                return  # 没有新文本需要添加
                
            # 🎯 直接添加文本到缓存，不计算向量
            logger.info(f"添加 {len(new_texts)} 个新推广文本样本")
            
            # 更新缓存映射
            start_idx = len(self._texts)
            for i, text in enumerate(new_texts):
                text_hash = self._get_text_hash(text)
                self._vector_cache[text_hash] = start_idx + i
                self._texts.append(text)
            
            # 保存到文件
            self._save_vectors()
            
            logger.info(f"推广文本缓存更新完成，总计 {len(self._texts)} 个样本")
            
        except Exception as e:
            logger.error(f"添加推广文本失败: {e}")
    
    def add_sample_vector(self, content: str):
        """添加单个推广样本 - Linus式简化版本（无需向量）"""
        if self.disabled:
            return
        if not content or not content.strip():
            return
            
        content = content.strip()
        text_hash = self._get_text_hash(content)
        
        # 检查是否已存在
        if text_hash in self._vector_cache:
            return
            
        # 🚀 直接添加文本样本，不计算向量
        self._encode_texts([content])
    
    def remove_sample_vector(self, content: str):
        """移除推广样本 - Linus式简化版本"""
        if self.disabled:
            return
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
            
            # 🔥 不再操作向量数组，已废弃
            
            # 更新后续索引
            for key, idx in self._vector_cache.items():
                if idx > remove_idx:
                    self._vector_cache[key] = idx - 1
            
            # 保存更新
            self._save_vectors()
            
            logger.info(f"移除推广样本成功，剩余 {len(self._texts)} 个样本")
            
        except Exception as e:
            logger.error(f"移除推广样本失败: {e}")
    
    def update_cache(self):
        """更新文本缓存（同步推广样本）- Linus式简化版本"""
        if self.disabled:
            return
        try:
            from app.routers.training.base import load_promo_samples
            samples = load_promo_samples()
            
            # 提取现有样本的内容
            current_contents = set()
            for sample in samples:
                if sample.get('promo_content'):
                    current_contents.add(sample['promo_content'].strip())
            
            # 找出缓存中多余的文本（样本已删除）
            cached_contents = set(self._texts)
            to_remove = cached_contents - current_contents
            
            # 移除多余的样本
            for content in to_remove:
                self.remove_sample_vector(content)
            
            # 添加新的样本
            to_add = current_contents - set(self._texts)
            if to_add:
                self._encode_texts(list(to_add))
            
            logger.info(f"推广文本缓存同步完成，现有 {len(self._texts)} 个样本")
            
        except Exception as e:
            logger.error(f"更新推广文本缓存失败: {e}")
    
    def find_similar_samples(
        self, 
        query_text: str, 
        threshold: float = 0.85, 
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        查找相似的推广样本 - Linus式简化版本
        
        优先级：
        1. 完全匹配 → 100%
        2. 轻量相似度计算
        3. 简单Jaccard兜底
        
        Args:
            query_text: 查询文本
            threshold: 相似度阈值
            top_k: 返回最相似的k个样本
            
        Returns:
            [(样本文本, 相似度分数), ...]
        """
        if self.disabled:
            return []
        if not query_text or not query_text.strip():
            return []
        
        # 确保初始化，以正确加载向量数据
        self._ensure_initialized()
            
        if len(self._texts) == 0:
            return []
        
        query_text = query_text.strip()
        results = []
        
        try:
            # 🎯 第一优先：完全匹配检查
            for i, text in enumerate(self._texts):
                if text.strip() == query_text:
                    logger.info(f"🎯 完全匹配找到: {text[:50]}...")
                    return [(text, 1.0)]  # 100% 相似度
            
            # 🚀 第二优先：编辑距离相似度（最佳方案）
            logger.debug("使用编辑距离计算相似度")
            for text in self._texts:
                edit_sim = self._edit_distance_similarity(query_text, text)
                if edit_sim >= threshold:
                    results.append((text, edit_sim))
            
            # 如果编辑距离没找到结果，降级使用Jaccard
            if not results:
                logger.debug("编辑距离无匹配，使用Jaccard兜底")
                for text in self._texts:
                    jaccard_sim = self._jaccard_similarity(query_text, text)
                    if jaccard_sim >= threshold * 0.9:  # 降低阈值10%
                        results.append((text, jaccard_sim))
            
            # 排序返回top-k
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"查找相似推广样本失败: {e}")
            return []
    
    def _edit_distance_similarity(self, text1: str, text2: str) -> float:
        """计算编辑距离相似度 - Linus最爱的简单有效方案"""
        try:
            import difflib
            return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
        except:
            return 0.0
    
    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """计算Jaccard相似度"""
        try:
            # 简单字符级别的Jaccard相似度
            set1 = set(text1.lower())
            set2 = set(text2.lower())
            
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            
            return intersection / union if union > 0 else 0.0
        except:
            return 0.0
    
    def check_sync_status(self) -> Dict:
        """检查推广向量同步状态"""
        if self.disabled:
            return {'disabled': True, 'reason': 'sentence_transformers not available'}
        try:
            from app.routers.training.base import load_promo_samples
            samples = load_promo_samples()
            
            # 从样本中提取内容
            sample_contents = set()
            for sample in samples:
                if sample.get('promo_content'):
                    sample_contents.add(sample['promo_content'].strip())
            
            # 获取当前缓存的内容
            cached_contents = set(self._texts)
            
            # 计算差异
            missing_in_vectors = sample_contents - cached_contents  # 样本有但向量没有
            extra_in_vectors = cached_contents - sample_contents    # 向量有但样本没有
            
            is_synced = len(missing_in_vectors) == 0 and len(extra_in_vectors) == 0
            
            return {
                'is_synced': is_synced,
                'sync_needed': not is_synced,
                'total_samples': len(samples),
                'total_vectors': len(self._texts),
                'missing_vectors': len(missing_in_vectors),
                'extra_vectors': len(extra_in_vectors),
                'sample_contents': list(sample_contents)[:5],  # 示例内容
                'cached_contents': list(cached_contents)[:5]   # 示例内容
            }
            
        except Exception as e:
            logger.error(f"检查推广向量同步状态失败: {e}")
            return {
                'is_synced': False,
                'sync_needed': True,
                'total_samples': 0,
                'total_vectors': len(self._texts),
                'error': str(e)
            }
    
    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        if self.disabled:
            return {'disabled': True, 'reason': 'sentence_transformers not available'}
        
        # 确保初始化，以获取准确统计
        self._ensure_initialized()
        
        return {
            'total_vectors': len(self._texts),
            'cache_file_exists': self.vector_cache_file.exists(),
            'vector_file_exists': self.vector_data_file.exists(),
            'model_loaded': self.model is not None,
            'vector_dimension': self._vectors.shape[1] if self._vectors is not None else 0
        }
    
    def rebuild_vectors_from_samples_file(self) -> Dict:
        """
        从推广样本文件重建文本索引 - Linus式简化版本
        便捷方法，用于API调用和自动同步
        """
        if self.disabled:
            return {'success': False, 'reason': 'PromoVectorManager disabled'}
        self._ensure_initialized()
        try:
            logger.info("开始从推广样本文件重建文本索引...")
            
            # 清空现有缓存
            self._vector_cache = {}
            self._vectors = None
            self._texts = []
            
            # 调用已有的更新缓存方法
            self.update_cache()
            
            # 统计结果
            sample_count = len(self._texts)
            
            success_msg = f"推广文本重建完成，共 {sample_count} 个样本"
            logger.info(success_msg)
            
            return {
                'success': True,
                'message': success_msg,
                'count': sample_count,
                'total_samples': sample_count
            }
            
        except Exception as e:
            error_msg = f"推广文本重建失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'count': 0,
                'error': str(e)
            }
    
    def clear_cache(self):
        """清空文本缓存 - Linus式简化版本"""
        if self.disabled:
            return
        try:
            self._vector_cache = {}
            self._vectors = None
            self._texts = []
            
            # 删除缓存文件
            if self.vector_cache_file.exists():
                self.vector_cache_file.unlink()
            # 🔥 不再删除向量数据文件，已废弃
                
            logger.info("推广文本缓存已清空")
            
        except Exception as e:
            logger.error(f"清空推广文本缓存失败: {e}")

# 全局实例
promo_vector_manager = PromoVectorManager()