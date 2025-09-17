"""
统一过滤引擎 - 简化实现
整合现有过滤器提供统一接口
"""
import logging
from typing import Tuple, Optional, List, Dict, Any
from app.services.filters.filter_pipeline import FilterPipeline
from app.services.filters.ad_detector import AdDetector
from app.services.filters.base import FilterContext

logger = logging.getLogger(__name__)


class UnifiedFilterEngine:
    """统一过滤引擎"""

    def __init__(self):
        self.filter_pipeline = FilterPipeline()
        self.ad_detector = AdDetector()

    async def detect_advertisement(
        self,
        content: str,
        channel_id: Optional[str] = None,
        message_obj: Optional[Dict[str, Any]] = None,
        media_files: Optional[List] = None
    ) -> Tuple[bool, str, str]:
        """检测广告内容

        Returns:
            (是否为广告, 过滤后内容, 过滤原因)
        """
        try:
            # 使用广告检测器
            is_ad, score, keywords = self.ad_detector.detect(content)

            if is_ad:
                keyword_list = [kw['keyword'] for kw in keywords]
                reason = f"广告检测: 权重={score:.1f}, 关键词={','.join(keyword_list[:5])}"
                return True, "", reason

            # 创建过滤上下文
            context = FilterContext(
                channel_id=channel_id or "unknown",
                message_id=message_obj.get('message_id') if message_obj else None,
                metadata={}
            )

            # 使用过滤管道处理
            result = await self.filter_pipeline.process(content, context)

            if result.final_content != content:
                return False, result.final_content, "内容已过滤"

            return False, content, ""

        except Exception as e:
            logger.error(f"过滤引擎处理失败: {e}")
            return False, content, ""


# 全局实例
unified_filter_engine = UnifiedFilterEngine()


class FilterEngineCompat:
    """兼容层 - 提供旧接口"""

    def __init__(self):
        self.engine = unified_filter_engine

    def filter_message_sync(self, content: str, channel_id: str = None):
        """同步版本的消息过滤 - 兼容旧接口"""
        try:
            import asyncio
            # 在同步环境中运行异步方法
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已在异步环境，创建新任务
                future = asyncio.ensure_future(
                    self.engine.detect_advertisement(content, channel_id)
                )
                # 等待完成
                while not future.done():
                    pass
                return future.result()
            else:
                # 在新的事件循环中运行
                return loop.run_until_complete(
                    self.engine.detect_advertisement(content, channel_id)
                )
        except Exception as e:
            logger.error(f"同步过滤失败: {e}")
            return False, content, ""


# 兼容层实例
filter_engine_compat = FilterEngineCompat()