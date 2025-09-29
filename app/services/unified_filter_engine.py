"""
统一过滤引擎 - 简化实现
整合现有过滤器提供统一接口
"""
import logging
from typing import Tuple, Optional, List, Dict, Any
from app.services.filters.filter_pipeline import FilterPipeline
from app.services.filters.ad_detector import AdDetector
from app.services.filters.base import FilterContext
from app.services.filters.tail_filter import TailFilter
from app.services.filters.separator_filter import SeparatorFilter
from app.services.filters.text_filter import TextFilter
from app.services.filters.markdown_filter import MarkdownFilter
from app.services.duplicate_detector import DuplicateDetector

logger = logging.getLogger(__name__)


class UnifiedFilterEngine:
    """统一过滤引擎"""

    def __init__(self):
        self.filter_pipeline = FilterPipeline()
        self.ad_detector = AdDetector()

        # 初始化所有过滤器并添加到管道
        # 注意：顺序很重要，这是过滤的执行顺序
        self.filter_pipeline.add_filter(TailFilter())
        self.filter_pipeline.add_filter(SeparatorFilter())
        self.filter_pipeline.add_filter(TextFilter())
        self.filter_pipeline.add_filter(MarkdownFilter())
        self.filter_pipeline.add_filter(DuplicateDetector())

        logger.info(f"统一过滤引擎已初始化，包含 {len(self.filter_pipeline.filters)} 个过滤器")

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

    async def analyze_with_details(
        self,
        content: str,
        channel_id: Optional[str] = None,
        message_obj: Optional[Dict[str, Any]] = None,
        media_files: Optional[List] = None
    ) -> Dict[str, Any]:
        """分析内容并返回详细的过滤结果

        专门用于测试端点，返回每个过滤器的执行细节

        Returns:
            包含详细过滤信息的字典
        """
        try:
            original_length = len(content)

            # 先执行广告检测
            is_ad, score, keywords = self.ad_detector.detect(content)

            ad_detection_result = {
                'name': '广告检测',
                'enabled': True,
                'is_ad': is_ad,
                'total_score': score,
                'threshold': self.ad_detector.threshold,
                'confidence': score / self.ad_detector.threshold if self.ad_detector.threshold > 0 else 0,
                'matched_keywords': keywords if is_ad else [],
                'description': f"检测为广告，得分: {score}/{self.ad_detector.threshold}" if is_ad else "未检测为广告"
            }

            # 如果是广告，直接返回
            if is_ad:
                return {
                    'is_ad': True,
                    'final_content': "",
                    'original_content': content,
                    'total_removed_length': original_length,
                    'removal_percentage': 100.0,
                    'filters': [ad_detection_result],
                    'filter_reason': f"广告检测: 权重={score:.1f}"
                }

            # 创建过滤上下文
            context = FilterContext(
                channel_id=channel_id or "unknown",
                message_id=message_obj.get('message_id') if message_obj else None,
                metadata={}
            )

            # 使用过滤管道处理并获取详细结果
            pipeline_result = await self.filter_pipeline.process(content, context)

            # 构建过滤器详细结果
            filter_details = []

            # 添加各个过滤器的结果
            for filter_name, filter_result in pipeline_result.filter_results.items():
                filter_info = {
                    'name': self._get_filter_display_name(filter_name),
                    'enabled': True,
                    'filtered_content': filter_result.filtered_content,
                    'removed_length': len(content) - len(filter_result.filtered_content) if filter_result.filtered_content else 0,
                    'processing_time_ms': getattr(filter_result, 'processing_time_ms', 0)
                }

                # 根据过滤器类型添加特定信息
                if filter_name == 'TailFilter':
                    filter_info['description'] = filter_result.reason if not filter_result.passed else "未检测到尾部内容"
                elif filter_name == 'SeparatorFilter':
                    filter_info['description'] = filter_result.reason if not filter_result.passed else "未检测到需要过滤的分隔符内容"
                elif filter_name == 'TextFilter':
                    details = filter_result.details or {}
                    filter_info['matched_keywords'] = details.get('matched_keywords', [])
                    filter_info['description'] = filter_result.reason if not filter_result.passed else "未检测到需要过滤的文本内容"
                elif filter_name == 'MarkdownFilter':
                    filter_info['description'] = "Markdown格式已清理" if not filter_result.passed else "无需处理Markdown"
                elif filter_name == 'DuplicateDetector':
                    details = filter_result.details or {}
                    filter_info['is_duplicate'] = not filter_result.passed
                    filter_info['similarity'] = details.get('similarity_score', 0)
                    filter_info['duplicate_id'] = details.get('original_message_id')
                    filter_info['description'] = filter_result.reason if not filter_result.passed else "无重复"

                filter_details.append(filter_info)

            # 添加广告检测结果（即使未检测为广告）
            filter_details.append(ad_detection_result)

            # 计算总体统计
            final_content = pipeline_result.final_content
            total_removed = original_length - len(final_content)
            removal_percentage = (total_removed / original_length * 100) if original_length > 0 else 0

            return {
                'is_ad': False,
                'final_content': final_content,
                'original_content': content,
                'total_removed_length': total_removed,
                'removal_percentage': removal_percentage,
                'filters': filter_details,
                'filter_reason': pipeline_result.overall_reason or "",
                'early_stopped': pipeline_result.early_stopped_at is not None,
                'processing_time_ms': pipeline_result.total_processing_time_ms
            }

        except Exception as e:
            logger.error(f"详细分析失败: {e}", exc_info=True)
            return {
                'is_ad': False,
                'final_content': content,
                'original_content': content,
                'total_removed_length': 0,
                'removal_percentage': 0,
                'filters': [{
                    'name': '错误',
                    'enabled': False,
                    'error': str(e)
                }],
                'filter_reason': f"分析失败: {e}"
            }

    def _get_filter_display_name(self, filter_name: str) -> str:
        """获取过滤器的显示名称"""
        name_mapping = {
            'TailFilter': '尾部过滤',
            'SeparatorFilter': '分隔符过滤',
            'TextFilter': '文本过滤',
            'MarkdownFilter': 'Markdown过滤',
            'DuplicateDetector': '去重检测',
            'AdDetector': '广告检测'
        }
        return name_mapping.get(filter_name, filter_name)


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