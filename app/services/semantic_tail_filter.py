"""
基于语义的智能尾部过滤器 - 轻量级包装器
将过滤功能委托给专门的子模块处理
"""

import logging

logger = logging.getLogger(__name__)


class SemanticTailFilter:
    """基于语义的智能尾部过滤器 - 轻量级包装器"""
    
    def __init__(self):
        # 延迟导入避免循环依赖
        self._filter_engine = None
    
    def _get_filter_engine(self):
        """延迟初始化过滤引擎"""
        if self._filter_engine is None:
            from .tail_filter_engine import TailFilterEngine
            self._filter_engine = TailFilterEngine()
        return self._filter_engine
    
    def calculate_semantic_score(self, text: str, full_content: str = None) -> float:
        """委托给语义分析器处理"""
        return self._get_filter_engine().semantic_analyzer.calculate_semantic_score(text, full_content)
    
    def calculate_relevance(self, tail: str, full_content: str) -> float:
        """委托给语义分析器处理"""
        return self._get_filter_engine().semantic_analyzer.calculate_relevance(tail, full_content)
    
    def detect_topic_switch(self, main_content: str, tail: str) -> bool:
        """委托给模式匹配器处理"""
        return self._get_filter_engine().pattern_matcher.detect_topic_switch(main_content, tail)
    
    def is_likely_promotion(self, text: str, semantic_score: float) -> bool:
        """委托给语义分析器处理"""
        return self._get_filter_engine().semantic_analyzer.is_likely_promotion(text, semantic_score)
    
    
    def filter_message(self, content: str, has_media: bool = False) -> tuple:
        """主要过滤接口 - 委托给过滤引擎处理"""
        return self._get_filter_engine().filter_message(content, has_media)
    


# 全局实例
semantic_tail_filter = SemanticTailFilter()