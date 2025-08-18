"""
AI语义广告检测器
使用预训练的语言模型进行语义相似度检测
"""
import logging
import json
from typing import Dict, Any, List
from pathlib import Path

from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class AIAdDetector:
    """AI语义广告检测器"""
    
    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold
        self._model = None
        self._embeddings = []
        self._initialized = False
        
        self._initialize_model()
    
    def _initialize_model(self):
        """初始化AI模型"""
        try:
            from app.services.model_cache_manager import get_cached_model
            # 使用缓存管理器获取模型，避免重复下载
            self._model = get_cached_model('paraphrase-multilingual-MiniLM-L12-v2')
            self._initialized = True
            logger.info("✅ AI广告检测模型初始化成功")
            
            # 延迟加载训练数据
            self._load_training_data()
            
        except ImportError:
            logger.warning("⚠️ sentence-transformers 未安装，AI广告检测功能暂不可用")
        except Exception as e:
            logger.error(f"AI广告检测模型初始化失败: {e}")
    
    def _load_training_data(self):
        """加载AI训练数据"""
        try:
            ad_samples_file = PathConfig.AD_TRAINING_FILE
            if not ad_samples_file.exists():
                logger.debug("没有找到广告训练数据文件")
                return
            
            with open(ad_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 使用统一的samples字段
            ad_samples = data.get("samples", [])
            if ad_samples:
                # 提取内容
                contents = [s["content"] for s in ad_samples if s.get("content")]
                if contents:
                    logger.info(f"正在加载 {len(contents)} 个广告样本...")
                    self._embeddings = self._model.encode(contents)
                    logger.info(f"✅ 成功加载 {len(self._embeddings)} 个广告样本")
                    
        except Exception as e:
            logger.error(f"加载广告训练数据失败: {e}")
    
    async def detect(self, content: str) -> Dict[str, Any]:
        """AI语义广告检测"""
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'similarity_score': 0.0,
            'method': 'AI语义检测'
        }
        
        if not self._initialized or len(self._embeddings) == 0:
            result['error'] = 'AI模型未初始化或无训练数据'
            return result
        
        try:
            # 计算文本的嵌入向量
            text_embedding = self._model.encode([content])[0].reshape(1, -1)
            
            # 计算与所有广告样本的相似度
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np
            
            similarities = cosine_similarity(text_embedding, self._embeddings)
            max_similarity = float(np.max(similarities))
            
            result['similarity_score'] = max_similarity
            
            # 判断是否为广告
            if max_similarity >= self.threshold:
                result['is_ad'] = True
                result['confidence'] = max_similarity
                logger.debug(f"AI检测到广告内容，相似度: {max_similarity:.3f}")
            else:
                result['confidence'] = 1.0 - max_similarity
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"AI广告检测失败: {e}")
        
        return result
    
    def is_available(self) -> bool:
        """检查AI检测器是否可用"""
        return self._initialized and len(self._embeddings) > 0
    
    def check_semantic_coherence(self, main_text: str, button_texts: List[str]) -> float:
        """检查按钮文本与正文的语义相关性"""
        if not self._initialized or not main_text or not button_texts:
            return 1.0
        
        try:
            # 计算正文的嵌入向量
            main_embedding = self._model.encode([main_text])[0]
            
            # 计算所有按钮文本的组合嵌入向量
            combined_button_text = ' '.join(button_texts)
            button_embedding = self._model.encode([combined_button_text])[0]
            
            # 计算余弦相似度
            from sklearn.metrics.pairwise import cosine_similarity
            similarity = cosine_similarity(
                main_embedding.reshape(1, -1),
                button_embedding.reshape(1, -1)
            )[0][0]
            
            return float(similarity)
            
        except Exception as e:
            logger.debug(f"语义相关性检查失败: {e}")
            return 1.0