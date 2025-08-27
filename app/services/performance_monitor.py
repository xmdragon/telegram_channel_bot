"""
性能监控模块
为消息采集系统提供详细的性能分析和计时功能
"""
import time
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager, contextmanager
from functools import wraps
from logging.handlers import TimedRotatingFileHandler

from app.core.path_config import PathConfig


class PerformanceTimer:
    """高精度计时器"""
    
    def __init__(self, name: str = "unnamed"):
        self.name = name
        self.start_time = None
        self.end_time = None
        self.children: Dict[str, 'PerformanceTimer'] = {}
        self.metrics: Dict[str, Any] = {}
    
    def start(self):
        """开始计时"""
        self.start_time = time.perf_counter()
        return self
    
    def stop(self):
        """停止计时"""
        if self.start_time is None:
            return 0
        self.end_time = time.perf_counter()
        return self.get_duration_ms()
    
    def get_duration_ms(self) -> float:
        """获取耗时（毫秒）"""
        if self.start_time is None:
            return 0
        end = self.end_time or time.perf_counter()
        return (end - self.start_time) * 1000
    
    def add_child(self, name: str) -> 'PerformanceTimer':
        """添加子计时器"""
        child = PerformanceTimer(name)
        self.children[name] = child
        return child
    
    def set_metric(self, key: str, value: Any):
        """设置性能指标"""
        self.metrics[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            'name': self.name,
            'time_ms': round(self.get_duration_ms(), 2),
            'metrics': self.metrics
        }
        
        if self.children:
            result['children'] = {name: timer.to_dict() for name, timer in self.children.items()}
            
        return result


class PerformanceLogger:
    """性能日志记录器"""
    
    def __init__(self):
        self.logger = None
        self._setup_logger()
    
    def _setup_logger(self):
        """设置性能日志记录器"""
        # 确保日志目录存在
        PathConfig.LOGS_DIR.mkdir(exist_ok=True)
        
        # 创建性能专用日志记录器
        self.logger = logging.getLogger('performance')
        self.logger.setLevel(logging.INFO)
        
        # 清除现有的处理器
        self.logger.handlers.clear()
        
        # 创建按小时轮转的文件处理器
        file_handler = TimedRotatingFileHandler(
            filename=str(PathConfig.LOGS_DIR / "performance.log"),
            when='H',
            interval=1,
            backupCount=24,
            encoding='utf-8'
        )
        
        # 设置格式化器（JSON格式）
        formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.propagate = False  # 防止传播到其他日志器
    
    def log_performance(self, data: Dict[str, Any]):
        """记录性能数据"""
        # 添加时间戳
        data['timestamp'] = datetime.now().isoformat()
        
        # 序列化为JSON并记录
        json_data = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        self.logger.info(json_data)


# 全局性能日志记录器实例
perf_logger = PerformanceLogger()


class PerformanceContext:
    """性能监控上下文"""
    
    def __init__(self, 
                 operation: str,
                 channel_id: str = None,
                 message_id: int = None,
                 channel_name: str = None,
                 message_type: str = None,
                 content_length: int = None):
        self.operation = operation
        self.channel_id = channel_id
        self.message_id = message_id
        self.channel_name = channel_name
        self.message_type = message_type
        self.content_length = content_length
        
        # 性能数据
        self.timer = PerformanceTimer(operation)
        self.stages: Dict[str, PerformanceTimer] = {}
        self.bottlenecks: List[str] = []
        self.metadata: Dict[str, Any] = {}
        
        # 阈值设置（毫秒）
        self.slow_thresholds = {
            'message_total': 5000,      # 总处理时间超过5秒
            'filter_stage': 1000,       # 单个过滤器超过1秒
            'media_processing': 3000,   # 媒体处理超过3秒
            'storage_operation': 500,   # 存储操作超过500ms
        }
    
    def start_stage(self, stage_name: str) -> PerformanceTimer:
        """开始一个处理阶段"""
        stage_timer = PerformanceTimer(stage_name).start()
        self.stages[stage_name] = stage_timer
        return stage_timer
    
    def end_stage(self, stage_name: str, **metrics):
        """结束一个处理阶段"""
        if stage_name in self.stages:
            timer = self.stages[stage_name]
            duration = timer.stop()
            
            # 添加额外指标
            for key, value in metrics.items():
                timer.set_metric(key, value)
            
            # 检查是否为瓶颈
            threshold = self.slow_thresholds.get(stage_name, 
                                               self.slow_thresholds.get('filter_stage', 1000))
            if duration > threshold:
                self.bottlenecks.append(f"{stage_name}:{duration:.1f}ms")
    
    def set_metadata(self, **kwargs):
        """设置元数据"""
        self.metadata.update(kwargs)
    
    def finalize(self):
        """完成性能监控并记录"""
        total_duration = self.timer.stop()
        
        # 构建性能报告
        performance_data = {
            'operation': self.operation,
            'channel_id': self.channel_id,
            'channel_name': self.channel_name,
            'message_id': self.message_id,
            'message_type': self.message_type,
            'content_length': self.content_length,
            'total_time_ms': round(total_duration, 2),
            
            # 阶段耗时
            'stages': {name: timer.to_dict() for name, timer in self.stages.items()},
            
            # 瓶颈标识
            'bottlenecks': self.bottlenecks,
            
            # 元数据
            'metadata': self.metadata
        }
        
        # 记录到性能日志
        perf_logger.log_performance(performance_data)
        
        # 如果有严重的性能问题，同时记录到主日志
        if total_duration > self.slow_thresholds['message_total']:
            main_logger = logging.getLogger(__name__)
            main_logger.warning(f"性能警告: {self.operation} 处理耗时 {total_duration:.1f}ms "
                              f"(消息: {self.channel_name}#{self.message_id})")


