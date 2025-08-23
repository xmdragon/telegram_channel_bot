"""
尾部过滤器 - 整合智能和语义尾部过滤逻辑

整合 intelligent_tail_filter.py 和 semantic_tail_filter.py 的功能，
提供统一的尾部过滤接口，优先使用intelligent_tail_filter，
失败时降级到semantic_tail_filter。

Author: Claude
Created: 2025-08-15
"""

import time
import logging
from typing import Dict, Any, Optional, Tuple
import asyncio

from app.services.filters.base import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)

# 尝试导入智能尾部过滤器，如果失败则标记为不可用
try:
    from app.services.intelligent_tail_filter import intelligent_tail_filter
    INTELLIGENT_FILTER_AVAILABLE = True
    logger.info("✅ 智能尾部过滤器加载成功")
except Exception as e:
    intelligent_tail_filter = None
    INTELLIGENT_FILTER_AVAILABLE = False
    logger.warning(f"⚠️ 智能尾部过滤器不可用: {e}")

# 语义尾部过滤器（作为降级选项）
try:
    from app.services.semantic_tail_filter import semantic_tail_filter
    SEMANTIC_FILTER_AVAILABLE = True
    logger.info("✅ 语义尾部过滤器加载成功")
except Exception as e:
    semantic_tail_filter = None
    SEMANTIC_FILTER_AVAILABLE = False
    logger.error(f"❌ 语义尾部过滤器不可用: {e}")


