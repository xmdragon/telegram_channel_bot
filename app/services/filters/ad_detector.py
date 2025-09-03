"""
广告检测过滤器 - 重构版本
整合结构化检测、AI检测和模式检测的统一广告检测器
检测到广告时返回 should_early_stop=True

Author: Claude
Created: 2025-08-15  
Refactored: 2025-08-18 - 模块化架构，遵循500行限制
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple

from .base import BaseFilter, FilterContext, FilterResult
from .ad_detection import AIAdDetector, StructuralAdDetector, PatternAdDetector, PromotionalEntityDetector

logger = logging.getLogger(__name__)


class AdDetectorFilter(BaseFilter):
    """广告检测过滤器 - 重构版本，整合多种检测方法"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("ad_detector", config)
        
        # 初始化各个检测器
        self.ai_detector = AIAdDetector(
            threshold=self.config.get('ai_threshold', 0.7)  # 提高检测敏感度
        )
        
        self.structural_detector = StructuralAdDetector(
            coherence_threshold=self.config.get('semantic_coherence_threshold', 0.35),
            url_threshold=self.config.get('suspicious_url_threshold', 0.8)
        )
        
        self.pattern_detector = PatternAdDetector(
            pattern_weights=self.config.get('pattern_weights', {})
        )
        
        self.entity_detector = PromotionalEntityDetector()
        
        # 综合评分阈值
        self.final_threshold = self.config.get('final_threshold', 0.7)
        
        logger.info("✅ 广告检测过滤器初始化完成 - 模块化架构")
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """执行广告检测 - 使用统一检测器"""
        start_time = time.time()
        
        result = FilterResult(
            filtered_content=content,
            passed=True,
            confidence=0.0,
            details={}
        )
        
        try:
            # 🔧 新版本：使用统一广告检测器
            from app.services.unified_ad_detector import get_unified_ad_detector
            unified_detector = get_unified_ad_detector()
            
            # 构造统一检测器所需的上下文
            unified_context = {
                'message_id': context.message_id,
                'channel_id': context.channel_id,
                'media_files': context.get_metadata('media_files', []),
                'telegram_message': context.get_metadata('telegram_message'),
                'buttons': context.get_metadata('buttons', []),
                'entities': context.get_metadata('entities', [])
            }
            
            # 执行统一检测
            detection_result = await unified_detector.detect_advertisement(content, unified_context)
            
            # 转换结果格式以保持兼容性
            is_ad = detection_result['is_ad']
            final_score = detection_result['confidence']
            main_reason = detection_result['reason']
            
            if is_ad:
                # 🔧 新版本：使用统一检测器的拒绝逻辑结果
                should_reject = detection_result['should_reject']
                
                if should_reject:
                    # 自动拒绝：拒绝消息并early stop
                    result.passed = False
                    result.should_early_stop = True
                    result.reason = f"统一检测器自动拒绝: {main_reason}"
                    result.filtered_content = content  # 保持内容不变
                    logger.info(f"统一检测器自动拒绝: {main_reason}")
                else:
                    # 仅检测标记：让消息继续通过后续过滤器
                    result.passed = True
                    result.should_early_stop = False
                    result.reason = f"统一检测器标记广告: {main_reason}"
                    result.filtered_content = content  # 保持原始内容
                    logger.debug(f"统一检测器仅标记（未启用自动拒绝）: {main_reason}")
                
                result.confidence = final_score
                
                # 在context中记录广告检测结果，供后续处理使用
                context.add_metadata('ad_detection_result', {
                    'is_ad': True,
                    'confidence': final_score,
                    'main_reason': main_reason,
                    'detection_method': detection_result.get('detection_method', 'unified'),
                    'step_results': detection_result.get('step_results', {}),
                    'training_data_collected': detection_result.get('training_data_collected', False)
                })
                
                # 记录详细判定依据
                result.details = {
                    'unified_detection_result': detection_result,
                    'final_score': final_score,
                    'main_reason': main_reason,
                    'detection_method': detection_result.get('detection_method', 'unified'),
                    'should_reject': should_reject,
                    'action': 'auto_rejected' if should_reject else 'detected_only'
                }
                
                logger.info(f"🔍 统一广告检测: 置信度 {final_score:.2f}, 方法: {detection_result.get('detection_method', 'unified')}")
            else:
                result.details = {
                    'unified_detection_result': detection_result,
                    'final_score': final_score,
                    'detection_method': detection_result.get('detection_method', 'none'),
                    'all_methods_passed': True
                }
                logger.debug(f"✅ 统一广告检测完成，置信度: {final_score:.2f}，未检测到广告")
                
        except Exception as e:
            logger.error(f"广告检测失败: {e}", exc_info=True)
            # 异常时不影响消息处理，允许通过
            result.details['error'] = str(e)
        
        # 计算处理时间
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        return result
    
    # 🔧 已移除：_comprehensive_ad_detection 和 _evaluate_detection_results 
    # 这些方法已被统一广告检测器替代，保持代码简洁
    
    async def validate_config(self) -> bool:
        """验证配置是否有效"""
        try:
            # 检查阈值参数
            if not (0.0 < self.final_threshold <= 1.0):
                logger.error("final_threshold 必须在 (0, 1] 范围内")
                return False
            
            return True
        except Exception as e:
            logger.error(f"验证配置失败: {e}")
            return False


# 懒加载默认实例
_ad_detector_filter_instance = None

def get_ad_detector_filter():
    """获取广告检测过滤器实例（懒加载）"""
    global _ad_detector_filter_instance
    if _ad_detector_filter_instance is None:
        _ad_detector_filter_instance = AdDetectorFilter()
    return _ad_detector_filter_instance

# 兼容性：保持ad_detector_filter属性访问
class AdDetectorFilterProxy:
    """广告检测过滤器代理，实现懒加载"""
    def __getattr__(self, name):
        return getattr(get_ad_detector_filter(), name)
    
    def __setattr__(self, name, value):
        setattr(get_ad_detector_filter(), name, value)

ad_detector_filter = AdDetectorFilterProxy()