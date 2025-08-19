#!/usr/bin/env python3
"""
训练图片压缩工具
用于压缩现有的训练图片，减少存储空间
"""
import os
import sys
import cv2
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

class TrainingImageCompressor:
    def __init__(self):
        self.training_dir = PathConfig.AD_TRAINING_DIR
        self.images_dir = self.training_dir / "images"
        self.metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        
    def compress_image(self, image):
        """压缩图片尺寸"""
        height, width = image.shape[:2]
        
        # 设置最大尺寸（训练用途不需要太高分辨率）
        max_width = 800
        max_height = 600
        
        # 如果图片过大，按比例缩放
        if width > max_width or height > max_height:
            scale_w = max_width / width
            scale_h = max_height / height
            scale = min(scale_w, scale_h)
            
            new_width = int(width * scale)
            new_height = int(height * scale)
            
            image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
            logger.debug(f"图片压缩：{width}x{height} -> {new_width}x{new_height}")
        
        return image
    
    def compress_image_file(self, file_path: Path) -> bool:
        """压缩单个图片文件"""
        try:
            # 获取原始文件大小
            original_size = file_path.stat().st_size
            
            # 如果文件已经很小，跳过
            if original_size < 100 * 1024:  # 小于100KB
                logger.debug(f"跳过小文件: {file_path} ({original_size/1024:.1f}KB)")
                return False
            
            # 读取图片
            image = cv2.imread(str(file_path))
            if image is None:
                logger.warning(f"无法读取图片文件: {file_path}")
                return False
            
            # 压缩尺寸
            image = self.compress_image(image)
            
            # 编码为JPEG（压缩质量）
            _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 65])
            
            # 创建临时文件
            temp_file = file_path.with_suffix('.tmp')
            with open(temp_file, 'wb') as f:
                f.write(buffer.tobytes())
            
            # 获取压缩后大小
            compressed_size = temp_file.stat().st_size
            
            # 如果压缩效果显著，替换原文件
            if compressed_size < original_size * 0.8:  # 压缩率超过20%
                temp_file.replace(file_path)
                logger.info(f"✅ 压缩成功: {file_path.name} {original_size/1024:.1f}KB -> {compressed_size/1024:.1f}KB")
                return True
            else:
                # 压缩效果不明显，删除临时文件
                temp_file.unlink()
                logger.debug(f"压缩效果不明显，保持原文件: {file_path.name}")
                return False
                
        except Exception as e:
            logger.error(f"压缩图片文件失败 {file_path}: {e}")
            return False
    
    def compress_all_images(self):
        """压缩所有训练图片"""
        if not self.images_dir.exists():
            logger.warning(f"训练图片目录不存在: {self.images_dir}")
            return
        
        # 统计信息
        total_files = 0
        compressed_files = 0
        total_original_size = 0
        total_compressed_size = 0
        
        # 遍历所有图片文件
        for image_file in self.images_dir.rglob("*.jpg"):
            if image_file.is_file():
                total_files += 1
                original_size = image_file.stat().st_size
                total_original_size += original_size
                
                # 压缩文件
                if self.compress_image_file(image_file):
                    compressed_files += 1
                
                # 计算压缩后大小
                compressed_size = image_file.stat().st_size
                total_compressed_size += compressed_size
        
        # 输出统计结果
        logger.info(f"\n📊 压缩统计:")
        logger.info(f"总文件数: {total_files}")
        logger.info(f"压缩文件数: {compressed_files}")
        logger.info(f"原始总大小: {total_original_size / (1024*1024):.1f} MB")
        logger.info(f"压缩后总大小: {total_compressed_size / (1024*1024):.1f} MB")
        
        if total_original_size > 0:
            compression_ratio = (total_original_size - total_compressed_size) / total_original_size * 100
            logger.info(f"总压缩率: {compression_ratio:.1f}%")
            logger.info(f"节省空间: {(total_original_size - total_compressed_size) / (1024*1024):.1f} MB")

def main():
    """主函数"""
    compressor = TrainingImageCompressor()
    
    logger.info("🗜️  开始压缩训练图片...")
    compressor.compress_all_images()
    logger.info("✅ 压缩完成")

if __name__ == "__main__":
    main()