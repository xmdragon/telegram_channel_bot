"""
消息广告检测处理器 - 基于语义向量的纯广告检测
专门负责广告检测逻辑，与过滤处理分离

Author: Claude
Created: 2025-09-08
"""

import logging
import asyncio
from typing import Tuple

from app.services.processors.base import MessageProcessor, ProcessorResult, MessageContext
from app.services.semantic_extractor import get_semantic_extractor
from app.services.vector_manager import VectorManager

logger = logging.getLogger(__name__)


class MessageAdDetectorProcessor(MessageProcessor):
    """消息广告检测处理器 - 基于语义向量的纯广告检测"""
    
    def __init__(self):
        super().__init__("MessageAdDetectorProcessor")
        
        # 延迟初始化，避免循环依赖
        self._semantic_extractor = None
        self._vector_manager = None
    
    @property
    def semantic_extractor(self):
        """延迟加载语义提取器"""
        if self._semantic_extractor is None:
            self._semantic_extractor = get_semantic_extractor(768)
        return self._semantic_extractor
    
    @property
    def vector_manager(self):
        """延迟加载向量管理器"""
        if self._vector_manager is None:
            self._vector_manager = VectorManager()
        return self._vector_manager
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        广告检测主流程：
        1. 检查自动拒绝配置
        2. 进行语义向量检测
        3. 根据检测结果决定是否拒绝
        """
        try:
            # 检查自动拒绝配置
            auto_reject_enabled = await self._check_auto_reject_config()
            if not auto_reject_enabled:
                self.logger.debug("自动拒绝广告未启用，跳过广告检测")
                return ProcessorResult(True, context)
            
            # 进行语义广告检测
            is_ad, similarity, reason = await self._detect_advertisement(context)
            
            if is_ad:
                # 检测到广告，标记拒绝
                context.should_reject = True
                context.auto_rejected = True
                context.reject_reason = reason
                
                self.logger.info(f"🚫 语义检测到广告，自动拒绝: {reason}")
                
                # 通知统计更新
                await self._notify_ad_detected(context)
            else:
                self.logger.debug(f"✅ 语义检测：非广告内容（相似度: {similarity:.3f}）")
            
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
        语义广告检测
        
        Returns:
            (是否广告, 相似度, 原因描述)
        """
        try:
            # 获取过滤后的干净文本用于检测
            content = context.filtered_content or context.processed_content
            
            if not content or not content.strip():
                return False, 0.0, "空内容"
            
            # 提取语义向量
            extract_result = self.semantic_extractor.extract_vector_with_info(content)
            
            if not extract_result['success']:
                return False, 0.0, f"向量提取失败: {extract_result.get('error_message', 'unknown')}"
            
            # 与广告向量库比较
            content_vector = extract_result['vector']
            is_ad, similarity, match_info = self.vector_manager.is_advertisement(content_vector)
            
            if is_ad:
                reason = f"语义向量检测到广告（相似度: {similarity:.3f}）"
                return True, similarity, reason
            
            return False, similarity, "语义检测：非广告内容"
            
        except Exception as e:
            self.logger.error(f"语义广告检测失败: {e}")
            return False, 0.0, f"检测异常: {str(e)}"
    
    async def _notify_ad_detected(self, context: MessageContext):
        """通知广告检测结果（用于统计和学习）"""
        try:
            # 这里可以添加统计更新、学习机制等
            # 但保持处理器职责单一，不做复杂逻辑
            pass
        except Exception as e:
            self.logger.error(f"广告检测通知失败: {e}")