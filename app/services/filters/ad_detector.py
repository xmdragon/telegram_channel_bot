"""
广告检测器 - Linus式独立实现
完全独立的类，所有逻辑在一个文件中，不依赖外部

Author: Claude (Linus式重构)
Created: 2025-09-13
"""

import json
import logging
import time
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class AdDetector:
    """广告检测器 - 基于关键词权重的检测

    功能：
    1. 加载关键词配置（支持热更新）
    2. 计算关键词权重
    3. 判断是否为广告

    无继承，无外部依赖，所有代码在一个类中
    """

    def __init__(self):
        """初始化广告检测器"""
        self.keywords_file = PathConfig.AD_KEYWORDS_FILE
        self.keywords: Dict[str, float] = {}
        self.threshold: float = 3.0
        self._file_mtime: float = 0

        # 初始加载
        self._load_keywords()

    def _load_keywords(self) -> None:
        """加载关键词配置"""
        try:
            if not self.keywords_file.exists():
                logger.warning(f"关键词配置文件不存在: {self.keywords_file}")
                return

            with open(self.keywords_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 支持向后兼容：整数权重自动转为浮点数
            keywords_data = data.get('keywords', {})
            self.keywords = {k: float(v) for k, v in keywords_data.items()}
            self.threshold = float(data.get('threshold', 3.0))
            self._file_mtime = self.keywords_file.stat().st_mtime

            logger.info(f"加载关键词配置: {len(self.keywords)}个关键词, 阈值={self.threshold}")

        except Exception as e:
            logger.error(f"加载关键词配置失败: {e}")
            self.keywords = {}
            self.threshold = 3.0

    def reload_if_needed(self) -> None:
        """检查并重新加载配置（如果文件已更新）"""
        try:
            if self.keywords_file.exists():
                current_mtime = self.keywords_file.stat().st_mtime
                if current_mtime != self._file_mtime:
                    logger.info("检测到关键词配置更新，重新加载...")
                    self._load_keywords()
        except Exception as e:
            logger.warning(f"检查配置更新失败: {e}")

    def detect(self, content: str) -> Tuple[bool, float, List[Dict[str, float]]]:
        """检测内容是否为广告

        Args:
            content: 要检测的内容

        Returns:
            (是否为广告, 总权重, 命中的关键词列表)
            关键词列表格式: [{'keyword': '关键词', 'weight': 权重}, ...]
        """
        # 检查是否需要重新加载配置
        self.reload_if_needed()

        if not content or not self.keywords:
            return False, 0.0, []

        # 转换为小写进行匹配
        content_lower = content.lower()

        # 计算权重
        total_weight = 0.0
        matched_keywords = []

        for keyword, weight in self.keywords.items():
            if keyword.lower() in content_lower:
                total_weight += weight
                matched_keywords.append({
                    'keyword': keyword,
                    'weight': weight
                })

        # 按权重排序
        matched_keywords.sort(key=lambda x: x['weight'], reverse=True)

        # 判断是否为广告
        is_ad = total_weight >= self.threshold

        if is_ad:
            logger.debug(f"检测到广告: 权重={total_weight:.1f}, 关键词={[k['keyword'] for k in matched_keywords[:3]]}")

        return is_ad, total_weight, matched_keywords

    def add_keyword(self, keyword: str, weight: float) -> bool:
        """添加新关键词

        Args:
            keyword: 关键词
            weight: 权重

        Returns:
            是否成功
        """
        try:
            # 加载最新配置
            self.reload_if_needed()

            # 添加关键词
            self.keywords[keyword] = weight

            # 保存配置
            data = {
                'keywords': self.keywords,
                'threshold': self.threshold,
                'updated_at': time.strftime("%Y-%m-%dT%H:%M:%S"),
                'version': '1.0.0'
            }

            with open(self.keywords_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self._file_mtime = self.keywords_file.stat().st_mtime
            logger.info(f"添加关键词: {keyword} (权重: {weight})")
            return True

        except Exception as e:
            logger.error(f"添加关键词失败: {e}")
            return False

    def remove_keyword(self, keyword: str) -> bool:
        """删除关键词

        Args:
            keyword: 关键词

        Returns:
            是否成功
        """
        try:
            # 加载最新配置
            self.reload_if_needed()

            if keyword not in self.keywords:
                return False

            # 删除关键词
            del self.keywords[keyword]

            # 保存配置
            data = {
                'keywords': self.keywords,
                'threshold': self.threshold,
                'updated_at': time.strftime("%Y-%m-%dT%H:%M:%S"),
                'version': '1.0.0'
            }

            with open(self.keywords_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self._file_mtime = self.keywords_file.stat().st_mtime
            logger.info(f"删除关键词: {keyword}")
            return True

        except Exception as e:
            logger.error(f"删除关键词失败: {e}")
            return False

    def set_threshold(self, threshold: float) -> bool:
        """设置检测阈值

        Args:
            threshold: 新阈值

        Returns:
            是否成功
        """
        try:
            # 加载最新配置
            self.reload_if_needed()

            self.threshold = threshold

            # 保存配置
            data = {
                'keywords': self.keywords,
                'threshold': self.threshold,
                'updated_at': time.strftime("%Y-%m-%dT%H:%M:%S"),
                'version': '1.0.0'
            }

            with open(self.keywords_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self._file_mtime = self.keywords_file.stat().st_mtime
            logger.info(f"更新阈值: {threshold}")
            return True

        except Exception as e:
            logger.error(f"设置阈值失败: {e}")
            return False

