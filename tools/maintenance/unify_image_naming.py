#!/usr/bin/env python3
"""
图片命名统一工具
删除缩略图，重命名所有图片为统一格式
"""
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageNamingUnifier:
    def __init__(self):
        self.training_dir = PathConfig.AD_TRAINING_DIR
        self.images_dir = self.training_dir / "images"
        self.metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        
    def load_metadata(self) -> dict:
        """加载现有元数据"""
        if self.metadata_file.exists():
            try:
                return SafeFileOperation.read_json_safe(self.metadata_file)
            except Exception as e:
                logger.error(f"加载元数据失败: {e}")
        
        return {"media_files": {}, "updated_at": None}
    
    def save_metadata(self, metadata: dict):
        """保存元数据"""
        try:
            metadata["updated_at"] = datetime.now().isoformat()
            SafeFileOperation.write_json_safe(self.metadata_file, metadata)
            logger.info(f"元数据已保存: {len(metadata['media_files'])} 个文件记录")
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")
    
    def analyze_files(self):
        """分析现有文件"""
        if not self.images_dir.exists():
            logger.warning(f"训练图片目录不存在: {self.images_dir}")
            return
        
        stats = {
            "total_files": 0,
            "thumb_files": [],
            "snapshot_files": [],
            "normal_files": [],
            "duplicate_pairs": []
        }
        
        # 分析所有文件
        for image_file in self.images_dir.rglob("*.jpg"):
            if image_file.is_file():
                stats["total_files"] += 1
                filename = image_file.name
                
                if "_thumb" in filename:
                    stats["thumb_files"].append(image_file)
                elif "_snapshot" in filename:
                    stats["snapshot_files"].append(image_file)
                else:
                    stats["normal_files"].append(image_file)
        
        # 检查重复对（原图和缩略图）
        for thumb_file in stats["thumb_files"]:
            original_name = thumb_file.name.replace("_thumb", "")
            original_path = thumb_file.parent / original_name
            if original_path.exists():
                stats["duplicate_pairs"].append((original_path, thumb_file))
        logger.info(f"📊 文件分析结果:")
        logger.info(f"总文件数: {stats['total_files']}")
        logger.info(f"缩略图文件: {len(stats['thumb_files'])}")
        logger.info(f"快照文件: {len(stats['snapshot_files'])}")
        logger.info(f"正常文件: {len(stats['normal_files'])}")
        logger.info(f"重复对（原图+缩略图）: {len(stats['duplicate_pairs'])}")
        
        return stats
    
    def get_unified_filename(self, old_filename: str, message_id: str = None) -> str:
        """
        生成统一的文件名格式
        新格式: {message_id}_{timestamp}_{hash}.jpg
        """
        # 提取现有信息
        parts = old_filename.replace('.jpg', '').split('_')
        
        if message_id is None:
            # 尝试从文件名提取消息ID
            try:
                message_id = parts[0]
                int(message_id)  # 验证是数字
            except (ValueError, IndexError):
                message_id = "unknown"
        
        # 提取时间戳
        timestamp = None
        
        # 查找连续的日期和时间部分
        for i in range(len(parts) - 1):
            date_part = parts[i]
            time_part = parts[i + 1]
            
            if len(date_part) == 8 and len(time_part) == 6:
                try:
                    # 尝试验证是否为有效日期时间
                    combined_timestamp = f"{date_part}_{time_part}"
                    datetime.strptime(combined_timestamp, "%Y%m%d_%H%M%S")
                    timestamp = combined_timestamp
                    break
                except:
                    continue
        
        if timestamp is None:
            # 如果找不到有效时间戳，使用当前时间
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 提取哈希（最后一个部分，排除后缀）
        hash_part = None
        for part in reversed(parts):
            if part not in ["thumb", "snapshot", "frame"] and len(part) >= 8:
                hash_part = part[:8]  # 只保留前8位
                break
        
        if hash_part is None:
            # 生成一个简单的哈希
            import hashlib
            hash_part = hashlib.md5(old_filename.encode()).hexdigest()[:8]
        
        return f"{message_id}_{timestamp}_{hash_part}.jpg"
    
    def delete_thumbnails(self, metadata: dict, dry_run: bool = False):
        """删除缩略图文件和对应元数据"""
        deleted_files = []
        deleted_metadata = []
        
        # 遍历元数据找到缩略图
        files_to_remove = []
        for file_hash, info in metadata["media_files"].items():
            file_path = info.get("path", "")
            if "_thumb" in file_path:
                full_path = PathConfig.AD_TRAINING_DIR / file_path
                files_to_remove.append((file_hash, full_path, info))
        
        # 删除文件和元数据
        for file_hash, file_path, info in files_to_remove:
            try:
                if file_path.exists():
                    if not dry_run:
                        file_path.unlink()
                    deleted_files.append(str(file_path))
                    logger.info(f"🗑️  删除缩略图: {file_path.name}")
                
                if not dry_run:
                    del metadata["media_files"][file_hash]
                deleted_metadata.append(file_hash)
                
            except Exception as e:
                logger.error(f"删除文件失败 {file_path}: {e}")
        
        return deleted_files, deleted_metadata
    
    def rename_files(self, metadata: dict, dry_run: bool = False):
        """重命名文件为统一格式"""
        renamed_files = []
        
        # 收集需要重命名的文件
        rename_operations = []
        
        for file_hash, info in metadata["media_files"].items():
            old_path = PathConfig.AD_TRAINING_DIR / info["path"]
            old_filename = old_path.name
            
            # 检查是否需要重命名（包含特殊后缀）
            if "_snapshot" in old_filename or "_frame" in old_filename:
                # 提取消息ID
                message_ids = info.get("message_ids", [])
                message_id = str(message_ids[0]) if message_ids else "unknown"
                
                # 生成新文件名
                new_filename = self.get_unified_filename(old_filename, message_id)
                new_path = old_path.parent / new_filename
                
                # 避免重名冲突
                counter = 1
                base_new_filename = new_filename
                while new_path.exists() and new_path != old_path:
                    name_parts = base_new_filename.split('.')
                    new_filename = f"{name_parts[0]}_{counter}.{name_parts[1]}"
                    new_path = old_path.parent / new_filename
                    counter += 1
                
                if new_path != old_path:  # 需要重命名
                    rename_operations.append((old_path, new_path, file_hash, info))
        
        # 执行重命名操作
        for old_path, new_path, file_hash, info in rename_operations:
            try:
                if not dry_run:
                    old_path.rename(new_path)
                    # 更新元数据中的路径
                    relative_path = str(new_path.relative_to(PathConfig.AD_TRAINING_DIR))
                    info["path"] = relative_path
                    info["display_path"] = relative_path
                    metadata["media_files"][file_hash] = info
                
                renamed_files.append((str(old_path), str(new_path)))
                logger.info(f"📝 重命名: {old_path.name} -> {new_path.name}")
                
            except Exception as e:
                logger.error(f"重命名失败 {old_path} -> {new_path}: {e}")
        
        return renamed_files
    
    def unify_naming(self, dry_run: bool = False):
        """统一命名格式"""
        if not self.images_dir.exists():
            logger.warning(f"训练图片目录不存在: {self.images_dir}")
            return
        
        logger.info(f"🔧 {'预览模式' if dry_run else '执行模式'}：开始统一图片命名...")
        
        # 分析现有文件
        stats = self.analyze_files()
        
        # 加载元数据
        metadata = self.load_metadata()
        original_count = len(metadata["media_files"])
        
        # 1. 删除缩略图
        logger.info("\\n🗑️  删除缩略图文件...")
        deleted_files, deleted_metadata = self.delete_thumbnails(metadata, dry_run)
        
        # 2. 重命名文件
        logger.info("\\n📝 重命名文件为统一格式...")
        renamed_files = self.rename_files(metadata, dry_run)
        
        # 3. 保存更新后的元数据
        if not dry_run and (deleted_metadata or renamed_files):
            self.save_metadata(metadata)
        
        # 输出结果
        final_count = len(metadata["media_files"])
        logger.info(f"\\n📊 操作结果:")
        logger.info(f"模式: {'预览模式' if dry_run else '执行模式'}")
        logger.info(f"删除缩略图: {len(deleted_files)} 个")
        logger.info(f"重命名文件: {len(renamed_files)} 个")
        logger.info(f"元数据记录: {original_count} -> {final_count}")
        
        # 显示新的命名格式示例
        if renamed_files:
            logger.info(f"\\n📝 重命名示例:")
            for old_name, new_name in renamed_files[:3]:
                logger.info(f"  {Path(old_name).name} -> {Path(new_name).name}")
            if len(renamed_files) > 3:
                logger.info(f"  ... 还有 {len(renamed_files) - 3} 个文件")
        
        return {
            "deleted_files": len(deleted_files),
            "renamed_files": len(renamed_files),
            "final_count": final_count
        }

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="图片命名统一工具")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际修改文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    unifier = ImageNamingUnifier()
    
    if args.dry_run:
        logger.info("🔍 预览模式：检查需要进行的操作...")
    else:
        logger.info("⚠️  警告：这将删除缩略图并重命名文件！")
        confirm = input("确认执行吗？(y/N): ")
        if confirm.lower() != 'y':
            logger.info("操作已取消")
            return
    
    result = unifier.unify_naming(dry_run=args.dry_run)
    
    if args.dry_run:
        logger.info("✅ 预览完成，使用不带 --dry-run 参数执行实际操作")
    else:
        logger.info("✅ 命名统一完成")

if __name__ == "__main__":
    main()