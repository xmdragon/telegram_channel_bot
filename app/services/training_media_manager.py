"""
训练媒体文件管理器
负责保存和管理用于AI训练的媒体文件
"""
import os
import shutil
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
import cv2

logger = logging.getLogger(__name__)


class TrainingMediaManager:
    """训练媒体文件管理器"""
    
    def __init__(self):
        self.base_dir = Path("data/ad_training_data")
        self.images_dir = self.base_dir / "images"
        self.videos_dir = self.base_dir / "videos"
        self.metadata_file = self.base_dir / "media_metadata.json"
        
        # 确保目录存在
        self.ensure_directories()
        
        # 加载元数据
        self.metadata = self.load_metadata()
        
        # 初始化视觉相似度检测器
        self.visual_detector = None
        self._init_visual_detector()
    
    def ensure_directories(self):
        """确保必要的目录存在"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(exist_ok=True)
        self.videos_dir.mkdir(exist_ok=True)
        
        # 创建月份目录
        current_month = datetime.now().strftime("%Y-%m")
        (self.images_dir / current_month).mkdir(exist_ok=True)
        (self.videos_dir / current_month).mkdir(exist_ok=True)
    
    def load_metadata(self) -> Dict:
        """加载媒体元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载媒体元数据失败: {e}")
        return {"media_files": {}, "updated_at": None}
    
    def save_metadata(self):
        """保存媒体元数据"""
        try:
            self.metadata["updated_at"] = datetime.now().isoformat()
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存媒体元数据失败: {e}")
    
    def _init_visual_detector(self):
        """初始化视觉相似度检测器"""
        try:
            from app.services.visual_similarity import VisualSimilarityDetector
            self.visual_detector = VisualSimilarityDetector()
            logger.info("视觉相似度检测器初始化成功")
        except Exception as e:
            logger.warning(f"无法初始化视觉相似度检测器: {e}")
            self.visual_detector = None
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """计算文件哈希值"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def extract_video_frame(self, video_path: Path) -> Optional[bytes]:
        """从视频提取第一帧"""
        try:
            cap = cv2.VideoCapture(str(video_path))
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                # 将帧转换为JPEG格式的字节数据
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return buffer.tobytes()
            return None
        except Exception as e:
            logger.error(f"提取视频帧失败: {e}")
            return None
    
    async def check_visual_duplicate(self, media_data: bytes, media_type: str) -> Optional[Dict]:
        """检查视觉重复
        
        Returns:
            如果找到相似文件，返回现有文件信息，否则返回None
        """
        if not self.visual_detector:
            return None
        
        try:
            # 计算当前媒体的视觉哈希
            current_hashes = self.visual_detector.calculate_perceptual_hashes(media_data)
            
            # 遍历现有媒体文件，查找视觉相似的
            for file_hash, file_info in self.metadata.get("media_files", {}).items():
                if "visual_hashes" not in file_info:
                    continue
                
                # 比较视觉哈希
                similarities = self.visual_detector.compare_hashes(
                    current_hashes, 
                    file_info["visual_hashes"]
                )
                
                # 如果有任何一种哈希相似度超过阈值，认为是重复
                for hash_type, similarity, distance in similarities:
                    if similarity >= 0.85:  # 85%相似度阈值
                        logger.info(
                            f"发现视觉相似文件 ({hash_type} 相似度: {similarity*100:.1f}%): "
                            f"{file_info['path']}"
                        )
                        return {
                            "file_hash": file_hash,
                            "file_info": file_info,
                            "similarity": similarity,
                            "hash_type": hash_type
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"检查视觉重复失败: {e}")
            return None
    
    async def save_training_media(
        self, 
        source_path: str, 
        message_id: int, 
        media_type: str,
        channel_id: Optional[str] = None,
        is_ad: bool = True
    ) -> Optional[str]:
        """
        保存训练用的媒体文件
        
        Args:
            source_path: 源文件路径（temp_media中的文件）
            message_id: 消息ID
            media_type: 媒体类型（photo/video/document）
            channel_id: 频道ID
            is_ad: 是否为广告
            
        Returns:
            保存后的文件路径，失败返回None
        """
        try:
            source = Path(source_path)
            if not source.exists():
                logger.warning(f"源文件不存在: {source_path}")
                return None
            
            # 计算文件哈希
            file_hash = self.calculate_file_hash(source)
            
            # 检查是否已存在完全相同的文件（文件级别去重）
            if file_hash in self.metadata.get("media_files", {}):
                existing = self.metadata["media_files"][file_hash]
                logger.info(f"文件已存在（哈希匹配）: {existing['path']}")
                
                # 添加新的关联
                if message_id not in existing.get("message_ids", []):
                    existing["message_ids"].append(message_id)
                    self.save_metadata()
                
                return existing["path"]
            
            # 准备媒体数据用于视觉哈希计算
            media_data = None
            visual_hashes = None
            
            if self.visual_detector:
                if media_type in ["photo", "image"]:
                    # 读取图片数据
                    with open(source, 'rb') as f:
                        media_data = f.read()
                elif media_type in ["video", "animation"]:
                    # 提取视频第一帧
                    media_data = self.extract_video_frame(source)
                
                # 检查视觉重复（视觉级别去重）
                if media_data:
                    duplicate = await self.check_visual_duplicate(media_data, media_type)
                    if duplicate:
                        existing_info = duplicate["file_info"]
                        logger.info(
                            f"发现视觉相似文件（{duplicate['hash_type']} 相似度: "
                            f"{duplicate['similarity']*100:.1f}%），合并引用: {existing_info['path']}"
                        )
                        
                        # 添加新的关联到视觉相似的文件
                        if message_id not in existing_info.get("message_ids", []):
                            existing_info["message_ids"].append(message_id)
                            # 更新视觉相似文件的元数据
                            self.metadata["media_files"][duplicate["file_hash"]] = existing_info
                            self.save_metadata()
                        
                        return existing_info["path"]
                    
                    # 计算并保存视觉哈希供后续使用
                    try:
                        visual_hashes = self.visual_detector.calculate_perceptual_hashes(media_data)
                    except Exception as e:
                        logger.warning(f"计算视觉哈希失败: {e}")
                        visual_hashes = None
            
            # 确定目标目录
            current_month = datetime.now().strftime("%Y-%m")
            if media_type in ["photo", "image"]:
                target_dir = self.images_dir / current_month
            elif media_type in ["video", "animation"]:
                target_dir = self.videos_dir / current_month
            else:
                target_dir = self.images_dir / current_month  # 默认放到图片目录
            
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成目标文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = source.suffix or ".jpg"  # 默认扩展名
            target_filename = f"{message_id}_{timestamp}_{file_hash[:8]}{ext}"
            target_path = target_dir / target_filename
            
            # 复制文件
            shutil.copy2(source, target_path)
            logger.info(f"已保存训练媒体: {target_path}")
            
            # 更新元数据
            relative_path = str(target_path.relative_to(Path("data")))
            metadata_entry = {
                "path": relative_path,
                "message_ids": [message_id],
                "channel_id": channel_id,
                "media_type": media_type,
                "is_ad": is_ad,
                "file_size": target_path.stat().st_size,
                "saved_at": datetime.now().isoformat(),
                "original_name": source.name,
                "file_hash": file_hash  # 保存文件哈希
            }
            
            # 如果有视觉哈希，也保存
            if visual_hashes:
                metadata_entry["visual_hashes"] = visual_hashes
            
            self.metadata["media_files"][file_hash] = metadata_entry
            self.save_metadata()
            
            return relative_path
            
        except Exception as e:
            logger.error(f"保存训练媒体失败: {e}")
            return None
    
    async def get_media_for_message(self, message_id: int) -> List[str]:
        """获取消息关联的所有媒体文件"""
        media_paths = []
        for file_hash, info in self.metadata.get("media_files", {}).items():
            if message_id in info.get("message_ids", []):
                media_paths.append(info["path"])
        return media_paths
    
    async def cleanup_orphaned_media(self):
        """清理没有关联训练数据的媒体文件"""
        # TODO: 实现清理逻辑
        pass
    
    def get_statistics(self) -> Dict:
        """获取媒体文件统计信息"""
        stats = {
            "total_files": len(self.metadata.get("media_files", {})),
            "total_size": 0,
            "by_type": {},
            "by_month": {}
        }
        
        for info in self.metadata.get("media_files", {}).values():
            stats["total_size"] += info.get("file_size", 0)
            
            # 按类型统计
            media_type = info.get("media_type", "unknown")
            stats["by_type"][media_type] = stats["by_type"].get(media_type, 0) + 1
            
            # 按月份统计
            saved_at = info.get("saved_at", "")
            if saved_at:
                month = saved_at[:7]  # YYYY-MM
                stats["by_month"][month] = stats["by_month"].get(month, 0) + 1
        
        # 转换大小为可读格式
        stats["total_size_mb"] = round(stats["total_size"] / (1024 * 1024), 2)
        
        return stats


# 全局实例
training_media_manager = TrainingMediaManager()