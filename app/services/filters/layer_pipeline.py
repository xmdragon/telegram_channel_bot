"""
分层管道 - 协调内容清理层和检测器层的执行

负责协调两个层的执行顺序：
1. ContentFilterLayer - 内容清理层 (先执行)
2. DetectorLayer - 检测器层 (后执行)

设计理念：
- 先清理内容，再检测内容 - 避免因推广内容干扰检测结果
- 保持与现有FilterPipeline的接口兼容
- 统一管理两层的配置和统计

Author: Claude
Created: 2025-08-31
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from .base import FilterContext, PipelineResult
from .content_filter_layer import ContentFilterLayer, LayerConfig
from app.services.detectors import DetectorLayer, DetectorLayerConfig

logger = logging.getLogger(__name__)


@dataclass
class LayerPipelineConfig:
    """分层管道配置"""
    # 内容清理层配置
    content_layer_timeout: float = 30.0
    content_layer_enabled: bool = True
    
    # 检测器层配置
    detector_layer_timeout: float = 30.0
    detector_layer_enabled: bool = True
    enable_early_stopping: bool = True
    
    # 管道全局配置
    pipeline_timeout: float = 60.0
    enable_detailed_stats: bool = True
    enable_performance_monitoring: bool = True


class LayerPipeline:
    """
    分层管道 - 两阶段设计
    
    阶段1: 内容清理层 - 清理推广内容，优化后续检测
    阶段2: 检测器层 - 检测问题内容，支持Early Stopping
    
    这种设计消除了"边界情况" - 所有过滤器被明确分为两类
    """
    
    def __init__(self, config: Optional[LayerPipelineConfig] = None):
        self.config = config or LayerPipelineConfig()
        
        # 初始化两个层
        self.content_layer = self._init_content_layer()
        self.detector_layer = self._init_detector_layer()
        
        # 管道统计
        self.pipeline_stats = {
            'total_processed': 0,
            'total_passed': 0,
            'total_rejected': 0,
            'early_stopped': 0,
            'content_layer_filtered': 0,
            'detector_layer_rejected': 0,
            'performance_stats': []
        }
        
        logger.info("分层管道初始化完成 - 内容清理层 + 检测器层")
    
    def _init_content_layer(self) -> Optional[ContentFilterLayer]:
        """初始化内容清理层"""
        if not self.config.content_layer_enabled:
            logger.info("内容清理层已禁用")
            return None
        
        layer_config = LayerConfig(
            layer_timeout=self.config.content_layer_timeout,
            enable_detailed_stats=self.config.enable_detailed_stats
        )
        return ContentFilterLayer(layer_config)
    
    def _init_detector_layer(self) -> Optional[DetectorLayer]:
        """初始化检测器层"""
        if not self.config.detector_layer_enabled:
            logger.info("检测器层已禁用")
            return None
            
        layer_config = DetectorLayerConfig(
            enable_early_stopping=self.config.enable_early_stopping,
            layer_timeout=self.config.detector_layer_timeout,
            enable_detailed_stats=self.config.enable_detailed_stats
        )
        return DetectorLayer(layer_config)
    
    async def process(self, content: str, context: FilterContext) -> PipelineResult:
        """
        执行分层管道处理
        
        两阶段处理：
        1. 内容清理层：清理推广内容，优化内容质量
        2. 检测器层：检测问题内容，决定是否拒绝
        
        Args:
            content: 原始内容
            context: 过滤器上下文
            
        Returns:
            PipelineResult: 最终处理结果
        """
        start_time = datetime.now()
        current_content = content
        all_filter_results = {}
        all_reasons = []
        early_stopped_at = None
        final_passed = True
        
        logger.debug(f"🚀 开始分层管道处理 - 内容长度: {len(content)} 字符")
        
        # === 阶段1: 内容清理层 ===
        if self.content_layer:
            try:
                logger.debug("🔧 执行内容清理层")
                content_result = await self.content_layer.process(current_content, context)
                
                # 更新内容
                current_content = content_result.final_content
                
                # 🚀 双轨检测：在上下文中保存原始内容
                context.add_metadata('original_content', content)
                context.add_metadata('filtered_content', current_content)
                context.add_metadata('content_changed', current_content != content)
                
                # 合并结果
                all_filter_results.update(content_result.filter_results)
                if content_result.overall_reason:
                    all_reasons.append(content_result.overall_reason)
                
                # 记录清理效果
                if current_content != content:
                    self.pipeline_stats['content_layer_filtered'] += 1
                    logger.debug(f"🔄 内容清理完成: {len(content)} → {len(current_content)} 字符")
                
            except Exception as e:
                logger.error(f"❌ 内容清理层处理失败: {e}")
                # 清理失败不影响后续检测，使用原内容
                current_content = content
                context.add_metadata('original_content', content)
                context.add_metadata('filtered_content', content)
                context.add_metadata('content_changed', False)
        else:
            logger.debug("⏭️ 内容清理层已禁用")
            # 即使内容清理层禁用，也要为检测器层提供双轨数据
            context.add_metadata('original_content', content)
            context.add_metadata('filtered_content', current_content)
            context.add_metadata('content_changed', False)
        
        # === 阶段2: 检测器层 ===
        if self.detector_layer:
            try:
                logger.debug("🔍 执行检测器层")
                detector_result = await self.detector_layer.process(current_content, context)
                
                # 合并检测结果
                all_filter_results.update(detector_result.filter_results)
                if detector_result.overall_reason:
                    all_reasons.append(detector_result.overall_reason)
                
                # 更新最终状态
                final_passed = detector_result.passed
                if hasattr(detector_result, 'early_stopped_at') and detector_result.early_stopped_at:
                    early_stopped_at = detector_result.early_stopped_at
                elif hasattr(detector_result, 'early_stopped') and detector_result.early_stopped:
                    early_stopped_at = "DetectorLayer"
                
                # 记录检测效果
                if not final_passed:
                    self.pipeline_stats['detector_layer_rejected'] += 1
                if early_stopped_at:
                    self.pipeline_stats['early_stopped'] += 1
                
            except Exception as e:
                logger.error(f"❌ 检测器层处理失败: {e}")
                # 检测失败时默认通过，保证系统可用性
                final_passed = True
        else:
            logger.debug("⏭️ 检测器层已禁用")
        
        # 计算总处理时间
        total_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # 整合最终结果
        overall_reason = "; ".join(all_reasons) if all_reasons else ""
        
        # 更新管道统计
        self.pipeline_stats['total_processed'] += 1
        if final_passed:
            self.pipeline_stats['total_passed'] += 1
        else:
            self.pipeline_stats['total_rejected'] += 1
        
        # 记录性能数据
        if self.config.enable_performance_monitoring:
            self.pipeline_stats['performance_stats'].append({
                'timestamp': start_time.isoformat(),
                'original_length': len(content),
                'final_length': len(current_content),
                'total_time_ms': total_time,
                'passed': final_passed,
                'early_stopped': early_stopped_at is not None,
                'content_layer_enabled': self.content_layer is not None,
                'detector_layer_enabled': self.detector_layer is not None
            })
            
            # 保持性能数据在合理范围内
            if len(self.pipeline_stats['performance_stats']) > 1000:
                self.pipeline_stats['performance_stats'] = self.pipeline_stats['performance_stats'][-500:]
        
        # 记录最终结果
        status_emoji = "✅" if final_passed else "🚫"
        early_stop_info = f" (Early Stop at {early_stopped_at})" if early_stopped_at else ""
        logger.info(f"{status_emoji} 分层管道处理完成 - 耗时: {total_time:.2f}ms, 通过: {final_passed}{early_stop_info}")
        
        return PipelineResult(
            final_content=current_content,
            passed=final_passed,
            overall_reason=overall_reason,
            filter_results=all_filter_results,
            total_processing_time_ms=total_time,
            early_stopped_at=early_stopped_at
        )
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """获取管道统计信息"""
        stats = self.pipeline_stats.copy()
        
        # 添加层级统计
        if self.content_layer:
            stats['content_layer_stats'] = self.content_layer.get_stats()
        
        if self.detector_layer:
            stats['detector_layer_stats'] = self.detector_layer.get_stats()
        
        return stats
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        stats = self.get_pipeline_stats()
        
        # 计算性能指标
        total = stats['total_processed']
        if total == 0:
            return {'message': '暂无性能数据'}
        
        return {
            'total_processed': total,
            'pass_rate': stats['total_passed'] / total * 100,
            'rejection_rate': stats['total_rejected'] / total * 100,
            'early_stop_rate': stats['early_stopped'] / total * 100,
            'content_filter_rate': stats['content_layer_filtered'] / total * 100,
            'detector_rejection_rate': stats['detector_layer_rejected'] / total * 100,
            'avg_processing_time_ms': sum(p['total_time_ms'] for p in stats['performance_stats'][-100:]) / min(100, len(stats['performance_stats'])) if stats['performance_stats'] else 0
        }
    
    def reset_stats(self):
        """重置所有统计信息"""
        # 重置管道统计
        self.pipeline_stats = {
            'total_processed': 0,
            'total_passed': 0,
            'total_rejected': 0,
            'early_stopped': 0,
            'content_layer_filtered': 0,
            'detector_layer_rejected': 0,
            'performance_stats': []
        }
        
        # 重置层级统计
        if self.content_layer:
            self.content_layer.reset_stats()
        
        if self.detector_layer:
            self.detector_layer.reset_stats()
        
        logger.info("分层管道统计信息已重置")
    
    def get_layer_info(self) -> Dict[str, Any]:
        """获取分层信息"""
        info = {
            'pipeline_name': 'LayerPipeline',
            'architecture': 'two_layer',
            'processing_order': ['ContentFilterLayer', 'DetectorLayer'],
            'config': {
                'content_layer_enabled': self.config.content_layer_enabled,
                'detector_layer_enabled': self.config.detector_layer_enabled,
                'enable_early_stopping': self.config.enable_early_stopping,
                'pipeline_timeout': self.config.pipeline_timeout
            }
        }
        
        # 添加层级信息
        if self.content_layer:
            info['content_layer_info'] = self.content_layer.get_filter_info()
        
        if self.detector_layer:
            info['detector_layer_info'] = self.detector_layer.get_detector_info()
        
        return info


# 创建全局实例（暂时不启用，等待配置）
# layer_pipeline = LayerPipeline()