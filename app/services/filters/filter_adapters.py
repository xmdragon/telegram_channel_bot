"""
过滤器适配器 - 将独立过滤器适配到FilterPipeline
"""
import time
import logging
from typing import Optional
from .base import FilterContext, FilterResult
from .markdown_filter import MarkdownFilter as OriginalMarkdownFilter
from .separator_filter import SeparatorFilter as OriginalSeparatorFilter

logger = logging.getLogger(__name__)


class MarkdownFilterAdapter:
    """Markdown过滤器适配器"""

    def __init__(self):
        self.name = "MarkdownFilter"
        self._filter = OriginalMarkdownFilter()
        self._enabled = True

    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self._enabled

    async def process_with_timing(self, content: str, context: FilterContext) -> FilterResult:
        """带计时的处理方法 - 适配FilterPipeline"""
        start_time = time.perf_counter()

        try:
            # 调用原始filter方法
            filtered_content, removed_count = self._filter.filter(content, entities=None)

            # 构造FilterResult
            processing_time_ms = (time.perf_counter() - start_time) * 1000

            result = FilterResult(
                filtered_content=filtered_content,
                passed=True,  # Markdown过滤不拦截消息
                reason="",
                confidence=1.0,
                details={
                    "removed_links": removed_count,
                    "original_length": len(content),
                    "filtered_length": len(filtered_content)
                },
                processing_time_ms=processing_time_ms,
                should_early_stop=False
            )

            return result

        except Exception as e:
            logger.error(f"Markdown过滤失败: {e}")
            processing_time_ms = (time.perf_counter() - start_time) * 1000

            # 错误时返回原内容
            return FilterResult(
                filtered_content=content,
                passed=True,
                reason=f"Markdown过滤错误: {str(e)}",
                confidence=0.0,
                details={"error": str(e)},
                processing_time_ms=processing_time_ms,
                should_early_stop=False
            )


class SeparatorFilterAdapter:
    """分隔符过滤器适配器"""

    def __init__(self):
        self.name = "SeparatorFilter"
        self._filter = OriginalSeparatorFilter()
        self._enabled = True

    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self._enabled

    async def process_with_timing(self, content: str, context: FilterContext) -> FilterResult:
        """带计时的处理方法 - 适配FilterPipeline"""
        start_time = time.perf_counter()

        try:
            # 调用原始filter_content方法
            filtered_content, stats = self._filter.filter_content(content, return_matched_rules=False)

            # 构造FilterResult
            processing_time_ms = (time.perf_counter() - start_time) * 1000

            result = FilterResult(
                filtered_content=filtered_content,
                passed=True,  # 分隔符过滤不拦截消息
                reason="",
                confidence=1.0,
                details={
                    "matched_separators": stats.get("matched_count", 0),
                    "original_length": len(content),
                    "filtered_length": len(filtered_content),
                    "cut_position": stats.get("cut_position")  # 截断位置
                },
                processing_time_ms=processing_time_ms,
                should_early_stop=False
            )

            return result

        except Exception as e:
            logger.error(f"分隔符过滤失败: {e}")
            processing_time_ms = (time.perf_counter() - start_time) * 1000

            # 错误时返回原内容
            return FilterResult(
                filtered_content=content,
                passed=True,
                reason=f"分隔符过滤错误: {str(e)}",
                confidence=0.0,
                details={"error": str(e)},
                processing_time_ms=processing_time_ms,
                should_early_stop=False
            )
