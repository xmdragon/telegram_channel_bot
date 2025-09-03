"""
内容过滤层 - 管理所有内容清理过滤器

负责管理4个内容清理过滤器的执行顺序和协调：
1. TailFilter - 尾部过滤
2. MarkdownFilter - Markdown格式清理 (调整到TailFilter后)
3. FooterPromoFilter - 尾部推广链接过滤
4. PromoVectorFilter - 推广内容向量过滤

Author: Claude
Created: 2025-08-31
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from .base import BaseFilter, FilterContext, FilterResult, PipelineResult
from .tail_filter import TailFilter
from .markdown_filter import MarkdownFilter
from .footer_promo_filter import FooterPromoFilter
from .promo_vector_filter import PromoVectorFilter

logger = logging.getLogger(__name__)


@dataclass
class LayerConfig:
    """分层配置"""
    enable_early_stopping: bool = False  # 内容清理层不支持Early Stopping
    layer_timeout: float = 30.0          # 整层超时时间(秒)
    enable_detailed_stats: bool = True   # 启用详细统计


class ContentFilterLayer:
    """
    内容过滤层 - Linus式设计
    
    职责单一：只负责内容清理，不做内容检测
    执行顺序固定：TailFilter → MarkdownFilter → FooterPromoFilter → PromoVectorFilter
    """
    
    def __init__(self, config: Optional[LayerConfig] = None):
        self.config = config or LayerConfig()
        self.filters: List[BaseFilter] = []
        self.stats = {
            'total_processed': 0,
            'total_filtered': 0,
            'filter_stats': {},
            'performance_stats': []
        }
        self._initialize_filters()
    
    def _initialize_filters(self):
        """按固定顺序初始化内容清理过滤器"""
        # 固定顺序，符合Linus"消除特殊情况"原则
        filter_instances = [
            TailFilter(),                # 1. 尾部过滤 - 最重要，优先处理
            MarkdownFilter(),            # 2. Markdown清理 - 调整到TailFilter后
            FooterPromoFilter(),         # 3. 尾部推广链接过滤
            PromoVectorFilter(),         # 4. 推广内容向量过滤
        ]
        
        for filter_instance in filter_instances:
            self.filters.append(filter_instance)
            # 初始化过滤器统计
            self.stats['filter_stats'][filter_instance.name] = {
                'processed': 0,
                'filtered': 0,
                'total_time_ms': 0,
                'avg_time_ms': 0
            }
        
        logger.info(f"内容过滤层初始化完成，加载了 {len(self.filters)} 个过滤器")
    
    async def process(self, content: str, context: FilterContext) -> PipelineResult:
        """
        执行内容过滤层处理
        
        按固定顺序执行所有内容清理过滤器，不支持Early Stopping
        
        Args:
            content: 要处理的内容
            context: 过滤器上下文
            
        Returns:
            PipelineResult: 处理结果
        """
        start_time = datetime.now()
        current_content = content
        filter_results = {}
        reasons = []
        
        logger.debug(f"🔧 开始内容过滤层处理 - 内容长度: {len(content)} 字符")
        
        # 串行执行所有过滤器
        for filter_instance in self.filters:
            filter_start = datetime.now()
            
            try:
                # 检查过滤器是否可以处理该内容
                if hasattr(filter_instance, 'can_handle') and not filter_instance.can_handle(current_content, context):
                    logger.debug(f"⏭️ {filter_instance.name} 跳过处理")
                    continue
                
                # 执行过滤
                filter_result = await filter_instance.filter(current_content, context)
                filter_results[filter_instance.name] = filter_result
                
                # 更新内容
                if filter_result.filtered_content != current_content:
                    logger.debug(f"🔄 {filter_instance.name} 修改了内容: {len(current_content)} → {len(filter_result.filtered_content)} 字符")
                    current_content = filter_result.filtered_content
                
                # 过滤器阶段不记录原因，只专注于内容清理
                # 原因信息留给检测阶段记录
                
                # 更新统计信息
                filter_time = (datetime.now() - filter_start).total_seconds() * 1000
                self._update_filter_stats(filter_instance.name, filter_time, filter_result.filtered_content != content)
                
            except Exception as e:
                logger.error(f"❌ {filter_instance.name} 处理失败: {e}")
                # 过滤器失败不影响整体流程，继续下一个
                filter_results[filter_instance.name] = FilterResult(
                    filtered_content=current_content,
                    passed=True,  # 失败时认为通过，保持内容
                    reason=f"处理失败: {e}",
                    confidence=0.0
                )
        
        # 计算总处理时间
        total_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # 统计过滤效果  
        was_filtered = current_content != content
        # 内容清理层不产生原因信息，只负责内容清理
        overall_reason = ""
        
        # 更新层级统计
        self.stats['total_processed'] += 1
        if was_filtered:
            self.stats['total_filtered'] += 1
        
        # 记录性能数据
        if self.config.enable_detailed_stats:
            self.stats['performance_stats'].append({
                'timestamp': start_time.isoformat(),
                'content_length': len(content),
                'filtered_length': len(current_content),
                'processing_time_ms': total_time,
                'was_filtered': was_filtered,
                'filters_applied': len(filter_results)
            })
            
            # 保持性能数据在合理范围内
            if len(self.stats['performance_stats']) > 1000:
                self.stats['performance_stats'] = self.stats['performance_stats'][-500:]
        
        logger.info(f"✅ 内容过滤层处理完成 - 耗时: {total_time:.2f}ms, 过滤: {was_filtered}")
        
        return PipelineResult(
            final_content=current_content,
            passed=True,  # 内容清理层始终通过，只修改内容
            overall_reason=overall_reason,
            filter_results=filter_results,
            total_processing_time_ms=total_time,
            early_stopped_at=None  # 内容清理层不支持Early Stopping
        )
    
    def _update_filter_stats(self, filter_name: str, processing_time_ms: float, was_filtered: bool):
        """更新过滤器统计信息"""
        if filter_name not in self.stats['filter_stats']:
            return
            
        stats = self.stats['filter_stats'][filter_name]
        stats['processed'] += 1
        if was_filtered:
            stats['filtered'] += 1
        stats['total_time_ms'] += processing_time_ms
        stats['avg_time_ms'] = stats['total_time_ms'] / stats['processed']
    
    def get_stats(self) -> Dict[str, Any]:
        """获取分层统计信息"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats['total_processed'] = 0
        self.stats['total_filtered'] = 0
        for filter_name in self.stats['filter_stats']:
            self.stats['filter_stats'][filter_name] = {
                'processed': 0,
                'filtered': 0,
                'total_time_ms': 0,
                'avg_time_ms': 0
            }
        self.stats['performance_stats'].clear()
        logger.info("内容过滤层统计信息已重置")
    
    def get_filter_info(self) -> Dict[str, Any]:
        """获取过滤器信息"""
        return {
            'layer_name': 'ContentFilterLayer',
            'layer_type': 'content_cleaning',
            'total_filters': len(self.filters),
            'filter_names': [f.name for f in self.filters],
            'execution_order': [
                'TailFilter',
                'MarkdownFilter', 
                'FooterPromoFilter',
                'PromoVectorFilter'
            ],
            'supports_early_stopping': False,
            'config': {
                'enable_detailed_stats': self.config.enable_detailed_stats,
                'layer_timeout': self.config.layer_timeout
            }
        }


# 创建全局实例
content_filter_layer = ContentFilterLayer()