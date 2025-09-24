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
        """基于entities删除链接实体和包含链接的BlockQuote

        Args:
            content: 原始内容
            entities: Telegram实体列表

        Returns:
            (过滤后内容, 移除的链接数)
        """
        try:
            # 预先计算内容的UTF-16单元长度，用于过滤无效entities
            def get_utf16_length(s):
                """计算字符串的UTF-16单元长度"""
                length = 0
                for char in s:
                    code_point = ord(char)
                    if code_point <= 0xFFFF:
                        length += 1
                    else:
                        length += 2  # 非BMP字符占用2个UTF-16单元
                return length

            content_utf16_length = get_utf16_length(content)

            # 1. 收集有效范围内的URL实体
            url_ranges = []
            blockquote_entities = []
            link_entities = []

            for entity in entities:
                # 检查entity是否在有效范围内
                if entity.offset < 0 or entity.offset >= content_utf16_length:
                    continue  # 静默忽略超出范围的entity

                # 如果entity部分超出，截断到有效范围
                entity_end = min(entity.offset + entity.length, content_utf16_length)
                if entity_end <= entity.offset:
                    continue  # 完全超出范围，忽略

                entity_class_name = entity.__class__.__name__

                # 收集URL实体
                if entity_class_name in ['MessageEntityUrl', 'MessageEntityTextUrl'] or hasattr(entity, 'url'):
                    url_ranges.append((entity.offset, entity_end))
                    link_entities.append({
                        'offset': entity.offset,
                        'length': entity_end - entity.offset,
                        'type': 'url'
                    })
                # 单独收集BlockQuote实体
                elif entity_class_name == 'MessageEntityBlockquote':
                    blockquote_entities.append({
                        'offset': entity.offset,
                        'length': entity_end - entity.offset,
                        'type': 'blockquote'
                    })

            # 2. 检查每个BlockQuote是否包含或紧邻URL
            for blockquote in blockquote_entities:
                bq_start = blockquote['offset']
                bq_end = blockquote['offset'] + blockquote['length']

                # 检查是否有URL在BlockQuote范围内或紧邻（前后10个字符）
                contains_url = False
                for url_start, url_end in url_ranges:
                    # URL在BlockQuote内部
                    if url_start >= bq_start and url_end <= bq_end:
                        contains_url = True
                        break
                    # URL紧邻BlockQuote（容差10个字符）
                    if abs(url_start - bq_end) < 10 or abs(bq_start - url_end) < 10:
                        contains_url = True
                        break

                # 只删除包含URL的BlockQuote
                if contains_url:
                    link_entities.append(blockquote)
                    logger.debug(f"BlockQuote包含URL，将被删除: offset={bq_start}, length={blockquote['length']}")

            if not link_entities:
                return content, 0

            # 按offset降序排序，从后向前删除避免位置偏移
            link_entities.sort(key=lambda x: x['offset'], reverse=True)

            # 使用字符级别处理，避免UTF-16编码问题
            # Telegram的offset和length是基于UTF-16代码单元的
            removed_count = 0
            filtered_content = content

            # 将字符串转换为UTF-16代码单元列表
            def string_to_utf16_units(s):
                """将字符串转换为UTF-16代码单元列表"""
                units = []
                for char in s:
                    # 检查是否是代理对（4字节UTF-16字符）
                    code_point = ord(char)
                    if code_point <= 0xFFFF:
                        # BMP字符，1个UTF-16单元
                        units.append(char)
                    else:
                        # 非BMP字符，需要代理对（2个UTF-16单元）
                        # Python已经处理了这个，但我们需要标记它占用2个单元
                        units.append(char)
                        units.append('')  # 占位符，表示这是一个双单元字符
                return units

            # 将UTF-16单元列表转回字符串
            def utf16_units_to_string(units):
                """将UTF-16单元列表转换回字符串"""
                result = []
                i = 0
                while i < len(units):
                    if units[i] != '':
                        result.append(units[i])
                    i += 1
                return ''.join(result)

            # 转换为UTF-16单元
            utf16_units = string_to_utf16_units(filtered_content)

            for entity in link_entities:
                try:
                    offset = entity['offset']
                    length = entity['length']

                    # 再次检查是否在有效范围内（由于前面已经过滤，这里一般不会触发）
                    if offset < 0 or offset + length > len(utf16_units):
                        continue  # 静默忽略

                    # 删除指定范围的单元
                    # 从后往前处理，所以直接删除不会影响其他实体的位置
                    del utf16_units[offset:offset + length]
                    removed_count += 1

                except Exception as e:
                    continue  # 静默处理异常

            # 转回字符串
            if removed_count > 0:
                filtered_content = utf16_units_to_string(utf16_units)
                logger.debug(f"Markdown过滤: 删除了 {removed_count} 个实体")

            return filtered_content, removed_count

        except Exception as e:
            logger.error(f"基于entities过滤失败: {e}")
            # 失败时返回原内容，确保处理继续
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