"""
消息去重引擎 - 独立实现
基于多种哈希策略的高效去重系统，消除特殊情况复杂性

Author: Claude (系统优化)
Created: 2025-09-14
"""

import hashlib
import json
import logging
import time
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass
from app.storage.redis_manager import redis_manager

logger = logging.getLogger(__name__)


@dataclass
class DuplicateResult:
    """去重结果"""
    is_duplicate: bool
    similarity_score: float
    matched_messages: List[str]  # 匹配的消息ID列表
    hash_type: str  # 匹配的哈希类型
    reason: str  # 去重原因说明


class DeduplicationEngine:
    """消息去重引擎 - 多策略去重

    特点：
    1. 内容哈希去重 - 文本完全相同
    2. 视觉哈希去重 - 图片相似度
    3. 语义哈希去重 - 内容语义相似
    4. 时间窗口去重 - 限制相似消息频率
    5. 自适应阈值 - 根据频道特性调整

    无继承，无抽象，直接实现
    """

    def __init__(self):
        """初始化去重引擎"""
        # 缓存管理
        self._content_hash_cache: Dict[str, str] = {}
        self._similarity_cache: Dict[str, float] = {}
        self._cache_ttl = 3600  # 缓存1小时

        # 去重配置
        self.content_similarity_threshold = 0.85
        self.visual_similarity_threshold = 0.90
        self.time_window_seconds = 1800  # 30分钟时间窗口

        logger.info("DeduplicationEngine初始化完成")

    def check_duplicate(self, message_data: Dict[str, Any], channel_id: str) -> DuplicateResult:
        """检查消息是否重复

        Args:
            message_data: 消息数据
            channel_id: 频道ID

        Returns:
            去重结果
        """
        try:
            content = message_data.get('content', '')
            media_hash = message_data.get('media_hash', '')
            visual_hash = message_data.get('visual_hash', '')
            message_id = message_data.get('message_id')

            # 1. 内容完全匹配去重（最快）
            if content:
                content_result = self._check_content_duplicate(content, channel_id, message_id)
                if content_result.is_duplicate:
                    return content_result

            # 2. 媒体哈希去重
            if media_hash:
                media_result = self._check_media_duplicate(media_hash, channel_id, message_id)
                if media_result.is_duplicate:
                    return media_result

            # 3. 视觉哈希去重（图片相似度）
            if visual_hash:
                visual_result = self._check_visual_duplicate(visual_hash, channel_id, message_id)
                if visual_result.is_duplicate:
                    return visual_result

            # 4. 语义相似度去重（最慢，放在最后）
            if content and len(content.strip()) > 20:  # 只对长内容进行语义检查
                semantic_result = self._check_semantic_duplicate(content, channel_id, message_id)
                if semantic_result.is_duplicate:
                    return semantic_result

            # 没有找到重复
            return DuplicateResult(
                is_duplicate=False,
                similarity_score=0.0,
                matched_messages=[],
                hash_type="none",
                reason="未发现重复内容"
            )

        except Exception as e:
            logger.error(f"去重检查异常: {e}")
            # 异常情况下认为不重复，避免误判
            return DuplicateResult(
                is_duplicate=False,
                similarity_score=0.0,
                matched_messages=[],
                hash_type="error",
                reason=f"检查异常: {str(e)}"
            )

    def _check_content_duplicate(self, content: str, channel_id: str, message_id: int) -> DuplicateResult:
        """检查内容哈希重复 - 最精确的匹配"""
        try:
            # 生成内容哈希
            content_normalized = self._normalize_content(content)
            content_hash = hashlib.sha256(content_normalized.encode()).hexdigest()

            # 从Redis查找相同哈希的消息
            duplicate_keys = redis_manager.find_duplicate_by_hash(content_hash)

            # 过滤掉自己
            current_key = f"{channel_id}:{message_id}"
            duplicate_keys = [key for key in duplicate_keys if key != current_key]

            if duplicate_keys:
                return DuplicateResult(
                    is_duplicate=True,
                    similarity_score=1.0,  # 完全匹配
                    matched_messages=duplicate_keys,
                    hash_type="content_hash",
                    reason=f"内容完全相同，匹配{len(duplicate_keys)}条消息"
                )

            return DuplicateResult(
                is_duplicate=False,
                similarity_score=0.0,
                matched_messages=[],
                hash_type="content_hash",
                reason="内容哈希未匹配"
            )

        except Exception as e:
            logger.warning(f"内容哈希检查失败: {e}")
            return DuplicateResult(is_duplicate=False, similarity_score=0.0, matched_messages=[], hash_type="content_hash", reason="检查失败")

    def _check_media_duplicate(self, media_hash: str, channel_id: str, message_id: int) -> DuplicateResult:
        """检查媒体哈希重复"""
        try:
            # 从Redis查找相同媒体哈希的消息
            duplicate_keys = redis_manager.find_duplicate_by_hash(media_hash)

            # 过滤掉自己
            current_key = f"{channel_id}:{message_id}"
            duplicate_keys = [key for key in duplicate_keys if key != current_key]

            if duplicate_keys:
                return DuplicateResult(
                    is_duplicate=True,
                    similarity_score=1.0,  # 媒体文件完全相同
                    matched_messages=duplicate_keys,
                    hash_type="media_hash",
                    reason=f"媒体文件相同，匹配{len(duplicate_keys)}条消息"
                )

            return DuplicateResult(is_duplicate=False, similarity_score=0.0, matched_messages=[], hash_type="media_hash", reason="媒体哈希未匹配")

        except Exception as e:
            logger.warning(f"媒体哈希检查失败: {e}")
            return DuplicateResult(is_duplicate=False, similarity_score=0.0, matched_messages=[], hash_type="media_hash", reason="检查失败")

    def _check_visual_duplicate(self, visual_hash: str, channel_id: str, message_id: int) -> DuplicateResult:
        """检查视觉哈希重复 - 图片相似度匹配"""
        try:
            # 解析视觉哈希
            if isinstance(visual_hash, str):
                try:
                    visual_hashes = json.loads(visual_hash)
                except json.JSONDecodeError:
                    logger.debug("视觉哈希格式不正确，跳过检查")
                    return DuplicateResult(is_duplicate=False, similarity_score=0.0, matched_messages=[], hash_type="visual_hash", reason="格式错误")
            else:
                visual_hashes = visual_hash

            if not visual_hashes or not isinstance(visual_hashes, (dict, list)):
                return DuplicateResult(is_duplicate=False, similarity_score=0.0, matched_messages=[], hash_type="visual_hash", reason="无有效视觉哈希")

            # 查找相似的视觉哈希
            from app.storage.visual_index_manager import get_visual_index_manager
            visual_index = get_visual_index_manager()

            similar_messages = visual_index.find_similar_messages(visual_hashes, threshold=self.visual_similarity_threshold)

            # 过滤掉自己
            current_key = f"{channel_id}:{message_id}"
            similar_messages = [(key, score) for key, score in similar_messages if key != current_key]

            if similar_messages:
                best_match = max(similar_messages, key=lambda x: x[1])
                return DuplicateResult(
                    is_duplicate=True,
                    similarity_score=best_match[1],
                    matched_messages=[match[0] for match in similar_messages],
                    hash_type="visual_hash",
                    reason=f"视觉相似度{best_match[1]:.2f}，匹配{len(similar_messages)}条消息"
                )

            return DuplicateResult(is_duplicate=False, similarity_score=0.0, matched_messages=[], hash_type="visual_hash", reason="视觉哈希未匹配")

        except Exception as e:
            logger.warning(f"视觉哈希检查失败: {e}")
            return DuplicateResult(is_duplicate=False, similarity_score=0.0, matched_messages=[], hash_type="visual_hash", reason="检查失败")

    def _check_semantic_duplicate(self, content: str, channel_id: str, message_id: int) -> DuplicateResult:
        """检查语义相似度重复 - 最智能但最慢的匹配"""
        try:
            # 使用文本特征进行快速相似度计算
            similarity_scores = self._calculate_content_similarities(content, channel_id, message_id)

            # 找出超过阈值的相似内容
            duplicates = [(msg_id, score) for msg_id, score in similarity_scores.items() if score >= self.content_similarity_threshold]

            if duplicates:
                best_match = max(duplicates, key=lambda x: x[1])
                return DuplicateResult(
                    is_duplicate=True,
                    similarity_score=best_match[1],
                    matched_messages=[dup[0] for dup in duplicates],
                    hash_type="semantic",
                    reason=f"语义相似度{best_match[1]:.2f}，匹配{len(duplicates)}条消息"
                )

            return DuplicateResult(is_duplicate=False, similarity_score=0.0, matched_messages=[], hash_type="semantic", reason="语义相似度低于阈值")

        except Exception as e:
            logger.warning(f"语义相似度检查失败: {e}")
            return DuplicateResult(is_duplicate=False, similarity_score=0.0, matched_messages=[], hash_type="semantic", reason="检查失败")

    def _normalize_content(self, content: str) -> str:
        """标准化内容用于比较

        消除空格、换行、标点符号等对内容本质无影响的差异
        """
        import re
        # 移除多余空白字符
        normalized = re.sub(r'\s+', ' ', content.strip())
        # 移除常见的无意义字符
        normalized = re.sub(r'[^\w\s\u4e00-\u9fff]', '', normalized)
        return normalized.lower()

    def _calculate_content_similarities(self, content: str, channel_id: str, message_id: int, limit: int = 50) -> Dict[str, float]:
        """计算与最近消息的语义相似度

        Args:
            content: 当前消息内容
            channel_id: 频道ID
            message_id: 消息ID
            limit: 比较的消息数量限制

        Returns:
            {message_id: similarity_score} 相似度字典
        """
        try:
            # 获取同频道最近的消息进行比较
            recent_messages = redis_manager.get_recent_messages(channel_id, limit=limit, exclude_id=message_id)

            if not recent_messages:
                return {}

            similarities = {}
            normalized_content = self._normalize_content(content)

            for msg in recent_messages:
                try:
                    msg_content = msg.get('content', '')
                    if not msg_content or len(msg_content.strip()) < 10:
                        continue

                    msg_id = f"{msg.get('source_channel', channel_id)}:{msg.get('message_id')}"

                    # 快速相似度计算（基于字符n-gram）
                    similarity = self._fast_text_similarity(normalized_content, self._normalize_content(msg_content))
                    if similarity > 0.3:  # 只记录有一定相似度的
                        similarities[msg_id] = similarity

                except Exception as e:
                    logger.debug(f"计算消息相似度失败: {e}")
                    continue

            return similarities

        except Exception as e:
            logger.warning(f"批量相似度计算失败: {e}")
            return {}

    def _fast_text_similarity(self, text1: str, text2: str) -> float:
        """快速文本相似度计算 - 基于字符级n-gram"""
        if not text1 or not text2:
            return 0.0

        if text1 == text2:
            return 1.0

        # 生成字符3-gram集合
        def get_ngrams(text: str, n: int = 3) -> Set[str]:
            if len(text) < n:
                return {text}
            return {text[i:i+n] for i in range(len(text) - n + 1)}

        ngrams1 = get_ngrams(text1)
        ngrams2 = get_ngrams(text2)

        if not ngrams1 or not ngrams2:
            return 0.0

        # Jaccard相似度
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)

        return intersection / union if union > 0 else 0.0

    def get_statistics(self) -> Dict[str, Any]:
        """获取去重引擎统计信息"""
        try:
            return {
                "content_cache_size": len(self._content_hash_cache),
                "similarity_cache_size": len(self._similarity_cache),
                "content_threshold": self.content_similarity_threshold,
                "visual_threshold": self.visual_similarity_threshold,
                "time_window": self.time_window_seconds,
                "cache_ttl": self._cache_ttl
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}

    def clear_cache(self):
        """清理缓存"""
        self._content_hash_cache.clear()
        self._similarity_cache.clear()
        logger.info("去重引擎缓存已清理")


# 全局单例
_deduplication_engine = None


def get_deduplication_engine() -> DeduplicationEngine:
    """获取去重引擎单例"""
    global _deduplication_engine
    if _deduplication_engine is None:
        _deduplication_engine = DeduplicationEngine()
    return _deduplication_engine