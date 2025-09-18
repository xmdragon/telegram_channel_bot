"""
Markdown链接过滤器 - 独立实现
完全独立的类，不继承任何基类，消除所有抽象层

Author: Claude ()
Created: 2025-09-13
"""

import re
import logging
from typing import Tuple, List, Optional, Any

logger = logging.getLogger(__name__)


class MarkdownFilter:
    """Markdown链接过滤器 - 移除所有链接

    功能：
    1. 基于entities删除链接实体（Telegram原生链接）
    2. 基于正则删除markdown格式链接
    3. 返回过滤后的内容

    无继承，无抽象，直接实现
    """

    def __init__(self):
        """初始化Markdown过滤器"""
        # 只保留核心的markdown正则
        self.markdown_pattern = re.compile(r'\[([^\]]*)\]\(([^\)]+)\)')

    def filter(self, content: str, entities: Optional[List[Any]] = None) -> Tuple[str, int]:
        """过滤markdown链接和链接实体

        Args:
            content: 原始内容
            entities: Telegram消息实体列表（可选）

        Returns:
            (过滤后内容, 移除的链接数)
        """
        if not content:
            return content, 0

        total_removed = 0
        current_content = content

        # 1. 基于entities删除链接（如果提供）
        if entities:
            current_content, entities_removed = self._filter_by_entities(current_content, entities)
            total_removed += entities_removed
            if entities_removed > 0:
                logger.debug(f"通过entities移除了 {entities_removed} 个链接")

        # 2. 基于正则删除markdown格式链接
        current_content, markdown_removed = self._filter_by_regex(current_content)
        total_removed += markdown_removed
        if markdown_removed > 0:
            logger.debug(f"通过正则移除了 {markdown_removed} 个markdown链接")

        return current_content, total_removed

    def _filter_by_entities(self, content: str, entities: List[Any]) -> Tuple[str, int]:
        """基于entities删除所有链接实体

        Args:
            content: 原始内容
            entities: Telegram实体列表

        Returns:
            (过滤后内容, 移除的链接数)
        """
        try:
            # 收集所有链接类型的实体
            link_entities = []
            for entity in entities:
                # 处理 Telethon 实体对象
                entity_class_name = entity.__class__.__name__
                if entity_class_name in ['MessageEntityUrl', 'MessageEntityTextUrl', 'MessageEntityBlockquote'] or hasattr(entity, 'url'):
                    link_entities.append({
                        'offset': entity.offset,
                        'length': entity.length
                    })

            if not link_entities:
                return content, 0

            # 按offset降序排序，从后向前删除避免位置偏移
            link_entities.sort(key=lambda x: x['offset'], reverse=True)

            # 将字符串转为字节处理UTF-16偏移
            content_utf16 = content.encode('utf-16-le')
            removed_count = 0

            for entity in link_entities:
                try:
                    # Telegram使用UTF-16偏移
                    byte_offset = entity['offset'] * 2
                    byte_length = entity['length'] * 2

                    # 提取要删除的部分
                    before = content_utf16[:byte_offset]
                    after = content_utf16[byte_offset + byte_length:]

                    # 重新组合
                    content_utf16 = before + after
                    removed_count += 1

                except Exception as e:
                    logger.warning(f"处理entity失败: {e}")
                    continue

            # 转回字符串
            filtered_content = content_utf16.decode('utf-16-le')
            return filtered_content, removed_count

        except Exception as e:
            logger.error(f"基于entities过滤失败: {e}")
            return content, 0

    def _filter_by_regex(self, content: str) -> Tuple[str, int]:
        """基于正则删除markdown格式链接

        Args:
            content: 原始内容

        Returns:
            (过滤后内容, 移除的链接数)
        """
        try:
            # 查找所有markdown链接
            matches = list(self.markdown_pattern.finditer(content))
            if not matches:
                return content, 0

            # 替换markdown链接为纯文本
            filtered_content = content
            for match in reversed(matches):  # 从后向前处理避免位置偏移
                link_text = match.group(1)  # 链接文本部分
                if link_text:  # 如果有文本，保留文本
                    filtered_content = filtered_content[:match.start()] + link_text + filtered_content[match.end():]
                else:  # 如果没有文本，整个删除
                    filtered_content = filtered_content[:match.start()] + filtered_content[match.end():]

            return filtered_content, len(matches)

        except Exception as e:
            logger.error(f"基于正则过滤失败: {e}")
            return content, 0