class TailFilter(BaseFilter):
    """尾部过滤器
    
    整合智能尾部过滤和语义尾部过滤逻辑，提供统一接口：
    1. 优先使用intelligent_tail_filter（AI语义分析）
    2. 失败时降级到semantic_tail_filter（规则语义分析）
    3. 详细记录过滤过程和结果
    4. 不进行Early Stop，继续后续过滤器
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化尾部过滤器
        
        Args:
            config: 配置参数，支持：
                - intelligent_threshold: 智能过滤置信度阈值 (默认0.6)
                - semantic_threshold: 语义过滤阈值 (默认0.5) 
                - enabled: 是否启用 (默认True)
                - enable_intelligent: 是否启用智能过滤 (默认True)
                - enable_semantic: 是否启用语义过滤降级 (默认True)
        """
        super().__init__("tail_filter", config)
        
        # 配置参数 - 使用动态阈值
        self.intelligent_threshold = self.get_threshold('intelligent', 0.6)
        self.semantic_threshold = self.get_threshold('semantic', 0.5)
        self.enable_intelligent = self.config.get('enable_intelligent', True) and INTELLIGENT_FILTER_AVAILABLE
        self.enable_semantic = self.config.get('enable_semantic', True) and SEMANTIC_FILTER_AVAILABLE
        
        # 统计信息
        self._intelligent_success = 0
        self._intelligent_failures = 0
        self._semantic_fallback = 0
        self._filtered_count = 0
        
        # 检查可用的过滤方法
        available_methods = []
        if self.enable_intelligent:
            available_methods.append("智能过滤")
        if self.enable_semantic:
            available_methods.append("语义过滤")
        
        if not available_methods:
            logger.error("❌ 没有可用的尾部过滤方法")
        
        logger.info(f"✅ 尾部过滤器初始化完成 - 可用方法: {', '.join(available_methods)}")
        logger.info(f"   智能阈值: {self.intelligent_threshold}, 语义阈值: {self.semantic_threshold}")
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """过滤前预检查 - Linus式简化：消除特殊情况，让过滤器自然处理所有输入"""
        # 移除所有预检查限制，让过滤器内部逻辑自行判断
        # 空内容、短内容、少行数内容都应该被处理，而不是预先跳过
        return True
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """执行尾部过滤
        
        Args:
            content: 要过滤的内容
            context: 过滤器上下文
            
        Returns:
            FilterResult: 过滤结果
        """
        start_time = time.time()
        
        logger.info(f"🔍 开始尾部过滤 - 内容长度: {len(content)} 字符")
        logger.debug(f"内容预览: {content[:200]}{'...' if len(content) > 200 else ''}")
        
        # 检查是否有可用的过滤方法
        if not (self.enable_intelligent or self.enable_semantic):
            logger.debug("没有可用的过滤方法，跳过尾部过滤")
            processing_time = (time.time() - start_time) * 1000
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=processing_time,
                reason="无可用过滤方法",
                confidence=0.0,
                should_early_stop=False,
                details={'no_methods_available': True}
            )
        
        # 构建上下文信息
        filter_context = {
            'channel_id': context.channel_id,
            'user_id': context.user_id,
            'message_type': context.message_type,
        }
        
        # 检查是否有媒体
        has_media = context.message_type in ['photo', 'video', 'document']
        
        filtered_content = content
        removed_tail = ""
        analysis_details = {}
        filter_method = "none"
        confidence = 0.0
        
        try:
            # 方法1：尝试智能尾部过滤
            if self.enable_intelligent:
                try:
                    logger.debug("尝试使用智能尾部过滤器...")
                    
                    # 调用智能过滤器
                    analysis = await intelligent_tail_filter.analyze_message(content, filter_context)
                    
                    # 获取当前阈值（支持动态更新）
                    current_intelligent_threshold = self.get_threshold('intelligent', self.intelligent_threshold)
                    predicted_score = analysis.get('confidence', 0.0)
                    
                    if (analysis.get('should_filter_tail', False) and 
                        predicted_score >= current_intelligent_threshold):
                        
                        filtered_content = analysis['main_content']
                        removed_tail = analysis['tail_content']
                        confidence = analysis['confidence']
                        filter_method = "intelligent"
                        
                        analysis_details = {
                            'method': 'intelligent',
                            'tail_boundary': analysis.get('tail_boundary', -1),
                            'tail_analysis': analysis.get('tail_analysis', {}),
                            'confidence': confidence,
                            'filter_reason': analysis.get('tail_analysis', {}).get('filter_reason', '')
                        }
                        
                        # 记录成功的反馈
                        self.record_threshold_feedback('intelligent', predicted_score, 'positive', current_intelligent_threshold)
                        
                        self._intelligent_success += 1
                        logger.info(f"✅ 智能尾部过滤成功 - 置信度: {confidence:.2f}, "
                                   f"移除长度: {len(removed_tail)}, 阈值: {current_intelligent_threshold:.2f}")
                        
                    else:
                        # 记录未过滤的反馈（如果有预测分数）
                        if predicted_score > 0:
                            self.record_threshold_feedback('intelligent', predicted_score, 'negative', current_intelligent_threshold)
                        
                        logger.debug(f"智能过滤器判定不需要过滤 - "
                                    f"should_filter: {analysis.get('should_filter_tail', False)}, "
                                    f"confidence: {predicted_score:.2f} < {current_intelligent_threshold:.2f}")
                        
                        analysis_details['intelligent_analysis'] = analysis
                        
                except Exception as e:
                    self._intelligent_failures += 1
                    logger.warning(f"⚠️ 智能尾部过滤失败: {e}")
                    analysis_details['intelligent_error'] = str(e)
            
            # 方法2：如果智能过滤未生效且启用语义过滤，尝试语义降级
            if (filter_method == "none" and self.enable_semantic and 
                removed_tail == ""):
                
                try:
                    logger.debug("降级到语义尾部过滤器...")
                    
                    # 调用语义过滤器
                    semantic_result = semantic_tail_filter.filter_message(content, has_media)
                    semantic_filtered, filtered, semantic_tail, semantic_analysis = semantic_result
                    
                    if filtered and semantic_tail:
                        # 语义过滤器找到了尾部
                        semantic_score = semantic_analysis.get('best_score', 0.0)
                        current_semantic_threshold = self.get_threshold('semantic', self.semantic_threshold)
                        
                        if semantic_score >= current_semantic_threshold:
                            filtered_content = semantic_filtered
                            removed_tail = semantic_tail
                            confidence = semantic_score
                            filter_method = "semantic"
                            
                            # 记录成功的反馈
                            self.record_threshold_feedback('semantic', semantic_score, 'positive', current_semantic_threshold)
                            
                            analysis_details.update({
                                'method': 'semantic',
                                'semantic_score': semantic_score,
                                'semantic_analysis': semantic_analysis,
                                'filter_reason': f'语义得分: {semantic_score:.2f} >= {current_semantic_threshold:.2f}'
                            })
                            
                            self._semantic_fallback += 1
                            logger.info(f"✅ 语义降级过滤成功 - 得分: {semantic_score:.2f}, "
                                       f"移除长度: {len(removed_tail)}, 阈值: {current_semantic_threshold:.2f}")
                        else:
                            # 记录未过滤的反馈
                            self.record_threshold_feedback('semantic', semantic_score, 'negative', current_semantic_threshold)
                            
                            logger.debug(f"语义过滤器得分不足 - {semantic_score:.2f} < {current_semantic_threshold:.2f}")
                            analysis_details['semantic_analysis'] = semantic_analysis
                    else:
                        logger.debug("语义过滤器判定不需要过滤")
                        analysis_details['semantic_analysis'] = semantic_analysis
                        
                except Exception as e:
                    logger.warning(f"⚠️ 语义尾部过滤降级失败: {e}")
                    analysis_details['semantic_error'] = str(e)
            
            # 计算处理时间
            processing_time = (time.time() - start_time) * 1000
            
            # 判断是否过滤了内容
            content_filtered = len(removed_tail) > 0
            
            if content_filtered:
                self._filtered_count += 1
                filter_ratio = len(removed_tail) / len(content)
                
                # 生成详细日志
                logger.info(f"🎯 尾部过滤完成 - 方法: {filter_method}")
                logger.info(f"   原始长度: {len(content)} -> 过滤后: {len(filtered_content)}")
                logger.info(f"   移除长度: {len(removed_tail)} ({filter_ratio:.1%})")
                logger.info(f"   置信度: {confidence:.3f}")
                logger.debug(f"   移除内容预览: {removed_tail[:100]}{'...' if len(removed_tail) > 100 else ''}")
            else:
                logger.debug(f"未检测到尾部内容，保留原文 - 处理时间: {processing_time:.1f}ms")
            
            # 构建过滤结果
            result = FilterResult(
                filtered_content=filtered_content,
                passed=True,  # 尾部过滤不阻止消息通过，只是修改内容
                processing_time_ms=processing_time,
                reason=f"尾部过滤({filter_method})" if content_filtered else "无需尾部过滤",
                confidence=confidence,
                should_early_stop=False,  # 尾部过滤不进行Early Stop
                details=analysis_details
            )
            
            # 如果过滤了内容，记录修改信息
            if content_filtered:
                result.modifications.append(f"移除尾部内容({len(removed_tail)}字符)")
                result.details['removed_tail'] = removed_tail
                result.details['removal_position'] = len(filtered_content)
                result.details['filter_method'] = filter_method
                result.details['original_length'] = len(content)
                result.details['filtered_length'] = len(filtered_content)
            
            return result
            
        except Exception as e:
            # 异常情况下返回原内容
            processing_time = (time.time() - start_time) * 1000
            logger.error(f"❌ 尾部过滤器异常: {e}")
            
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=processing_time,
                reason=f"尾部过滤异常: {str(e)}",
                confidence=0.0,
                should_early_stop=False,
                details={'error': str(e), 'exception_type': type(e).__name__}
            )
    
    async def post_filter(self, result: FilterResult, context: FilterContext) -> FilterResult:
        """过滤后处理"""
        # 调用基类统计更新
        result = await super().post_filter(result, context)
        
        # 更新自定义统计
        if result.details.get('filter_method') == 'intelligent':
            pass  # 已在filter中更新
        elif result.details.get('filter_method') == 'semantic':
            pass  # 已在filter中更新
            
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取过滤器统计信息"""
        base_stats = super().get_stats()
        
        # 添加自定义统计
        custom_stats = {
            'intelligent_success': self._intelligent_success,
            'intelligent_failures': self._intelligent_failures,
            'semantic_fallback': self._semantic_fallback,
            'filtered_count': self._filtered_count,
            'intelligent_success_rate': (
                self._intelligent_success / max(self._intelligent_success + self._intelligent_failures, 1)
            ),
            'fallback_rate': (
                self._semantic_fallback / max(self._stats['total_processed'], 1)
            )
        }
        
        base_stats.update(custom_stats)
        return base_stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        super().reset_stats()
        self._intelligent_success = 0
        self._intelligent_failures = 0
        self._semantic_fallback = 0
        self._filtered_count = 0
    
    async def validate_config(self) -> bool:
        """验证配置是否有效"""
        try:
            # 检查阈值范围
            if not (0.0 <= self.intelligent_threshold <= 1.0):
                logger.error(f"智能过滤阈值无效: {self.intelligent_threshold}")
                return False
            
            if not (0.0 <= self.semantic_threshold <= 1.0):
                logger.error(f"语义过滤阈值无效: {self.semantic_threshold}")
                return False
            
            # 检查是否至少有一种方法可用
            if not (self.enable_intelligent or self.enable_semantic):
                if not (INTELLIGENT_FILTER_AVAILABLE or SEMANTIC_FILTER_AVAILABLE):
                    logger.warning("没有可用的过滤器依赖，尾部过滤功能将被禁用")
                    return True  # 配置有效，但功能不可用
                else:
                    logger.error("必须至少启用一种过滤方法")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"配置验证异常: {e}")
            return False


# 创建默认实例（阈值将从阈值管理器动态获取）
tail_filter = TailFilter({
    'enable_intelligent': True,
    'enable_semantic': True
})