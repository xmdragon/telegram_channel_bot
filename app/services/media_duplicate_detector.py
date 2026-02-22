"""
媒体文件去重检测器 - 使用感知哈希（pHash）进行图片/视频缩略图相似度检测
"""
import logging
import time
from datetime import timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

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
        except ImportError as e:
            logger.error(f"媒体去重依赖库未安装: {e}")
            raise ImportError("需要安装imagehash和pillow库")

@dataclass
class MediaDuplicateResult:
    """媒体去重检测结果"""
    is_duplicate: bool
    original_message_id: Optional[str] = None
    similarity_score: float = 0.0
    detection_reason: str = ""
    detection_method: str = "media"

class MediaDuplicateDetector:
    """媒体文件去重检测器 - 使用感知哈希进行相似度检测"""

    def __init__(self):
        self._db = None
        self.phash_threshold = 5
        self.standard_size = (256, 256)
        self._hash_cache = {}
        self._phash_segment_bits = 16
        self._phash_segment_hex = max(1, self._phash_segment_bits // 4)
        self._phash_segment_count = max(1, 64 // self._phash_segment_bits)
        self._max_bucket_queries = 80
        self._max_similarity_candidates = 200
        self._retention_ttl_seconds: Optional[int] = None
        self._retention_ttl_last_fetch: float = 0.0

    @property
    def db_manager(self):
        """延迟初始化数据库管理器"""
        if self._db is None:
            from app.storage.database import db_manager
            self._db = db_manager
        return self._db

    def _get_conn(self):
        return self.db_manager._get_connection()

    def _calc_expires(self, ttl_seconds: int) -> str:
        return (get_current_time() + timedelta(seconds=ttl_seconds)).isoformat()

    async def detect_duplicate(
        self, media_path: str, message_id: str,
        file_size: Optional[int] = None
    ) -> MediaDuplicateResult:
        """检测媒体文件是否重复"""
        try:
            _ensure_dependencies()
            return await self._do_detect(media_path, message_id, file_size)
        except ImportError:
            return MediaDuplicateResult(
                is_duplicate=False, detection_reason="dependencies_missing")
        except Exception as e:
            logger.error(f"媒体去重检测失败 {media_path}: {e}")
            return MediaDuplicateResult(
                is_duplicate=False,
                detection_reason=f"error_{str(e)[:50]}")

    async def _do_detect(
        self, media_path: str, message_id: str,
        file_size: Optional[int]
    ) -> MediaDuplicateResult:
        """执行去重检测核心逻辑"""
        if file_size:
            result = await self._check_size_match(
                file_size, message_id, media_path)
            if result:
                return result
        if not Path(media_path).exists():
            return MediaDuplicateResult(
                is_duplicate=False, detection_reason="file_not_found")
        hash_values = await self._calculate_hashes(media_path)
        if not hash_values:
            return MediaDuplicateResult(
                is_duplicate=False, detection_reason="hash_calculation_failed")
        similar = await self._find_similar_images(
            hash_values['phash'], message_id)
        if similar:
            best = similar[0]
            similarity = 1.0 - (best['distance'] / 64.0)
            logger.info(
                f"发现相似媒体: {message_id} -> {best['message_id']} "
                f"(距离: {best['distance']}, 相似度: {similarity:.3f})")
            return MediaDuplicateResult(
                is_duplicate=True,
                original_message_id=best['message_id'],
                similarity_score=similarity,
                detection_reason=f"phash_distance_{best['distance']}")
        await self._save_hash(hash_values, message_id, file_size)
        return MediaDuplicateResult(
            is_duplicate=False, detection_reason="no_similar_media")

    async def _check_size_match(
        self, file_size: int, message_id: str, media_path: str
    ) -> Optional[MediaDuplicateResult]:
        """检查文件大小匹配"""
        dupes = await self._find_by_file_size(file_size, message_id)
        if not dupes:
            return None
        logger.info(
            f"文件大小重复: {message_id} "
            f"(size={file_size}, matches={len(dupes)})")
        if not Path(media_path).exists():
            return MediaDuplicateResult(
                is_duplicate=True, original_message_id=dupes[0],
                similarity_score=0.95,
                detection_reason=f"same_file_size_{file_size}")
        return None

    async def _find_by_file_size(
        self, file_size: int, exclude_id: str
    ) -> List[str]:
        """根据文件大小查找可能重复的消息"""
        try:
            conn = self._get_conn()
            now = get_current_time().isoformat()
            rows = conn.execute(
                """SELECT message_id FROM media_sizes
                   WHERE file_size = ?
                   AND (expires_at IS NULL OR expires_at > ?)""",
                (file_size, now),
            ).fetchall()
            real_exclude = self._get_real_message_id(exclude_id)
            return [
                r[0] for r in rows
                if r[0] and r[0] != real_exclude and r[0] != exclude_id
            ]
        except Exception as e:
            logger.error(f"按文件大小查找失败: {e}")
            return []

    async def detect_duplicate_batch(
        self, media_paths: List[str], message_id: str
    ) -> MediaDuplicateResult:
        """批量检测多个媒体文件（用于组消息）"""
        for idx, media_path in enumerate(media_paths):
            sub_id = f"{message_id}:media{idx}"
            result = await self.detect_duplicate(media_path, sub_id)
            if result.is_duplicate:
                result.detection_reason = f"media_{idx}_in_group_duplicate"
                return result
        return MediaDuplicateResult(
            is_duplicate=False,
            detection_reason="no_media_duplicate_in_group")

    def _split_phash_into_segments(self, phash: str) -> List[str]:
        if not phash:
            return []
        seg_len = self._phash_segment_hex
        req_len = seg_len * self._phash_segment_count
        if len(phash) < req_len:
            phash = phash.ljust(req_len, '0')
        return [
            phash[i * seg_len:(i + 1) * seg_len]
            for i in range(self._phash_segment_count)
        ]

    def _compose_band_bucket_key(self, band_idx: int, seg: str) -> str:
        return f"media:phash:band:{band_idx}:{seg}"

    def _generate_segment_neighbors(
        self, segment: str, limit: int = 8
    ) -> List[str]:
        neighbors: List[str] = []
        try:
            value = int(segment, 16)
        except ValueError:
            return neighbors
        for bit in range(self._phash_segment_bits):
            neighbors.append(
                f"{(value ^ (1 << bit)):0{self._phash_segment_hex}x}")
            if len(neighbors) >= limit:
                break
        return neighbors

    def _generate_band_bucket_keys(self, phash: str) -> List[str]:
        segments = self._split_phash_into_segments(phash)
        keys: List[str] = []
        for idx, seg in enumerate(segments):
            keys.append(self._compose_band_bucket_key(idx, seg))
            for nb in self._generate_segment_neighbors(seg):
                keys.append(self._compose_band_bucket_key(idx, nb))
                if len(keys) >= self._max_bucket_queries:
                    break
            if len(keys) >= self._max_bucket_queries:
                break
        return keys

    def _get_band_bucket_keys_for_storage(self, phash: str) -> List[str]:
        segments = self._split_phash_into_segments(phash)
        return [
            self._compose_band_bucket_key(i, s)
            for i, s in enumerate(segments)
        ]

    def _generate_legacy_bucket_keys(self, phash: str) -> List[str]:
        if not phash:
            return []
        prefix = phash[:6]
        keys = {f"media:phash:bucket:{prefix}"}
        if prefix:
            last = prefix[-1]
            for c in '0123456789abcdef':
                if c == last:
                    continue
                keys.add(f"media:phash:bucket:{prefix[:-1]}{c}")
                if len(keys) >= 6:
                    break
        return list(keys)

    async def _get_retention_ttl(self) -> int:
        now = time.time()
        if self._retention_ttl_seconds and (
            now - self._retention_ttl_last_fetch) < 300:
            return self._retention_ttl_seconds
        try:
            from app.services.config_manager import config_manager
            days = await config_manager.get_config(
                'duplicate_detection.retention_days', 30)
            days = float(days)
        except Exception:
            days = 30.0
        self._retention_ttl_seconds = max(1, int(days * 86400))
        self._retention_ttl_last_fetch = now
        return self._retention_ttl_seconds

    async def _calculate_hashes(
        self, media_path: str
    ) -> Optional[Dict[str, str]]:
        """计算图片的感知哈希"""
        if media_path in self._hash_cache:
            return self._hash_cache[media_path]
        try:
            img = Image.open(media_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img = img.resize(self.standard_size, Image.Resampling.LANCZOS)
            hv = {
                'phash': str(imagehash.phash(img)),
                'dhash': str(imagehash.dhash(img)),
                'whash': str(imagehash.whash(img)),
                'average_hash': str(imagehash.average_hash(img)),
            }
            if len(self._hash_cache) > 1000:
                for k in list(self._hash_cache.keys())[:500]:
                    del self._hash_cache[k]
            self._hash_cache[media_path] = hv
            return hv
        except Exception as e:
            logger.error(f"计算图片哈希失败 {media_path}: {e}")
            return None

    async def _find_similar_images(
        self, phash: str, current_message_id: str
    ) -> List[Dict[str, Any]]:
        """查找相似的图片"""
        try:
            seen_keys = set()
            bucket_seq = []
            for k in (self._generate_band_bucket_keys(phash)
                      + self._generate_legacy_bucket_keys(phash)):
                if k not in seen_keys:
                    seen_keys.add(k)
                    bucket_seq.append(k)
            raw = self._query_buckets(bucket_seq)
            if raw:
                raw = list(dict.fromkeys(raw))
            return self._filter_candidates(
                raw, phash, current_message_id)
        except Exception as e:
            logger.error(f"查找相似图片失败: {e}")
            return []

    def _query_buckets(self, bucket_keys: List[str]) -> List[str]:
        """从SQLite查询桶中的候选项"""
        conn = self._get_conn()
        now = get_current_time().isoformat()
        candidates: List[str] = []
        for bk in bucket_keys:
            try:
                rows = conn.execute(
                    """SELECT payload FROM media_lsh_buckets
                       WHERE bucket_key = ?
                       AND (expires_at IS NULL OR expires_at > ?)""",
                    (bk, now),
                ).fetchall()
                for r in rows:
                    if r[0]:
                        candidates.append(r[0])
            except Exception as e:
                logger.debug(f"读取桶失败 {bk}: {e}")
            if len(candidates) >= self._max_similarity_candidates:
                break
        return candidates

    def _filter_candidates(
        self, candidates: List[str], phash: str,
        current_message_id: str
    ) -> List[Dict[str, Any]]:
        """过滤候选项，计算汉明距离"""
        cur_real = self._get_real_message_id(current_message_id)
        seen_ids = set()
        similar: List[Dict[str, Any]] = []
        for cand in candidates:
            if ':' not in cand:
                continue
            parts = cand.split(':', 1)
            if len(parts) != 2:
                continue
            stored_hash, full_id = parts
            real_id = self._get_real_message_id(full_id)
            if not real_id or real_id == cur_real or real_id in seen_ids:
                continue
            dist = self._hamming_distance(phash, stored_hash)
            if dist <= self.phash_threshold:
                seen_ids.add(real_id)
                similar.append({
                    'message_id': real_id,
                    'distance': dist, 'hash': stored_hash})
        similar.sort(key=lambda x: x['distance'])
        return similar

    async def _save_hash(
        self, hash_values: Dict[str, str],
        message_id: str, file_size: Optional[int] = None
    ):
        """保存图片哈希到SQLite"""
        try:
            phash = hash_values['phash']
            real_id = self._get_real_message_id(message_id)
            ttl = await self._get_retention_ttl()
            expires = self._calc_expires(ttl)
            payload = f"{phash}:{real_id}"
            self._save_lsh_buckets(phash, payload, expires)
            self._save_fingerprint(
                hash_values, real_id, message_id, expires)
            if file_size:
                self._save_file_size(file_size, real_id, expires)
            logger.debug(f"保存媒体哈希: {real_id} -> phash:{phash[:8]}...")
        except Exception as e:
            logger.error(f"保存图片哈希失败: {e}")

    def _save_lsh_buckets(
        self, phash: str, payload: str, expires: str
    ):
        """保存LSH桶数据（分段桶+遗留桶）"""
        conn = self._get_conn()
        all_keys = self._get_band_bucket_keys_for_storage(phash)
        all_keys.append(f"media:phash:bucket:{phash[:6]}")
        for bk in all_keys:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO media_lsh_buckets
                       (bucket_key, payload, expires_at)
                       VALUES (?, ?, ?)""",
                    (bk, payload, expires))
            except Exception as e:
                logger.debug(f"写入桶失败 {bk}: {e}")
        conn.commit()

    def _save_fingerprint(
        self, hv: Dict[str, str],
        real_id: str, original_id: str, expires: str
    ):
        """保存指纹记录"""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO media_fingerprints
               (message_id, phash, dhash, whash, average_hash,
                original_id, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (real_id, hv['phash'], hv['dhash'], hv['whash'],
             hv['average_hash'], original_id,
             get_current_time().isoformat(), expires))
        conn.commit()

    def _save_file_size(
        self, file_size: int, real_id: str, expires: str
    ):
        """保存文件大小索引"""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO media_sizes
               (file_size, message_id, expires_at)
               VALUES (?, ?, ?)""",
            (file_size, real_id, expires))
        conn.commit()

    def _get_real_message_id(self, message_id: str) -> str:
        """获取真实的消息ID（移除:media后缀）"""
        return message_id.split(':media')[0] if ':media' in message_id else message_id

    def _hamming_distance(self, hash1: str, hash2: str) -> int:
        """计算两个哈希的汉明距离"""
        if len(hash1) != len(hash2):
            return 64
        try:
            return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')
        except ValueError:
            return 64


# 创建全局实例
media_duplicate_detector = MediaDuplicateDetector()

__all__ = [
    'MediaDuplicateDetector',
    'MediaDuplicateResult',
    'media_duplicate_detector'
]
