"""
尾部过滤器 - 完全独立，所有代码在一个类里
基于正则规则的直接匹配，无需导入其他文件

Author: Claude (Linus式重构)
Created: 2025-09-13
"""

import re
import json
import logging
from pathlib import Path
from typing import Tuple, List
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class TailFilter:
    """尾部过滤器 - 基于正则规则的直接匹配"""

    def __init__(self):
        """初始化并加载规则"""
        self.regex_rules: List[re.Pattern] = []
        self.initialized = False
        self._samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
        self._samples_mtime = 0
        self._load_rules()

    def _load_rules(self):
        """从样本文件加载正则规则"""
        try:
            if not self._samples_file.exists():
                logger.warning(f"样本文件不存在: {self._samples_file}")
                return

            self._samples_mtime = self._samples_file.stat().st_mtime

            with open(self._samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 获取规则
            rules = data.get('rules', []) or []
            if not rules and 'samples' in data:
                # 兼容旧格式
                all_rules = set()
                for sample in data['samples']:
                    if sample.get('rules'):
                        all_rules.update(sample['rules'])
                rules = list(all_rules)

            # 编译正则
            self.regex_rules = []
            for rule in rules:
                if not rule:
                    continue
                try:
                    compiled = re.compile(rule, re.IGNORECASE | re.MULTILINE)
                    self.regex_rules.append(compiled)
                except re.error as e:
                    logger.warning(f"正则编译失败 '{rule}': {e}")

            if self.regex_rules:
                self.initialized = True
                logger.info(f"加载了 {len(self.regex_rules)} 条尾部过滤规则")

        except Exception as e:
            logger.error(f"加载尾部规则失败: {e}")

    def filter(self, content: str) -> Tuple[str, bool, str]:
        """过滤尾部内容

        Args:
            content: 输入内容

        Returns:
            (过滤后内容, 是否过滤, 删除的内容)
        """
        # 检查是否需要重新加载
        if self._samples_file.exists():
            current_mtime = self._samples_file.stat().st_mtime
            if current_mtime != self._samples_mtime:
                logger.info("检测到规则文件更新，重新加载...")
                self._load_rules()

        # 如果未初始化或内容为空，直接返回
        if not self.initialized or not content:
            return content, False, ""

        # 按行分割
        lines = content.split('\n')
        if len(lines) <= 1:
            return content, False, ""

        # 从后向前查找第一个匹配的行
        matched_idx = -1
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if not line:
                continue

            # 检查是否匹配任何规则
            for rule in self.regex_rules:
                if rule.search(line):
                    matched_idx = i
                    break

            if matched_idx != -1:
                break

        # 如果找到匹配，删除该行及其后的所有内容
        if matched_idx != -1:
            filtered_lines = lines[:matched_idx]

            # 去除末尾空行
            while filtered_lines and not filtered_lines[-1].strip():
                filtered_lines.pop()

            filtered = '\n'.join(filtered_lines)
            removed = '\n'.join(lines[matched_idx:])

            logger.debug(f"尾部过滤: 匹配在第 {matched_idx + 1} 行")
            return filtered, True, removed

        # 没有匹配
        return content, False, ""