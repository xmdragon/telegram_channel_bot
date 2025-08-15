#!/usr/bin/env python3
"""
为现有视频生成缺失的缩略图
"""
import sys
import json
import logging
from pathlib import Path
import cv2
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))
from app.utils.safe_file_ops import SafeFileOperation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_thumbnails():
    """为所有没有缩略图的视频生成预览图"""
    
    # 读取媒体元数据
    media_metadata_file = Path("data/ad_training_data/media_metadata.json")
    if not media_metadata_file.exists():
        logger.error("媒体元数据文件不存在")
        return
    
    metadata = SafeFileOperation.read_json_safe(media_metadata_file)
    if not metadata or "media_files" not in metadata:
        logger.error("无法读取媒体元数据")
        return
    
    updated_count = 0
    error_count = 0
    
    # 遍历所有媒体文件
    for file_hash, info in metadata["media_files"].items():
        # 检查是否是视频且没有缩略图
        if info.get("media_type") in ["video", "animation"]:
            video_path = Path("data") / info["path"]
            
            # 检查是否已有缩略图或display_path
            if "thumbnail_path" in info or "display_path" in info:
                if info.get("display_path", "").endswith(".jpg"):
                    logger.debug(f"视频已有缩略图: {info['path']}")
                    continue
            
            # 检查视频文件是否存在
            if not video_path.exists():
                logger.warning(f"视频文件不存在: {video_path}")
                continue
            
            try:
                # 提取消息ID和时间戳
                message_id = info.get("message_ids", [0])[0]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # 生成缩略图路径
                video_parent = video_path.parent.name  # 获取年月目录（如 2025-08）
                thumbnail_dir = Path("data/ad_training_data/images") / video_parent
                thumbnail_dir.mkdir(parents=True, exist_ok=True)
                
                # 生成缩略图文件名
                thumbnail_filename = f"{message_id}_{timestamp}_{file_hash[:8]}_thumb.jpg"
                thumbnail_path = thumbnail_dir / thumbnail_filename
                
                # 提取视频第一帧
                cap = cv2.VideoCapture(str(video_path))
                ret, frame = cap.read()
                cap.release()
                
                if ret:
                    # 保存缩略图
                    cv2.imwrite(str(thumbnail_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    
                    # 更新元数据 - 确保路径不包含ad_training_data前缀
                    relative_thumbnail_path = str(thumbnail_path.relative_to(Path("data/ad_training_data")))
                    info["thumbnail_path"] = relative_thumbnail_path
                    info["display_path"] = relative_thumbnail_path
                    
                    logger.info(f"✅ 生成缩略图: {video_path.name} -> {thumbnail_filename}")
                    updated_count += 1
                else:
                    logger.error(f"❌ 无法读取视频帧: {video_path}")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"❌ 处理视频失败 {video_path}: {e}")
                error_count += 1
    
    # 保存更新后的元数据
    if updated_count > 0:
        metadata["updated_at"] = datetime.now().isoformat()
        SafeFileOperation.write_json_safe(media_metadata_file, metadata)
        logger.info(f"\n✅ 元数据已更新")
    
    # 输出统计
    logger.info(f"\n=== 处理完成 ===")
    logger.info(f"生成缩略图: {updated_count}")
    logger.info(f"处理失败: {error_count}")
    
    return updated_count, error_count


if __name__ == "__main__":
    print("开始生成缺失的视频缩略图...")
    updated, errors = generate_thumbnails()
    print(f"\n完成！生成了 {updated} 个缩略图，{errors} 个失败。")