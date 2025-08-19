#!/usr/bin/env python3
"""
媒体元数据同步工具
用于同步文件系统中的图片文件和元数据记录
"""
import os
import sys
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MediaMetadataSync:
    def __init__(self):
        self.training_dir = PathConfig.AD_TRAINING_DIR
        self.images_dir = self.training_dir / "images"
        self.metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        
    def calculate_file_hash(self, file_path: Path) -> str:
        """计算文件哈希值"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def extract_message_id_from_filename(self, filename: str) -> int:
        """从文件名提取消息ID"""
        try:
            # 文件名格式：message_id_timestamp_hash[_suffix].jpg
            parts = filename.replace('.jpg', '').split('_')
            if len(parts) >= 1:
                return int(parts[0])
        except (ValueError, IndexError):
            pass
        return -1  # 无法提取时使用-1
    
    def categorize_file(self, filename: str) -> str:
        """分类文件类型"""
        if '_snapshot' in filename:
            return 'video_snapshot'
        elif '_thumb' in filename:
            return 'thumbnail'
        elif '_frame' in filename:
            return 'video_frame'
        else:
            return 'image'
    
    def load_metadata(self) -> dict:
        """加载现有元数据"""
        if self.metadata_file.exists():
            try:
                return SafeFileOperation.read_json_safe(self.metadata_file)
            except Exception as e:
                logger.error(f"加载元数据失败: {e}")
        
        return {
            "media_files": {},
            "updated_at": None
        }
    
    def save_metadata(self, metadata: dict):
        """保存元数据"""
        try:
            metadata["updated_at"] = datetime.now().isoformat()
            SafeFileOperation.write_json_safe(self.metadata_file, metadata)
            logger.info(f"元数据已保存: {len(metadata['media_files'])} 个文件记录")
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")
    
    def should_skip_file(self, file_path: Path, metadata: dict) -> tuple:
        """
        检查是否应该跳过文件
        返回 (should_skip, reason, existing_hash)
        """
        # 检查是否已有相同路径的记录
        relative_path = str(file_path.relative_to(PathConfig.AD_TRAINING_DIR))
        
        for file_hash, info in metadata["media_files"].items():
            if info.get("path") == relative_path:
                return True, "路径已存在", file_hash
        
        # 检查是否为缩略图且原图已存在
        filename = file_path.name
        if "_thumb" in filename:
            # 查找对应的原图
            original_name = filename.replace("_thumb", "")
            original_path = file_path.parent / original_name
            if original_path.exists():
                return True, "缩略图跳过（原图存在）", None
        
        return False, "", None
    
    def create_metadata_entry(self, file_path: Path, file_hash: str) -> dict:
        """为文件创建元数据条目"""
        filename = file_path.name
        file_size = file_path.stat().st_size
        message_id = self.extract_message_id_from_filename(filename)
        file_type = self.categorize_file(filename)
        
        # 确定媒体类型
        if file_type in ['video_snapshot', 'video_frame']:
            original_media_type = 'video'
            media_type = 'image'  # 保存的是图片
        else:
            original_media_type = 'photo'
            media_type = 'image'
        
        relative_path = str(file_path.relative_to(PathConfig.AD_TRAINING_DIR))
        
        return {
            "path": relative_path,
            "message_ids": [message_id] if message_id != -1 else [],
            "channel_id": None,  # 无法从文件名推断
            "media_type": media_type,
            "original_media_type": original_media_type,
            "is_ad": True,  # 训练目录中的都是广告
            "file_size": file_size,
            "saved_at": datetime.now().isoformat(),
            "original_name": filename,
            "file_hash": file_hash,
            "display_path": relative_path,
            "sync_source": "file_system",  # 标记来源
            "file_category": file_type
        }
    
    def sync_metadata(self, dry_run: bool = False):
        """同步元数据"""
        if not self.images_dir.exists():
            logger.warning(f"训练图片目录不存在: {self.images_dir}")
            return
        
        # 加载现有元数据
        metadata = self.load_metadata()
        original_count = len(metadata["media_files"])
        
        # 统计信息
        stats = {
            "total_files": 0,
            "existing_records": 0,
            "new_records": 0,
            "skipped_thumbnails": 0,
            "error_files": 0
        }
        
        # 遍历所有图片文件
        for image_file in self.images_dir.rglob("*.jpg"):
            if image_file.is_file():
                stats["total_files"] += 1
                
                try:
                    # 检查是否应该跳过
                    should_skip, reason, existing_hash = self.should_skip_file(image_file, metadata)
                    
                    if should_skip:
                        if "缩略图" in reason:
                            stats["skipped_thumbnails"] += 1
                        else:
                            stats["existing_records"] += 1
                        logger.debug(f"跳过文件: {image_file.name} - {reason}")
                        continue
                    
                    # 计算文件哈希
                    file_hash = self.calculate_file_hash(image_file)
                    
                    # 检查是否已有相同哈希的记录
                    if file_hash in metadata["media_files"]:
                        stats["existing_records"] += 1
                        logger.debug(f"文件已存在（哈希匹配）: {image_file.name}")
                        continue
                    
                    # 创建新的元数据条目
                    if not dry_run:
                        metadata_entry = self.create_metadata_entry(image_file, file_hash)
                        metadata["media_files"][file_hash] = metadata_entry
                    
                    stats["new_records"] += 1
                    logger.info(f"✅ 添加元数据: {image_file.name}")
                    
                except Exception as e:
                    stats["error_files"] += 1
                    logger.error(f"处理文件失败 {image_file}: {e}")
        
        # 保存更新后的元数据
        if not dry_run and stats["new_records"] > 0:
            self.save_metadata(metadata)
        
        # 输出统计结果
        final_count = len(metadata["media_files"])
        logger.info(f"\n📊 同步统计:")
        logger.info(f"模式: {'预览模式' if dry_run else '执行模式'}")
        logger.info(f"总文件数: {stats['total_files']}")
        logger.info(f"已有记录: {stats['existing_records']}")
        logger.info(f"新增记录: {stats['new_records']}")
        logger.info(f"跳过缩略图: {stats['skipped_thumbnails']}")
        logger.info(f"错误文件: {stats['error_files']}")
        logger.info(f"元数据记录: {original_count} -> {final_count}")
        
        return stats

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="媒体元数据同步工具")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际修改文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    syncer = MediaMetadataSync()
    
    if args.dry_run:
        logger.info("🔍 预览模式：检查需要同步的文件...")
    else:
        logger.info("🔧 执行模式：开始同步元数据...")
    
    stats = syncer.sync_metadata(dry_run=args.dry_run)
    
    if args.dry_run:
        logger.info("✅ 预览完成，使用 --dry-run=false 执行实际同步")
    else:
        logger.info("✅ 同步完成")

if __name__ == "__main__":
    main()