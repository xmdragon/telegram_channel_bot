"""
过滤器基础架构 - 抽象基类定义

Author: Claude
Created: 2025-08-15
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
import time
import logging
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class FilterContext:
    """过滤器上下文信息"""
    message_id: Optional[int] = None
    channel_id: Optional[int] = None 
    user_id: Optional[int] = None
    timestamp: float = field(default_factory=time.time)
    message_type: str = "text"  # text, photo, video, document, etc.
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_metadata(self, key: str, value: Any) -> None:
        """添加元数据"""
        self.metadata[key] = value
        
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)


@dataclass 
class FilterResult:
    """过滤器处理结果"""
    # 过滤后的内容
    filtered_content: str
    
    # 是否通过过滤（False表示被过滤掉）
    passed: bool = True
    
    # 过滤器处理时间(毫秒)
    processing_time_ms: float = 0.0
    
    # 过滤理由
    reason: Optional[str] = None
    
    # 置信度 (0.0-1.0)
    confidence: float = 0.0
    
    # 详细的判定依据
    details: Dict[str, Any] = field(default_factory=dict)
    
    # 是否应该早停（用于去重和广告检测）
    should_early_stop: bool = False
    
    # 修改的内容（如果有）
    modifications: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """管道完整结果"""
    # 最终过滤后的内容
    final_content: str
    
    # 是否通过整个管道
    passed: bool = True
    
    # 总处理时间(毫秒)
    total_processing_time_ms: float = 0.0
    
    # 各个过滤器的结果
    filter_results: Dict[str, FilterResult] = field(default_factory=dict)
    
    # 整体过滤理由
    overall_reason: Optional[str] = None
    
    # 早停的过滤器名称
    early_stopped_at: Optional[str] = None
    
    # 应用的过滤器列表
    applied_filters: List[str] = field(default_factory=list)


class BaseFilter(ABC):
    """过滤器抽象基类
    
    所有具体的过滤器都必须继承此类并实现filter方法
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """初始化过滤器
        
        Args:
            name: 过滤器名称
            config: 配置参数
        """
        self.name = name
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self._stats = {
            'total_processed': 0,
            'total_filtered': 0,
            'total_processing_time_ms': 0.0,
            'avg_processing_time_ms': 0.0
        }
        
        # 初始化阈值管理器
        self._threshold_manager = None
        self._initialize_threshold_manager()
        
    @abstractmethod
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """过滤器主要处理逻辑
        
        Args:
            content: 要过滤的内容
            context: 过滤器上下文
            
        Returns:
            FilterResult: 过滤结果
        """
        pass
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """过滤前预检查，用于快速跳过不需要处理的内容
        
        Args:
            content: 要过滤的内容
            context: 过滤器上下文
            
        Returns:
            bool: True表示需要继续处理，False表示跳过
        """
        return True
    
    async def post_filter(self, result: FilterResult, context: FilterContext) -> FilterResult:
        """过滤后处理，用于结果的后处理和统计更新
        
        Args:
            result: 过滤结果
            context: 过滤器上下文
            
        Returns:
            FilterResult: 处理后的结果
        """
        # 更新统计信息
        self._update_stats(result)
        return result
    
    async def process_with_timing(self, content: str, context: FilterContext) -> FilterResult:
        """带性能计时的过滤器处理方法
        
        Args:
            content: 要过滤的内容
            context: 过滤器上下文
            
        Returns:
            FilterResult: 过滤结果（包含处理时间）
        """
        # 如果过滤器被禁用，直接返回原内容
        if not self.enabled:
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0.0,
                reason=f"{self.name} disabled"
            )
        
        start_time = time.perf_counter()
        
        try:
            # 预检查
            should_process = await self.pre_filter(content, context)
            if not should_process:
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    processing_time_ms=(time.perf_counter() - start_time) * 1000,
                    reason=f"{self.name} pre-filter skipped"
                )
            
            # 执行实际的过滤逻辑
            result = await self.filter(content, context)
            
            # 设置处理时间
            processing_time = (time.perf_counter() - start_time) * 1000
            result.processing_time_ms = processing_time
            
            # 后处理
            result = await self.post_filter(result, context)
            
            # 记录性能日志（如果耗时过长）
            if processing_time > 500:  # 超过500ms记录警告
                logger.warning(f"过滤器 {self.name} 处理耗时 {processing_time:.1f}ms")
            
            return result
            
        except Exception as e:
            processing_time = (time.perf_counter() - start_time) * 1000
            logger.error(f"过滤器 {self.name} 处理失败: {e}")
            
            # 返回失败结果
            return FilterResult(
                filtered_content=content,
                passed=False,
                processing_time_ms=processing_time,
                reason=f"{self.name} error: {str(e)}"
            )
    
    def _update_stats(self, result: FilterResult) -> None:
        """更新统计信息"""
        self._stats['total_processed'] += 1
        if not result.passed:
            self._stats['total_filtered'] += 1
        
        self._stats['total_processing_time_ms'] += result.processing_time_ms
        self._stats['avg_processing_time_ms'] = (
            self._stats['total_processing_time_ms'] / self._stats['total_processed']
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取过滤器统计信息"""
        return {
            'name': self.name,
            'enabled': self.enabled,
            **self._stats,
            'filter_rate': (
                self._stats['total_filtered'] / max(self._stats['total_processed'], 1)
            )
        }
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            'total_processed': 0,
            'total_filtered': 0,
            'total_processing_time_ms': 0.0,
            'avg_processing_time_ms': 0.0
        }
    
    def is_enabled(self) -> bool:
        """检查过滤器是否启用"""
        return self.enabled
    
    def enable(self) -> None:
        """启用过滤器"""
        self.enabled = True
        
    def disable(self) -> None:
        """禁用过滤器"""
        self.enabled = False
    
    def update_config(self, config: Dict[str, Any]) -> None:
        """更新配置"""
        self.config.update(config)
        self.enabled = self.config.get('enabled', self.enabled)
    
    async def validate_config(self) -> bool:
        """验证配置是否有效"""
        return True
    
    def __str__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, enabled={self.enabled})>"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def _initialize_threshold_manager(self):
        """初始化阈值管理器"""
        try:
            from app.core.threshold_manager import threshold_manager
            self._threshold_manager = threshold_manager
        except ImportError as e:
            logger.warning(f"⚠️ 无法导入阈值管理器: {e}")
            self._threshold_manager = None
    
    def get_threshold(self, metric_name: str, default: float = 0.5) -> float:
        """
        获取动态阈值
        
        Args:
            metric_name: 指标名称
            default: 默认阈值
            
        Returns:
            float: 当前最优阈值
        """
        if self._threshold_manager:
            try:
                return self._threshold_manager.get_threshold(self.name, metric_name)
            except Exception as e:
                logger.debug(f"获取阈值失败: {e}")
        
        # Fallback到配置或默认值
        return self.config.get(f'{metric_name}_threshold', default)
    
    def record_threshold_feedback(self, metric_name: str, predicted_score: float, 
                                 actual_result: str, threshold_used: float = None):
        """
        记录阈值反馈
        
        Args:
            metric_name: 指标名称
            predicted_score: 预测分数
            actual_result: 实际结果 ('positive', 'negative')
            threshold_used: 使用的阈值
        """
        if self._threshold_manager:
            try:
                self._threshold_manager.record_feedback(
                    self.name, metric_name, predicted_score, 
                    actual_result, threshold_used
                )
            except Exception as e:
                logger.debug(f"记录阈值反馈失败: {e}")
    
    def get_threshold_config(self, metric_name: str) -> Dict:
        """获取阈值配置信息"""
        if self._threshold_manager:
            try:
                return self._threshold_manager.get_threshold_config(self.name, metric_name)
            except Exception as e:
                logger.debug(f"获取阈值配置失败: {e}")
        
        return {}


class FilterException(Exception):
    """过滤器异常基类"""
    
    def __init__(self, filter_name: str, message: str, original_error: Optional[Exception] = None):
        self.filter_name = filter_name
        self.original_error = original_error
        super().__init__(f"Filter '{filter_name}': {message}")


class FilterConfigError(FilterException):
    """过滤器配置错误"""
    pass


class FilterProcessingError(FilterException):
    """过滤器处理错误"""
    pass