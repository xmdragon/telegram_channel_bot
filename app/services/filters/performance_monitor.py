"""
过滤系统性能监控器 - 性能分析工具
实时监控各个过滤器的性能指标，识别瓶颈和优化机会

Author: Claude (性能优化)
Created: 2025-09-14
"""

import time
import asyncio
import logging
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


@dataclass
class FilterMetrics:
    """过滤器性能指标"""
    name: str
    total_calls: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    avg_time: float = 0.0
    success_count: int = 0
    error_count: int = 0
    last_call_time: Optional[datetime] = None
    recent_times: deque = field(default_factory=lambda: deque(maxlen=100))  # 最近100次调用时间

    def update(self, execution_time: float, success: bool = True):
        """更新指标"""
        self.total_calls += 1
        self.total_time += execution_time
        self.min_time = min(self.min_time, execution_time)
        self.max_time = max(self.max_time, execution_time)
        self.avg_time = self.total_time / self.total_calls
        self.last_call_time = datetime.now()
        self.recent_times.append(execution_time)

        if success:
            self.success_count += 1
        else:
            self.error_count += 1

    def get_recent_avg(self, window: int = 10) -> float:
        """获取最近N次调用的平均时间"""
        recent = list(self.recent_times)[-window:]
        return sum(recent) / len(recent) if recent else 0.0

    def get_success_rate(self) -> float:
        """获取成功率"""
        return (self.success_count / self.total_calls * 100) if self.total_calls > 0 else 0.0


