"""
文本过滤器 - 支持普通文本和正则表达式过滤
在分隔符过滤之后对文本进行二次过滤

Author: Claude
Created: 2025-09-29
"""

import re
import json
import logging
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from datetime import datetime
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class TextFilter:
    """文本过滤器

    功能：
    1. 支持普通文本关键词过滤
    2. 支持正则表达式过滤
    3. 对分隔符过滤后的文本进行再次过滤
    """

    def __init__(self):
        """初始化文本过滤器"""
        self.filters: List[Dict[str, any]] = []
        self.compiled_regexes: Dict[str, re.Pattern] = {}
        self.filters_file = PathConfig.TRAINING_DIR / "text_filters.json"
        self.load_filters()

    def load_filters(self) -> None:
        """从文件加载过滤器配置"""
        try:
            if self.filters_file.exists():
                with open(self.filters_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.filters = data.get('filters', [])

                    # 编译正则表达式
                    self.compiled_regexes = {}
                    for filter_item in self.filters:
                        if filter_item.get('is_regex', False):
                            try:
                                pattern = filter_item['keyword']
                                self.compiled_regexes[pattern] = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                            except re.error as e:
                                logger.warning(f"无效的正则表达式 '{pattern}': {e}")

                    logger.info(f"加载了 {len(self.filters)} 个文本过滤器")
            else:
                self.filters = []
                self.save_filters()
                logger.info("创建新的文本过滤器配置文件")
        except Exception as e:
            logger.error(f"加载文本过滤器失败: {e}")
            self.filters = []

    def save_filters(self) -> bool:
        """保存过滤器配置到文件"""
        try:
            # 确保目录存在
            self.filters_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'filters': self.filters,
                'updated_at': datetime.now().isoformat()
            }

            with open(self.filters_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"保存了 {len(self.filters)} 个文本过滤器")
            return True
        except Exception as e:
            logger.error(f"保存文本过滤器失败: {e}")
            return False

    def add_filter(self, keyword: str, is_regex: bool = False) -> bool:
        """添加过滤器

        Args:
            keyword: 过滤关键词或正则表达式
            is_regex: 是否为正则表达式

        Returns:
            是否添加成功
        """
        # 检查是否已存在
        for filter_item in self.filters:
            if filter_item['keyword'] == keyword:
                logger.warning(f"过滤器已存在: {keyword}")
                return False

        # 如果是正则表达式，验证其有效性
        if is_regex:
            try:
                compiled = re.compile(keyword, re.IGNORECASE | re.MULTILINE)
                self.compiled_regexes[keyword] = compiled
            except re.error as e:
                logger.error(f"无效的正则表达式 '{keyword}': {e}")
                return False

        # 添加到列表
        self.filters.append({
            'keyword': keyword,
            'is_regex': is_regex
        })

        # 保存到文件
        if self.save_filters():
            logger.info(f"添加文本过滤器: {keyword} (正则: {is_regex})")
            return True
        return False

    def remove_filter(self, keyword: str) -> bool:
        """删除过滤器

        Args:
            keyword: 要删除的关键词

        Returns:
            是否删除成功
        """
        # 查找并删除
        for i, filter_item in enumerate(self.filters):
            if filter_item['keyword'] == keyword:
                del self.filters[i]

                # 如果是正则表达式，也删除编译后的版本
                if keyword in self.compiled_regexes:
                    del self.compiled_regexes[keyword]

                # 保存到文件
                if self.save_filters():
                    logger.info(f"删除文本过滤器: {keyword}")
                    return True
                return False

        logger.warning(f"过滤器不存在: {keyword}")
        return False

    def get_filters(self) -> List[Dict[str, any]]:
        """获取所有过滤器

        Returns:
            过滤器列表
        """
        return self.filters.copy()

    def filter(self, text: str) -> Tuple[str, bool, List[str]]:
        """过滤文本内容

        Args:
            text: 要过滤的文本

        Returns:
            (过滤后的文本, 是否有过滤, 匹配的关键词列表)
        """
        if not text or not self.filters:
            return text, False, []

        original_text = text
        filtered_text = text
        matched_keywords = []

        for filter_item in self.filters:
            keyword = filter_item['keyword']
            is_regex = filter_item.get('is_regex', False)

            if is_regex:
                # 使用正则表达式过滤
                if keyword in self.compiled_regexes:
                    pattern = self.compiled_regexes[keyword]
                    if pattern.search(filtered_text):
                        matched_keywords.append(keyword)
                        filtered_text = pattern.sub('', filtered_text)
            else:
                # 普通文本过滤（不区分大小写）
                if keyword.lower() in filtered_text.lower():
                    matched_keywords.append(keyword)
                    # 使用正则表达式进行不区分大小写的替换
                    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                    filtered_text = pattern.sub('', filtered_text)

        # 不做额外的空白字符处理，只过滤关键词

        # 判断是否有过滤
        is_filtered = filtered_text != original_text

        if is_filtered:
            logger.debug(f"文本过滤: 移除 {len(matched_keywords)} 个关键词, 原长度={len(original_text)}, 新长度={len(filtered_text)}")

        return filtered_text, is_filtered, matched_keywords

    def test_filter(self, text: str) -> Dict[str, any]:
        """测试文本过滤效果

        Args:
            text: 要测试的文本

        Returns:
            测试结果字典
        """
        filtered_text, is_filtered, matched_keywords = self.filter(text)

        return {
            'original_text': text,
            'filtered_text': filtered_text,
            'is_filtered': is_filtered,
            'matched_keywords': matched_keywords,
            'original_length': len(text),
            'filtered_length': len(filtered_text),
            'removed_length': len(text) - len(filtered_text),
            'filter_count': len(self.filters)
        }


# 单例模式
_text_filter_instance = None

def get_text_filter() -> TextFilter:
    """获取文本过滤器实例（单例）"""
    global _text_filter_instance
    if _text_filter_instance is None:
        _text_filter_instance = TextFilter()
    return _text_filter_instance