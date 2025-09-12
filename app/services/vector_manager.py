"""
广告向量管理器 - Linus式简洁设计
负责广告向量的存储、检索、去重和相似度计算

Author: Claude  
Created: 2025-08-31
"""

import json
import os
import logging
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import fcntl
import hashlib
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class VectorManager:
    """广告向量管理器 - 统一的向量存储和检索系统"""
    
    def __init__(self, vector_dir: str = "data/training/ad/vectors"):
        self.vector_dir = vector_dir
        self.vector_file = os.path.join(vector_dir, "ad_vectors.json")
        self.metadata_file = os.path.join(vector_dir, "metadata.json")
        
        # 白名单向量库（非广告内容）
        self.whitelist_dir = "data/training/whitelist/vectors"
        self.whitelist_file = os.path.join(self.whitelist_dir, "whitelist_vectors.json")
        os.makedirs(self.whitelist_dir, exist_ok=True)
        
        # 确保目录存在
        os.makedirs(vector_dir, exist_ok=True)
        
        # 向量缓存
        self._vector_cache = None
        self._last_modified = 0
        self._whitelist_cache = None
        self._whitelist_last_modified = 0
        
        # 配置参数 - 从配置文件读取阈值
        self.similarity_threshold = self._load_threshold()  # 广告检测阈值
        self.duplicate_threshold = 0.95  # 向量去重阈值
        
        logger.info(f"向量管理器初始化完成 - 存储路径: {vector_dir}, 阈值: {self.similarity_threshold}")
    
    def _get_file_lock(self, file_path: str, mode: str = 'r'):
        """获取文件锁（防止并发访问冲突）"""
        lock_file = file_path + '.lock'
        lock_fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY)
        
        if mode == 'w':
            fcntl.flock(lock_fd, fcntl.LOCK_EX)  # 独占锁
        else:
            fcntl.flock(lock_fd, fcntl.LOCK_SH)  # 共享锁
            
        return lock_fd
    
    def _release_file_lock(self, lock_fd: int):
        """释放文件锁"""
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    
    def _load_vectors(self) -> Dict[str, Any]:
        """加载向量数据（带缓存）"""
        try:
            # 检查文件修改时间
            if os.path.exists(self.vector_file):
                mtime = os.path.getmtime(self.vector_file)
                if self._vector_cache is not None and mtime <= self._last_modified:
                    return self._vector_cache
                
                # 加载向量文件
                lock_fd = self._get_file_lock(self.vector_file, 'r')
                try:
                    with open(self.vector_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 更新缓存
                    self._vector_cache = data
                    self._last_modified = mtime
                    
                    logger.debug(f"加载了 {len(data.get('vectors', []))} 个向量")
                    return data
                finally:
                    self._release_file_lock(lock_fd)
            else:
                # 文件不存在，返回空结构
                empty_data = {
                    'vectors': [],
                    'metadata': {
                        'created_at': datetime.now().isoformat(),
                        'total_count': 0,
                        'last_updated': datetime.now().isoformat()
                    }
                }
                self._vector_cache = empty_data
                return empty_data
                
        except Exception as e:
            logger.error(f"加载向量数据失败: {e}")
            return {'vectors': [], 'metadata': {}}
    
    def _load_whitelist_vectors(self) -> Dict[str, Any]:
        """加载白名单向量数据（带缓存）"""
        try:
            # 检查文件修改时间
            if os.path.exists(self.whitelist_file):
                mtime = os.path.getmtime(self.whitelist_file)
                if self._whitelist_cache is not None and mtime <= self._whitelist_last_modified:
                    return self._whitelist_cache
                
                # 加载向量文件
                lock_fd = self._get_file_lock(self.whitelist_file, 'r')
                try:
                    with open(self.whitelist_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 更新缓存
                    self._whitelist_cache = data
                    self._whitelist_last_modified = mtime
                    
                    logger.debug(f"加载了 {len(data.get('vectors', []))} 个白名单向量")
                    return data
                finally:
                    self._release_file_lock(lock_fd)
            else:
                # 文件不存在，返回空结构
                empty_data = {
                    'vectors': [],
                    'metadata': {
                        'created_at': datetime.now().isoformat(),
                        'total_count': 0,
                        'last_updated': datetime.now().isoformat()
                    }
                }
                self._whitelist_cache = empty_data
                return empty_data
                
        except Exception as e:
            logger.error(f"加载白名单向量数据失败: {e}")
            return {'vectors': [], 'metadata': {}}
    
    def _load_threshold(self) -> float:
        """从配置文件加载阈值"""
        try:
            from app.core.path_config import PathConfig
            config_path = os.path.join(PathConfig.CONFIG_DIR, "thresholds.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    thresholds = json.load(f)
                    # 读取ad_detector.classifier.current
                    threshold = thresholds.get('ad_detector', {}).get('classifier', {}).get('current', 0.84)
                    logger.info(f"从配置文件加载广告检测阈值: {threshold}")
                    return threshold
            logger.warning("阈值配置文件不存在，使用默认值0.84")
            return 0.84  # 默认使用较高阈值，避免误判
        except Exception as e:
            logger.error(f"加载阈值配置失败: {e}，使用默认值0.84")
            return 0.84  # 默认使用较高阈值，避免误判
    
    def _save_vectors(self, data: Dict[str, Any]) -> bool:
        """保存向量数据"""
        try:
            # 更新元数据
            data['metadata'].update({
                'last_updated': datetime.now().isoformat(),
                'total_count': len(data.get('vectors', []))
            })
            
            lock_fd = self._get_file_lock(self.vector_file, 'w')
            try:
                with open(self.vector_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # 更新缓存
                self._vector_cache = data
                self._last_modified = os.path.getmtime(self.vector_file)
                
                logger.debug(f"保存了 {len(data.get('vectors', []))} 个向量")
                return True
            finally:
                self._release_file_lock(lock_fd)
                
        except Exception as e:
            logger.error(f"保存向量数据失败: {e}")
            return False
    
    def _vector_hash(self, vector: List[float]) -> str:
        """计算向量hash用于去重"""
        vector_str = ','.join([f"{v:.6f}" for v in vector])
        return hashlib.md5(vector_str.encode()).hexdigest()[:16]
    
    def add_vector(self, vector: List[float], content: str, source: str = "manual", metadata: Dict[str, Any] = None) -> bool:
        """添加新向量到数据库"""
        try:
            if not vector or len(vector) == 0:
                logger.warning("尝试添加空向量")
                return False
            
            # 检查是否重复
            if self.is_duplicate_vector(vector):
                logger.info(f"向量已存在，跳过添加: {content[:50]}...")
                return False
            
            # 加载现有数据
            data = self._load_vectors()
            
            # 创建新向量记录
            vector_record = {
                'id': self._vector_hash(vector),
                'vector': vector,
                'content': content[:500],  # 限制内容长度
                'source': source,
                'created_at': datetime.now().isoformat(),
                'metadata': metadata or {}
            }
            
            # 添加到列表
            data['vectors'].append(vector_record)
            
            # 保存数据
            if self._save_vectors(data):
                logger.info(f"成功添加向量: {content[:50]}... (来源: {source})")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"添加向量失败: {e}")
            return False
    
    def is_duplicate_vector(self, new_vector: List[float]) -> bool:
        """检查向量是否重复"""
        try:
            data = self._load_vectors()
            vectors = data.get('vectors', [])
            
            if not vectors:
                return False
            
            # 计算与所有现有向量的相似度
            new_vector_array = np.array(new_vector).reshape(1, -1)
            
            for record in vectors:
                existing_vector = np.array(record['vector']).reshape(1, -1)
                similarity = cosine_similarity(new_vector_array, existing_vector)[0][0]
                
                if similarity >= self.duplicate_threshold:
                    logger.debug(f"发现重复向量，相似度: {similarity:.3f}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查向量重复性失败: {e}")
            return False
    
    def find_similar_vectors(self, query_vector: List[float], top_k: int = 5) -> List[Tuple[Dict, float]]:
        """查找相似向量"""
        try:
            data = self._load_vectors()
            vectors = data.get('vectors', [])
            
            if not vectors:
                return []
            
            query_array = np.array(query_vector).reshape(1, -1)
            similarities = []
            
            # 计算与所有向量的相似度
            for record in vectors:
                vector_array = np.array(record['vector']).reshape(1, -1)
                similarity = cosine_similarity(query_array, vector_array)[0][0]
                similarities.append((record, similarity))
            
            # 按相似度排序
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # 返回top_k结果
            return similarities[:top_k]
            
        except Exception as e:
            logger.error(f"查找相似向量失败: {e}")
            return []
    
    def is_advertisement(self, query_vector: List[float]) -> Tuple[bool, float, Dict[str, Any]]:
        """判断向量是否为广告（加入白名单检查）"""
        try:
            # 1. 先检查白名单（非广告向量）
            whitelist_similarity = self._check_whitelist_similarity(query_vector)
            
            # 如果与白名单高度相似（>0.9），直接判定为非广告
            if whitelist_similarity > 0.9:
                return False, whitelist_similarity, {
                    'reason': '白名单匹配',
                    'whitelist_similarity': whitelist_similarity,
                    'similarity': 0.0,  # 对广告向量的相似度
                    'threshold': self.similarity_threshold
                }
            
            # 2. 检查广告向量
            similar_vectors = self.find_similar_vectors(query_vector, top_k=1)
            
            if not similar_vectors:
                return False, 0.0, {'reason': '向量库为空'}
            
            best_match, ad_similarity = similar_vectors[0]
            
            # 3. 综合判断：广告相似度超过阈值 且 白名单相似度不高
            is_ad = ad_similarity >= self.similarity_threshold and whitelist_similarity < 0.8
            
            result_info = {
                'similarity': ad_similarity,
                'whitelist_similarity': whitelist_similarity,
                'threshold': self.similarity_threshold,
                'matched_content': best_match.get('content', '')[:100],
                'matched_source': best_match.get('source', ''),
                'matched_id': best_match.get('id', ''),
                'decision_reason': '广告向量匹配' if is_ad else ('白名单保护' if whitelist_similarity > 0.8 else '相似度不足')
            }
            
            return is_ad, ad_similarity, result_info
            
        except Exception as e:
            logger.error(f"向量广告检测失败: {e}")
            return False, 0.0, {'error': str(e)}
    
    def _check_whitelist_similarity(self, query_vector: List[float]) -> float:
        """检查与白名单向量的最高相似度"""
        try:
            whitelist_data = self._load_whitelist_vectors()
            whitelist_vectors = whitelist_data.get('vectors', [])
            
            if not whitelist_vectors:
                return 0.0
            
            query_array = np.array(query_vector).reshape(1, -1)
            max_similarity = 0.0
            
            # 计算与所有白名单向量的相似度
            for record in whitelist_vectors:
                vector_array = np.array(record['vector']).reshape(1, -1)
                similarity = cosine_similarity(query_array, vector_array)[0][0]
                max_similarity = max(max_similarity, similarity)
            
            return max_similarity
            
        except Exception as e:
            logger.error(f"白名单相似度检查失败: {e}")
            return 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取向量库统计信息"""
        try:
            data = self._load_vectors()
            vectors = data.get('vectors', [])
            metadata = data.get('metadata', {})
            
            # 按来源统计
            source_stats = {}
            for record in vectors:
                source = record.get('source', 'unknown')
                source_stats[source] = source_stats.get(source, 0) + 1
            
            return {
                'total_vectors': len(vectors),
                'source_distribution': source_stats,
                'similarity_threshold': self.similarity_threshold,
                'duplicate_threshold': self.duplicate_threshold,
                'created_at': metadata.get('created_at'),
                'last_updated': metadata.get('last_updated'),
                'storage_path': self.vector_file
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def cleanup_duplicates(self) -> int:
        """清理重复向量"""
        try:
            data = self._load_vectors()
            vectors = data.get('vectors', [])
            
            if len(vectors) <= 1:
                return 0
            
            # 去重逻辑
            unique_vectors = []
            removed_count = 0
            
            for i, record in enumerate(vectors):
                is_duplicate = False
                current_vector = np.array(record['vector']).reshape(1, -1)
                
                # 与已保留的向量比较
                for unique_record in unique_vectors:
                    unique_vector = np.array(unique_record['vector']).reshape(1, -1)
                    similarity = cosine_similarity(current_vector, unique_vector)[0][0]
                    
                    if similarity >= self.duplicate_threshold:
                        is_duplicate = True
                        removed_count += 1
                        logger.debug(f"移除重复向量: {record.get('content', '')[:50]}...")
                        break
                
                if not is_duplicate:
                    unique_vectors.append(record)
            
            # 保存清理后的数据
            if removed_count > 0:
                data['vectors'] = unique_vectors
                self._save_vectors(data)
                logger.info(f"清理完成，移除了 {removed_count} 个重复向量")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"清理重复向量失败: {e}")
            return 0
    
    def remove_vector_by_content(self, content: str) -> int:
        """根据内容移除相关向量"""
        try:
            if not content:
                return 0
            
            data = self._load_vectors()
            vectors = data.get('vectors', [])
            
            if not vectors:
                return 0
            
            # 使用文本内容匹配
            return self._remove_by_text_content(content, data)
            
        except Exception as e:
            logger.error(f"根据内容移除向量失败: {e}")
            return 0
    
    def _remove_by_vector_similarity(self, query_vector: List[float], content: str, data: Dict[str, Any]) -> int:
        """通过向量相似度移除向量"""
        try:
            vectors = data.get('vectors', [])
            query_array = np.array(query_vector).reshape(1, -1)
            remaining_vectors = []
            removed_count = 0
            
            for record in vectors:
                try:
                    vector_array = np.array(record['vector']).reshape(1, -1)
                    similarity = cosine_similarity(query_array, vector_array)[0][0]
                    
                    # 使用较高的阈值确保只移除非常相似的向量
                    if similarity >= 0.85:  # 85%相似度以上认为是同一内容
                        removed_count += 1
                        logger.debug(f"移除相似向量 (相似度: {similarity:.3f}): {record.get('content', '')[:50]}...")
                    else:
                        remaining_vectors.append(record)
                        
                except Exception as e:
                    logger.debug(f"处理向量时出错: {e}")
                    remaining_vectors.append(record)  # 出错时保留向量
            
            if removed_count > 0:
                data['vectors'] = remaining_vectors
                self._save_vectors(data)
                logger.info(f"通过向量相似度移除了 {removed_count} 个向量")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"通过向量相似度移除失败: {e}")
            return 0
    
    def _remove_by_text_content(self, content: str, data: Dict[str, Any]) -> int:
        """通过文本内容匹配移除向量（降级方案）"""
        try:
            vectors = data.get('vectors', [])
            remaining_vectors = []
            removed_count = 0
            content_lower = content.lower().strip()
            
            for record in vectors:
                record_content = record.get('content', '').lower().strip()
                
                # 文本完全匹配或包含关系
                if (content_lower == record_content or 
                    (len(content_lower) > 20 and content_lower in record_content) or
                    (len(record_content) > 20 and record_content in content_lower)):
                    removed_count += 1
                    logger.debug(f"移除匹配文本: {record.get('content', '')[:50]}...")
                else:
                    remaining_vectors.append(record)
            
            if removed_count > 0:
                data['vectors'] = remaining_vectors
                self._save_vectors(data)
                logger.info(f"通过文本匹配移除了 {removed_count} 个向量")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"通过文本匹配移除失败: {e}")
            return 0


    def add_whitelist_vector(self, vector: List[float], content: str, message_id: str = "", source: str = "user_feedback") -> bool:
        """添加白名单向量（非广告内容）"""
        try:
            # 检查向量重复性
            if self._is_whitelist_vector_duplicate(vector):
                logger.debug("白名单向量已存在，跳过添加")
                return True
            
            # 加载现有数据
            data = self._load_whitelist_vectors()
            
            # 创建新记录
            new_record = {
                "id": f"whitelist_{len(data['vectors']) + 1:05d}",
                "message_id": message_id,
                "vector": vector,
                "content_preview": content[:200],  # 保存内容预览
                "processed_text": content,
                "created_at": datetime.now().isoformat(),
                "source": source,
                "vector_hash": self._vector_hash(vector)
            }
            
            # 添加到向量列表
            data['vectors'].append(new_record)
            
            # 保存数据
            success = self._save_whitelist_vectors(data)
            if success:
                logger.info(f"✅ 添加白名单向量成功: {new_record['id']} (来源: {source})")
            else:
                logger.error(f"❌ 添加白名单向量失败: 保存错误")
            
            return success
            
        except Exception as e:
            logger.error(f"添加白名单向量异常: {e}")
            return False
    
    def _is_whitelist_vector_duplicate(self, vector: List[float]) -> bool:
        """检查白名单向量是否重复"""
        try:
            data = self._load_whitelist_vectors()
            vectors = data.get('vectors', [])
            
            if not vectors:
                return False
            
            new_vector_array = np.array(vector).reshape(1, -1)
            
            for record in vectors:
                existing_vector = np.array(record['vector']).reshape(1, -1)
                similarity = cosine_similarity(new_vector_array, existing_vector)[0][0]
                
                if similarity >= self.duplicate_threshold:
                    logger.debug(f"发现重复白名单向量，相似度: {similarity:.3f}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查白名单向量重复性失败: {e}")
            return False
    
    def _save_whitelist_vectors(self, data: Dict[str, Any]) -> bool:
        """保存白名单向量数据"""
        try:
            # 更新元数据
            data['metadata'].update({
                'last_updated': datetime.now().isoformat(),
                'total_count': len(data.get('vectors', []))
            })
            
            lock_fd = self._get_file_lock(self.whitelist_file, 'w')
            try:
                with open(self.whitelist_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # 更新缓存
                self._whitelist_cache = data
                self._whitelist_last_modified = os.path.getmtime(self.whitelist_file)
                
                logger.debug(f"保存了 {len(data.get('vectors', []))} 个白名单向量")
                return True
            finally:
                self._release_file_lock(lock_fd)
                
        except Exception as e:
            logger.error(f"保存白名单向量数据失败: {e}")
            return False


# 全局向量管理器实例
vector_manager = VectorManager()