"""
语义广告检测器 - Linus式简洁设计
基于ONNX语义向量的广告内容检测方案

Author: Claude
Created: 2025-08-31
Updated: 2025-09-06 (重命名，明确ONNX语义检测职责)
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple
import asyncio

from app.services.filters.base import BaseFilter, FilterContext, FilterResult
from app.services.vector_manager import vector_manager
from app.services.semantic_extractor import get_semantic_extractor

logger = logging.getLogger(__name__)


class SemanticAdDetector(BaseFilter):
    """语义广告检测器 - 基于ONNX语义理解的广告检测"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("semantic_ad_detector", config)
        
        # 核心组件
        self.vector_manager = vector_manager
        self.semantic_extractor = get_semantic_extractor(768)
        
        # 配置参数 - 调整为更合理的阈值
        self.similarity_threshold = self.config.get('similarity_threshold', 0.6)
        self.enable_self_learning = self.config.get('enable_self_learning', True)
        self.auto_reject_ads = self.config.get('auto_reject_ads', True)
        
        # Linus式简化：删除降级策略
        
        # 统计信息
        self.detection_stats = {
            'total_processed': 0,
            'vector_detections': 0,
            'self_learning_count': 0,
            'avg_similarity': 0.0
        }
        
        logger.info(f"向量广告检测器初始化 - 阈值: {self.similarity_threshold}, 自学习: {self.enable_self_learning}")
    
    # Linus式简化：删除降级引擎初始化方法
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """ONNX语义广告检测主方法 - 支持双轨检测"""
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
            
            # 🚀 双轨检测：获取原始内容和过滤内容
            original_content = context.get_metadata('original_content', content)
            filtered_content = context.get_metadata('filtered_content', content)
            content_changed = context.get_metadata('content_changed', False)
            
            logger.debug(f"🔄 双轨检测 - 内容变化: {content_changed}")
            
            # === 第一步：双轨向量检测 ===
            vector_result = await self._dual_track_detection(original_content, filtered_content, content_changed, context)
            
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
                    # 技术错误 - fail-fast原则，直接通过并记录错误
                    logger.error(f"向量检测技术故障: {error_message}")
                    result.reason = "向量检测失败，默认通过"
                    result.confidence = 0.0
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
    
    async def _dual_track_detection(self, original_content: str, filtered_content: str, content_changed: bool, context: FilterContext) -> Dict[str, Any]:
        """双轨检测：同时检测原始内容和过滤内容"""
        try:
            if not content_changed:
                # 内容没有变化，直接单轨检测
                return await self._vector_detection(original_content, context)
            
            # 内容有变化，进行双轨检测
            logger.debug(f"🔄 执行双轨检测 - 原始: {len(original_content)}, 过滤: {len(filtered_content)}")
            
            # 检测原始内容
            original_result = await self._vector_detection(original_content, context)
            # 检测过滤内容  
            filtered_result = await self._vector_detection(filtered_content, context)
            
            # 智能组合判断
            if original_result['success'] and filtered_result['success']:
                original_is_ad = original_result['is_ad']
                original_similarity = original_result['similarity']
                filtered_is_ad = filtered_result['is_ad'] 
                filtered_similarity = filtered_result['similarity']
                
                # Linus式判断逻辑
                if original_is_ad and not filtered_is_ad:
                    # 原始内容是广告，过滤后变干净 → 典型推广内容型广告
                    return {
                        'success': True,
                        'is_ad': True,
                        'similarity': original_similarity,
                        'detection_type': 'dual_track_promotion',
                        'details': {
                            'original_similarity': original_similarity,
                            'filtered_similarity': filtered_similarity,
                            'reason': '原始内容包含推广信息，过滤后变正常（推广型广告）'
                        }
                    }
                elif original_is_ad and filtered_is_ad:
                    # 原始和过滤都是广告 → 纯广告内容
                    max_similarity = max(original_similarity, filtered_similarity)
                    return {
                        'success': True,
                        'is_ad': True,
                        'similarity': max_similarity,
                        'detection_type': 'dual_track_pure_ad',
                        'details': {
                            'original_similarity': original_similarity,
                            'filtered_similarity': filtered_similarity,
                            'reason': '原始和过滤内容都是广告（纯广告）'
                        }
                    }
                elif not original_is_ad and filtered_is_ad:
                    # 原始正常，过滤后变广告 → 异常情况，以原始为准
                    return {
                        'success': True,
                        'is_ad': False,
                        'similarity': original_similarity,
                        'detection_type': 'dual_track_anomaly',
                        'details': {
                            'original_similarity': original_similarity,
                            'filtered_similarity': filtered_similarity,
                            'reason': '原始内容正常，过滤异常导致误判'
                        }
                    }
                else:
                    # 原始和过滤都正常 → 正常内容
                    return {
                        'success': True,
                        'is_ad': False,
                        'similarity': max(original_similarity, filtered_similarity),
                        'detection_type': 'dual_track_normal',
                        'details': {
                            'original_similarity': original_similarity,
                            'filtered_similarity': filtered_similarity,
                            'reason': '双轨检测均为正常内容'
                        }
                    }
            elif original_result['success']:
                # 只有原始内容检测成功，使用原始结果
                original_result['detection_type'] = 'original_only'
                return original_result
            elif filtered_result['success']:
                # 只有过滤内容检测成功，使用过滤结果
                filtered_result['detection_type'] = 'filtered_only'
                return filtered_result
            else:
                # 都失败了，返回原始错误
                return original_result
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': 'dual_track_error',
                'details': {'error': 'dual_track_detection_failed'}
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
                'auto_reject_ads': self.auto_reject_ads
            }
        }
    
    def cleanup_vectors(self) -> int:
        """清理重复向量"""
        return self.vector_manager.cleanup_duplicates()


# 全局语义广告检测器实例
_semantic_ad_detector = None

def get_semantic_ad_detector() -> SemanticAdDetector:
    """获取语义广告检测器实例（单例）"""
    global _semantic_ad_detector
    if _semantic_ad_detector is None:
        _semantic_ad_detector = SemanticAdDetector()
    return _semantic_ad_detector