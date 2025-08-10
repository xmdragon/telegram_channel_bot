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
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """计算文件哈希值"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
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
            
            # 检查是否已存在相同文件
            if file_hash in self.metadata.get("media_files", {}):
                existing = self.metadata["media_files"][file_hash]
                logger.info(f"文件已存在（哈希匹配）: {existing['path']}")
                
                # 添加新的关联
                if message_id not in existing.get("message_ids", []):
                    existing["message_ids"].append(message_id)
                    self.save_metadata()
                
                return existing["path"]
            
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
            self.metadata["media_files"][file_hash] = {
                "path": relative_path,
                "message_ids": [message_id],
                "channel_id": channel_id,
                "media_type": media_type,
                "is_ad": is_ad,
                "file_size": target_path.stat().st_size,
                "saved_at": datetime.now().isoformat(),
                "original_name": source.name
            }
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