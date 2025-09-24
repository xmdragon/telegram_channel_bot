"""
媒体文件去重检测器
使用感知哈希（pHash）进行图片/视频缩略图相似度检测
作为文本去重的补充

Author: Claude
Created: 2025-09-24
"""

import logging
import hashlib
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
        message_id: str
    ) -> MediaDuplicateResult:
        """
        检测媒体文件是否重复

        Args:
            media_path: 媒体文件路径
            message_id: 消息ID (格式: "channel_id:message_id")

        Returns:
            MediaDuplicateResult对象
        """
        try:
            # 确保依赖已加载
            _ensure_dependencies()

            # 验证文件存在
            if not Path(media_path).exists():
                logger.warning(f"媒体文件不存在: {media_path}")
                return MediaDuplicateResult(
                    is_duplicate=False,
                    detection_reason="file_not_found"
                )

            # 1. 计算图片哈希
            hash_values = await self._calculate_hashes(media_path)
            if not hash_values:
                return MediaDuplicateResult(
                    is_duplicate=False,
                    detection_reason="hash_calculation_failed"
                )

            # 2. 查找相似图片
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

            # 3. 无相似图片，保存新哈希
            await self._save_hash(hash_values, message_id)

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
            similar = []
            candidates_seen = set()  # 避免重复检查

            # 使用6位前缀（24bit）进行粗分桶，提高召回率
            bucket_prefix = phash[:6]

            # 策略1：查询原始桶
            bucket_keys = [f"media:phash:bucket:{bucket_prefix}"]

            # 策略2：邻桶搜索 - 对前缀最后一位做扰动（提高召回率）
            # 生成邻近的桶（汉明距离1的变化）
            last_char = bucket_prefix[-1]
            for alt_char in '0123456789abcdef':
                if alt_char != last_char:
                    neighbor_prefix = bucket_prefix[:-1] + alt_char
                    bucket_keys.append(f"media:phash:bucket:{neighbor_prefix}")
                    # 只查询最相近的4个邻桶，避免过多查询
                    if len(bucket_keys) >= 5:
                        break

            # 从所有相关桶中获取候选
            all_candidates = set()
            for bucket_key in bucket_keys:
                bucket_candidates = self.redis_manager.client.smembers(bucket_key)
                if bucket_candidates:
                    all_candidates.update(bucket_candidates)

            # 处理所有候选
            for candidate in all_candidates:
                # 关键修复：解码bytes为字符串
                if isinstance(candidate, bytes):
                    candidate = candidate.decode('utf-8')

                if not candidate or ':' not in candidate:
                    continue

                # 格式: "hash:channel_id:message_id" 或 "hash:channel_id:message_id:media0"
                # 需要正确分离哈希值和消息ID
                parts = candidate.split(':', 1)
                if len(parts) != 2:
                    continue

                stored_hash = parts[0]  # 第一部分是哈希
                full_msg_id = parts[1]  # 剩余部分是完整消息ID

                # 获取真实的消息ID
                real_msg_id = self._get_real_message_id(full_msg_id)

                # 跳过自己（也要考虑:media后缀）
                current_real_id = self._get_real_message_id(current_message_id)
                if real_msg_id == current_real_id:
                    continue

                # 计算汉明距离
                distance = self._hamming_distance(phash, stored_hash)

                # 只保留距离小于阈值的
                if distance <= self.phash_threshold:
                    similar.append({
                        'message_id': real_msg_id,  # 返回真实的消息ID
                        'distance': distance,
                        'hash': stored_hash
                    })

                    logger.debug(
                        f"发现相似图片: {real_msg_id} (距离: {distance})"
                    )

            # 按距离排序，最相似的在前
            similar.sort(key=lambda x: x['distance'])

            return similar

        except Exception as e:
            logger.error(f"查找相似图片失败: {e}")
            return []

    async def _save_hash(self, hash_values: Dict[str, str], message_id: str):
        """
        保存图片哈希到Redis

        Args:
            hash_values: 哈希值字典
            message_id: 消息ID
        """
        try:
            phash = hash_values['phash']

            # 获取真实的消息ID（去掉:media后缀）
            real_msg_id = self._get_real_message_id(message_id)

            # 1. 保存到分桶索引（使用6位前缀进行粗分桶）
            bucket_prefix = phash[:6]  # 使用6位前缀（24bit）
            bucket_key = f"media:phash:bucket:{bucket_prefix}"
            # 存储格式："hash:real_message_id"（不包含:media后缀）
            self.redis_manager.client.sadd(bucket_key, f"{phash}:{real_msg_id}")

            # 2. 保存完整哈希信息（使用真实消息ID作为key）
            meta_key = f"media:meta:{real_msg_id}"
            hash_values['original_id'] = message_id  # 保存原始ID（包含:media后缀）
            self.redis_manager.client.hset(meta_key, mapping=hash_values)

            # 3. 如果有:media后缀，建立映射关系
            if ':media' in message_id:
                # 保存子媒体到主消息的映射
                mapping_key = f"media:mapping:{message_id}"
                self.redis_manager.client.set(mapping_key, real_msg_id)
                self.redis_manager.client.expire(mapping_key, 30 * 24 * 3600)

            # 4. 设置过期时间（30天）
            ttl = 30 * 24 * 3600
            self.redis_manager.client.expire(bucket_key, ttl)
            self.redis_manager.client.expire(meta_key, ttl)

            logger.debug(f"保存媒体哈希: {real_msg_id} -> bucket:{bucket_prefix}")

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