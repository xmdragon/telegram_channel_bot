"""
广告检测器 - 独立实现
完全独立的类，所有逻辑在一个文件中，不依赖外部

Author: Claude ()
Created: 2025-09-13
"""

import json
import logging
import time
from typing import Dict, List, Tuple, Optional, Any
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

    def detect(self, content: str) -> Tuple[bool, float, List[Dict[str, Any]]]:
        """检测内容是否为广告 - 性能优化版本

        Args:
            content: 要检测的内容

        Returns:
            (是否为广告, 总权重, 命中的关键词详情)
            关键词详情格式: [{
                'keyword': str,
                'weight': float,
                'positions': [{'start': int, 'end': int}]
            }]
        """
        # 检查是否需要重新加载配置
        self.reload_if_needed()

        if not content or not self.keywords:
            return False, 0.0, []

        # 性能优化：预处理内容
        content_lower = content.lower()
        content_length = len(content_lower)

        # 优化：使用集合进行O(1)查找的预筛选
        content_chars = set(content_lower)
        potential_keywords = []

        for keyword, weight in self.keywords.items():
            keyword_lower = keyword.lower()
            # 快速预筛选：检查关键词的字符是否在内容中
            if all(char in content_chars for char in set(keyword_lower)):
                potential_keywords.append((keyword, keyword_lower, weight))

        if not potential_keywords:
            return False, 0.0, []

        # 优化：批量匹配和权重累计
        total_weight = 0.0
        matched_keywords = []

        # 使用更高效的字符串搜索
        for keyword, keyword_lower, weight in potential_keywords:
            if keyword_lower in content_lower:
                # 精确计算位置（仅对匹配的关键词）
                positions = self._find_keyword_positions(content_lower, keyword_lower)

                if positions:
                    # 重复关键词权重累加策略
                    count = len(positions)
                    if count <= 5:
                        adjusted_weight = weight * count  # 5次内线性累加
                    else:
                        # 超过5次后递减增长，防止权重爆炸
                        adjusted_weight = weight * (5 + (count - 5) * 0.5)

                    total_weight += adjusted_weight
                    matched_keywords.append({
                        'keyword': keyword,
                        'weight': adjusted_weight,
                        'positions': positions
                    })

                    # 优化：早期退出优化
                    if total_weight >= self.threshold * 2.0:  # 明显超过阈值就提前结束
                        logger.debug(f"早期退出: 权重{total_weight:.1f}明显超过阈值{self.threshold}")
                        break

        # 按权重排序
        matched_keywords.sort(key=lambda x: x['weight'], reverse=True)

        # 判断是否为广告
        is_ad = total_weight >= self.threshold

        if is_ad:
            logger.debug(f"检测到广告: 权重={total_weight:.1f}, 关键词={[k['keyword'] for k in matched_keywords[:3]]}")

        return is_ad, total_weight, matched_keywords

    def _find_keyword_positions(self, content_lower: str, keyword_lower: str) -> List[Dict[str, int]]:
        """高效查找关键词位置"""
        positions = []
        start = 0
        keyword_len = len(keyword_lower)

        # 使用更高效的查找方法
        while True:
            pos = content_lower.find(keyword_lower, start)
            if pos == -1:
                break
            positions.append({
                'start': pos,
                'end': pos + keyword_len
            })
            start = pos + 1

            # 限制单个关键词的最大匹配数，防止性能问题
            if len(positions) >= 10:  # 最多记录10个位置
                break

        return positions

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

    def update_keyword(self, keyword: str, weight: float) -> bool:
        """更新关键词权重

        Args:
            keyword: 关键词
            weight: 新权重

        Returns:
            是否成功
        """
        try:
            # 加载最新配置
            self.reload_if_needed()

            if keyword not in self.keywords:
                return False

            # 更新关键词
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
            logger.info(f"更新关键词: {keyword} (新权重: {weight})")
            return True

        except Exception as e:
            logger.error(f"更新关键词失败: {e}")
            return False

    def get_keywords(self) -> Dict[str, float]:
        """获取所有关键词

        Returns:
            关键词字典
        """
        self.reload_if_needed()
        return self.keywords.copy()

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

    def handle_positive_feedback(self, new_keywords: Dict[str, float]) -> bool:
        """处理"广告"反馈：添加新关键词

        Args:
            new_keywords: 新关键词及其权重 {'关键词': 权重}

        Returns:
            是否成功
        """
        try:
            if not new_keywords:
                return True

            # 加载最新配置
            self.reload_if_needed()

            # 批量添加关键词
            added_count = 0
            for keyword, weight in new_keywords.items():
                if keyword and weight > 0:
                    self.keywords[keyword] = float(weight)
                    added_count += 1

            if added_count > 0:
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
                logger.info(f"正面反馈处理完成: 添加了 {added_count} 个关键词")

            return True

        except Exception as e:
            logger.error(f"处理正面反馈失败: {e}")
            return False

    def handle_negative_feedback(self, matched_keywords: List[str]) -> bool:
        """处理"不是广告"反馈：降低关键词权重，权重1.0删除

        Args:
            matched_keywords: 匹配的关键词列表

        Returns:
            是否成功
        """
        try:
            if not matched_keywords:
                return True

            # 加载最新配置
            self.reload_if_needed()

            decreased_keywords = []
            deleted_keywords = []

            for keyword in matched_keywords:
                if keyword in self.keywords:
                    current_weight = self.keywords[keyword]

                    # 权重减少策略：高权重减少更多
                    if current_weight > 5.0:
                        new_weight = current_weight - 2.0
                    elif current_weight > 2.0:
                        new_weight = current_weight - 1.0
                    else:
                        new_weight = current_weight - 0.5

                    # 如果权重降到1.0或以下，删除关键词
                    if new_weight <= 1.0:
                        del self.keywords[keyword]
                        deleted_keywords.append(keyword)
                    else:
                        self.keywords[keyword] = new_weight
                        decreased_keywords.append(f"{keyword}({current_weight:.1f}→{new_weight:.1f})")

            if decreased_keywords or deleted_keywords:
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
                logger.info(f"负面反馈处理完成: 降权={decreased_keywords}, 删除={deleted_keywords}")

            return True

        except Exception as e:
            logger.error(f"处理负面反馈失败: {e}")
            return False


# 全局实例
_ad_detector_instance = None


def get_ad_detector() -> AdDetector:
    """获取广告检测器单例

    Returns:
        AdDetector实例
    """
    global _ad_detector_instance
    if _ad_detector_instance is None:
        _ad_detector_instance = AdDetector()
    return _ad_detector_instance
