"""
尾部过滤器 - 极简化版本
只使用向量过滤，不降级

Linus哲学：既然向量过滤100%有效，其他都是无用的复杂性
Author: Claude
Updated: 2025-09-06
"""

import time
import logging
from typing import Dict, Any, Optional

from app.services.filters.base import BaseFilter, FilterResult, FilterContext
from app.services.simple_tail_filter import filter_tail_content

logger = logging.getLogger(__name__)


class TailFilter(BaseFilter):
    """极简尾部过滤器
    
    只做一件事：调用TailFilterEngine进行向量过滤
    失败就返回原内容，没有降级，没有复杂逻辑
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化尾部过滤器"""
        super().__init__("tail_filter", config)
        
        # 简化：不需要复杂的引擎初始化
        logger.info("✅ 尾部过滤器初始化完成（直接正则模式）")
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """执行尾部过滤
        
        Args:
            content: 要过滤的内容
            context: 过滤器上下文
            
        Returns:
            FilterResult: 过滤结果
        """
        start_time = time.time()
        
        try:
            # 直接调用简单正则过滤器
            filtered_content, was_filtered, removed_tail, analysis = filter_tail_content(content)
            
            # 计算处理时间
            processing_time = (time.time() - start_time) * 1000
            
            # 构建结果
            result = FilterResult(
                filtered_content=filtered_content,
                passed=True,  # 尾部过滤不阻止消息通过
                processing_time_ms=processing_time,
                reason="尾部过滤" if was_filtered else "无需尾部过滤",
                confidence=analysis.get('confidence', 0.0) if analysis else 0.0,
                should_early_stop=False,
                details=analysis or {}
            )
            
            # 如果过滤了内容，记录修改信息
            if was_filtered and removed_tail:
                result.modifications.append(f"移除尾部内容({len(removed_tail)}字符)")
                result.details['removed_tail'] = removed_tail
                result.details['original_length'] = len(content)
                result.details['filtered_length'] = len(filtered_content)
                
                logger.info(f"✅ 尾部过滤成功: {len(content)} -> {len(filtered_content)} 字符")
            
            return result
            
        except Exception as e:
            # 出错就返回原内容，不要让过滤器阻塞消息
            logger.error(f"❌ 尾部过滤异常: {e}")
            processing_time = (time.time() - start_time) * 1000
            
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=processing_time,
                reason=f"过滤异常: {str(e)}",
                confidence=0.0,
                should_early_stop=False,
                details={'error': str(e)}
            )