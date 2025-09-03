"""
推广内容向量检测器 - Linus式简洁设计
基于语义向量的推广内容检测方案

Author: Claude
Created: 2025-08-31
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple
import asyncio

from app.services.filters.base import BaseFilter, FilterContext, FilterResult
from app.services.vector_manager import vector_manager
from app.services.semantic_extractor import get_semantic_extractor

logger = logging.getLogger(__name__)


class PromoVectorDetector(BaseFilter):
    """推广内容向量检测器 - 消除特殊情况的统一设计"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("promo_vector_detector", config)
        
        # 核心组件
        self.vector_manager = vector_manager
        self.semantic_extractor = get_semantic_extractor(768)
        
        # 配置参数
        self.similarity_threshold = self.config.get('similarity_threshold', 0.7)
        self.enable_self_learning = self.config.get('enable_self_learning', True)
        self.auto_reject_ads = self.config.get('auto_reject_ads', True)
        
        # 降级策略
        self.enable_fallback = self.config.get('enable_fallback', True)
        self.fallback_engine = None
        
        # 统计信息
        self.detection_stats = {
            'total_processed': 0,
            'vector_detections': 0,
            'fallback_detections': 0,
            'self_learning_count': 0,
            'avg_similarity': 0.0
        }
        
        logger.info(f"向量广告检测器初始化 - 阈值: {self.similarity_threshold}, 自学习: {self.enable_self_learning}")
    
    def _init_fallback_engine(self):
        """懒加载降级引擎"""
        if self.fallback_engine is None and self.enable_fallback:
            try:
                # 懒加载，避免循环导入
                from app.services.unified_filter_engine import UnifiedFilterEngine
                self.fallback_engine = UnifiedFilterEngine()
                logger.debug("降级引擎初始化完成")
            except Exception as e:
                logger.error(f"降级引擎初始化失败: {e}")
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """向量化广告检测主方法"""
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
            
            # === 第一步：向量检测 ===
            vector_result = await self._vector_detection(content, context)
            
            if vector_result['success']:
                # 向量检测成功
                result.confidence = vector_result['similarity']
                result.details.update(vector_result['details'])
                
                if vector_result['is_ad']:
                    # 检测到广告
                    self.detection_stats['vector_detections'] += 1
                    
                    if self.auto_reject_ads:
                        # 自动拒绝模式
                        result.passed = False
                        result.should_early_stop = True
                        result.reason = f"向量检测到广告: 相似度 {vector_result['similarity']:.3f}"
                        
                        logger.info(f"🚫 向量检测拒绝广告 - 相似度: {vector_result['similarity']:.3f}")
                        
                        # 自学习：将检测到的广告加入向量库
                        if self.enable_self_learning:
                            await self._self_learn(content, context, 'detected_ad')
                    else:
                        # 仅标记模式
                        result.passed = True
                        result.should_early_stop = False
                        result.reason = f"向量检测到疑似广告: 相似度 {vector_result['similarity']:.3f}"
                        
                        logger.debug(f"🔍 向量检测标记 - 相似度: {vector_result['similarity']:.3f}")
                else:
                    # 未检测到广告
                    result.reason = f"向量检测正常: 相似度 {vector_result['similarity']:.3f}"
                    logger.debug(f"✅ 向量检测正常 - 相似度: {vector_result['similarity']:.3f}")
                
                # 记录平均相似度
                self._update_avg_similarity(vector_result['similarity'])
                
            else:
                # === 第二步：根据错误类型决定处理方式 ===
                error_type = vector_result.get('error_type', 'unknown')
                error_message = vector_result['error']
                
                if error_type == 'invalid_text':
                    # 文本无效（正常情况）- 不触发降级，直接通过
                    logger.debug(f"文本无效跳过向量检测: {error_message}")
                    result.reason = "文本预处理后无有效内容，跳过检测"
                    result.confidence = 0.1
                    result.details['skip_reason'] = error_message
                    
                elif error_type == 'technical_error':
                    # 技术错误 - 启用降级检测
                    logger.warning(f"向量检测技术故障: {error_message}，启用降级模式")
                    
                    fallback_result = await self._fallback_detection(content, context)
                    
                    if fallback_result['success']:
                        self.detection_stats['fallback_detections'] += 1
                        
                        result.confidence = 0.8 if fallback_result['is_ad'] else 0.2
                        result.details.update(fallback_result['details'])
                        
                        if fallback_result['is_ad']:
                            if self.auto_reject_ads:
                                result.passed = False
                                result.should_early_stop = True
                                result.reason = f"降级检测到广告: {fallback_result['reason']}"
                            else:
                                result.passed = True
                                result.should_early_stop = False
                                result.reason = f"降级检测到疑似广告: {fallback_result['reason']}"
                        else:
                            result.reason = "降级检测正常"
                    else:
                        # 完全失败，保守通过
                        logger.error("向量检测和降级检测都失败，默认通过")
                        result.reason = "检测失败，默认通过"
                        result.details['error'] = error_message
                        
                else:
                    # 未知错误类型 - 保守处理
                    logger.warning(f"向量检测未知错误: {error_message}")
                    result.reason = f"检测异常，默认通过: {error_message}"
                    result.details['error'] = error_message
            
            # 在context中记录检测结果
            context.add_metadata('vector_ad_detection', {
                'is_ad': not result.passed,
                'confidence': result.confidence,
                'method': 'vector' if vector_result['success'] else 'fallback',
                'similarity': vector_result.get('similarity', 0.0),
                'reason': result.reason
            })
            
        except Exception as e:
            logger.error(f"向量广告检测异常: {e}", exc_info=True)
            # 异常时默认通过
            result.reason = f"检测异常: {str(e)}"
            result.details['error'] = str(e)
        
        # 记录处理时间
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        return result
    
    async def _vector_detection(self, content: str, context: FilterContext) -> Dict[str, Any]:
        """向量检测核心逻辑"""
        try:
            # 使用增强的向量提取方法获取详细信息
            extract_result = self.semantic_extractor.extract_vector_with_info(content)
            
            if not extract_result['success']:
                error_type = extract_result['error_type']
                error_message = extract_result['error_message']
                
                return {
                    'success': False,
                    'error': error_message,
                    'error_type': error_type,
                    'details': {
                        'processed_text': extract_result['processed_text']
                    }
                }
            
            content_vector = extract_result['vector']
            
            # 与向量库比较
            is_ad, similarity, match_info = self.vector_manager.is_advertisement(content_vector)
            
            return {
                'success': True,
                'is_ad': is_ad,
                'similarity': similarity,
                'content_vector': content_vector,  # 用于自学习
                'error_type': 'none',
                'details': {
                    'vector_detection': True,
                    'match_info': match_info,
                    'vector_dim': len(content_vector),
                    'threshold': self.similarity_threshold,
                    'processed_text': extract_result['processed_text']
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': 'technical_error',
                'details': {}
            }
    
    async def _fallback_detection(self, content: str, context: FilterContext) -> Dict[str, Any]:
        """降级检测逻辑"""
        try:
            if not self.enable_fallback:
                return {
                    'success': False,
                    'error': '降级检测已禁用',
                    'details': {}
                }
            
            # 初始化降级引擎
            self._init_fallback_engine()
            
            if self.fallback_engine:
                # 使用高风险模式检测
                is_high_risk, risk_patterns = self.fallback_engine.is_high_risk_ad(content)
                
                return {
                    'success': True,
                    'is_ad': is_high_risk,
                    'reason': f"高风险广告({len(risk_patterns)}个特征)" if is_high_risk else "高风险检测正常",
                    'details': {
                        'fallback_detection': True,
                        'risk_patterns': risk_patterns,
                        'pattern_count': len(risk_patterns)
                    }
                }
            else:
                return {
                    'success': False,
                    'error': '降级引擎不可用',
                    'details': {}
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'details': {}
            }
    
    async def _self_learn(self, content: str, context: FilterContext, learn_type: str):
        """自学习功能"""
        if not self.enable_self_learning:
            return
        
        try:
            # 提取向量（如果还没有的话）
            content_vector = self.semantic_extractor.extract_vector(content)
            
            if content_vector:
                # 添加到向量库
                success = self.vector_manager.add_vector(
                    vector=content_vector,
                    content=content,
                    source=f"self_learning_{learn_type}",
                    metadata={
                        'learn_type': learn_type,
                        'channel_id': context.channel_id,
                        'message_id': context.message_id
                    }
                )
                
                if success:
                    self.detection_stats['self_learning_count'] += 1
                    logger.info(f"自学习成功: {learn_type} - {content[:50]}...")
                else:
                    logger.debug(f"自学习跳过（重复向量）: {content[:50]}...")
            
        except Exception as e:
            logger.error(f"自学习失败: {e}")
    
    def _update_avg_similarity(self, similarity: float):
        """更新平均相似度统计"""
        current_avg = self.detection_stats['avg_similarity']
        total_processed = self.detection_stats['total_processed']
        
        # 增量计算平均值
        self.detection_stats['avg_similarity'] = (
            (current_avg * (total_processed - 1) + similarity) / total_processed
        )
    
    def manual_learn_ad(self, content: str, context: Optional[FilterContext] = None) -> bool:
        """手动标记广告样本进行学习"""
        try:
            if not context:
                context = FilterContext(message_id="manual", channel_id="manual")
            
            # 同步调用自学习
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已在事件循环中，创建任务
                asyncio.create_task(self._self_learn(content, context, 'manual_ad'))
            else:
                # 如果不在事件循环中，直接运行
                loop.run_until_complete(self._self_learn(content, context, 'manual_ad'))
            
            return True
            
        except Exception as e:
            logger.error(f"手动学习失败: {e}")
            return False
    
    def get_detection_stats(self) -> Dict[str, Any]:
        """获取检测统计信息"""
        vector_stats = self.vector_manager.get_stats()
        
        return {
            'detector_stats': self.detection_stats.copy(),
            'vector_manager_stats': vector_stats,
            'semantic_extractor_info': self.semantic_extractor.get_model_info(),
            'config': {
                'similarity_threshold': self.similarity_threshold,
                'enable_self_learning': self.enable_self_learning,
                'auto_reject_ads': self.auto_reject_ads,
                'enable_fallback': self.enable_fallback
            }
        }
    
    def cleanup_vectors(self) -> int:
        """清理重复向量"""
        return self.vector_manager.cleanup_duplicates()


# 全局推广内容向量检测器实例
_promo_vector_detector = None

def get_promo_vector_detector() -> PromoVectorDetector:
    """获取推广内容向量检测器实例（单例）"""
    global _promo_vector_detector
    if _promo_vector_detector is None:
        _promo_vector_detector = PromoVectorDetector()
    return _promo_vector_detector