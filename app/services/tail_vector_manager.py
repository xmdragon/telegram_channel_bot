"""
尾部向量管理器
管理尾部文本的向量化存储、相似度计算和聚类分析
"""
import numpy as np
import logging
from typing import List, Dict, Optional, Tuple, Any
import json
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import DBSCAN
import threading
from datetime import datetime

from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)

class TailVectorManager:
    """尾部向量管理器"""
    
    def __init__(self):
        self.vectors = None  # numpy array of vectors
        self.sample_ids = []  # 对应的样本ID列表
        self.clusters = None  # 聚类结果
        self.model = None
        self._lock = threading.RLock()
        
        # 文件路径
        self.vector_file = PathConfig.TAIL_TRAINING_DIR / "tail_vectors.npz"
        self.index_file = PathConfig.TAIL_TRAINING_DIR / "vector_index.json"
        
        # 聚类参数
        self.cluster_eps = 0.3
        self.cluster_min_samples = 2
        
        # 初始化
        self._load_model()
        self._load_vectors()
    
    def _load_model(self):
        """加载sentence-transformers模型（使用缓存管理器）"""
        try:
            # 🔧 Linus式解决方案：使用专用模型缓存管理器避免重复下载
            from app.services.model_cache_manager import ModelCacheManager
            
            cache_manager = ModelCacheManager()
            self.model = cache_manager.get_model()  # 使用配置文件中的模型
            
            if self.model:
                logger.info("✅ 向量管理器AI模型加载成功（使用缓存管理器）")
            else:
                logger.error("❌ 向量管理器AI模型加载失败，向量功能不可用")
                
        except Exception as e:
            logger.error(f"❌ AI模型加载失败: {e}")
            self.model = None
            # 不抛出异常，允许程序继续运行
    
    def _load_vectors(self):
        """从文件加载向量数据"""
        try:
            if self.vector_file.exists() and self.index_file.exists():
                # 加载向量
                data = np.load(self.vector_file)
                self.vectors = data['vectors']
                
                # 加载索引
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                    self.sample_ids = index_data['sample_ids']
                    self.clusters = np.array(index_data.get('clusters', []))
                
                logger.info(f"✅ 加载了 {len(self.vectors)} 个向量")
            else:
                # 初始化空数据
                self.vectors = np.empty((0, 384))  # MiniLM模型输出384维向量
                self.sample_ids = []
                self.clusters = np.array([])
                logger.info("📝 初始化空向量数据库")
                
        except Exception as e:
            logger.error(f"❌ 加载向量数据失败: {e}")
            # 初始化空数据作为fallback
            self.vectors = np.empty((0, 384))
            self.sample_ids = []
            self.clusters = np.array([])
    
    def add_vector(self, text: str, sample_id: int) -> int:
        """
        添加新的向量
        
        Args:
            text: 文本内容
            sample_id: 样本ID
            
        Returns:
            向量在数组中的索引
        """
        with self._lock:
            if not self.model:
                raise RuntimeError("AI模型未加载")
            
            # 向量化文本
            vector = self.model.encode([text])[0]
            
            # 添加到数组
            if self.vectors.size == 0:
                self.vectors = vector.reshape(1, -1)
            else:
                self.vectors = np.vstack([self.vectors, vector])
            
            # 添加ID
            self.sample_ids.append(sample_id)
            
            # 返回索引
            vector_index = len(self.sample_ids) - 1
            
            logger.debug(f"➕ 添加向量 - 样本ID: {sample_id}, 索引: {vector_index}")
            return vector_index
    
    def update_vector(self, vector_index: int, text: str):
        """
        更新指定索引的向量
        
        Args:
            vector_index: 向量索引
            text: 新的文本内容
        """
        with self._lock:
            if not self.model:
                raise RuntimeError("AI模型未加载")
            
            if vector_index >= len(self.vectors):
                raise ValueError(f"向量索引 {vector_index} 超出范围")
            
            # 重新向量化
            new_vector = self.model.encode([text])[0]
            self.vectors[vector_index] = new_vector
            
            logger.debug(f"🔄 更新向量 - 索引: {vector_index}")
    
    def remove_vector(self, sample_id: int):
        """
        删除指定样本的向量
        
        Args:
            sample_id: 样本ID
        """
        with self._lock:
            try:
                # 找到索引
                vector_index = self.sample_ids.index(sample_id)
                
                # 删除向量
                self.vectors = np.delete(self.vectors, vector_index, axis=0)
                
                # 删除ID
                self.sample_ids.pop(vector_index)
                
                # 更新聚类信息
                if len(self.clusters) > vector_index:
                    self.clusters = np.delete(self.clusters, vector_index)
                
                logger.debug(f"➖ 删除向量 - 样本ID: {sample_id}")
                
            except ValueError:
                logger.warning(f"⚠️ 未找到样本 {sample_id} 的向量")
    
    def find_similar(self, text: str, top_k: int = 5, threshold: float = 0.7) -> List[Dict]:
        """
        查找相似的样本
        
        Args:
            text: 查询文本
            top_k: 返回最相似的K个结果
            threshold: 相似度阈值
            
        Returns:
            相似样本列表，每个包含 sample_id, similarity, vector_index
        """
        with self._lock:
            if not self.model or self.vectors.size == 0:
                return []
            
            # 向量化查询文本
            query_vector = self.model.encode([text])[0].reshape(1, -1)
            
            # 计算相似度
            similarities = cosine_similarity(query_vector, self.vectors)[0]
            
            # 获取最相似的结果
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            results = []
            for idx in top_indices:
                similarity = similarities[idx]
                if similarity >= threshold:
                    results.append({
                        'sample_id': int(self.sample_ids[idx]),  # 转换numpy类型为Python int
                        'similarity': round(float(similarity), 4),
                        'vector_index': int(idx)  # 转换numpy类型为Python int
                    })
            
            logger.debug(f"🔍 找到 {len(results)} 个相似样本")
            return results
    
    def find_most_similar(self, text: str, threshold: float = 0.5) -> Optional[Dict]:
        """
        查找最相似的样本
        
        Args:
            text: 查询文本
            threshold: 相似度阈值
            
        Returns:
            最相似的样本信息，或None
        """
        similar = self.find_similar(text, top_k=1, threshold=threshold)
        return similar[0] if similar else None
    
    def cluster_analysis(self, eps: float = None, min_samples: int = None) -> Dict:
        """
        对所有向量进行聚类分析
        
        Args:
            eps: DBSCAN参数
            min_samples: DBSCAN参数
            
        Returns:
            聚类结果统计
        """
        with self._lock:
            if self.vectors.size == 0:
                return {"clusters": {}, "noise_points": 0, "total_samples": 0}
            
            # 使用参数或默认值
            eps = eps or self.cluster_eps
            min_samples = min_samples or self.cluster_min_samples
            
            # 执行聚类
            clustering = DBSCAN(eps=eps, min_samples=min_samples)
            self.clusters = clustering.fit_predict(self.vectors)
            
            # 统计结果
            unique_clusters = np.unique(self.clusters)
            cluster_info = {}
            noise_points = 0
            
            for cluster_id in unique_clusters:
                if cluster_id == -1:  # 噪声点
                    noise_points = np.sum(self.clusters == -1)
                else:
                    cluster_samples = np.where(self.clusters == cluster_id)[0]
                    cluster_info[int(cluster_id)] = {
                        'sample_count': len(cluster_samples),
                        'sample_ids': [self.sample_ids[idx] for idx in cluster_samples],
                        'representative_id': self.sample_ids[cluster_samples[0]]  # 第一个作为代表
                    }
            
            result = {
                'clusters': cluster_info,
                'noise_points': noise_points,
                'total_samples': len(self.vectors),
                'cluster_count': len(cluster_info)
            }
            
            logger.info(f"📊 聚类完成 - {result['cluster_count']} 个聚类, {noise_points} 个噪声点")
            return result
    
    def get_cluster_samples(self, cluster_id: int) -> List[int]:
        """
        获取指定聚类的所有样本ID
        
        Args:
            cluster_id: 聚类ID
            
        Returns:
            样本ID列表
        """
        if self.clusters is None or len(self.clusters) == 0:
            return []
        
        cluster_indices = np.where(self.clusters == cluster_id)[0]
        return [self.sample_ids[idx] for idx in cluster_indices]
    
    def calculate_similarity_matrix(self) -> np.ndarray:
        """
        计算所有样本间的相似度矩阵
        
        Returns:
            相似度矩阵
        """
        if self.vectors.size == 0:
            return np.array([])
        
        return cosine_similarity(self.vectors)
    
    def save(self):
        """保存向量数据到文件"""
        with self._lock:
            try:
                # 确保目录存在
                PathConfig.ensure_directories()
                
                # 保存向量
                if self.vectors.size > 0:
                    np.savez_compressed(self.vector_file, vectors=self.vectors)
                
                # 保存索引信息
                index_data = {
                    'sample_ids': self.sample_ids,
                    'clusters': self.clusters.tolist() if self.clusters is not None else [],
                    'saved_at': datetime.now().isoformat(),
                    'vector_count': len(self.sample_ids)
                }
                
                with open(self.index_file, 'w', encoding='utf-8') as f:
                    json.dump(index_data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"💾 保存 {len(self.sample_ids)} 个向量到文件")
                
            except Exception as e:
                logger.error(f"❌ 保存向量数据失败: {e}")
                raise
    
    def rebuild_from_samples(self, samples: List[Dict]):
        """
        从样本数据重建向量数据库
        
        Args:
            samples: 样本数据列表，每个包含 id 和 tail_part
        """
        with self._lock:
            if not self.model:
                raise RuntimeError("AI模型未加载")
            
            logger.info(f"🔄 重建向量数据库 - {len(samples)} 个样本")
            
            # 清空现有数据
            self.vectors = np.empty((0, 384))
            self.sample_ids = []
            self.clusters = np.array([])
            
            if not samples:
                logger.info("📝 样本列表为空，创建空向量数据库")
                return
            
            # 批量向量化
            texts = [sample['tail_part'] for sample in samples]
            ids = [sample['id'] for sample in samples]
            
            try:
                # 一次性向量化所有文本
                vectors = self.model.encode(texts)
                
                # 保存数据
                self.vectors = vectors
                self.sample_ids = ids
                
                logger.info(f"✅ 重建完成 - {len(self.sample_ids)} 个向量")
                
                # 自动执行聚类
                self.cluster_analysis()
                
            except Exception as e:
                logger.error(f"❌ 重建向量数据库失败: {e}")
                raise
    
    def rebuild_vectors_from_samples_file(self):
        """
        🔥 从训练样本文件重建向量索引
        便捷方法，用于API调用
        """
        try:
            from app.routers.training.base import load_tail_filter_samples
            samples = load_tail_filter_samples()
            
            # 过滤出有效样本（有尾部内容的）
            valid_samples = [s for s in samples if s.get('tail_part')]
            
            logger.info(f"📋 从文件加载了 {len(samples)} 个样本，其中 {len(valid_samples)} 个有效")
            
            if not valid_samples:
                logger.warning("⚠️ 没有找到有效的尾部样本")
                return {"success": False, "message": "没有找到有效的尾部样本"}
            
            # 重建向量
            self.rebuild_from_samples(valid_samples)
            
            # 保存到文件
            self.save()
            
            result = {
                "success": True,
                "message": f"成功重建 {len(valid_samples)} 个向量",
                "total_samples": len(samples),
                "vectorized_samples": len(valid_samples),
                "vector_count": len(self.sample_ids)
            }
            
            logger.info(f"✅ 向量重建完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 向量重建失败: {e}")
            return {"success": False, "message": f"重建失败: {str(e)}"}
    
    def get_statistics(self) -> Dict:
        """
        获取向量数据库统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            stats = {
                'total_vectors': len(self.sample_ids),
                'vector_dimensions': self.vectors.shape[1] if self.vectors.size > 0 else 0,
                'has_clusters': self.clusters is not None and len(self.clusters) > 0,
                'cluster_count': len(np.unique(self.clusters)) - (1 if -1 in self.clusters else 0) if self.clusters is not None else 0,
                'noise_points': np.sum(self.clusters == -1) if self.clusters is not None else 0,
                'storage_size_mb': self.vectors.nbytes / (1024 * 1024) if self.vectors.size > 0 else 0
            }
            
            return stats
    
    def health_check(self) -> Dict:
        """
        健康检查
        
        Returns:
            健康状态信息
        """
        health = {
            'model_loaded': self.model is not None,
            'vectors_loaded': self.vectors is not None and self.vectors.size > 0,
            'index_consistent': len(self.sample_ids) == len(self.vectors) if self.vectors.size > 0 else True,
            'files_exist': {
                'vector_file': self.vector_file.exists(),
                'index_file': self.index_file.exists()
            }
        }
        
        health['overall_healthy'] = all([
            health['model_loaded'],
            health['index_consistent']
        ])
        
        return health
    
    def check_sync_status(self) -> Dict:
        """
        检查向量数据库与样本文件的同步状态
        
        Returns:
            同步状态信息
        """
        try:
            from app.routers.training.base import load_tail_filter_samples
            samples = load_tail_filter_samples()
            
            # 过滤出有效样本（有尾部内容的）
            valid_samples = [s for s in samples if s.get('tail_part')]
            sample_ids = {s['id'] for s in valid_samples}
            
            # 检查向量数据库状态
            vector_ids = set(self.sample_ids) if self.sample_ids else set()
            
            # 计算差异
            missing_in_vectors = sample_ids - vector_ids  # 样本有但向量没有
            extra_in_vectors = vector_ids - sample_ids    # 向量有但样本没有
            
            is_synced = len(missing_in_vectors) == 0 and len(extra_in_vectors) == 0
            
            status = {
                'is_synced': is_synced,
                'total_samples': len(valid_samples),
                'total_vectors': len(self.sample_ids),
                'missing_vectors': len(missing_in_vectors),
                'extra_vectors': len(extra_in_vectors),
                'sync_needed': not is_synced,
                'last_vector_update': self.index_file.stat().st_mtime if self.index_file.exists() else None,
                'last_samples_update': PathConfig.TAIL_FILTER_SAMPLES_FILE.stat().st_mtime if PathConfig.TAIL_FILTER_SAMPLES_FILE.exists() else None
            }
            
            if not is_synced:
                logger.warning(f"🔄 向量数据库不同步: 缺少 {len(missing_in_vectors)} 个向量，多余 {len(extra_in_vectors)} 个向量")
            else:
                logger.info(f"✅ 向量数据库已同步: {len(valid_samples)} 个样本")
            
            return status
            
        except Exception as e:
            logger.error(f"❌ 检查同步状态失败: {e}")
            return {
                'is_synced': False,
                'error': str(e),
                'sync_needed': True
            }


# 懒加载全局实例
_tail_vector_manager_instance = None

def get_tail_vector_manager():
    """获取尾部向量管理器实例（懒加载）"""
    global _tail_vector_manager_instance
    if _tail_vector_manager_instance is None:
        # 检查AI功能是否启用
        try:
            from app.core.ai_config import is_module_enabled
            if not is_module_enabled('semantic_tail_filter'):
                logger.info("🔒 尾部向量管理器已禁用，使用空实现")
                from app.services.dummy_implementations import DummyTailVectorManager
                _tail_vector_manager_instance = DummyTailVectorManager()
                return _tail_vector_manager_instance
        except ImportError:
            pass
        
        _tail_vector_manager_instance = TailVectorManager()
    return _tail_vector_manager_instance

# 兼容性：保持tail_vector_manager属性访问
class TailVectorManagerProxy:
    """尾部向量管理器代理，实现懒加载"""
    def __getattr__(self, name):
        return getattr(get_tail_vector_manager(), name)
    
    def __setattr__(self, name, value):
        setattr(get_tail_vector_manager(), name, value)

tail_vector_manager = TailVectorManagerProxy()