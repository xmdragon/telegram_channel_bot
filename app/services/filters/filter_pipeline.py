"""
过滤器管道 - 主协调器

支持5个过滤器的串行执行，Early Stopping机制，完整的日志记录和统计

Author: Claude
Created: 2025-08-15
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

from .base import BaseFilter, FilterContext, FilterResult, PipelineResult, FilterException

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """管道配置"""
    # 启用早停机制
    enable_early_stopping: bool = True
    
    # 可以触发早停的过滤器类型
    early_stop_filters: Set[str] = field(default_factory=lambda: {
        'ad_detector'
    })
    
    # 并发处理限制
    max_concurrent_filters: int = 1  # 当前版本支持串行执行
    
    # 超时设置(秒)
    filter_timeout: float = 30.0
    pipeline_timeout: float = 60.0
    
    # 统计配置
    enable_detailed_stats: bool = True
    stats_window_size: int = 1000  # 统计窗口大小


class FilterPipeline:
    """过滤器管道协调器
    
    负责协调多个过滤器的执行，支持：
    - 串行执行5个过滤器
    - Early Stopping机制
    - 详细的日志记录
    - 性能统计
    - 错误处理和恢复
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """初始化管道
        
        Args:
            config: 管道配置
        """
        self.config = config or PipelineConfig()
        self.filters: List = []  # 支持BaseFilter和独立过滤器类
        self.filter_map: Dict[str, Any] = {}
        
        # 统计信息
        self._pipeline_stats = {
            'total_processed': 0,
            'total_passed': 0,
            'total_filtered': 0,
            'early_stopped': 0,
            'errors': 0,
            'avg_processing_time_ms': 0.0,
            'total_processing_time_ms': 0.0
        }
        
        # 性能监控
        self._recent_results = []
    
    def _get_filter_name(self, filter_instance) -> str:
        """获取过滤器名称 - 兼容独立类和BaseFilter类
        
        Args:
            filter_instance: 过滤器实例
            
        Returns:
            str: 过滤器名称（优先使用name属性，否则使用类名）
        """
        return getattr(filter_instance, 'name', filter_instance.__class__.__name__)
        
    def add_filter(self, filter_instance) -> None:
        """添加过滤器到管道
        
        Args:
            filter_instance: 过滤器实例
        """
        filter_name = self._get_filter_name(filter_instance)
        
        if filter_name in self.filter_map:
            logger.warning(f"过滤器 {filter_name} 已存在，将被替换")
            
        self.filters.append(filter_instance)
        self.filter_map[filter_name] = filter_instance
        
        logger.info(f"添加过滤器: {filter_name} (总数: {len(self.filters)})")
    
    def remove_filter(self, filter_name: str) -> bool:
        """从管道中移除过滤器
        
        Args:
            filter_name: 过滤器名称
            
        Returns:
            bool: 是否成功移除
        """
        if filter_name not in self.filter_map:
            return False
            
        # 从列表中移除
        self.filters = [f for f in self.filters if self._get_filter_name(f) != filter_name]
        del self.filter_map[filter_name]
        
        logger.info(f"移除过滤器: {filter_name} (剩余: {len(self.filters)})")
        return True
    
    def get_filter(self, filter_name: str) -> Optional[Any]:
        """获取指定的过滤器
        
        Args:
            filter_name: 过滤器名称
            
        Returns:
            Any: 过滤器实例（BaseFilter或独立过滤器类），不存在时返回None
        """
        return self.filter_map.get(filter_name)
    
    def list_filters(self) -> List[str]:
        """获取所有过滤器名称列表"""
        return [self._get_filter_name(f) for f in self.filters]
    
    async def process(self, content: str, context: FilterContext) -> PipelineResult:
        """处理内容通过整个过滤器管道（带详细性能计时）
        
        Args:
            content: 要处理的内容
            context: 过滤器上下文
            
        Returns:
            PipelineResult: 管道处理结果
        """
        start_time = time.perf_counter()
        pipeline_result = PipelineResult(final_content=content)
        
        try:
            logger.info(f"开始管道处理: message_id={context.message_id}, "
                       f"filters={len(self.filters)}, content_length={len(content)}")
            
            current_content = content
            
            # 逐个执行过滤器（带详细计时）
            for i, filter_instance in enumerate(self.filters):
                if not getattr(filter_instance, 'is_enabled', lambda: True)():
                    logger.debug(f"跳过已禁用的过滤器: {self._get_filter_name(filter_instance)}")
                    continue
                
                filter_start = time.perf_counter()
                
                try:
                    # 使用带计时的过滤器执行方法
                    filter_result = await filter_instance.process_with_timing(
                        current_content, context
                    )
                    
                    # 记录过滤器结果
                    filter_name = self._get_filter_name(filter_instance)
                    pipeline_result.filter_results[filter_name] = filter_result
                    pipeline_result.applied_filters.append(filter_name)
                    
                    # 更新当前内容
                    current_content = filter_result.filtered_content
                    
                    # 检查是否通过
                    if not filter_result.passed:
                        pipeline_result.passed = False
                        pipeline_result.overall_reason = filter_result.reason
                        
                        logger.info(f"内容被过滤器拦截: {self._get_filter_name(filter_instance)}, "
                                   f"reason={filter_result.reason}, "
                                   f"confidence={filter_result.confidence}")
                    
                    # 检查早停条件
                    if (self.config.enable_early_stopping and 
                        filter_result.should_early_stop and
                        self._get_filter_name(filter_instance) in self.config.early_stop_filters):
                        
                        pipeline_result.early_stopped_at = self._get_filter_name(filter_instance)
                        self._pipeline_stats['early_stopped'] += 1
                        
                        logger.info(f"管道早停: {self._get_filter_name(filter_instance)}, "
                                   f"reason={filter_result.reason}")
                        break
                        
                except Exception as e:
                    error_msg = f"过滤器执行失败: {self._get_filter_name(filter_instance)}, error={str(e)}"
                    logger.error(error_msg, exc_info=True)
                    
                    # 记录错误结果
                    error_result = FilterResult(
                        filtered_content=current_content,
                        passed=True,  # 错误时默认通过
                        reason=f"过滤器错误: {str(e)}",
                        confidence=0.0,
                        details={'error': str(e), 'error_type': type(e).__name__}
                    )
                    filter_name = self._get_filter_name(filter_instance)
                    pipeline_result.filter_results[filter_name] = error_result
                    pipeline_result.applied_filters.append(filter_name)
                    
                    self._pipeline_stats['errors'] += 1
                    
                    # 继续执行下一个过滤器（容错机制）
                    continue
            
            # 设置最终结果
            pipeline_result.final_content = current_content
            
        except Exception as e:
            logger.error(f"管道执行异常: {str(e)}", exc_info=True)
            pipeline_result.passed = False
            pipeline_result.overall_reason = f"管道执行异常: {str(e)}"
            self._pipeline_stats['errors'] += 1
        
        finally:
            # 计算总处理时间
            total_time_ms = (time.time() - start_time) * 1000
            pipeline_result.total_processing_time_ms = total_time_ms
            
            # 更新统计
            self._update_pipeline_stats(pipeline_result, total_time_ms)
            
            logger.info(f"管道处理完成: passed={pipeline_result.passed}, "
                       f"time={total_time_ms:.2f}ms, "
                       f"filters_applied={len(pipeline_result.applied_filters)}, "
                       f"early_stopped={pipeline_result.early_stopped_at is not None}")
        
        return pipeline_result
    
    async def _execute_single_filter(self, filter_instance: BaseFilter, 
                                   content: str, context: FilterContext) -> FilterResult:
        """执行单个过滤器
        
        Args:
            filter_instance: 过滤器实例
            content: 内容
            context: 上下文
            
        Returns:
            FilterResult: 过滤结果
        """
        filter_start_time = time.time()
        
        try:
            # 预检查
            if not await filter_instance.pre_filter(content, context):
                logger.debug(f"过滤器预检查跳过: {self._get_filter_name(filter_instance)}")
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    reason="预检查跳过",
                    processing_time_ms=0.0
                )
            
            # 执行过滤器（带超时）
            filter_result = await asyncio.wait_for(
                filter_instance.filter(content, context),
                timeout=self.config.filter_timeout
            )
            
            # 计算处理时间
            processing_time_ms = (time.time() - filter_start_time) * 1000
            filter_result.processing_time_ms = processing_time_ms
            
            # 后处理
            filter_result = await filter_instance.post_filter(filter_result, context)
            
            logger.debug(f"过滤器执行完成: {self._get_filter_name(filter_instance)}, "
                        f"passed={filter_result.passed}, "
                        f"time={processing_time_ms:.2f}ms, "
                        f"confidence={filter_result.confidence}")
            
            return filter_result
            
        except asyncio.TimeoutError:
            filter_name = self._get_filter_name(filter_instance)
            error_msg = f"过滤器超时: {filter_name}"
            logger.error(error_msg)
            raise FilterException(filter_name, "执行超时")
            
        except Exception as e:
            processing_time_ms = (time.time() - filter_start_time) * 1000
            logger.error(f"过滤器执行异常: {self._get_filter_name(filter_instance)}, "
                        f"error={str(e)}, time={processing_time_ms:.2f}ms", 
                        exc_info=True)
            raise
    
    def _update_pipeline_stats(self, result: PipelineResult, processing_time_ms: float) -> None:
        """更新管道统计信息"""
        self._pipeline_stats['total_processed'] += 1
        
        if result.passed:
            self._pipeline_stats['total_passed'] += 1
        else:
            self._pipeline_stats['total_filtered'] += 1
        
        self._pipeline_stats['total_processing_time_ms'] += processing_time_ms
        self._pipeline_stats['avg_processing_time_ms'] = (
            self._pipeline_stats['total_processing_time_ms'] / 
            self._pipeline_stats['total_processed']
        )
        
        # 保存最近的结果用于性能分析
        if self.config.enable_detailed_stats:
            self._recent_results.append({
                'timestamp': time.time(),
                'passed': result.passed,
                'processing_time_ms': processing_time_ms,
                'filters_applied': len(result.applied_filters),
                'early_stopped': result.early_stopped_at is not None
            })
            
            # 限制窗口大小
            if len(self._recent_results) > self.config.stats_window_size:
                self._recent_results.pop(0)
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """获取管道统计信息"""
        stats = {
            'pipeline': dict(self._pipeline_stats),
            'filters': {}
        }
        
        # 添加各个过滤器的统计
        for filter_instance in self.filters:
            filter_name = self._get_filter_name(filter_instance)
            stats['filters'][filter_name] = getattr(filter_instance, 'get_stats', lambda: {})()
        
        # 计算额外的统计指标
        total = self._pipeline_stats['total_processed']
        if total > 0:
            stats['pipeline'].update({
                'pass_rate': self._pipeline_stats['total_passed'] / total,
                'filter_rate': self._pipeline_stats['total_filtered'] / total,
                'early_stop_rate': self._pipeline_stats['early_stopped'] / total,
                'error_rate': self._pipeline_stats['errors'] / total
            })
        
        return stats
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if not self._recent_results:
            return {}
        
        processing_times = [r['processing_time_ms'] for r in self._recent_results]
        
        return {
            'window_size': len(self._recent_results),
            'avg_processing_time_ms': sum(processing_times) / len(processing_times),
            'min_processing_time_ms': min(processing_times),
            'max_processing_time_ms': max(processing_times),
            'recent_pass_rate': sum(1 for r in self._recent_results if r['passed']) / len(self._recent_results),
            'recent_early_stop_rate': sum(1 for r in self._recent_results if r['early_stopped']) / len(self._recent_results)
        }
    
    def reset_stats(self) -> None:
        """重置所有统计信息"""
        self._pipeline_stats = {
            'total_processed': 0,
            'total_passed': 0,
            'total_filtered': 0,
            'early_stopped': 0,
            'errors': 0,
            'avg_processing_time_ms': 0.0,
            'total_processing_time_ms': 0.0
        }
        self._recent_results.clear()
        
        # 重置各个过滤器的统计
        for filter_instance in self.filters:
            filter_instance.reset_stats()
        
        logger.info("管道统计信息已重置")
    
    def get_filter_chain_info(self) -> Dict[str, Any]:
        """获取过滤器链信息"""
        return {
            'total_filters': len(self.filters),
            'enabled_filters': len([f for f in self.filters if getattr(f, 'is_enabled', lambda: True)()]),
            'filter_chain': [
                {
                    'name': self._get_filter_name(f),
                    'enabled': getattr(f, 'is_enabled', lambda: True)(),
                    'type': f.__class__.__name__
                }
                for f in self.filters
            ],
            'early_stop_filters': list(self.config.early_stop_filters),
            'config': {
                'enable_early_stopping': self.config.enable_early_stopping,
                'filter_timeout': self.config.filter_timeout,
                'pipeline_timeout': self.config.pipeline_timeout
            }
        }
    
    async def validate_pipeline(self) -> Dict[str, Any]:
        """验证管道配置和状态"""
        results = {
            'valid': True,
            'warnings': [],
            'errors': [],
            'filter_validations': {}
        }
        
        # 检查过滤器数量
        if len(self.filters) == 0:
            results['warnings'].append("管道中没有过滤器")
        elif len(self.filters) > 5:
            results['warnings'].append(f"过滤器数量超过推荐的5个: {len(self.filters)}")
        
        # 验证各个过滤器
        for filter_instance in self.filters:
            try:
                validate_method = getattr(filter_instance, 'validate_config', None)
                if validate_method:
                    filter_valid = await validate_method()
                else:
                    filter_valid = True  # 独立过滤器默认配置有效
                filter_name = self._get_filter_name(filter_instance)
                results['filter_validations'][filter_name] = {
                    'valid': filter_valid,
                    'enabled': getattr(filter_instance, 'is_enabled', lambda: True)()
                }
                if not filter_valid:
                    results['errors'].append(f"过滤器配置无效: {filter_name}")
                    results['valid'] = False
            except Exception as e:
                results['errors'].append(f"过滤器验证失败: {self._get_filter_name(filter_instance)}, error={str(e)}")
                results['valid'] = False
        
        return results
    
    def __str__(self) -> str:
        enabled_count = len([f for f in self.filters if getattr(f, 'is_enabled', lambda: True)()])
        return f"<FilterPipeline(filters={len(self.filters)}, enabled={enabled_count})>"
    
    def __repr__(self) -> str:
        return self.__str__()