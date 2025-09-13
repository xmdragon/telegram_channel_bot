"""
内容处理器 - Linus式极简实现
统一的内容处理管道，使用独立的过滤器类，无抽象层

Author: Claude (Linus式重构)
Created: 2025-09-13
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import logging

from app.services.filters.tail_filter import TailFilter
from app.services.filters.markdown_filter import MarkdownFilter
from app.services.filters.separator_filter import SeparatorFilter
from app.services.filters.ad_detector import AdDetector

logger = logging.getLogger(__name__)


@dataclass
class LocalMessage:
    """简化的消息对象，只包含处理需要的字段"""
    message_id: int
    channel_id: Optional[str] = None
    content: str = ""
    filtered_content: str = ""
    filter_reason: Optional[str] = None
    status: str = "pending"
    reject_reason: Optional[str] = None
    is_ad: bool = False
    ad_weight: float = 0.0
    hit_keywords: Optional[List[Dict]] = None
    entities: Optional[List] = None

    def __post_init__(self):
        if self.filtered_content == "":
            self.filtered_content = self.content


class ContentProcessor:
    """内容处理器 - 直接使用独立的过滤器类

    处理流程：
    1. 尾部过滤 - 删除推广内容
    2. Markdown过滤 - 删除链接
    3. 分隔符过滤 - 删除特定内容块
    4. 广告检测 - 识别广告内容

    无继承，无抽象，直接调用
    """

    def __init__(self):
        """初始化处理器，创建所有独立的过滤器实例"""
        self.tail_filter = TailFilter()
        self.markdown_filter = MarkdownFilter()
        self.separator_filter = SeparatorFilter()
        self.ad_detector = AdDetector()

        logger.info("ContentProcessor初始化完成（Linus式架构）")

    async def process(self, message: LocalMessage, config_manager: Optional[Any] = None, detect_ad: bool = True) -> LocalMessage:
        """处理消息内容

        Args:
            message: 要处理的消息
            config_manager: 配置管理器（用于获取自动拒绝广告配置）
            detect_ad: 是否进行广告检测

        Returns:
            处理后的消息对象
        """
        try:
            if not message.content:
                return message

            current_content = message.content
            filter_reasons = []

            # 1. 尾部过滤
            filtered_content, is_filtered, removed_tail = self.tail_filter.filter(current_content)
            if is_filtered:
                current_content = filtered_content
                filter_reasons.append(f"尾部过滤: 删除{len(removed_tail)}字符")
                logger.info(f"消息 {message.message_id} 尾部过滤: {len(message.content)} -> {len(current_content)} 字符")

            # 2. Markdown链接过滤
            filtered_content, links_removed = self.markdown_filter.filter(current_content, message.entities)
            if links_removed > 0:
                current_content = filtered_content
                filter_reasons.append(f"Markdown过滤: 移除{links_removed}个链接")
                logger.info(f"消息 {message.message_id} Markdown过滤: 移除{links_removed}个链接")

            # 3. 分隔符过滤
            filtered_content, separator_stats = self.separator_filter.filter_content(current_content)
            removed_blocks = separator_stats.get('removed_blocks_count', 0)
            if removed_blocks > 0:
                current_content = filtered_content
                removed_chars = separator_stats.get('original_length', 0) - separator_stats.get('filtered_length', 0)
                filter_reasons.append(f"分隔符过滤: 移除{removed_blocks}个块({removed_chars}字符)")
                logger.info(f"消息 {message.message_id} 分隔符过滤: 移除{removed_blocks}个内容块")

            # 4. 广告检测（可选）
            if detect_ad:
                is_ad, total_weight, matched_keywords = self.ad_detector.detect(current_content)

                if is_ad:
                    message.is_ad = True
                    message.ad_weight = total_weight
                    message.hit_keywords = matched_keywords[:10]  # 保存前10个关键词

                    # 准备日志
                    keyword_names = [item['keyword'] for item in matched_keywords[:3]]
                    filter_reasons.append(f"广告检测: 权重={total_weight:.1f}, 关键词={','.join(keyword_names)}")
                    logger.info(f"消息 {message.message_id} 检测为广告: 权重={total_weight:.1f}")

                    # 根据配置决定是否自动拒绝
                    if config_manager:
                        try:
                            auto_reject = await config_manager.get_auto_reject_ads()
                            if auto_reject:
                                message.status = "rejected"
                                message.reject_reason = f"自动拒绝广告(权重:{total_weight:.1f})"
                                logger.info(f"消息 {message.message_id} 被自动拒绝（广告）")
                        except Exception as e:
                            logger.error(f"获取自动拒绝配置失败: {e}")

            # 更新消息
            message.filtered_content = current_content
            if filter_reasons:
                message.filter_reason = "; ".join(filter_reasons)

            return message

        except Exception as e:
            logger.error(f"内容处理失败 {message.message_id}: {e}")
            return message