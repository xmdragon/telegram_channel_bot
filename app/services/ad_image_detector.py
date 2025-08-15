"""
广告图片检测器
使用视觉哈希技术识别已知的广告图片
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import asyncio
from PIL import Image

from app.services.visual_similarity import VisualSimilarityDetector

logger = logging.getLogger(__name__)

class AdImageDetector:
    """广告图片检测器 - 基于视觉哈希的图片广告识别"""
    
    def __init__(self):
        self.visual_detector = VisualSimilarityDetector()
        self.ad_image_hashes = {}  # {file_hash: {visual_hashes, metadata}}
        self.hash_index = {  # 反向索引：哈希值 -> 文件列表
            'phash': {},
            'dhash': {},
            'ahash': {}
        }
        from app.core.path_config import PathConfig
        self.training_data_dir = PathConfig.AD_TRAINING_DIR
        self.index_file = PathConfig.AD_IMAGE_HASHES_FILE
        self.metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        
        # 相似度阈值（汉明距离）
        self.phash_threshold = 10  # pHash差异阈值
        self.dhash_threshold = 12  # dHash差异阈值
        self.ahash_threshold = 12  # aHash差异阈值
        
        # 加载已有的哈希索引
        self.load_ad_image_hashes()
    
    def load_ad_image_hashes(self) -> None:
        """加载广告图片的视觉哈希索引"""
        try:
            # 优先从索引文件加载
            if self.index_file.exists():
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.ad_image_hashes = data.get('ad_images', {})
                    self._rebuild_hash_index()
                    logger.info(f"✅ 从索引文件加载了 {len(self.ad_image_hashes)} 个广告图片哈希")
                    return
            
            # 如果没有索引文件，从媒体元数据构建
            if self.metadata_file.exists():
                logger.info("📦 开始构建广告图片哈希索引...")
                self.build_hash_index_from_metadata()
            else:
                logger.warning("⚠️ 未找到训练数据，广告图片检测功能暂不可用")
                
        except Exception as e:
            logger.error(f"加载广告图片哈希失败: {e}")
    
    def build_hash_index_from_metadata(self) -> None:
        """从媒体元数据文件构建哈希索引"""
        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            media_files = metadata.get('media_files', {})
            ad_count = 0
            
            for file_hash, file_info in media_files.items():
                # 获取媒体类型
                media_type = file_info.get('media_type', '')
                
                # 只处理图片文件
                if not media_type or not media_type.startswith('image'):
                    # 如果没有media_type，通过文件扩展名判断
                    path = file_info.get('path', '')
                    if not path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                        continue
                
                # 获取或计算视觉哈希
                visual_hashes = file_info.get('visual_hashes')
                if not visual_hashes:
                    # 尝试计算视觉哈希
                    file_path = self.training_data_dir / file_info.get('path', '')
                    if file_path.exists():
                        try:
                            with open(file_path, 'rb') as f:
                                image_data = f.read()
                            visual_hashes = self.visual_detector.calculate_perceptual_hashes(image_data)
                            file_info['visual_hashes'] = visual_hashes
                        except Exception as e:
                            logger.debug(f"计算视觉哈希失败 {file_path}: {e}")
                            continue
                
                if visual_hashes:
                    self.ad_image_hashes[file_hash] = {
                        'visual_hashes': visual_hashes,
                        'path': file_info.get('path'),
                        'message_id': file_info.get('message_id'),
                        'added_at': file_info.get('added_at'),
                        'channel_id': file_info.get('channel_id')
                    }
                    ad_count += 1
            
            if ad_count > 0:
                self._rebuild_hash_index()
                self.save_hash_index()
                logger.info(f"✅ 构建完成：发现 {ad_count} 个广告图片")
            else:
                logger.warning("⚠️ 未发现广告图片训练样本")
                
        except Exception as e:
            logger.error(f"构建哈希索引失败: {e}")
    
    def _rebuild_hash_index(self) -> None:
        """重建反向哈希索引"""
        self.hash_index = {
            'phash': {},
            'dhash': {},
            'ahash': {}
        }
        
        for file_hash, data in self.ad_image_hashes.items():
            visual_hashes = data.get('visual_hashes', {})
            
            # 建立反向索引
            for hash_type in ['phash', 'dhash', 'ahash']:
                if hash_type in visual_hashes:
                    hash_value = visual_hashes[hash_type]
                    if hash_value not in self.hash_index[hash_type]:
                        self.hash_index[hash_type][hash_value] = []
                    self.hash_index[hash_type][hash_value].append(file_hash)
    
    def save_hash_index(self) -> None:
        """保存哈希索引到文件"""
        try:
            self.training_data_dir.mkdir(parents=True, exist_ok=True)
            
            data = {
                'ad_images': self.ad_image_hashes,
                'updated_at': datetime.now().isoformat()
            }
            
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 哈希索引已保存: {len(self.ad_image_hashes)} 个广告图片")
            
        except Exception as e:
            logger.error(f"保存哈希索引失败: {e}")
    
    async def is_known_ad(self, visual_hashes: Dict) -> Tuple[bool, float, Optional[str]]:
        """
        检查图片是否为已知的广告图片
        
        Args:
            visual_hashes: 图片的视觉哈希值
            
        Returns:
            (是否为广告, 相似度, 匹配的广告ID)
        """
        if not visual_hashes or not self.ad_image_hashes:
            return False, 0.0, None
        
        try:
            best_match = None
            best_similarity = 0.0
            
            # 快速检查完全匹配（SHA256）
            if 'sha256' in visual_hashes:
                sha256 = visual_hashes['sha256']
                for file_hash, data in self.ad_image_hashes.items():
                    ad_hashes = data.get('visual_hashes', {})
                    if ad_hashes.get('sha256') == sha256:
                        logger.info(f"🎯 完全匹配广告图片: {file_hash}")
                        return True, 100.0, file_hash
            
            # 使用pHash进行相似度匹配（最准确）
            if 'phash' in visual_hashes:
                phash = visual_hashes['phash']
                
                # 遍历所有广告图片
                for file_hash, data in self.ad_image_hashes.items():
                    ad_hashes = data.get('visual_hashes', {})
                    if 'phash' not in ad_hashes:
                        continue
                    
                    # 计算汉明距离
                    distance = self.visual_detector.calculate_hash_distance(
                        phash, ad_hashes['phash']
                    )
                    
                    if distance <= self.phash_threshold:
                        similarity = 100 * (1 - distance / 64)  # 64位哈希
                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_match = file_hash
            
            # 如果pHash没有匹配，尝试dHash
            if not best_match and 'dhash' in visual_hashes:
                dhash = visual_hashes['dhash']
                
                for file_hash, data in self.ad_image_hashes.items():
                    ad_hashes = data.get('visual_hashes', {})
                    if 'dhash' not in ad_hashes:
                        continue
                    
                    distance = self.visual_detector.calculate_hash_distance(
                        dhash, ad_hashes['dhash']
                    )
                    
                    if distance <= self.dhash_threshold:
                        similarity = 100 * (1 - distance / 64)
                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_match = file_hash
            
            if best_match:
                logger.info(f"🎯 检测到广告图片，相似度: {best_similarity:.1f}%，匹配: {best_match}")
                return True, best_similarity, best_match
            
            return False, 0.0, None
            
        except Exception as e:
            logger.error(f"广告图片检测失败: {e}")
            return False, 0.0, None
    
    async def add_ad_image(self, image_path: str, metadata: Dict = None) -> bool:
        """
        添加新的广告图片到索引
        
        Args:
            image_path: 图片文件路径
            metadata: 图片元数据
            
        Returns:
            是否添加成功
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return False
            
            # 计算视觉哈希
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            visual_hashes = self.visual_detector.calculate_perceptual_hashes(image_data)
            
            # 生成文件哈希作为ID
            import hashlib
            file_hash = hashlib.md5(image_data).hexdigest()
            
            # 检查是否已存在
            if file_hash in self.ad_image_hashes:
                logger.info(f"广告图片已存在: {file_hash}")
                return True
            
            # 添加到索引
            self.ad_image_hashes[file_hash] = {
                'visual_hashes': visual_hashes,
                'path': os.path.basename(image_path),
                'added_at': datetime.now().isoformat(),
                **(metadata or {})
            }
            
            # 更新反向索引
            self._rebuild_hash_index()
            
            # 保存索引
            self.save_hash_index()
            
            logger.info(f"✅ 新增广告图片到索引: {file_hash}")
            return True
            
        except Exception as e:
            logger.error(f"添加广告图片失败: {e}")
            return False
    
    async def remove_ad_image(self, file_hash: str) -> bool:
        """
        从索引中移除广告图片
        
        Args:
            file_hash: 文件哈希ID
            
        Returns:
            是否移除成功
        """
        try:
            if file_hash not in self.ad_image_hashes:
                logger.warning(f"广告图片不存在: {file_hash}")
                return False
            
            # 从索引中移除
            del self.ad_image_hashes[file_hash]
            
            # 更新反向索引
            self._rebuild_hash_index()
            
            # 保存索引
            self.save_hash_index()
            
            logger.info(f"✅ 从索引移除广告图片: {file_hash}")
            return True
            
        except Exception as e:
            logger.error(f"移除广告图片失败: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        stats = {
            'total_ad_images': len(self.ad_image_hashes),
            'phash_indexed': len(set().union(*self.hash_index['phash'].values())) if self.hash_index['phash'] else 0,
            'dhash_indexed': len(set().union(*self.hash_index['dhash'].values())) if self.hash_index['dhash'] else 0,
            'ahash_indexed': len(set().union(*self.hash_index['ahash'].values())) if self.hash_index['ahash'] else 0,
            'index_file': str(self.index_file),
            'index_exists': self.index_file.exists()
        }
        return stats

# 全局实例
ad_image_detector = AdImageDetector()