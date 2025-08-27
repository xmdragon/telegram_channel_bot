"""
轻量级广告检测器
使用编辑距离进行文本相似度检测，替代重量级AI模型
🚀 Linus式简化：去除sentence_transformers依赖
"""
import logging
import json
import difflib
from typing import Dict, Any, List
from pathlib import Path

from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class AIAdDetector:
    """轻量级广告检测器 - 基于文本相似度"""
    
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self._ad_samples = []  # 存储广告样本文本
        self._initialized = False
        
        self._initialize_samples()
    
    def _initialize_samples(self):
        """初始化广告样本 - 轻量级方案"""
        try:
            self._load_training_data()
            self._initialized = len(self._ad_samples) > 0
            
            if self._initialized:
                logger.info(f"✅ 轻量级广告检测器初始化成功，加载 {len(self._ad_samples)} 个样本")
            else:
                logger.info("⚠️ 未找到广告样本，检测器处于待机状态")
            
        except Exception as e:
            logger.error(f"广告检测器初始化失败: {e}")
    
    def _load_training_data(self):
        """加载广告训练数据 - 轻量级方案"""
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
                # 🚀 Linus式简化：直接存储文本，无需嵌入向量
                self._ad_samples = [s["content"] for s in ad_samples if s.get("content")]
                logger.debug(f"✅ 加载 {len(self._ad_samples)} 个广告样本")
                    
        except Exception as e:
            logger.error(f"加载广告训练数据失败: {e}")
    
    async def detect(self, content: str) -> Dict[str, Any]:
        """轻量级广告检测 - 基于文本相似度"""
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'similarity_score': 0.0,
            'method': '轻量级文本匹配'
        }
        
        if not self._initialized or len(self._ad_samples) == 0:
            result['error'] = '无广告样本数据'
            return result
        
        if not content or not content.strip():
            return result
        
        try:
            content = content.strip()
            max_similarity = 0.0
            
            # 🚀 第一优先：完全匹配检查
            for sample in self._ad_samples:
                if content == sample.strip():
                    result['is_ad'] = True
                    result['confidence'] = 1.0
                    result['similarity_score'] = 1.0
                    logger.debug("完全匹配广告样本")
                    return result
            
            # 🚀 第二优先：编辑距离相似度
            for sample in self._ad_samples:
                # 使用difflib计算相似度
                similarity = difflib.SequenceMatcher(None, content, sample.strip()).ratio()
                max_similarity = max(max_similarity, similarity)
                
                if similarity >= self.threshold:
                    result['is_ad'] = True
                    result['confidence'] = similarity
                    result['similarity_score'] = similarity
                    logger.debug(f"文本相似度检测到广告内容，相似度: {similarity:.3f}")
                    break
            
            if not result['is_ad']:
                result['similarity_score'] = max_similarity
                result['confidence'] = 1.0 - max_similarity
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"广告检测失败: {e}")
        
        return result
    
    def is_available(self) -> bool:
        """检查检测器是否可用"""
        return self._initialized and len(self._ad_samples) > 0
    
    def check_semantic_coherence(self, main_text: str, button_texts: List[str]) -> float:
        """检查按钮文本与正文的语义相关性 - 轻量级方案"""
        if not main_text or not button_texts:
            return 1.0
        
        try:
            # 🚀 Linus式简化：使用简单的词汇重叠度
            main_words = set(main_text.lower().split())
            button_words = set(' '.join(button_texts).lower().split())
            
            if not main_words or not button_words:
                return 1.0
            
            # 计算Jaccard相似度
            intersection = main_words & button_words
            union = main_words | button_words
            jaccard_similarity = len(intersection) / len(union) if union else 0.0
            
            # 转换到0.3-1.0范围，0.3以下认为不相关
            normalized_similarity = 0.3 + (jaccard_similarity * 0.7)
            
            return min(normalized_similarity, 1.0)
            
        except Exception as e:
            logger.debug(f"语义相关性检查失败: {e}")
            return 1.0