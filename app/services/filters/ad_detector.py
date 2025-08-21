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
        """执行广告检测"""
        start_time = time.time()
        
        result = FilterResult(
            filtered_content=content,
            passed=True,
            confidence=0.0,
            details={}
        )
        
        try:
            # 获取消息结构信息
            buttons = context.get_metadata('buttons', [])
            entities = context.get_metadata('entities', [])
            message = context.get_metadata('telegram_message')
            
            # 执行多种检测方法
            detection_results = await self._comprehensive_ad_detection(
                content, buttons, entities, message, context
            )
            
            # 综合评估
            final_score, is_ad, main_reason = self._evaluate_detection_results(detection_results)
            
            if is_ad:
                # 🔧 重要修改：根据配置决定是否early stop
                # 检查自动拒绝广告配置
                try:
                    # 先尝试config_manager
                    from app.services.config_manager import config_manager
                    auto_reject_ads = await config_manager.get_config('review.auto_reject_ads', False)
                    
                    # 如果config_manager返回False，直接读取配置文件确认
                    if not auto_reject_ads:
                        import json
                        with open('data/config/system.json', 'r') as f:
                            config_data = json.load(f)
                        raw_value = config_data.get('review.auto_reject_ads', {}).get('value', 'false')
                        auto_reject_ads = (raw_value == 'true')
                        logger.debug(f"直接读取配置文件: auto_reject_ads = {auto_reject_ads}")
                    
                    if auto_reject_ads:
                        # 启用自动拒绝：拒绝消息并early stop
                        result.passed = False
                        result.should_early_stop = True
                        result.reason = f"自动拒绝广告消息: {main_reason}"
                        result.filtered_content = ""  # 清空内容
                        logger.info(f"广告检测器自动拒绝: {main_reason}")
                    else:
                        # 仅检测标记：让消息继续通过后续过滤器
                        result.passed = True
                        result.should_early_stop = False
                        result.reason = f"AI检测到疑似广告: {main_reason}"
                        result.filtered_content = content  # 保持原始内容
                        logger.debug(f"广告检测器仅标记（未启用自动拒绝）: {main_reason}")
                        
                except Exception as e:
                    # 配置读取失败时，采用保守策略：仅检测标记
                    result.passed = True
                    result.should_early_stop = False
                    result.reason = f"AI检测到疑似广告: {main_reason}"
                    result.filtered_content = content
                    logger.warning(f"读取auto_reject_ads配置失败，采用保守策略: {e}")
                
                result.confidence = final_score
                
                # 在context中记录广告检测结果，供后续处理使用
                context.add_metadata('ad_detection_result', {
                    'is_ad': True,
                    'confidence': final_score,
                    'main_reason': main_reason,
                    'detection_results': detection_results,
                    'threshold': self.final_threshold,
                    'methods_used': list(detection_results.keys())
                })
                
                # 记录详细判定依据
                result.details = {
                    'detection_results': detection_results,
                    'final_score': final_score,
                    'main_reason': main_reason,
                    'threshold': self.final_threshold,
                    'methods_used': list(detection_results.keys()),
                    'action': 'detected_only'  # 标记为仅检测
                }
                
                logger.info(f"🔍 AI广告检测（仅标记）: 置信度 {final_score:.2f}, 原因: {main_reason}")
            else:
                result.details = {
                    'detection_results': detection_results,
                    'final_score': final_score,
                    'all_methods_passed': True
                }
                logger.debug(f"✅ 广告检测完成，综合评分: {final_score:.2f}，未超过阈值 {self.final_threshold}")
                
        except Exception as e:
            logger.error(f"广告检测失败: {e}", exc_info=True)
            # 异常时不影响消息处理，允许通过
            result.details['error'] = str(e)
        
        # 计算处理时间
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        return result
    
    async def _comprehensive_ad_detection(self, content: str, buttons: List[Dict], 
                                        entities: List[Dict], message: Any,
                                        context: FilterContext) -> Dict[str, Dict]:
        """综合广告检测：整合所有检测方法"""
        results = {}
        
        # 1. AI语义检测
        if self.ai_detector.is_available() and content:
            results['ai_detection'] = await self.ai_detector.detect(content)
        
        # 2. 结构化检测（按钮和实体）
        if buttons or entities:
            results['structural_detection'] = await self.structural_detector.detect(
                content, buttons, entities, message, self.ai_detector
            )
        
        # 3. 模式匹配检测
        if content:
            results['pattern_detection'] = await self.pattern_detector.detect(content)
        
        # 4. 推广实体模式检测
        if entities:
            results['promotional_entity_detection'] = await self.entity_detector.detect(
                content, entities
            )
        
        return results
    
    def _evaluate_detection_results(self, detection_results: Dict[str, Dict]) -> Tuple[float, bool, str]:
        """综合评估检测结果"""
        scores = []
        reasons = []
        
        # AI检测结果
        if 'ai_detection' in detection_results:
            ai_result = detection_results['ai_detection']
            if ai_result.get('is_ad', False):
                # 对于AI检测，直接使用原始置信度，不降权
                scores.append(ai_result['confidence'])  
                reasons.append(f"AI检测(相似度:{ai_result.get('similarity_score', 0):.2f})")
        
        # 结构化检测结果
        if 'structural_detection' in detection_results:
            struct_result = detection_results['structural_detection']
            if struct_result.get('is_ad', False):
                scores.append(struct_result['confidence'] * 0.85)
                reasons.append("结构化检测")
        
        # 模式检测结果
        if 'pattern_detection' in detection_results:
            pattern_result = detection_results['pattern_detection']
            if pattern_result.get('is_ad', False):
                scores.append(pattern_result['confidence'] * 0.8)
                reasons.append(f"模式匹配(权重:{pattern_result.get('total_weight', 0)})")
        
        # 推广实体检测结果
        if 'promotional_entity_detection' in detection_results:
            promo_result = detection_results['promotional_entity_detection']
            if promo_result.get('is_ad', False):
                scores.append(promo_result['confidence'] * 0.75)
                reasons.append("推广实体模式")
        
        # 计算最终得分
        if scores:
            final_score = max(scores)  # 使用最高分数
            main_reason = reasons[scores.index(max(scores))]
            is_ad = final_score >= self.final_threshold
        else:
            final_score = 0.0
            main_reason = "无广告特征"
            is_ad = False
        
        return final_score, is_ad, main_reason
    
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