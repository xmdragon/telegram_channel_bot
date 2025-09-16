"""
检测器层 - 管理所有内容检测器

负责管理1个内容检测器的执行和Early Stopping机制：
1. WeightedKeywordDetector - 基于权重关键词的广告检测

检测器层的特点：
- 支持Early Stopping机制
- 检测到问题时可以立即终止后续处理
- 主要用于判断内容是否应该被拒绝

Author: Claude
Created: 2025-08-31
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from datetime import datetime

from app.services.filters.base import BaseFilter, FilterContext, FilterResult, PipelineResult
from .weighted_keyword_detector import WeightedKeywordDetector, get_weighted_keyword_detector

logger = logging.getLogger(__name__)


@dataclass
class DetectorLayerConfig:
    """检测器层配置"""
    enable_early_stopping: bool = True       # 启用Early Stopping机制
    early_stop_detectors: Set[str] = None    # 支持早停的检测器
    layer_timeout: float = 30.0              # 整层超时时间(秒)
    enable_detailed_stats: bool = True       # 启用详细统计
    
    def __post_init__(self):
        if self.early_stop_detectors is None:
            self.early_stop_detectors = {'keyword_ad_detector'}


class DetectorLayer:
    """
    检测器层 - 设计
    
    职责单一：只负责内容检测，不做内容清理
    支持Early Stopping：检测到问题时立即停止
    执行顺序：WeightedKeywordDetector
    """
    
    def __init__(self, config: Optional[DetectorLayerConfig] = None):
        self.config = config or DetectorLayerConfig()
        self.detectors: List[BaseFilter] = []
        self.stats = {
            'total_processed': 0,
            'total_rejected': 0,
            'early_stopped': 0,
            'detector_stats': {},
            'performance_stats': []
        }
        self._initialize_detectors()
    
    def _initialize_detectors(self):
        """按固定顺序初始化检测器"""
        # 固定顺序，符合Linus"消除特殊情况"原则
        detector_instances = [
            get_weighted_keyword_detector(),  # 1. 权重关键词广告检测 - 基于权重匹配，简洁高效
        ]
        
        for detector in detector_instances:
            self.detectors.append(detector)
            # 初始化检测器统计
            self.stats['detector_stats'][detector.name] = {
                'processed': 0,
                'rejected': 0,
                'early_stopped': 0,
                'total_time_ms': 0,
                'avg_time_ms': 0
            }
        
        logger.info(f"检测器层初始化完成，加载了 {len(self.detectors)} 个检测器")
        logger.info(f"Early Stopping支持的检测器: {list(self.config.early_stop_detectors)}")
    
    async def process(self, content: str, context: FilterContext) -> PipelineResult:
        """
        执行检测器层处理
        
        支持Early Stopping机制，一旦检测到问题立即停止后续检测器
        
        Args:
            content: 要检测的内容（已经过内容清理）
            context: 过滤器上下文
            
        Returns:
            PipelineResult: 检测结果
        """
        start_time = datetime.now()
        detector_results = {}
        reasons = []
        early_stopped = False
        final_passed = True
        
        logger.debug(f"🔍 开始检测器层处理 - 内容长度: {len(content)} 字符")
        
        # 串行执行检测器，支持Early Stopping
        for detector in self.detectors:
            detector_start = datetime.now()
            
            try:
                # 检查检测器是否可以处理该内容
                if hasattr(detector, 'can_handle') and not detector.can_handle(content, context):
                    logger.debug(f"⏭️ {detector.name} 跳过检测")
                    continue
                
                # 执行检测
                detector_result = await detector.filter(content, context)
                detector_results[detector.name] = detector_result
                
                # 只有检测到问题时才记录原因
                if not detector_result.passed and detector_result.reason:
                    reasons.append(f"检测到广告内容")
                
                # 更新统计信息
                detector_time = (datetime.now() - detector_start).total_seconds() * 1000
                was_rejected = not detector_result.passed
                self._update_detector_stats(detector.name, detector_time, was_rejected, False)
                
                # Early Stopping检查
                if not detector_result.passed and self.config.enable_early_stopping:
                    if detector.name in self.config.early_stop_detectors or \
                       (hasattr(detector_result, 'should_early_stop') and detector_result.should_early_stop):
                        logger.info(f"⚡ Early Stopping触发 - {detector.name} 检测到问题")
                        final_passed = False
                        early_stopped = True
                        
                        # 更新Early Stop统计
                        self.stats['early_stopped'] += 1
                        self.stats['detector_stats'][detector.name]['early_stopped'] += 1
                        
                        break  # 立即停止后续检测器
                
                # 如果检测器返回未通过，但不触发Early Stop，继续执行
                if not detector_result.passed:
                    final_passed = False
                
            except Exception as e:
                logger.error(f"❌ {detector.name} 检测失败: {e}")
                # 检测器失败不影响整体流程，认为通过检测
                detector_results[detector.name] = FilterResult(
                    filtered_content=content,
                    passed=True,  # 失败时认为通过
                    reason=f"检测失败: {e}",
                    confidence=0.0
                )
                
                # 更新错误统计
                detector_time = (datetime.now() - detector_start).total_seconds() * 1000
                self._update_detector_stats(detector.name, detector_time, False, False)
        
        # 计算总处理时间
        total_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # 整合检测结果
        overall_reason = "; ".join(reasons) if reasons else ""
        
        # 更新层级统计
        self.stats['total_processed'] += 1
        if not final_passed:
            self.stats['total_rejected'] += 1
        
        # 记录性能数据
        if self.config.enable_detailed_stats:
            self.stats['performance_stats'].append({
                'timestamp': start_time.isoformat(),
                'content_length': len(content),
                'processing_time_ms': total_time,
                'passed': final_passed,
                'early_stopped': early_stopped,
                'detectors_executed': len(detector_results),
                'total_detectors': len(self.detectors)
            })
            
            # 保持性能数据在合理范围内
            if len(self.stats['performance_stats']) > 1000:
                self.stats['performance_stats'] = self.stats['performance_stats'][-500:]
        
        status_emoji = "✅" if final_passed else "🚫"
        early_stop_info = " (Early Stop)" if early_stopped else ""
        logger.info(f"{status_emoji} 检测器层处理完成 - 耗时: {total_time:.2f}ms, 通过: {final_passed}{early_stop_info}")
        
        return PipelineResult(
            final_content=content,  # 检测器不修改内容
            passed=final_passed,
            overall_reason=overall_reason,
            filter_results=detector_results,
            total_processing_time_ms=total_time,
            early_stopped_at="DetectorLayer" if early_stopped else None
        )
    
    def _update_detector_stats(self, detector_name: str, processing_time_ms: float, was_rejected: bool, early_stopped: bool):
        """更新检测器统计信息"""
        if detector_name not in self.stats['detector_stats']:
            return
            
        stats = self.stats['detector_stats'][detector_name]
        stats['processed'] += 1
        if was_rejected:
            stats['rejected'] += 1
        if early_stopped:
            stats['early_stopped'] += 1
        stats['total_time_ms'] += processing_time_ms
        stats['avg_time_ms'] = stats['total_time_ms'] / stats['processed']
    
    def get_stats(self) -> Dict[str, Any]:
        """获取检测器层统计信息"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats['total_processed'] = 0
        self.stats['total_rejected'] = 0
        self.stats['early_stopped'] = 0
        for detector_name in self.stats['detector_stats']:
            self.stats['detector_stats'][detector_name] = {
                'processed': 0,
                'rejected': 0,
                'early_stopped': 0,
                'total_time_ms': 0,
                'avg_time_ms': 0
            }
        self.stats['performance_stats'].clear()
        logger.info("检测器层统计信息已重置")
    
    def get_detector_info(self) -> Dict[str, Any]:
        """获取检测器信息"""
        return {
            'layer_name': 'DetectorLayer',
            'layer_type': 'content_detection',
            'total_detectors': len(self.detectors),
            'detector_names': [d.name for d in self.detectors],
            'execution_order': [
                'WeightedKeywordDetector'
            ],
            'supports_early_stopping': True,
            'early_stop_detectors': list(self.config.early_stop_detectors),
            'config': {
                'enable_early_stopping': self.config.enable_early_stopping,
                'enable_detailed_stats': self.config.enable_detailed_stats,
                'layer_timeout': self.config.layer_timeout
            }
        }


# 创建全局实例
detector_layer = DetectorLayer()