@asynccontextmanager
async def performance_monitor(operation: str, **context_kwargs):
    """异步性能监控上下文管理器"""
    perf_ctx = PerformanceContext(operation, **context_kwargs)
    perf_ctx.timer.start()
    
    try:
        yield perf_ctx
    finally:
        perf_ctx.finalize()


@contextmanager
def sync_performance_monitor(operation: str, **context_kwargs):
    """同步性能监控上下文管理器"""
    perf_ctx = PerformanceContext(operation, **context_kwargs)
    perf_ctx.timer.start()
    
    try:
        yield perf_ctx
    finally:
        perf_ctx.finalize()


def perf_timer(operation_name: str = None, 
               stage_name: str = None,
               include_args: bool = False):
    """性能计时装饰器
    
    Args:
        operation_name: 操作名称，如果为None则使用函数名
        stage_name: 阶段名称，用于在现有上下文中添加阶段
        include_args: 是否包含函数参数信息
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            
            # 尝试从参数中提取上下文信息
            context_info = {}
            if include_args and len(args) > 0:
                # 尝试从第一个参数提取信息
                first_arg = args[0]
                if hasattr(first_arg, 'channel_id'):
                    context_info['channel_id'] = first_arg.channel_id
                if hasattr(first_arg, 'telegram_message'):
                    msg = first_arg.telegram_message
                    context_info['message_id'] = getattr(msg, 'id', None)
                    content = getattr(msg, 'text', '') or getattr(msg, 'caption', '')
                    if content:
                        context_info['content_length'] = len(content)
            
            # 检查是否在现有的性能上下文中
            if stage_name and hasattr(func, '_perf_context'):
                # 在现有上下文中添加阶段
                perf_ctx = func._perf_context
                stage_timer = perf_ctx.start_stage(stage_name)
                try:
                    result = await func(*args, **kwargs)
                    perf_ctx.end_stage(stage_name)
                    return result
                except Exception as e:
                    perf_ctx.end_stage(stage_name, error=str(e))
                    raise
            else:
                # 创建新的性能监控上下文
                async with performance_monitor(op_name, **context_info) as perf_ctx:
                    # 将上下文传递给被装饰的函数（如果支持）
                    if hasattr(func, '__code__') and 'perf_ctx' in func.__code__.co_varnames:
                        result = await func(*args, perf_ctx=perf_ctx, **kwargs)
                    else:
                        # 临时设置上下文属性
                        func._perf_context = perf_ctx
                        try:
                            result = await func(*args, **kwargs)
                        finally:
                            if hasattr(func, '_perf_context'):
                                delattr(func, '_perf_context')
                    return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            
            # 提取上下文信息（同步版本）
            context_info = {}
            if include_args and len(args) > 0:
                first_arg = args[0]
                if hasattr(first_arg, 'channel_id'):
                    context_info['channel_id'] = first_arg.channel_id
                if hasattr(first_arg, 'telegram_message'):
                    msg = first_arg.telegram_message
                    context_info['message_id'] = getattr(msg, 'id', None)
            
            with sync_performance_monitor(op_name, **context_info) as perf_ctx:
                if hasattr(func, '__code__') and 'perf_ctx' in func.__code__.co_varnames:
                    result = func(*args, perf_ctx=perf_ctx, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return result
        
        # 根据函数类型返回相应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# 便捷函数
def get_performance_stats() -> Dict[str, Any]:
    """获取性能统计信息"""
    # 可以在这里添加实时统计功能
    return {
        'monitor_active': True,
        'log_file': str(PathConfig.LOGS_DIR / "performance.log")
    }


def create_filter_timer(filter_name: str) -> PerformanceTimer:
    """为过滤器创建专用计时器"""
    return PerformanceTimer(f"filter_{filter_name}")