class PerformanceMonitor:
    """性能监控器 - 零开销监控

    特性：
    1. 零配置启动
    2. 低开销采集
    3. 实时分析
    4. 自动报警
    """

    def __init__(self):
        """初始化性能监控器"""
        self.metrics: Dict[str, FilterMetrics] = {}
        self.pipeline_metrics: Dict[str, List[float]] = defaultdict(list)  # 整体流水线性能
        self.bottleneck_alerts: List[Dict[str, Any]] = []
        self.monitoring_enabled = True

        # 性能阈值配置
        self.slow_threshold_ms = 100  # 慢操作阈值：100ms
        self.alert_threshold_ms = 500  # 报警阈值：500ms
        self.error_rate_threshold = 5.0  # 错误率阈值：5%

        # 统计窗口
        self.stats_window_minutes = 5
        self.alert_cooldown_minutes = 2

        self._last_alert_time = {}
        self._lock = threading.Lock()

        logger.info("PerformanceMonitor初始化完成")

    def start_filter_timing(self, filter_name: str) -> 'FilterTimer':
        """开始计时过滤器执行"""
        return FilterTimer(self, filter_name)

    def record_filter_execution(self, filter_name: str, execution_time: float, success: bool = True, **metadata):
        """记录过滤器执行结果"""
        if not self.monitoring_enabled:
            return

        try:
            with self._lock:
                if filter_name not in self.metrics:
                    self.metrics[filter_name] = FilterMetrics(filter_name)

                self.metrics[filter_name].update(execution_time, success)

                # 检查性能问题
                self._check_performance_issues(filter_name, execution_time, success)

        except Exception as e:
            logger.warning(f"记录性能指标失败: {e}")

    def record_pipeline_execution(self, pipeline_name: str, total_time: float, filter_times: Dict[str, float]):
        """记录整体流水线执行"""
        if not self.monitoring_enabled:
            return

        try:
            with self._lock:
                # 记录总时间
                self.pipeline_metrics[pipeline_name].append(total_time)

                # 限制历史记录大小
                if len(self.pipeline_metrics[pipeline_name]) > 1000:
                    self.pipeline_metrics[pipeline_name] = self.pipeline_metrics[pipeline_name][-500:]

                # 分析流水线瓶颈
                if filter_times:
                    bottleneck_filter = max(filter_times.items(), key=lambda x: x[1])
                    if bottleneck_filter[1] > self.slow_threshold_ms / 1000.0:  # 转换为秒
                        self._record_bottleneck(pipeline_name, bottleneck_filter[0], bottleneck_filter[1])

        except Exception as e:
            logger.warning(f"记录流水线性能失败: {e}")

    def _check_performance_issues(self, filter_name: str, execution_time: float, success: bool):
        """检查性能问题并生成报警"""
        try:
            metrics = self.metrics[filter_name]

            # 检查慢操作
            if execution_time > self.alert_threshold_ms / 1000.0:
                self._create_alert('slow_execution', {
                    'filter_name': filter_name,
                    'execution_time': execution_time * 1000,  # 转换为ms
                    'threshold': self.alert_threshold_ms
                })

            # 检查错误率
            if metrics.total_calls >= 10:  # 至少10次调用后才检查错误率
                error_rate = (metrics.error_count / metrics.total_calls) * 100
                if error_rate > self.error_rate_threshold:
                    self._create_alert('high_error_rate', {
                        'filter_name': filter_name,
                        'error_rate': error_rate,
                        'threshold': self.error_rate_threshold,
                        'total_calls': metrics.total_calls,
                        'error_count': metrics.error_count
                    })

        except Exception as e:
            logger.warning(f"检查性能问题失败: {e}")

    def _create_alert(self, alert_type: str, data: Dict[str, Any]):
        """创建性能报警"""
        try:
            alert_key = f"{alert_type}_{data.get('filter_name', 'unknown')}"

            # 报警冷却时间检查
            now = datetime.now()
            last_alert = self._last_alert_time.get(alert_key)
            if last_alert and (now - last_alert).total_seconds() < self.alert_cooldown_minutes * 60:
                return

            alert = {
                'type': alert_type,
                'timestamp': now.isoformat(),
                'data': data
            }

            self.bottleneck_alerts.append(alert)
            self._last_alert_time[alert_key] = now

            # 限制报警历史
            if len(self.bottleneck_alerts) > 100:
                self.bottleneck_alerts = self.bottleneck_alerts[-50:]

            # 记录日志
            if alert_type == 'slow_execution':
                logger.warning(f"⚠️ 慢操作报警: {data['filter_name']} 耗时 {data['execution_time']:.1f}ms (阈值: {data['threshold']}ms)")
            elif alert_type == 'high_error_rate':
                logger.warning(f"⚠️ 高错误率报警: {data['filter_name']} 错误率 {data['error_rate']:.1f}% (阈值: {data['threshold']}%)")

        except Exception as e:
            logger.warning(f"创建报警失败: {e}")

    def _record_bottleneck(self, pipeline_name: str, filter_name: str, execution_time: float):
        """记录流水线瓶颈"""
        try:
            bottleneck_data = {
                'pipeline': pipeline_name,
                'bottleneck_filter': filter_name,
                'execution_time': execution_time * 1000,  # 转换为ms
                'timestamp': datetime.now().isoformat()
            }

            logger.debug(f"🐌 流水线瓶颈: {pipeline_name} -> {filter_name} ({execution_time*1000:.1f}ms)")

        except Exception as e:
            logger.warning(f"记录瓶颈失败: {e}")

    def get_performance_report(self) -> Dict[str, Any]:
        """生成性能报告"""
        try:
            with self._lock:
                report = {
                    'timestamp': datetime.now().isoformat(),
                    'monitoring_enabled': self.monitoring_enabled,
                    'filters': {},
                    'pipelines': {},
                    'alerts': self.bottleneck_alerts[-10:],  # 最近10个报警
                    'summary': {}
                }

                # 过滤器指标
                for name, metrics in self.metrics.items():
                    report['filters'][name] = {
                        'total_calls': metrics.total_calls,
                        'avg_time_ms': metrics.avg_time * 1000,
                        'min_time_ms': metrics.min_time * 1000 if metrics.min_time != float('inf') else 0,
                        'max_time_ms': metrics.max_time * 1000,
                        'recent_avg_ms': metrics.get_recent_avg() * 1000,
                        'success_rate': metrics.get_success_rate(),
                        'error_count': metrics.error_count,
                        'last_call': metrics.last_call_time.isoformat() if metrics.last_call_time else None
                    }

                # 流水线指标
                for name, times in self.pipeline_metrics.items():
                    if times:
                        recent_times = times[-50:]  # 最近50次
                        report['pipelines'][name] = {
                            'total_executions': len(times),
                            'avg_time_ms': (sum(recent_times) / len(recent_times)) * 1000,
                            'min_time_ms': min(recent_times) * 1000,
                            'max_time_ms': max(recent_times) * 1000,
                            'recent_executions': len(recent_times)
                        }

                # 汇总统计
                if self.metrics:
                    total_calls = sum(m.total_calls for m in self.metrics.values())
                    total_errors = sum(m.error_count for m in self.metrics.values())
                    avg_success_rate = sum(m.get_success_rate() for m in self.metrics.values()) / len(self.metrics)

                    # 找出最慢的过滤器
                    slowest_filter = max(self.metrics.items(), key=lambda x: x[1].avg_time)

                    report['summary'] = {
                        'total_filter_calls': total_calls,
                        'total_errors': total_errors,
                        'overall_error_rate': (total_errors / total_calls * 100) if total_calls > 0 else 0,
                        'avg_success_rate': avg_success_rate,
                        'slowest_filter': {
                            'name': slowest_filter[0],
                            'avg_time_ms': slowest_filter[1].avg_time * 1000
                        },
                        'active_filters': len(self.metrics),
                        'active_pipelines': len(self.pipeline_metrics)
                    }

                return report

        except Exception as e:
            logger.error(f"生成性能报告失败: {e}")
            return {'error': str(e), 'timestamp': datetime.now().isoformat()}

    def get_bottleneck_analysis(self) -> Dict[str, Any]:
        """获取瓶颈分析"""
        try:
            with self._lock:
                analysis = {
                    'timestamp': datetime.now().isoformat(),
                    'recommendations': [],
                    'bottlenecks': [],
                    'optimization_opportunities': []
                }

                # 分析慢过滤器
                slow_filters = []
                for name, metrics in self.metrics.items():
                    if metrics.avg_time > self.slow_threshold_ms / 1000.0:
                        slow_filters.append((name, metrics.avg_time * 1000, metrics.total_calls))

                slow_filters.sort(key=lambda x: x[1], reverse=True)

                for name, avg_time, calls in slow_filters:
                    analysis['bottlenecks'].append({
                        'filter': name,
                        'avg_time_ms': avg_time,
                        'total_calls': calls,
                        'severity': 'high' if avg_time > self.alert_threshold_ms else 'medium'
                    })

                # 生成优化建议
                if slow_filters:
                    slowest = slow_filters[0]
                    analysis['recommendations'].append(
                        f"优先优化 {slowest[0]} 过滤器，平均耗时 {slowest[1]:.1f}ms"
                    )

                # 分析高错误率过滤器
                for name, metrics in self.metrics.items():
                    error_rate = (metrics.error_count / metrics.total_calls * 100) if metrics.total_calls > 0 else 0
                    if error_rate > self.error_rate_threshold and metrics.total_calls >= 5:
                        analysis['recommendations'].append(
                            f"检查 {name} 过滤器稳定性，错误率 {error_rate:.1f}%"
                        )

                # 分析缓存命中率
                content_processor_stats = None
                try:
                    from app.services.content_processor import ContentProcessor
                    # 如果有全局实例，获取其统计
                    # 这里需要根据实际架构调整
                except:
                    pass

                return analysis

        except Exception as e:
            logger.error(f"生成瓶颈分析失败: {e}")
            return {'error': str(e)}

    def reset_metrics(self):
        """重置所有指标"""
        with self._lock:
            self.metrics.clear()
            self.pipeline_metrics.clear()
            self.bottleneck_alerts.clear()
            self._last_alert_time.clear()
        logger.info("性能指标已重置")

    def set_monitoring_enabled(self, enabled: bool):
        """启用/禁用监控"""
        self.monitoring_enabled = enabled
        logger.info(f"性能监控已{'启用' if enabled else '禁用'}")


class FilterTimer:
    """过滤器计时器上下文管理器"""

    def __init__(self, monitor: PerformanceMonitor, filter_name: str):
        self.monitor = monitor
        self.filter_name = filter_name
        self.start_time = None
        self.success = True
        self.metadata = {}

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            execution_time = time.perf_counter() - self.start_time
            success = exc_type is None and self.success

            self.monitor.record_filter_execution(
                self.filter_name,
                execution_time,
                success,
                **self.metadata
            )

    def set_success(self, success: bool):
        """设置执行是否成功"""
        self.success = success

    def add_metadata(self, **kwargs):
        """添加元数据"""
        self.metadata.update(kwargs)


# 全局性能监控器实例
_performance_monitor = None


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def monitor_filter(filter_name: str):
    """装饰器：自动监控过滤器性能"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            monitor = get_performance_monitor()
            with monitor.start_filter_timing(filter_name) as timer:
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    timer.set_success(False)
                    raise

        def sync_wrapper(*args, **kwargs):
            monitor = get_performance_monitor()
            with monitor.start_filter_timing(filter_name) as timer:
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    timer.set_success(False)
                    raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator