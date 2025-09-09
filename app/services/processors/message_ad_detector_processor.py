"""
消息广告检测处理器 - 基于关键词的纯广告检测
专门负责广告检测逻辑，与过滤处理分离

"复杂性是万恶之源" - 移除ONNX，使用简单的关键词匹配

Author: Claude  
Created: 2025-09-08
Updated: 2025-09-09 (移除ONNX，改为关键词检测)
"""

import logging
import asyncio
from typing import Tuple

from app.services.processors.base import MessageProcessor, ProcessorResult, MessageContext
from app.services.detectors.keyword_ad_detector import get_keyword_ad_detector

logger = logging.getLogger(__name__)


class MessageAdDetectorProcessor(MessageProcessor):
    """消息广告检测处理器 - 基于关键词的纯广告检测"""
    
    def __init__(self):
        super().__init__("MessageAdDetectorProcessor")
        
        # 延迟初始化，避免循环依赖
        self._keyword_detector = None
    
    @property
    def keyword_detector(self):
        """延迟加载关键词检测器"""
        if self._keyword_detector is None:
            self._keyword_detector = get_keyword_ad_detector()
        return self._keyword_detector
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        广告检测主流程：
        1. 检查自动拒绝配置
        2. 进行关键词检测
        3. 根据检测结果决定是否拒绝
        """
        try:
            # 检查自动拒绝配置
            auto_reject_enabled = await self._check_auto_reject_config()
            if not auto_reject_enabled:
                self.logger.debug("自动拒绝广告未启用，跳过广告检测")
                return ProcessorResult(True, context)
            
            # 进行关键词广告检测
            is_ad, confidence, reason = await self._detect_advertisement(context)
            
            # 记录检测信息到上下文
            context.ad_detection_score = confidence
            context.ad_detection_threshold = 10  # 关键词检测的权重阈值
            
            if is_ad:
                # 检测到广告，标记拒绝
                context.should_reject = True
                context.auto_rejected = True
                context.reject_reason = reason
                context.ad_detected = True
                
                self.logger.info(f"🚫 关键词检测到广告，自动拒绝: {reason}")
                
                # 通知统计更新
                await self._notify_ad_detected(context)
            else:
                context.ad_detected = False
                self.logger.debug(f"✅ 关键词检测：非广告内容（置信度: {confidence:.3f}）")
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            self.logger.error(f"广告检测失败: {e}")
            # 检测失败时不拒绝消息，保证系统健壮性
            return ProcessorResult(True, context)
    
    async def _check_auto_reject_config(self) -> bool:
        """检查自动拒绝广告配置"""
        try:
            from app.services.config_manager import config_manager
            auto_reject_ads = await config_manager.get_config('review.auto_reject_ads', False)
            return bool(auto_reject_ads)
        except Exception as e:
            self.logger.error(f"获取自动拒绝配置失败: {e}")
            return False
    
    async def _detect_advertisement(self, context: MessageContext) -> Tuple[bool, float, str]:
        """
        关键词广告检测
        
        Returns:
            (是否广告, 置信度, 原因描述)
        """
        try:
            # 获取过滤后的干净文本用于检测
            content = context.filtered_content or context.processed_content
            
            if not content or not content.strip():
                return False, 0.0, "空内容"
            
            # 使用关键词检测器
            from app.services.filters.base import FilterContext
            filter_context = FilterContext(
                message_id=context.message_id,
                channel_id=context.channel_id
            )
            
            # 添加原始内容到上下文
            filter_context.add_metadata('original_content', context.original_content)
            
            # 执行关键词检测
            result = await self.keyword_detector.filter(content, filter_context)
            
            # 从结果中提取检测信息
            is_ad = not result.passed
            confidence = result.confidence
            reason = result.reason or "关键词检测完成"
            
            return is_ad, confidence, reason
            
        except Exception as e:
            self.logger.error(f"关键词广告检测失败: {e}")
            return False, 0.0, f"检测异常: {str(e)}"
    
    async def _notify_ad_detected(self, context: MessageContext):
        """通知广告检测结果（用于统计和学习）"""
        try:
            # 这里可以添加统计更新、学习机制等
            # 但保持处理器职责单一，不做复杂逻辑
            pass
        except Exception as e:
            self.logger.error(f"广告检测通知失败: {e}")
    
    def record_user_feedback(self, message_id: str, user_decision: str, 
                           detection_score: float, detection_threshold: float):
        """
        记录用户反馈（关键词检测暂不支持自动学习）
        
        Args:
            message_id: 消息ID
            user_decision: 用户决定 ('approve', 'reject')
            detection_score: 检测分数
            detection_threshold: 使用的阈值
        """
        try:
            # 关键词检测暂时不支持自动学习，仅记录日志
            self.logger.info(f"📝 记录广告检测反馈: {message_id} - 用户{user_decision}, 分数{detection_score:.3f}")
            
            # 可以在这里实现将误判的内容添加到白名单或训练数据的逻辑
            
        except Exception as e:
            self.logger.error(f"记录用户反馈失败: {e}")