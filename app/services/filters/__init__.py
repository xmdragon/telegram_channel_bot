"""
过滤器基础架构模块

统一的过滤器接口和管道系统，支持：
- 抽象基类BaseFilter定义统一接口
- FilterPipeline主管道协调器
- Early Stopping机制
- 详细的日志记录和统计
- 容错和性能监控

Author: Claude
Created: 2025-08-15
"""

from .base import (
    BaseFilter,
    FilterContext,
    FilterResult,
    PipelineResult,
    FilterException,
    FilterConfigError,
    FilterProcessingError
)

from .filter_pipeline import (
    FilterPipeline,
    PipelineConfig
)

# 导入具体的过滤器实现
from .duplicate_detector import DuplicateDetectorFilter, duplicate_detector_filter
from .ad_detector import AdDetectorFilter, ad_detector_filter
from .tail_filter import TailFilter, tail_filter

__all__ = [
    # 基础类和数据结构
    'BaseFilter',
    'FilterContext',
    'FilterResult',
    'PipelineResult',
    
    # 管道系统
    'FilterPipeline',
    'PipelineConfig',
    
    # 具体过滤器类
    'DuplicateDetectorFilter',
    'AdDetectorFilter',
    'TailFilter',
    
    # 预配置的过滤器实例
    'duplicate_detector_filter',
    'ad_detector_filter',
    'tail_filter',
    
    # 异常类
    'FilterException',
    'FilterConfigError',
    'FilterProcessingError',
    
    # 便利函数
    'create_pipeline',
    'create_early_stop_pipeline',
    'create_default_filters',
    'get_filter_info'
]

# 版本信息
__version__ = '1.0.0'

# 模块信息
__author__ = 'Claude'
__description__ = '过滤器基础架构 - 统一的过滤器接口和管道系统'

# 默认配置
DEFAULT_PIPELINE_CONFIG = {
    'enable_early_stopping': True,
    'early_stop_filters': {'duplicate_detector', 'ad_detector'},
    'max_concurrent_filters': 1,
    'filter_timeout': 30.0,
    'pipeline_timeout': 60.0,
    'enable_detailed_stats': True,
    'stats_window_size': 1000
}

# 支持的过滤器类型
SUPPORTED_FILTER_TYPES = {
    'duplicate_detector': '去重检测器',
    'ad_detector': '广告检测器', 
    'content_filter': '内容过滤器',
    'semantic_filter': '语义过滤器',
    'tail_filter': '尾部过滤器'
}

# 早停支持的过滤器
EARLY_STOP_CAPABLE_FILTERS = {
    'duplicate_detector', 
    'ad_detector'
}


def create_default_filters() -> dict:
    """创建默认的过滤器实例集合
    
    Returns:
        dict: 过滤器名称到实例的映射
    """
    return {
        'duplicate_detector': duplicate_detector_filter,
        'ad_detector': ad_detector_filter,
        'tail_filter': tail_filter
    }


def create_early_stop_pipeline() -> FilterPipeline:
    """创建支持早停的标准管道
    
    Returns:
        FilterPipeline: 配置好的管道，包含去重和广告检测器
    """
    pipeline = create_pipeline()
    
    # 添加早停过滤器（按优先级顺序：先去重，后广告检测）
    pipeline.add_filter(duplicate_detector_filter)
    pipeline.add_filter(ad_detector_filter)
    
    return pipeline


def create_pipeline(config: dict = None) -> FilterPipeline:
    """创建标准的过滤器管道
    
    Args:
        config: 管道配置，使用DEFAULT_PIPELINE_CONFIG作为默认值
        
    Returns:
        FilterPipeline: 配置好的管道实例
    """
    if config is None:
        config = DEFAULT_PIPELINE_CONFIG.copy()
    else:
        # 合并默认配置
        merged_config = DEFAULT_PIPELINE_CONFIG.copy()
        merged_config.update(config)
        config = merged_config
    
    pipeline_config = PipelineConfig(
        enable_early_stopping=config.get('enable_early_stopping', True),
        early_stop_filters=set(config.get('early_stop_filters', ['duplicate_detector', 'ad_detector'])),
        max_concurrent_filters=config.get('max_concurrent_filters', 1),
        filter_timeout=config.get('filter_timeout', 30.0),
        pipeline_timeout=config.get('pipeline_timeout', 60.0),
        enable_detailed_stats=config.get('enable_detailed_stats', True),
        stats_window_size=config.get('stats_window_size', 1000)
    )
    
    return FilterPipeline(pipeline_config)


def get_filter_info() -> dict:
    """获取过滤器模块信息
    
    Returns:
        dict: 模块信息
    """
    return {
        'version': __version__,
        'author': __author__,
        'description': __description__,
        'supported_filter_types': SUPPORTED_FILTER_TYPES,
        'early_stop_capable_filters': EARLY_STOP_CAPABLE_FILTERS,
        'default_config': DEFAULT_PIPELINE_CONFIG
    }


# 导入时的初始化日志
import logging
logger = logging.getLogger(__name__)
logger.info(f"过滤器基础架构模块已加载 - version: {__version__}")