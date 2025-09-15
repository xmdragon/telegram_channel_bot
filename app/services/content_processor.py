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
    """内容处理器 - Linus式性能优化版本

    处理流程（按性能优化顺序）：
    1. 快速预筛选 - 跳过明显的正常内容
    2. 尾部过滤 - 删除推广内容（最常见）
    3. 分隔符过滤 - 删除特定内容块
    4. Markdown过滤 - 删除链接
    5. 广告检测 - 识别广告内容（最慢，放最后）

    性能特性：
    - 延迟初始化过滤器
    - 智能缓存机制
    - 早期退出优化
    - 批量处理支持
    """

    def __init__(self):
        """延迟初始化处理器"""
        # 延迟初始化过滤器，避免启动开销
        self._tail_filter = None
        self._markdown_filter = None
        self._separator_filter = None
        self._ad_detector = None

        # 性能缓存
        self._content_cache = {}  # 内容处理结果缓存
        self._cache_hits = 0
        self._cache_misses = 0

        logger.info("ContentProcessor初始化完成（Linus式延迟加载架构）")

    @property
    def tail_filter(self):
        """延迟初始化尾部过滤器"""
        if self._tail_filter is None:
            self._tail_filter = TailFilter()
        return self._tail_filter

    @property
    def markdown_filter(self):
        """延迟初始化Markdown过滤器"""
        if self._markdown_filter is None:
            self._markdown_filter = MarkdownFilter()
        return self._markdown_filter

    @property
    def separator_filter(self):
        """延迟初始化分隔符过滤器"""
        if self._separator_filter is None:
            self._separator_filter = SeparatorFilter()
        return self._separator_filter

    @property
    def ad_detector(self):
        """延迟初始化广告检测器"""
        if self._ad_detector is None:
            self._ad_detector = AdDetector()
        return self._ad_detector

    def clear_cache(self):
        """清空内容缓存"""
        self._content_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info("ContentProcessor缓存已清空")

    async def process(self, message: LocalMessage, config_manager: Optional[Any] = None, detect_ad: bool = True) -> LocalMessage:
        """处理消息内容 - Linus式性能优化版本

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

            # Linus优化1: 缓存检查（基于内容哈希）
            import hashlib
            content_hash = hashlib.md5(message.content.encode()).hexdigest()

            if content_hash in self._content_cache:
                cached_result = self._content_cache[content_hash]
                self._cache_hits += 1
                logger.debug(f"缓存命中: 消息 {message.message_id}")

                # 应用缓存结果
                message.filtered_content = cached_result.get('filtered_content', message.content)
                message.filter_reason = cached_result.get('filter_reason', '')
                if detect_ad and cached_result.get('is_ad'):
                    message.is_ad = cached_result['is_ad']
                    message.ad_weight = cached_result['ad_weight']
                    message.hit_keywords = cached_result.get('hit_keywords', [])

                return message

            self._cache_misses += 1
            original_content = message.content
            current_content = original_content
            filter_reasons = []

            # Linus优化2: 快速预筛选 - 跳过明显正常的短内容
            if len(current_content.strip()) < 50 and not any(char in current_content for char in ['@', 'http', 't.me', '订阅', '频道']):
                logger.debug(f"快速预筛选: 消息 {message.message_id} 内容过短且无推广特征，跳过过滤")
                message.filtered_content = current_content
                return message

            # 重新排序处理步骤，按性能优化顺序

            # 1. 尾部过滤（最常见，最快，放第一）
            filtered_content, is_filtered, removed_tail = self.tail_filter.filter(current_content)
            if is_filtered:
                current_content = filtered_content
                filter_reasons.append(f"尾部过滤: 删除{len(removed_tail)}字符")
                logger.debug(f"消息 {message.message_id} 尾部过滤: {len(original_content)} -> {len(current_content)} 字符")

                # Linus优化3: 尾部过滤后如果内容太短，可能不需要后续处理
                if len(current_content.strip()) < 20:
                    message.filtered_content = current_content
                    message.filter_reason = "; ".join(filter_reasons)
                    self._cache_result(content_hash, message, detect_ad)
                    return message

            # 2. 分隔符过滤（较快，处理结构化内容）
            filtered_content, separator_stats = self.separator_filter.filter_content(current_content)
            removed_blocks = separator_stats.get('removed_blocks_count', 0)
            if removed_blocks > 0:
                current_content = filtered_content
                removed_chars = separator_stats.get('original_length', 0) - separator_stats.get('filtered_length', 0)
                filter_reasons.append(f"分隔符过滤: 移除{removed_blocks}个块({removed_chars}字符)")
                logger.debug(f"消息 {message.message_id} 分隔符过滤: 移除{removed_blocks}个内容块")

            # 3. Markdown链接过滤（中等开销）
            if message.entities and len(message.entities) > 0:  # 只有有entities时才处理
                filtered_content, links_removed = self.markdown_filter.filter(current_content, message.entities)
                if links_removed > 0:
                    current_content = filtered_content
                    filter_reasons.append(f"Markdown过滤: 移除{links_removed}个链接")
                    logger.debug(f"消息 {message.message_id} Markdown过滤: 移除{links_removed}个链接")

            # 4. 广告检测（最慢，放最后，支持早期退出）
            if detect_ad and current_content and len(current_content.strip()) > 10:
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

            # Linus优化4: 缓存处理结果
            self._cache_result(content_hash, message, detect_ad)

            return message

        except Exception as e:
            logger.error(f"内容处理失败 {message.message_id}: {e}")
            return message

    def _cache_result(self, content_hash: str, message: LocalMessage, detect_ad: bool):
        """缓存处理结果"""
        try:
            # 限制缓存大小，防止内存泄漏
            if len(self._content_cache) > 1000:
                # 删除最老的一半缓存条目
                keys_to_remove = list(self._content_cache.keys())[:500]
                for key in keys_to_remove:
                    del self._content_cache[key]

            cached_data = {
                'filtered_content': message.filtered_content,
                'filter_reason': message.filter_reason,
            }

            if detect_ad:
                cached_data.update({
                    'is_ad': message.is_ad,
                    'ad_weight': message.ad_weight,
                    'hit_keywords': message.hit_keywords
                })

            self._content_cache[content_hash] = cached_data

        except Exception as e:
            logger.warning(f"缓存结果失败: {e}")

    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        total_requests = self._cache_hits + self._cache_misses
        cache_hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'cache_hit_rate': f"{cache_hit_rate:.1f}%",
            'cache_size': len(self._content_cache),
            'total_requests': total_requests
        }

    def clear_cache(self):
        """清理缓存"""
        self._content_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info("ContentProcessor缓存已清理")