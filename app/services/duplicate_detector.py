"""
智能消息去重检测器
基于Linus "好品味"原则设计：简洁、实用、用户反馈驱动

Author: Claude
Created: 2025-09-22
"""

import re
import unicodedata
import hashlib
import logging
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class DuplicateResult:
    """去重检测结果"""
    is_duplicate: bool
    original_message_id: Optional[str] = None
    similarity_score: float = 0.0
    detection_reason: str = ""

class TextNormalizer:
    """文本规范化器 - 统一处理各种变体"""

    def __init__(self):
        # 编译正则表达式，提高性能
        # 只保留安全且必要的正则
        self.re_repeated_punct = re.compile(r"([!！?？。．…·、,，.]{2,})")
        # 正确的emoji Unicode范围，不会删除中文
        self.re_emoji = re.compile(r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U0001F900-\U0001F9FF\U0001FA70-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]+")

    def normalize(self, text: str) -> str:
        """
        文本规范化主函数

        Args:
            text: 原始文本

        Returns:
            规范化后的文本
        """
        if not text or not text.strip():
            return ""

        try:
            # 1. Unicode规范化
            text = unicodedata.normalize("NFKC", text)

            # 2. 统一大小写（中文不变，英文小写）
            text = text.lower()

            # 3. 删除emoji（使用正确的Unicode范围）
            text = self.re_emoji.sub("", text)

            # 4. 折叠重复标点
            text = self.re_repeated_punct.sub(lambda m: m.group(0)[0], text)

            # 5. 折叠空白字符
            text = re.sub(r"\s+", " ", text).strip()

            return text

        except Exception as e:
            logger.error(f"文本规范化失败: {e}")
            return text.strip()

class SimHashCalculator:
    """SimHash指纹计算器"""

    def __init__(self):
        self.hash_bits = 64

    def calculate(self, text: str) -> int:
        """
        计算文本的SimHash值

        Args:
            text: 规范化后的文本

        Returns:
            64位SimHash值
        """
        if not text:
            return 0

        try:
            # 生成3-gram特征
            features = self._extract_features(text)

            if not features:
                return 0

            # 计算SimHash
            return self._compute_simhash(features)

        except Exception as e:
            logger.error(f"SimHash计算失败: {e}")
            return 0

    def _extract_features(self, text: str) -> List[str]:
        """提取3-gram特征"""
        if len(text) < 3:
            return [text]

        features = []
        for i in range(len(text) - 2):
            features.append(text[i:i+3])

        return features

    def _compute_simhash(self, features: List[str]) -> int:
        """计算SimHash值"""
        vector = [0] * self.hash_bits

        for feature in features:
            # 计算特征哈希
            feature_hash = hashlib.md5(feature.encode('utf-8')).hexdigest()
            feature_int = int(feature_hash, 16)

            # 更新累加向量
            for i in range(self.hash_bits):
                bit = (feature_int >> i) & 1
                if bit:
                    vector[i] += 1
                else:
                    vector[i] -= 1

        # 生成最终SimHash
        simhash = 0
        for i in range(self.hash_bits):
            if vector[i] > 0:
                simhash |= (1 << i)

        return simhash

    def hamming_distance(self, hash1: int, hash2: int) -> int:
        """计算汉明距离"""
        return (hash1 ^ hash2).bit_count()

