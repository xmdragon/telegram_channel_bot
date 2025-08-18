"""
广告检测模块
包含AI检测、结构化检测、模式检测和推广实体检测
"""

# 懒加载重量级AI模块
def get_ai_ad_detector():
    """获取AI广告检测器类（懒加载）"""
    from .ai_detector import AIAdDetector
    return AIAdDetector

# 立即导入轻量级模块
from .structural_detector import StructuralAdDetector
from .pattern_detector import PatternAdDetector  
from .promotional_entity_detector import PromotionalEntityDetector

# 懒加载代理类
class _AIAdDetectorProxy:
    """AI广告检测器代理，实现懒加载"""
    def __new__(cls, *args, **kwargs):
        # 检查AI功能是否启用
        try:
            from app.core.ai_config import is_module_enabled
            if not is_module_enabled('ai_ad_detector'):
                from app.services.dummy_implementations import DummyAIAdDetector
                return DummyAIAdDetector(*args, **kwargs)
        except ImportError:
            pass
        
        AIAdDetector = get_ai_ad_detector()
        return AIAdDetector(*args, **kwargs)

# 兼容性：保持原有导入接口
AIAdDetector = _AIAdDetectorProxy

__all__ = [
    'AIAdDetector',
    'StructuralAdDetector', 
    'PatternAdDetector',
    'PromotionalEntityDetector',
    'get_ai_ad_detector'
]