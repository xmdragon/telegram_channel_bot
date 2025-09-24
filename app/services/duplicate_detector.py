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
                # 针对中文优化的相似度计算
                # 使用ratio代替token_set_ratio，更适合中文连续文本
                ratio_score = self.rapidfuzz.ratio(text1, text2) / 100.0
                partial_score = self.rapidfuzz.partial_ratio(text1, text2) / 100.0
                # 取两者较高值，提高中文检测准确率
                return max(ratio_score, partial_score)
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
                # 无候选，保存指纹并记录系统检测结果
                await self._save_fingerprint(simhash_value, message_id, normalized_content)
                await self._record_system_detection(message_id, False, 0.0)
                return DuplicateResult(False, detection_reason="no_candidates")

            # 4. 精筛：计算相似度（排除自身）
            best_match, best_score = await self._find_best_match(
                normalized_content, candidates, exclude_message_id=message_id
            )

            if best_match and best_score >= await self._get_similarity_threshold():
                # 找到重复消息，记录系统检测结果
                await self._record_system_detection(message_id, True, best_score)
                return DuplicateResult(
                    is_duplicate=True,
                    original_message_id=best_match,
                    similarity_score=best_score,
                    detection_reason="content_similar"
                )
            else:
                # 无重复，保存指纹并记录系统检测结果
                await self._save_fingerprint(simhash_value, message_id, normalized_content)
                await self._record_system_detection(message_id, False, best_score)
                return DuplicateResult(
                    False,
                    detection_reason=f"similarity_too_low_{best_score:.3f}" if best_match else "no_similar_match"
                )

        except Exception as e:
            logger.error(f"去重检测失败: {e}")
            return DuplicateResult(False, detection_reason=f"error_{str(e)[:50]}")

    def _get_lsh_buckets(self, simhash_int: int) -> List[str]:
        """
        将SimHash分成4个16位段，用于LSH分桶
        复杂度从O(C(64,3))降到O(4)
        """
        buckets = []
        for i in range(4):
            segment = (simhash_int >> (i * 16)) & 0xFFFF
            buckets.append(f"dup:simhash:band:{i}:{segment:04x}")
        return buckets

    def _calculate_hamming_distance(self, hash1: int, hash2: int) -> int:
        """计算两个SimHash的汉明距离"""
        return bin(hash1 ^ hash2).count('1')

    async def _find_similar_candidates(self, simhash_value: int) -> List[str]:
        """使用LSH分桶快速查找候选，避免组合爆炸"""
        try:
            candidates = set()

            # 获取TTL配置（用于保活）
            from app.services.config_manager import config_manager
            ttl_hours = await config_manager.get_config('duplicate_detection.ttl_hours', 24)
            ttl = int(ttl_hours) * 3600

            # 1. 精确匹配
            exact_key = f"dup:simhash:{simhash_value}"
            exact_matches = self.redis_manager.client.smembers(exact_key)
            if exact_matches:
                candidates.update(exact_matches)
                # 刷新TTL（保活机制）
                self.redis_manager.client.expire(exact_key, ttl)

            # 2. LSH分桶查找（只需4次Redis查询）
            bucket_keys = self._get_lsh_buckets(simhash_value)

            # 使用pipeline批量查询减少round-trip
            pipeline = self.redis_manager.client.pipeline()
            for key in bucket_keys:
                pipeline.smembers(key)
            bucket_results = pipeline.execute()

            # 合并所有桶的候选，并刷新命中桶的TTL
            for i, bucket_candidates in enumerate(bucket_results):
                if bucket_candidates:
                    candidates.update(bucket_candidates)
                    # 刷新命中桶的TTL（保活机制）
                    self.redis_manager.client.expire(bucket_keys[i], ttl)

            # 3. 后过滤：用真正的汉明距离验证
            threshold = await self._get_simhash_threshold()
            filtered_candidates = []

            for candidate_id in candidates:
                # 获取候选的SimHash值进行距离验证
                candidate_hash_key = f"dup:content:{candidate_id}"
                candidate_hash_str = self.redis_manager.client.hget(candidate_hash_key, 'simhash')

                if candidate_hash_str:
                    try:
                        candidate_hash = int(candidate_hash_str)
                        distance = self._calculate_hamming_distance(simhash_value, candidate_hash)
                        if distance <= threshold:
                            filtered_candidates.append(candidate_id)
                    except (ValueError, TypeError):
                        # 处理损坏的哈希值
                        continue

            return filtered_candidates[:20]  # 限制候选数量

        except Exception as e:
            logger.error(f"查找候选消息失败: {e}")
            return []

    async def _find_best_match(self, content: str, candidates: List[str], exclude_message_id: Optional[str] = None) -> Tuple[Optional[str], float]:
        """在候选消息中找到最佳匹配"""
        best_match = None
        best_score = 0.0

        try:
            for candidate_id in candidates:
                # 排除自身比较
                if exclude_message_id and candidate_id == exclude_message_id:
                    continue

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
        """获取消息的规范化内容（优先从缓存读取）"""
        try:
            # 优先从去重缓存读取
            content_key = f"dup:content:{message_id}"
            cached_content = self.redis_manager.client.hget(content_key, 'text')

            if cached_content:
                # 刷新TTL（保活机制）
                from app.services.config_manager import config_manager
                ttl_hours = await config_manager.get_config('duplicate_detection.ttl_hours', 24)
                ttl = int(ttl_hours) * 3600
                self.redis_manager.client.expire(content_key, ttl)
                return cached_content

            # 如果缓存中没有，尝试从消息本体读取（兼容旧数据）
            if ':' not in message_id:
                return None

            channel_id, msg_id = message_id.split(':', 1)
            message = self.redis_manager.get_message(channel_id, int(msg_id), silent=True)

            if not message:
                return None

            # 直接使用过滤后内容
            filtered_content = message.get('filtered_content', '')
            return self.normalizer.normalize(filtered_content)

        except Exception as e:
            logger.error(f"获取消息内容失败 {message_id}: {e}")
            return None

    async def _save_fingerprint(self, simhash_value: int, message_id: str, normalized_content: str):
        """保存消息指纹到精确索引和LSH分桶索引"""
        try:
            # 获取TTL配置
            from app.services.config_manager import config_manager
            ttl_hours = await config_manager.get_config('duplicate_detection.ttl_hours', 24)
            ttl = int(ttl_hours) * 3600

            # 1. 精确索引
            exact_key = f"dup:simhash:{simhash_value}"
            self.redis_manager.client.sadd(exact_key, message_id)
            self.redis_manager.client.expire(exact_key, ttl)

            # 2. LSH分桶索引
            bucket_keys = self._get_lsh_buckets(simhash_value)
            for bucket_key in bucket_keys:
                self.redis_manager.client.sadd(bucket_key, message_id)
                self.redis_manager.client.expire(bucket_key, ttl)

            # 3. 保存完整内容和SimHash值（不依赖消息本体）
            content_key = f"dup:content:{message_id}"
            self.redis_manager.client.hset(content_key, mapping={
                'text': normalized_content,  # 保存过滤后的文本内容
                'simhash': str(simhash_value),
                'length': len(normalized_content),
                'timestamp': datetime.now().isoformat()
            })
            self.redis_manager.client.expire(content_key, ttl)

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

    async def _record_system_detection(self, message_id: str, detected: bool, similarity_score: float = 0.0):
        """记录系统检测结果"""
        try:
            detection_key = f"dup:detection:{message_id}"
            self.redis_manager.client.hset(detection_key, mapping={
                'system_detected': str(detected).lower(),
                'similarity_score': str(similarity_score),
                'detection_time': datetime.now().isoformat()
            })
            self.redis_manager.client.expire(detection_key, 30 * 24 * 3600)  # 30天过期
        except Exception as e:
            logger.error(f"记录系统检测失败: {e}")

    async def _record_user_feedback(self, message_id: str, user_confirmed: bool, user_id: str):
        """记录用户反馈"""
        try:
            detection_key = f"dup:detection:{message_id}"
            self.redis_manager.client.hset(detection_key, mapping={
                'user_confirmed': str(user_confirmed).lower(),
                'user_id': user_id,
                'feedback_time': datetime.now().isoformat()
            })

            # 添加到反馈历史列表
            history_key = "dup:feedback_history"
            self.redis_manager.client.lpush(history_key, message_id)
            self.redis_manager.client.ltrim(history_key, 0, 999)  # 保留最近1000条

        except Exception as e:
            logger.error(f"记录用户反馈失败: {e}")

    # 保持向后兼容的旧方法
    async def _record_feedback(self, message_id: str, is_duplicate: bool, user_id: str):
        """记录用户反馈（向后兼容方法）"""
        await self._record_user_feedback(message_id, is_duplicate, user_id)

    async def _adjust_threshold_based_on_feedback(self):
        """基于用户反馈调整阈值"""
        try:
            # 获取最近100条反馈
            history_key = "dup:feedback_history"
            recent_message_ids = self.redis_manager.client.lrange(history_key, 0, 99)

            if len(recent_message_ids) < 20:  # 反馈太少，不调整
                return

            false_positives = 0  # 误报：系统认为重复，用户说不重复
            false_negatives = 0  # 漏报：系统认为不重复，用户说重复
            total_feedback = 0

            for message_id in recent_message_ids:
                detection_key = f"dup:detection:{message_id}"
                detection_data = self.redis_manager.client.hgetall(detection_key)

                if not detection_data:
                    continue

                # 正确获取系统判断和用户反馈
                system_detected = detection_data.get('system_detected', 'false').lower() == 'true'
                user_confirmed = detection_data.get('user_confirmed', 'false').lower() == 'true'

                total_feedback += 1

                # 计算误报和漏报
                if system_detected and not user_confirmed:
                    false_positives += 1  # 系统说重复，用户说不重复
                elif not system_detected and user_confirmed:
                    false_negatives += 1  # 系统说不重复，用户说重复

            if total_feedback == 0:
                return

            # 计算准确的误报率和漏报率
            false_positive_rate = false_positives / total_feedback
            false_negative_rate = false_negatives / total_feedback

            # 动态调整策略
            current_threshold = await self._get_similarity_threshold()
            adjustment = 0

            if false_positive_rate > 0.15:  # 误报率过高，提高阈值
                adjustment = min(0.02, false_positive_rate * 0.1)
            elif false_negative_rate > 0.15:  # 漏报率过高，降低阈值
                adjustment = -min(0.02, false_negative_rate * 0.1)

            if abs(adjustment) > 0.005:  # 只有调整幅度足够大才执行
                new_threshold = max(0.6, min(0.98, current_threshold + adjustment))
                logger.info(f"反馈统计: 误报率{false_positive_rate:.2%}, 漏报率{false_negative_rate:.2%}, 调整阈值: {current_threshold:.3f} -> {new_threshold:.3f}")
                # 这里应该更新配置到system.json

        except Exception as e:
            logger.error(f"阈值调整失败: {e}")


# 全局实例
duplicate_detector = DuplicateDetector()