class SimilarityCalculator:
    """相似度计算器"""

    def __init__(self):
        # 延迟导入rapidfuzz，避免启动时依赖问题
        self._rapidfuzz = None

    @property
    def rapidfuzz(self):
        """延迟导入rapidfuzz"""
        if self._rapidfuzz is None:
            try:
                from rapidfuzz import fuzz
                self._rapidfuzz = fuzz
            except ImportError:
                logger.warning("rapidfuzz未安装，使用简化相似度算法")
                self._rapidfuzz = None
        return self._rapidfuzz

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度

        Args:
            text1: 文本1（已规范化）
            text2: 文本2（已规范化）

        Returns:
            相似度分数 (0.0 - 1.0)
        """
        if not text1 or not text2:
            return 0.0

        try:
            # 快速长度检查
            len_diff = abs(len(text1) - len(text2)) / max(len(text1), len(text2), 1)
            if len_diff > 0.5:  # 长度差异超过50%，直接返回低相似度
                return 0.0

            if self.rapidfuzz:
                # 使用rapidfuzz进行精确计算
                return self.rapidfuzz.token_set_ratio(text1, text2) / 100.0
            else:
                # 简化算法：基于3-gram Jaccard相似度
                return self._jaccard_similarity(text1, text2)

        except Exception as e:
            logger.error(f"相似度计算失败: {e}")
            return 0.0

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """3-gram Jaccard相似度"""
        def get_trigrams(text):
            if len(text) < 3:
                return {text}
            return {text[i:i+3] for i in range(len(text) - 2)}

        grams1 = get_trigrams(text1)
        grams2 = get_trigrams(text2)

        intersection = len(grams1 & grams2)
        union = len(grams1 | grams2)

        return intersection / union if union > 0 else 0.0

class DuplicateDetector:
    """智能消息去重检测器 - 主入口类"""

    def __init__(self):
        self.normalizer = TextNormalizer()
        self.simhash_calculator = SimHashCalculator()
        self.similarity_calculator = SimilarityCalculator()

        # 延迟初始化Redis连接
        self._redis_manager = None

        logger.info("DuplicateDetector初始化完成")

    @property
    def redis_manager(self):
        """延迟初始化Redis管理器"""
        if self._redis_manager is None:
            from app.storage.redis_manager import redis_manager
            self._redis_manager = redis_manager
        return self._redis_manager

    async def detect_duplicate(self, message_content: str, message_id: str) -> DuplicateResult:
        """
        检测消息是否重复

        Args:
            message_content: 消息内容
            message_id: 消息ID (格式: "channel_id:message_id")

        Returns:
            DuplicateResult对象
        """
        try:
            # 1. 快速检查：空内容
            if not message_content or not message_content.strip():
                return DuplicateResult(False, detection_reason="empty_content")

            # 2. 文本规范化
            normalized_content = self.normalizer.normalize(message_content)
            if not normalized_content:
                return DuplicateResult(False, detection_reason="empty_after_normalize")

            # 3. 快筛：SimHash查找候选
            simhash_value = self.simhash_calculator.calculate(normalized_content)
            candidates = await self._find_similar_candidates(simhash_value)

            if not candidates:
                # 无候选，保存指纹并返回
                await self._save_fingerprint(simhash_value, message_id, normalized_content)
                return DuplicateResult(False, detection_reason="no_candidates")

            # 4. 精筛：计算相似度
            best_match, best_score = await self._find_best_match(
                normalized_content, candidates
            )

            if best_match and best_score >= await self._get_similarity_threshold():
                # 找到重复消息
                return DuplicateResult(
                    is_duplicate=True,
                    original_message_id=best_match,
                    similarity_score=best_score,
                    detection_reason="content_similar"
                )
            else:
                # 无重复，保存指纹
                await self._save_fingerprint(simhash_value, message_id, normalized_content)
                return DuplicateResult(
                    False,
                    detection_reason=f"similarity_too_low_{best_score:.3f}" if best_match else "no_similar_match"
                )

        except Exception as e:
            logger.error(f"去重检测失败: {e}")
            return DuplicateResult(False, detection_reason=f"error_{str(e)[:50]}")

    async def _find_similar_candidates(self, simhash_value: int) -> List[str]:
        """根据SimHash查找相似的候选消息"""
        try:
            candidates = []
            max_distance = await self._get_simhash_threshold()

            # 查找精确匹配和近似匹配
            for distance in range(max_distance + 1):
                if distance == 0:
                    # 精确匹配
                    key = f"dup:simhash:{simhash_value}"
                    exact_matches = self.redis_manager.client.smembers(key)
                    candidates.extend(exact_matches)
                else:
                    # 近似匹配（简化处理：只检查翻转少数位的情况）
                    for bit_pos in range(min(distance * 8, 64)):  # 限制搜索范围
                        flipped_hash = simhash_value ^ (1 << bit_pos)
                        key = f"dup:simhash:{flipped_hash}"
                        matches = self.redis_manager.client.smembers(key)
                        candidates.extend(matches)

            # 去重并限制数量
            unique_candidates = list(set(candidates))[:20]  # 最多检查20个候选
            return unique_candidates

        except Exception as e:
            logger.error(f"查找候选消息失败: {e}")
            return []

    async def _find_best_match(self, content: str, candidates: List[str]) -> Tuple[Optional[str], float]:
        """在候选消息中找到最佳匹配"""
        best_match = None
        best_score = 0.0

        try:
            for candidate_id in candidates:
                # 获取候选消息内容
                candidate_content = await self._get_message_content(candidate_id)
                if not candidate_content:
                    continue

                # 计算相似度
                score = self.similarity_calculator.calculate_similarity(content, candidate_content)

                if score > best_score:
                    best_score = score
                    best_match = candidate_id

            return best_match, best_score

        except Exception as e:
            logger.error(f"查找最佳匹配失败: {e}")
            return None, 0.0

    async def _get_message_content(self, message_id: str) -> Optional[str]:
        """获取消息的规范化内容"""
        try:
            # 先从内容缓存查找
            cache_key = f"dup:content:{message_id}"
            cached_content = self.redis_manager.client.get(cache_key)

            if cached_content:
                return cached_content

            # 缓存未命中，从消息存储获取
            if ':' not in message_id:
                return None

            channel_id, msg_id = message_id.split(':', 1)
            message = self.redis_manager.get_message(channel_id, int(msg_id), silent=True)

            if not message:
                return None

            # 规范化内容并缓存
            original_content = message.get('content', '')
            normalized_content = self.normalizer.normalize(original_content)

            if normalized_content:
                # 缓存规范化结果，TTL 7天
                self.redis_manager.client.setex(cache_key, 7 * 24 * 3600, normalized_content)

            return normalized_content

        except Exception as e:
            logger.error(f"获取消息内容失败 {message_id}: {e}")
            return None

    async def _save_fingerprint(self, simhash_value: int, message_id: str, normalized_content: str):
        """保存消息指纹"""
        try:
            # 保存SimHash索引
            simhash_key = f"dup:simhash:{simhash_value}"
            self.redis_manager.client.sadd(simhash_key, message_id)
            self.redis_manager.client.expire(simhash_key, 30 * 24 * 3600)  # 30天TTL

            # 保存内容缓存
            content_key = f"dup:content:{message_id}"
            self.redis_manager.client.setex(content_key, 7 * 24 * 3600, normalized_content)

        except Exception as e:
            logger.error(f"保存消息指纹失败: {e}")

    async def _get_simhash_threshold(self) -> int:
        """获取SimHash海明距离阈值"""
        try:
            from app.services.config_manager import config_manager
            threshold_str = await config_manager.get_config('duplicate_detection.simhash_threshold', '3')
            return int(threshold_str)
        except:
            return 3  # 默认值

    async def _get_similarity_threshold(self) -> float:
        """获取内容相似度阈值"""
        try:
            from app.services.config_manager import config_manager
            threshold_str = await config_manager.get_config('duplicate_detection.content_threshold', '0.92')
            return float(threshold_str)
        except:
            return 0.92  # 默认值

    async def mark_not_duplicate(self, message_id: str, user_id: str) -> bool:
        """
        用户标记消息为非重复

        Args:
            message_id: 消息ID
            user_id: 用户ID

        Returns:
            操作是否成功
        """
        try:
            # 记录用户反馈
            await self._record_feedback(message_id, False, user_id)

            # 基于反馈调整阈值
            await self._adjust_threshold_based_on_feedback()

            logger.info(f"用户 {user_id} 标记消息 {message_id} 为非重复")
            return True

        except Exception as e:
            logger.error(f"标记非重复失败: {e}")
            return False

    async def confirm_duplicate(self, message_id: str, user_id: str) -> bool:
        """
        用户确认消息为重复

        Args:
            message_id: 消息ID
            user_id: 用户ID

        Returns:
            操作是否成功
        """
        try:
            # 记录用户反馈
            await self._record_feedback(message_id, True, user_id)

            # 基于反馈调整阈值
            await self._adjust_threshold_based_on_feedback()

            logger.info(f"用户 {user_id} 确认消息 {message_id} 为重复")
            return True

        except Exception as e:
            logger.error(f"确认重复失败: {e}")
            return False

    async def _record_feedback(self, message_id: str, is_duplicate: bool, user_id: str):
        """记录用户反馈"""
        try:
            feedback_key = f"dup:feedback:{message_id}"
            feedback_data = {
                "is_duplicate": str(is_duplicate).lower(),
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }

            self.redis_manager.client.hmset(feedback_key, feedback_data)
            self.redis_manager.client.expire(feedback_key, 90 * 24 * 3600)  # 90天TTL

            # 添加到反馈历史列表
            history_key = "dup:feedback_history"
            self.redis_manager.client.lpush(history_key, message_id)
            self.redis_manager.client.ltrim(history_key, 0, 999)  # 保留最近1000条

        except Exception as e:
            logger.error(f"记录用户反馈失败: {e}")

    async def _adjust_threshold_based_on_feedback(self):
        """基于用户反馈调整阈值（简化版本）"""
        try:
            # 获取最近100条反馈
            history_key = "dup:feedback_history"
            recent_message_ids = self.redis_manager.client.lrange(history_key, 0, 99)

            if len(recent_message_ids) < 20:  # 反馈太少，不调整
                return

            false_positives = 0  # 误报：系统认为重复，用户说不重复
            false_negatives = 0  # 漏报：系统认为不重复，用户说重复

            for message_id in recent_message_ids:
                feedback_key = f"dup:feedback:{message_id}"
                feedback = self.redis_manager.client.hgetall(feedback_key)

                if not feedback:
                    continue

                user_says_duplicate = feedback.get('is_duplicate', 'false').lower() == 'true'

                # 这里需要获取系统的原始判断，简化处理
                # 实际实现中可以在检测时记录系统判断
                if not user_says_duplicate:
                    false_positives += 1
                # 漏报检测需要更复杂的逻辑，这里先忽略

            # 简化调整策略
            false_positive_rate = false_positives / len(recent_message_ids)

            if false_positive_rate > 0.15:  # 误报率超过15%，提高阈值
                current_threshold = await self._get_similarity_threshold()
                new_threshold = min(0.98, current_threshold + 0.02)

                # 这里应该更新配置，简化处理先记录日志
                logger.info(f"检测到高误报率({false_positive_rate:.2%})，建议提高阈值至 {new_threshold:.3f}")

        except Exception as e:
            logger.error(f"阈值调整失败: {e}")

# 全局实例
duplicate_detector = DuplicateDetector()