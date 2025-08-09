"""
视觉相似度检测服务
使用感知哈希(Perceptual Hash)技术检测图像相似度
即使图片经过压缩、调整大小、添加水印等修改，仍能识别为相似图片
"""
import logging
import io
from typing import Optional, Tuple, List
from PIL import Image
import imagehash
import hashlib
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal, Message

logger = logging.getLogger(__name__)

class VisualSimilarityDetector:
    """基于感知哈希的视觉相似度检测器"""
    
    def __init__(self):
        # 相似度阈值（汉明距离）
        self.phash_threshold = 10  # pHash差异阈值，越小越严格
        self.dhash_threshold = 12  # dHash差异阈值
        self.ahash_threshold = 12  # aHash差异阈值
        
        # 缓存时间窗口
        self.cache_hours = 48  # 检测48小时内的重复图片
        
        # 缓存最近计算的哈希值
        self._hash_cache = {}
        self._cache_max_size = 1000
    
    def calculate_perceptual_hashes(self, image_data: bytes) -> dict:
        """
        计算图片的多种感知哈希值
        
        Args:
            image_data: 图片二进制数据
            
        Returns:
            包含多种哈希值的字典
        """
        try:
            # 打开图片
            img = Image.open(io.BytesIO(image_data))
            
            # 如果是RGBA，转换为RGB
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            
            # 计算多种感知哈希
            hashes = {
                'phash': str(imagehash.phash(img)),  # 感知哈希
                'dhash': str(imagehash.dhash(img)),  # 差异哈希
                'ahash': str(imagehash.average_hash(img)),  # 平均哈希
                'whash': str(imagehash.whash(img)),  # 小波哈希
                'colorhash': str(imagehash.colorhash(img)),  # 颜色哈希
            }
            
            # 计算传统的SHA256哈希（用于完全相同的图片）
            hashes['sha256'] = hashlib.sha256(image_data).hexdigest()
            
            return hashes
            
        except Exception as e:
            logger.error(f"计算感知哈希时出错: {e}")
            # 如果无法计算感知哈希，至少返回SHA256
            return {
                'sha256': hashlib.sha256(image_data).hexdigest()
            }
    
    def calculate_hash_distance(self, hash1: str, hash2: str) -> int:
        """
        计算两个哈希值之间的汉明距离
        
        Args:
            hash1: 第一个哈希值
            hash2: 第二个哈希值
            
        Returns:
            汉明距离
        """
        try:
            # 将十六进制字符串转换为整数
            h1 = int(hash1, 16)
            h2 = int(hash2, 16)
            
            # 计算汉明距离
            xor = h1 ^ h2
            distance = bin(xor).count('1')
            
            return distance
        except:
            return 999  # 返回一个很大的值表示不相似
    
    def is_visually_similar(self, hashes1: dict, hashes2: dict) -> Tuple[bool, float]:
        """
        判断两组哈希值是否表示视觉相似的图片
        
        Args:
            hashes1: 第一张图片的哈希值字典
            hashes2: 第二张图片的哈希值字典
            
        Returns:
            (是否相似, 相似度分数0-100)
        """
        # 如果SHA256完全相同，100%相似
        if hashes1.get('sha256') == hashes2.get('sha256'):
            return True, 100.0
        
        similarities = []
        
        # 计算pHash相似度（最重要）
        if 'phash' in hashes1 and 'phash' in hashes2:
            distance = self.calculate_hash_distance(hashes1['phash'], hashes2['phash'])
            if distance <= self.phash_threshold:
                similarity = 100 * (1 - distance / 64)  # 64位哈希
                similarities.append(('phash', similarity, distance))
        
        # 计算dHash相似度
        if 'dhash' in hashes1 and 'dhash' in hashes2:
            distance = self.calculate_hash_distance(hashes1['dhash'], hashes2['dhash'])
            if distance <= self.dhash_threshold:
                similarity = 100 * (1 - distance / 64)
                similarities.append(('dhash', similarity, distance))
        
        # 计算aHash相似度
        if 'ahash' in hashes1 and 'ahash' in hashes2:
            distance = self.calculate_hash_distance(hashes1['ahash'], hashes2['ahash'])
            if distance <= self.ahash_threshold:
                similarity = 100 * (1 - distance / 64)
                similarities.append(('ahash', similarity, distance))
        
        # 如果有任何一种哈希算法认为相似
        if similarities:
            # 取最高相似度
            best_match = max(similarities, key=lambda x: x[1])
            logger.info(f"图片视觉相似: {best_match[0]}算法, 相似度{best_match[1]:.1f}%, 距离{best_match[2]}")
            return True, best_match[1]
        
        return False, 0.0
    
    async def check_visual_duplicate(self, 
                                    image_data: bytes,
                                    message_time: Optional[datetime] = None,
                                    message_id: Optional[int] = None,
                                    db: Optional[AsyncSession] = None) -> Tuple[bool, Optional[int], float]:
        """
        检查图片是否与历史消息中的图片视觉相似
        
        Args:
            image_data: 图片数据
            message_time: 消息时间
            message_id: 当前消息ID（用于排除自己）
            db: 数据库会话
            
        Returns:
            (是否重复, 原始消息ID, 相似度分数)
        """
        if not image_data:
            return False, None, 0.0
        
        # 计算当前图片的感知哈希
        current_hashes = self.calculate_perceptual_hashes(image_data)
        
        if message_time is None:
            message_time = datetime.utcnow()
        
        # 确保时间没有时区信息
        if hasattr(message_time, 'tzinfo') and message_time.tzinfo is not None:
            message_time = message_time.replace(tzinfo=None)
        
        use_external_db = db is not None
        if not use_external_db:
            db = AsyncSessionLocal()
        
        try:
            # 查询时间范围内的消息
            time_threshold = message_time - timedelta(hours=self.cache_hours)
            
            conditions = [
                Message.created_at >= time_threshold,
                Message.status != "rejected",
                or_(
                    Message.media_hash.isnot(None),
                    Message.combined_media_hash.isnot(None),
                    Message.visual_hash.isnot(None)  # 如果存储了视觉哈希
                )
            ]
            
            # 排除当前消息
            if message_id is not None:
                conditions.append(Message.id != message_id)
            
            result = await db.execute(
                select(Message).where(and_(*conditions)).order_by(Message.created_at.desc())
            )
            messages = result.scalars().all()
            
            # 检查每个历史消息
            for msg in messages:
                # 如果消息存储了视觉哈希，直接比较
                if hasattr(msg, 'visual_hash') and msg.visual_hash:
                    try:
                        stored_hashes = eval(msg.visual_hash)  # 存储为字符串形式的字典
                        is_similar, similarity = self.is_visually_similar(current_hashes, stored_hashes)
                        if is_similar:
                            logger.info(f"发现视觉相似图片，消息ID: {msg.id}, 相似度: {similarity:.1f}%")
                            return True, msg.id, similarity
                    except:
                        pass
                
                # 如果只有SHA256哈希，至少检查完全相同
                if msg.media_hash and msg.media_hash == current_hashes.get('sha256'):
                    logger.info(f"发现完全相同的图片，消息ID: {msg.id}")
                    return True, msg.id, 100.0
            
            return False, None, 0.0
            
        except Exception as e:
            logger.error(f"检查视觉重复时出错: {e}")
            return False, None, 0.0
        finally:
            if not use_external_db:
                await db.close()
    
    async def store_visual_hash(self, 
                               message_id: int,
                               image_data: bytes,
                               db: Optional[AsyncSession] = None):
        """
        存储消息的视觉哈希值
        
        Args:
            message_id: 消息ID
            image_data: 图片数据
            db: 数据库会话
        """
        use_external_db = db is not None
        if not use_external_db:
            db = AsyncSessionLocal()
        
        try:
            # 计算视觉哈希
            hashes = self.calculate_perceptual_hashes(image_data)
            
            # 查找消息
            result = await db.execute(
                select(Message).where(Message.id == message_id)
            )
            message = result.scalar_one_or_none()
            
            if message:
                # 存储视觉哈希（转换为字符串）
                message.visual_hash = str(hashes)
                
                # 如果还没有媒体哈希，也存储SHA256
                if not message.media_hash:
                    message.media_hash = hashes.get('sha256')
                
                if not use_external_db:
                    await db.commit()
                
                logger.debug(f"已存储消息 {message_id} 的视觉哈希")
                
        except Exception as e:
            logger.error(f"存储视觉哈希时出错: {e}")
            if not use_external_db:
                await db.rollback()
        finally:
            if not use_external_db:
                await db.close()
    
    def calculate_group_similarity(self, images1: List[bytes], images2: List[bytes]) -> float:
        """
        计算两组图片的整体相似度
        用于处理媒体组消息
        
        Args:
            images1: 第一组图片
            images2: 第二组图片
            
        Returns:
            整体相似度分数(0-100)
        """
        if not images1 or not images2:
            return 0.0
        
        # 如果数量差异太大，可能不是同一组消息
        if abs(len(images1) - len(images2)) > 2:
            return 0.0
        
        # 计算所有图片的哈希
        hashes1 = [self.calculate_perceptual_hashes(img) for img in images1]
        hashes2 = [self.calculate_perceptual_hashes(img) for img in images2]
        
        # 找出最佳匹配
        total_similarity = 0.0
        matched_count = 0
        
        for h1 in hashes1:
            best_similarity = 0.0
            for h2 in hashes2:
                is_similar, similarity = self.is_visually_similar(h1, h2)
                if similarity > best_similarity:
                    best_similarity = similarity
            
            if best_similarity > 50:  # 至少50%相似才算匹配
                total_similarity += best_similarity
                matched_count += 1
        
        # 计算整体相似度
        if matched_count == 0:
            return 0.0
        
        # 考虑匹配率和平均相似度
        match_rate = matched_count / max(len(images1), len(images2))
        avg_similarity = total_similarity / matched_count
        
        # 综合分数
        overall_similarity = match_rate * avg_similarity
        
        logger.info(f"媒体组相似度: 匹配{matched_count}/{len(images1)}, 整体相似度{overall_similarity:.1f}%")
        
        return overall_similarity

# 全局实例
visual_detector = VisualSimilarityDetector()