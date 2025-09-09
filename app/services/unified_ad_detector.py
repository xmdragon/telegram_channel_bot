"""
统一广告检测器 - 用于API调用
基于关键词检测的简化接口

"简洁就是美" - 为API提供统一的检测接口

Author: Claude
Created: 2025-09-09
"""

import logging
from typing import NamedTuple
from dataclasses import dataclass

from app.services.detectors.keyword_ad_detector import get_keyword_ad_detector
from app.services.filters.base import FilterContext

logger = logging.getLogger(__name__)


@dataclass
class AdDetectionResult:
    """广告检测结果"""
    is_ad: bool
    confidence: float
    reason: str = ""


class UnifiedAdDetector:
    """统一广告检测器 - 为API提供简化接口"""
    
    def __init__(self):
        self._keyword_detector = None
    
    @property 
    def keyword_detector(self):
        """延迟加载关键词检测器"""
        if self._keyword_detector is None:
            self._keyword_detector = get_keyword_ad_detector()
        return self._keyword_detector
    
    def detect(self, content: str) -> AdDetectionResult:
        """
        检测文本是否为广告
        
        Args:
            content: 要检测的文本内容
            
        Returns:
            AdDetectionResult: 检测结果
        """
        try:
            if not content or not content.strip():
                return AdDetectionResult(
                    is_ad=False,
                    confidence=0.0,
                    reason="空内容"
                )
            
            # 创建过滤上下文
            filter_context = FilterContext(
                message_id="api_test",
                channel_id="api_test"
            )
            
            # 使用事件循环执行异步检测
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已在事件循环中，创建任务
                    result = asyncio.create_task(
                        self._async_detect(content, filter_context)
                    )
                    # 这种情况下返回默认结果，因为无法等待
                    return AdDetectionResult(
                        is_ad=False,
                        confidence=0.0,
                        reason="异步环境中无法同步检测"
                    )
                else:
                    # 如果不在事件循环中，直接运行
                    result = loop.run_until_complete(
                        self._async_detect(content, filter_context)
                    )
                    return result
            except RuntimeError:
                # 没有事件循环，创建新的
                result = asyncio.run(
                    self._async_detect(content, filter_context)
                )
                return result
                
        except Exception as e:
            logger.error(f"统一广告检测失败: {e}")
            return AdDetectionResult(
                is_ad=False,
                confidence=0.0,
                reason=f"检测异常: {str(e)}"
            )
    
    async def detect_async(self, content: str) -> AdDetectionResult:
        """
        异步检测文本是否为广告
        
        Args:
            content: 要检测的文本内容
            
        Returns:
            AdDetectionResult: 检测结果
        """
        try:
            if not content or not content.strip():
                return AdDetectionResult(
                    is_ad=False,
                    confidence=0.0,
                    reason="空内容"
                )
            
            # 创建过滤上下文
            filter_context = FilterContext(
                message_id="api_test",
                channel_id="api_test"
            )
            
            return await self._async_detect(content, filter_context)
            
        except Exception as e:
            logger.error(f"统一广告检测失败: {e}")
            return AdDetectionResult(
                is_ad=False,
                confidence=0.0,
                reason=f"检测异常: {str(e)}"
            )
    
    async def _async_detect(self, content: str, filter_context: FilterContext) -> AdDetectionResult:
        """内部异步检测方法"""
        try:
            # 执行关键词检测
            result = await self.keyword_detector.filter(content, filter_context)
            
            # 转换为统一结果格式
            is_ad = not result.passed
            confidence = result.confidence
            reason = result.reason or "关键词检测完成"
            
            return AdDetectionResult(
                is_ad=is_ad,
                confidence=confidence,
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"异步广告检测失败: {e}")
            return AdDetectionResult(
                is_ad=False,
                confidence=0.0,
                reason=f"检测异常: {str(e)}"
            )
    
    def get_stats(self):
        """获取检测统计"""
        try:
            return self.keyword_detector.get_detection_stats()
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {
                "detector_stats": {},
                "rules_info": {},
                "config": {}
            }


# 全局统一广告检测器实例
_unified_ad_detector = None

def get_unified_ad_detector() -> UnifiedAdDetector:
    """获取统一广告检测器实例（单例）"""
    global _unified_ad_detector
    if _unified_ad_detector is None:
        _unified_ad_detector = UnifiedAdDetector()
    return _unified_ad_detector


# 创建全局实例供外部使用
unified_ad_detector = get_unified_ad_detector()