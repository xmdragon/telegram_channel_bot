"""
媒体文件去重检测器
使用感知哈希（pHash）进行图片/视频缩略图相似度检测
作为文本去重的补充

Author: Claude
Created: 2025-09-24
"""

import logging
import hashlib
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# 延迟导入，避免启动时依赖问题
imagehash = None
Image = None

def _ensure_dependencies():
    """确保依赖库已导入"""
    global imagehash, Image
    if imagehash is None:
        try:
            import imagehash as ih
            from PIL import Image as PILImage
            imagehash = ih
            Image = PILImage
            logger.info("媒体去重依赖库加载成功")
        except ImportError as e:
            logger.error(f"媒体去重依赖库未安装: {e}")
            logger.error("请运行: pip install imagehash pillow")
            raise ImportError("需要安装imagehash和pillow库")


@dataclass
class MediaDuplicateResult:
    """媒体去重检测结果"""
    is_duplicate: bool
    original_message_id: Optional[str] = None
    similarity_score: float = 0.0
    detection_reason: str = ""
    detection_method: str = "media"  # 标记是媒体检测


class MediaDuplicateDetector:
    """
    媒体文件去重检测器
    使用感知哈希进行相似度检测
    """

    def __init__(self):
        self.redis = None  # 延迟初始化
        self.phash_threshold = 5  # 汉明距离阈值（<=5认为相似）
        self.standard_size = (256, 256)  # 标准化尺寸
        self._hash_cache = {}  # 缓存已计算的哈希 {path: hash_values}
        self._phash_segment_bits = 16
        self._phash_segment_hex = max(1, self._phash_segment_bits // 4)
        self._phash_segment_count = max(1, 64 // self._phash_segment_bits)
        self._max_bucket_queries = 80
        self._max_similarity_candidates = 200
        self._retention_ttl_seconds: Optional[int] = None
        self._retention_ttl_last_fetch: float = 0.0

        logger.info("MediaDuplicateDetector初始化完成")

    @property
    def redis_manager(self):
        """延迟初始化Redis管理器"""
        if self.redis is None:
            from app.storage.redis_manager import redis_manager
            self.redis = redis_manager
        return self.redis

    async def detect_duplicate(
        self,
        media_path: str,
        message_id: str,
        file_size: Optional[int] = None
    ) -> MediaDuplicateResult:
        """
        检测媒体文件是否重复

        Args:
            media_path: 媒体文件路径
            message_id: 消息ID (格式: "channel_id:message_id")
            file_size: 文件大小（字节），用于快速比对

        Returns:
            MediaDuplicateResult对象
        """
        try:
            # 确保依赖已加载
            _ensure_dependencies()

            # 1. 快速检查：如果提供了文件大小，先进行文件大小比对
            if file_size:
                size_duplicates = await self._find_by_file_size(file_size, message_id)
                if size_duplicates:
                    logger.info(
                        f"📏 通过文件大小发现潜在重复: {message_id} "
                        f"(大小: {file_size} bytes, 匹配数: {len(size_duplicates)})"
                    )
                    # 如果文件不存在，仅基于文件大小判断（适用于远程Redis场景）
                    if not Path(media_path).exists():
                        # 返回第一个匹配的作为重复
                        return MediaDuplicateResult(
                            is_duplicate=True,
                            original_message_id=size_duplicates[0],
                            similarity_score=0.95,  # 文件大小相同给高分
                            detection_reason=f"same_file_size_{file_size}"
                        )

            # 2. 验证文件存在（如果需要进行哈希计算）
            if not Path(media_path).exists():
                logger.warning(f"媒体文件不存在: {media_path}")
                return MediaDuplicateResult(
                    is_duplicate=False,
                    detection_reason="file_not_found"
                )

            # 3. 计算图片哈希
            hash_values = await self._calculate_hashes(media_path)
            if not hash_values:
                return MediaDuplicateResult(
                    is_duplicate=False,
                    detection_reason="hash_calculation_failed"
                )

            # 4. 查找相似图片
            similar_images = await self._find_similar_images(
                hash_values['phash'],
                message_id
            )

            if similar_images:
                # 找到相似图片
                best_match = similar_images[0]  # 最相似的
                # 汉明距离转换为相似度分数 (0-1)
                similarity = 1.0 - (best_match['distance'] / 64.0)

                logger.info(
                    f"🖼️ 发现相似媒体: {message_id} -> {best_match['message_id']} "
                    f"(汉明距离: {best_match['distance']}, 相似度: {similarity:.3f})"
                )

                return MediaDuplicateResult(
                    is_duplicate=True,
                    original_message_id=best_match['message_id'],
                    similarity_score=similarity,
                    detection_reason=f"phash_distance_{best_match['distance']}"
                )

            # 5. 无相似图片，保存新哈希和文件大小
            await self._save_hash(hash_values, message_id, file_size)

            logger.debug(f"未发现相似媒体: {message_id}")
            return MediaDuplicateResult(
                is_duplicate=False,
                detection_reason="no_similar_media"
            )

        except ImportError:
            # 依赖未安装
            logger.error("媒体去重功能不可用：缺少依赖库")
            return MediaDuplicateResult(
                is_duplicate=False,
                detection_reason="dependencies_missing"
            )
        except Exception as e:
            logger.error(f"媒体去重检测失败 {media_path}: {e}")
            return MediaDuplicateResult(
                is_duplicate=False,
                detection_reason=f"error_{str(e)[:50]}"
            )

    async def _find_by_file_size(self, file_size: int, exclude_id: str) -> List[str]:
        """
        根据文件大小查找可能重复的消息

        Args:
            file_size: 文件大小（字节）
            exclude_id: 要排除的消息ID

        Returns:
            匹配的消息ID列表
        """
        try:
            size_key = f"media:size:{file_size}"
            all_ids = self.redis_manager.client.smembers(size_key)

            if not all_ids:
                return []

            decoded_ids = [
                value.decode('utf-8') if isinstance(value, bytes) else value
                for value in all_ids
            ]

            real_exclude_id = self._get_real_message_id(exclude_id)

            matched_ids = [
                msg_id for msg_id in decoded_ids
                if msg_id and msg_id != real_exclude_id and msg_id != exclude_id
            ]

            try:
                ttl = await self._get_retention_ttl()
                self.redis_manager.client.expire(size_key, ttl)
            except Exception:
                pass

            return matched_ids

        except Exception as e:
            logger.error(f"按文件大小查找失败: {e}")
            return []

    async def detect_duplicate_batch(
        self,
        media_paths: List[str],
        message_id: str
    ) -> MediaDuplicateResult:
        """
        批量检测多个媒体文件（用于组消息）
        任一媒体重复则整组标记为重复

        Args:
            media_paths: 媒体文件路径列表
            message_id: 消息ID

        Returns:
            MediaDuplicateResult对象
        """
        for idx, media_path in enumerate(media_paths):
            sub_id = f"{message_id}:media{idx}"
            result = await self.detect_duplicate(media_path, sub_id)

            if result.is_duplicate:
                # 找到重复，立即返回
                result.detection_reason = f"media_{idx}_in_group_duplicate"
                logger.info(f"组消息媒体 {idx} 检测到重复")
                return result

        # 都不重复
        return MediaDuplicateResult(
            is_duplicate=False,
            detection_reason="no_media_duplicate_in_group"
        )

    def _split_phash_into_segments(self, phash: str) -> List[str]:
        if not phash:
            return []
        segment_len = self._phash_segment_hex
        required_length = segment_len * self._phash_segment_count
        if len(phash) < required_length:
            phash = phash.ljust(required_length, '0')
        return [
            phash[i * segment_len:(i + 1) * segment_len]
            for i in range(self._phash_segment_count)
        ]

    def _compose_band_bucket_key(self, band_index: int, segment: str) -> str:
        return f"media:phash:band:{band_index}:{segment}"

    def _generate_segment_neighbors(self, segment: str, limit: int = 8) -> List[str]:
        neighbors: List[str] = []
        try:
            value = int(segment, 16)
        except ValueError:
            return neighbors

        for bit in range(self._phash_segment_bits):
            neighbor_val = value ^ (1 << bit)
            neighbors.append(f"{neighbor_val:0{self._phash_segment_hex}x}")
            if len(neighbors) >= limit:
                break
        return neighbors

    def _generate_band_bucket_keys(self, phash: str) -> List[str]:
        segments = self._split_phash_into_segments(phash)
        bucket_keys: List[str] = []
        for index, segment in enumerate(segments):
            bucket_keys.append(self._compose_band_bucket_key(index, segment))
            for neighbor in self._generate_segment_neighbors(segment):
                bucket_keys.append(self._compose_band_bucket_key(index, neighbor))
                if len(bucket_keys) >= self._max_bucket_queries:
                    break
            if len(bucket_keys) >= self._max_bucket_queries:
                break
        return bucket_keys

    def _get_band_bucket_keys_for_storage(self, phash: str) -> List[str]:
        segments = self._split_phash_into_segments(phash)
        return [self._compose_band_bucket_key(index, segment) for index, segment in enumerate(segments)]

    def _generate_legacy_bucket_keys(self, phash: str) -> List[str]:
        if not phash:
            return []
        prefix = phash[:6]
        bucket_keys = {f"media:phash:bucket:{prefix}"}

        if prefix:
            last_char = prefix[-1]
            for alt_char in '0123456789abcdef':
                if alt_char == last_char:
                    continue
                candidate = prefix[:-1] + alt_char
                bucket_keys.add(f"media:phash:bucket:{candidate}")
                if len(bucket_keys) >= 6:
                    break
        return list(bucket_keys)

    async def _get_retention_ttl(self) -> int:
        now = time.time()
        if self._retention_ttl_seconds and (now - self._retention_ttl_last_fetch) < 300:
            return self._retention_ttl_seconds

        try:
            from app.services.config_manager import config_manager
            retention_days = await config_manager.get_config('duplicate_detection.retention_days', 30)
            retention_days = float(retention_days)
        except Exception:
            retention_days = 30.0

        ttl_seconds = max(1, int(retention_days * 24 * 3600))
        self._retention_ttl_seconds = ttl_seconds
        self._retention_ttl_last_fetch = now
        return ttl_seconds

    async def _calculate_hashes(self, media_path: str) -> Optional[Dict[str, str]]:
        """
        计算图片的感知哈希

        Args:
            media_path: 图片路径

        Returns:
            哈希值字典
        """
        # 检查缓存
        if media_path in self._hash_cache:
            logger.debug(f"使用缓存的哈希值: {media_path}")
            return self._hash_cache[media_path]

        try:
            # 打开图片
            img = Image.open(media_path)

            # 转换为RGB模式（处理RGBA、灰度等）
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # 标准化尺寸，减少尺寸差异的影响
            img = img.resize(self.standard_size, Image.Resampling.LANCZOS)

            # 计算多种哈希值
            hash_values = {
                'phash': str(imagehash.phash(img)),  # 感知哈希，最稳定
                'dhash': str(imagehash.dhash(img)),  # 差异哈希
                'whash': str(imagehash.whash(img)),  # 小波哈希
                'average_hash': str(imagehash.average_hash(img))  # 平均哈希
            }

            # 缓存结果（限制缓存大小）
            if len(self._hash_cache) > 1000:
                # 清理一半缓存
                keys_to_remove = list(self._hash_cache.keys())[:500]
                for key in keys_to_remove:
                    del self._hash_cache[key]

            self._hash_cache[media_path] = hash_values

            logger.debug(f"计算哈希成功: {media_path} -> phash={hash_values['phash'][:16]}...")
            return hash_values

        except Exception as e:
            logger.error(f"计算图片哈希失败 {media_path}: {e}")
            return None

    async def _find_similar_images(
        self,
        phash: str,
        current_message_id: str
    ) -> List[Dict[str, Any]]:
        """
        查找相似的图片

        Args:
            phash: 感知哈希值
            current_message_id: 当前消息ID

        Returns:
            相似图片列表
        """
        try:
            ttl = await self._get_retention_ttl()
            bucket_sequence: List[str] = []
            seen_bucket_keys = set()

            for bucket_key in self._generate_band_bucket_keys(phash) + self._generate_legacy_bucket_keys(phash):
                if bucket_key not in seen_bucket_keys:
                    seen_bucket_keys.add(bucket_key)
                    bucket_sequence.append(bucket_key)

            raw_candidates: List[str] = []

            for bucket_key in bucket_sequence:
                try:
                    bucket_candidates = self.redis_manager.client.smembers(bucket_key)
                except Exception as redis_error:
                    logger.debug(f"读取桶失败 {bucket_key}: {redis_error}")
                    continue

                if bucket_candidates:
                    for candidate in bucket_candidates:
                        if isinstance(candidate, bytes):
                            candidate = candidate.decode('utf-8')
                        if candidate:
                            raw_candidates.append(candidate)
                    try:
                        self.redis_manager.client.expire(bucket_key, ttl)
                    except Exception:
                        pass

                if len(raw_candidates) >= self._max_similarity_candidates:
                    break

            if raw_candidates:
                raw_candidates = list(dict.fromkeys(raw_candidates))

            current_real_id = self._get_real_message_id(current_message_id)
            seen_message_ids = set()
            similar: List[Dict[str, Any]] = []

            for candidate in raw_candidates:
                if ':' not in candidate:
                    continue

                parts = candidate.split(':', 1)
                if len(parts) != 2:
                    continue

                stored_hash, full_msg_id = parts
                real_msg_id = self._get_real_message_id(full_msg_id)

                if not real_msg_id or real_msg_id == current_real_id or real_msg_id in seen_message_ids:
                    continue

                distance = self._hamming_distance(phash, stored_hash)
                if distance <= self.phash_threshold:
                    similar.append({
                        'message_id': real_msg_id,
                        'distance': distance,
                        'hash': stored_hash
                    })
                    seen_message_ids.add(real_msg_id)

                    meta_key = f"media:meta:{real_msg_id}"
                    try:
                        self.redis_manager.client.expire(meta_key, ttl)
                    except Exception:
                        pass

                    logger.debug(f"发现相似图片: {real_msg_id} (距离: {distance})")

            similar.sort(key=lambda x: x['distance'])
            return similar

        except Exception as e:
            logger.error(f"查找相似图片失败: {e}")
            return []

    async def _save_hash(self, hash_values: Dict[str, str], message_id: str, file_size: Optional[int] = None):
        """
        保存图片哈希到Redis

        Args:
            hash_values: 哈希值字典
            message_id: 消息ID
            file_size: 文件大小（可选）
        """
        try:
            phash = hash_values['phash']

            real_msg_id = self._get_real_message_id(message_id)
            ttl = await self._get_retention_ttl()

            payload = f"{phash}:{real_msg_id}"

            for bucket_key in self._get_band_bucket_keys_for_storage(phash):
                try:
                    self.redis_manager.client.sadd(bucket_key, payload)
                    self.redis_manager.client.expire(bucket_key, ttl)
                except Exception as redis_error:
                    logger.debug(f"写入分段桶失败 {bucket_key}: {redis_error}")

            legacy_bucket_key = f"media:phash:bucket:{phash[:6]}"
            try:
                self.redis_manager.client.sadd(legacy_bucket_key, payload)
                self.redis_manager.client.expire(legacy_bucket_key, ttl)
            except Exception:
                pass

            meta_key = f"media:meta:{real_msg_id}"
            hash_values['original_id'] = message_id
            self.redis_manager.client.hset(meta_key, mapping=hash_values)
            self.redis_manager.client.expire(meta_key, ttl)

            if ':media' in message_id:
                mapping_key = f"media:mapping:{message_id}"
                self.redis_manager.client.set(mapping_key, real_msg_id)
                self.redis_manager.client.expire(mapping_key, ttl)

            if file_size:
                size_key = f"media:size:{file_size}"
                self.redis_manager.client.sadd(size_key, real_msg_id)
                self.redis_manager.client.expire(size_key, ttl)
                logger.debug(f"保存文件大小索引: {file_size} -> {real_msg_id}")

            logger.debug(f"保存媒体哈希: {real_msg_id} -> phash:{phash[:8]}...")

        except Exception as e:
            logger.error(f"保存图片哈希失败: {e}")

    def _get_real_message_id(self, message_id: str) -> str:
        """
        获取真实的消息ID（移除:media后缀）

        Args:
            message_id: 可能包含:media后缀的消息ID

        Returns:
            真实的消息ID
        """
        return message_id.split(':media')[0] if ':media' in message_id else message_id

    def _hamming_distance(self, hash1: str, hash2: str) -> int:
        """
        计算两个哈希的汉明距离

        Args:
            hash1: 第一个哈希值（16进制字符串）
            hash2: 第二个哈希值（16进制字符串）

        Returns:
            汉明距离（不同位的数量）
        """
        if len(hash1) != len(hash2):
            return 64  # 最大距离

        try:
            # 转换为整数
            int1 = int(hash1, 16)
            int2 = int(hash2, 16)

            # XOR操作找出不同的位
            xor = int1 ^ int2

            # 计算1的个数（汉明距离）
            distance = bin(xor).count('1')

            return distance

        except ValueError:
            logger.error(f"无效的哈希值: {hash1[:8]}... or {hash2[:8]}...")
            return 64


# 创建全局实例
media_duplicate_detector = MediaDuplicateDetector()


# 导出
__all__ = [
    'MediaDuplicateDetector',
    'MediaDuplicateResult',
    'media_duplicate_detector'
]
