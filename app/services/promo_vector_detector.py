"""
推广内容检测器
基于规则的推广内容检测方案

Author: Claude
Created: 2025-08-31
"""

import logging
import time
from typing import Dict, List, Optional, Any
import asyncio

from app.services.filters.base import BaseFilter, FilterContext, FilterResult

logger = logging.getLogger(__name__)


class PromoVectorDetector(BaseFilter):
    """推广内容检测器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("promo_detector", config)
        
        # 配置参数
        self.similarity_threshold = self.config.get('similarity_threshold', 0.7)
        
        # 统计信息
        self.detection_stats = {
            'total_processed': 0,
            'detections': 0,
            'avg_confidence': 0.0
        }
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """推广内容检测主方法"""
        start_time = time.time()
        
        # 初始化结果
        result = FilterResult(
            filtered_content=content,
            passed=True,
            confidence=0.0,
            details={}
        )
        
        try:
            # 更新统计
            self.detection_stats['total_processed'] += 1
            
            # 基于规则的检测
            detection_result = await self._rule_based_detection(content, context)
            
            if detection_result['is_promo']:
                self.detection_stats['detections'] += 1
                result.confidence = detection_result['confidence']
                result.details.update(detection_result['details'])
                result.reason = f"检测到推广内容: 置信度 {detection_result['confidence']:.3f}"
                
                # 根据配置决定是否通过
                if detection_result['confidence'] > self.similarity_threshold:
                    result.passed = False
                    result.should_early_stop = True
                    logger.info(f"🚫 拒绝推广内容 - 置信度: {detection_result['confidence']:.3f}")
                else:
                    logger.debug(f"🔍 标记疑似推广 - 置信度: {detection_result['confidence']:.3f}")
            else:
                result.reason = f"内容正常: 置信度 {detection_result['confidence']:.3f}"
                logger.debug(f"✅ 检测正常 - 置信度: {detection_result['confidence']:.3f}")
            
            # 更新平均置信度
            self._update_avg_confidence(detection_result['confidence'])
            
            # 在context中记录检测结果
            context.add_metadata('promo_detection', {
                'is_promo': not result.passed,
                'confidence': result.confidence,
                'method': 'rule_based',
                'reason': result.reason
            })
            
        except Exception as e:
            logger.error(f"推广内容检测异常: {e}", exc_info=True)
            result.reason = f"检测异常: {str(e)}"
            result.details['error'] = str(e)
        
        # 记录处理时间
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        return result
    
    async def _rule_based_detection(self, content: str, context: FilterContext) -> Dict[str, Any]:
        """基于规则的推广检测"""
        try:
            if not content:
                return {
                    'is_promo': False,
                    'confidence': 0.0,
                    'details': {'reason': 'empty_content'}
                }
            
            # 简单的推广检测规则
            promo_keywords = [
                '订阅', '关注', '加入群', '扫码', '联系',
                '微信', 'QQ', '电话', '手机', '商务合作'
            ]
            
            confidence = 0.0
            matched_keywords = []
            
            for keyword in promo_keywords:
                if keyword in content:
                    confidence += 0.2
                    matched_keywords.append(keyword)
            
            # 限制最高置信度
            confidence = min(confidence, 1.0)
            
            is_promo = confidence > 0.3  # 基础阈值
            
            return {
                'is_promo': is_promo,
                'confidence': confidence,
                'details': {
                    'method': 'rule_based',
                    'matched_keywords': matched_keywords,
                    'threshold': 0.3
                }
            }
            
        except Exception as e:
            return {
                'is_promo': False,
                'confidence': 0.0,
                'details': {'error': str(e)}
            }
    
    def _update_avg_confidence(self, confidence: float):
        """更新平均置信度统计"""
        current_avg = self.detection_stats['avg_confidence']
        total_processed = self.detection_stats['total_processed']
        
        # 增量计算平均值
        self.detection_stats['avg_confidence'] = (
            (current_avg * (total_processed - 1) + confidence) / total_processed
        )
    
    def manual_learn_promo(self, content: str, context: Optional[FilterContext] = None) -> bool:
        """手动标记推广样本进行学习"""
        try:
            if not context:
                context = FilterContext(message_id="manual", channel_id="manual")
            
            logger.info(f"手动标记推广样本: {content[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"手动学习失败: {e}")
            return False
    
    def get_detection_stats(self) -> Dict[str, Any]:
        """获取检测统计信息"""        
        return {
            'detector_stats': self.detection_stats.copy(),
            'config': {
                'similarity_threshold': self.similarity_threshold
            }
        }
    
    def cleanup_data(self) -> int:
        """清理数据"""
        return 0


# 全局推广内容检测器实例
_promo_detector = None

def get_promo_vector_detector() -> PromoVectorDetector:
    """获取推广内容检测器实例（单例）"""
    global _promo_detector
    if _promo_detector is None:
        _promo_detector = PromoVectorDetector()
    return _promo_detector