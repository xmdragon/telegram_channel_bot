"""
AI模块的空实现
当AI功能禁用时使用这些轻量级实现
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class DummyTailFeatureExtractor:
    """尾部特征提取器的空实现"""
    
    def __init__(self):
        self.initialized = False
        logger.info("🔒 使用TailFeatureExtractor空实现（AI功能已禁用）")
    
    def extract_features(self, text: str) -> Dict[str, Any]:
        """返回空特征"""
        return {
            "text": text,
            "features": [],
            "scores": {},
            "should_filter": False,
            "analysis_time": datetime.now().isoformat()
        }
    
    def should_filter(self, text: str) -> bool:
        """不过滤任何内容"""
        return False
    
    def analyze_text(self, text: str) -> Dict[str, Any]:
        """返回空分析结果"""
        return self.extract_features(text)
    
    def calculate_scores(self, text: str, **kwargs) -> Dict[str, float]:
        """计算分数（空实现）"""
        return {
            "tail_score": 0.0,
            "promo_score": 0.0,
            "content_score": 1.0,
            "filter_confidence": 0.0
        }

class DummyTailVectorManager:
    """尾部向量管理器的空实现"""
    
    def __init__(self):
        self.initialized = False
        logger.info("🔒 使用TailVectorManager空实现（AI功能已禁用）")
    
    def add_vector(self, channel_id: str, text: str, vector: List[float] = None) -> bool:
        """不添加任何向量"""
        return True
    
    def find_similar(self, text: str, threshold: float = 0.8, limit: int = 10) -> List[Dict]:
        """不返回任何相似结果"""
        return []
    
    def get_channel_vectors(self, channel_id: str) -> List[Dict]:
        """不返回任何向量"""
        return []
    
    def get_health_status(self) -> Dict[str, Any]:
        """返回健康状态"""
        return {
            "model_loaded": False,
            "vector_count": 0,
            "index_size": 0,
            "memory_usage": "0MB",
            "index_consistent": True,
            "overall_healthy": True
        }

class DummyAIAdDetector:
    """AI广告检测器的空实现"""
    
    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold
        self._initialized = False
        logger.info("🔒 使用AIAdDetector空实现（AI功能已禁用）")
    
    def detect_ad(self, text: str, buttons: List[str] = None) -> Tuple[bool, float, str]:
        """不检测任何广告"""
        return False, 0.0, "AI功能已禁用"
    
    def add_sample(self, text: str, is_ad: bool) -> bool:
        """不添加任何样本"""
        return True
    
    def is_available(self) -> bool:
        """AI功能不可用"""
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """返回空统计"""
        return {
            "initialized": False,
            "sample_count": 0,
            "threshold": self.threshold
        }

class DummyIntelligentFilter:
    """智能过滤器的空实现"""
    
    def __init__(self):
        self.initialized = False
        logger.info("🔒 使用IntelligentFilter空实现（AI功能已禁用）")
    
    async def filter_content(self, content: str, channel_id: str = None) -> Tuple[str, bool, Dict]:
        """不过滤任何内容"""
        return content, False, {
            "filtered": False,
            "reason": "AI功能已禁用",
            "confidence": 0.0
        }
    
    async def learn_channel_pattern(self, channel_id: str, messages: List[str]) -> bool:
        """不学习任何模式"""
        return True
    
    def save_patterns(self, filepath: str):
        """不保存任何模式"""
        pass
    
    def load_patterns(self, filepath: str):
        """不加载任何模式"""
        pass

class DummyAdDetector:
    """广告检测器的空实现"""
    
    def __init__(self):
        self.initialized = False
        logger.info("🔒 使用AdDetector空实现（AI功能已禁用）")
    
    async def detect_ad_async(self, text: str) -> Tuple[bool, float, str]:
        """不检测任何广告"""
        return False, 0.0, "AI功能已禁用"
    
    def detect_ad(self, text: str) -> Tuple[bool, float, str]:
        """不检测任何广告"""
        return False, 0.0, "AI功能已禁用"
    
    def add_ad_sample(self, text: str) -> bool:
        """不添加任何样本"""
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """返回空统计"""
        return {
            "initialized": False,
            "ad_samples_count": 0,
            "model_name": None,
            "threshold": 0.75
        }