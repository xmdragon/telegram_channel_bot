#!/usr/bin/env python3
"""
视频帧处理工具
处理已从视频截取的图片：生成OCR，更正元数据类型
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

class VideoFrameProcessor:
    def __init__(self):
        self.metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        self.ocr_samples_file = PathConfig.OCR_SAMPLES_FILE
        
    def load_metadata(self) -> dict:
        """加载元数据"""
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
            logger.info(f"元数据已保存")
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")
    
    def load_ocr_samples(self) -> dict:
        """加载OCR样本"""
        if self.ocr_samples_file.exists():
            try:
                return SafeFileOperation.read_json_safe(self.ocr_samples_file)
            except Exception as e:
                logger.error(f"加载OCR样本失败: {e}")
        
        return {"samples": []}
    
    def save_ocr_samples(self, ocr_data: dict):
        """保存OCR样本"""
        try:
            SafeFileOperation.write_json_safe(self.ocr_samples_file, ocr_data)
            logger.info(f"OCR样本已保存")
        except Exception as e:
            logger.error(f"保存OCR样本失败: {e}")
    
    async def generate_ocr_for_image(self, image_path: Path) -> dict:
        """为图片生成OCR"""
        try:
            # 导入OCR服务
            from app.services.ocr_service import OCRService
            
            ocr_service = OCRService()
            
            # 执行OCR识别（使用正确的方法名）
            result = await ocr_service.extract_image_content(str(image_path))
            
            if result and result.get('texts'):
                # 合并所有识别的文本
                combined_text = '\n'.join(result.get('texts', []))
                return {
                    "text": combined_text,
                    "confidence": result.get('ad_score', 0.0),
                    "method": "easyocr"
                }
            else:
                logger.warning(f"OCR识别失败: {image_path.name}")
                return {"text": "", "confidence": 0.0, "method": "failed"}
                
        except Exception as e:
            logger.error(f"OCR处理失败 {image_path}: {e}")
            return {"text": "", "confidence": 0.0, "method": "error"}
    
    def find_video_frames(self, metadata: dict) -> list:
        """找到所有视频帧文件"""
        video_frames = []
        
        for file_hash, info in metadata["media_files"].items():
            # 检查是否为视频类型但文件扩展名是图片
            if (info.get("type") == "video" or 
                info.get("original_media_type") == "video" or
                info.get("media_type") == "video"):
                
                file_path = PathConfig.AD_TRAINING_DIR / info["path"]
                
                # 检查文件是否是图片格式
                if file_path.exists() and file_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                    video_frames.append({
                        "hash": file_hash,
                        "info": info,
                        "path": file_path
                    })
        
        return video_frames
    
    async def process_video_frames(self, dry_run: bool = False):
        """处理视频帧"""
        if not self.metadata_file.exists():
            logger.warning("元数据文件不存在")
            return
        
        logger.info(f"🎬 {'预览模式' if dry_run else '执行模式'}：开始处理视频帧...")
        
        # 加载数据
        metadata = self.load_metadata()
        ocr_data = self.load_ocr_samples()
        
        # 找到视频帧文件
        video_frames = self.find_video_frames(metadata)
        
        if not video_frames:
            logger.info("没有找到需要处理的视频帧文件")
            return
        
        logger.info(f"发现 {len(video_frames)} 个视频帧文件需要处理")
        
        stats = {
            "processed": 0,
            "ocr_generated": 0,
            "metadata_updated": 0,
            "errors": 0
        }
        
        for frame in video_frames:
            try:
                file_hash = frame["hash"]
                info = frame["info"]
                file_path = frame["path"]
                
                logger.info(f"处理: {file_path.name}")
                
                # 1. 生成OCR（如果还没有）
                existing_ocr = None
                for sample in ocr_data["samples"]:
                    if sample.get("file_hash") == file_hash:
                        existing_ocr = sample
                        break
                
                if not existing_ocr:
                    logger.info(f"  生成OCR: {file_path.name}")
                    if not dry_run:
                        ocr_result = await self.generate_ocr_for_image(file_path)
                        
                        # 添加OCR样本
                        ocr_sample = {
                            "file_hash": file_hash,
                            "file_path": str(file_path.relative_to(PathConfig.AD_TRAINING_DIR)),
                            "message_ids": info.get("message_ids", []),
                            "text": ocr_result["text"],
                            "confidence": ocr_result["confidence"],
                            "method": ocr_result["method"],
                            "created_at": datetime.now().isoformat(),
                            "source": "video_frame_processing"
                        }
                        
                        ocr_data["samples"].append(ocr_sample)
                        stats["ocr_generated"] += 1
                else:
                    logger.debug(f"  OCR已存在: {file_path.name}")
                
                # 2. 更正元数据类型
                if info.get("type") != "image":
                    logger.info(f"  更正类型: {info.get('type')} -> image")
                    if not dry_run:
                        info["type"] = "image"
                        info["media_type"] = "image"
                        # 保留原始媒体类型记录
                        if "original_media_type" not in info:
                            info["original_media_type"] = "video"
                        
                        metadata["media_files"][file_hash] = info
                        stats["metadata_updated"] += 1
                
                stats["processed"] += 1
                
            except Exception as e:
                logger.error(f"处理文件失败 {frame['path']}: {e}")
                stats["errors"] += 1
        
        # 保存数据
        if not dry_run and (stats["ocr_generated"] > 0 or stats["metadata_updated"] > 0):
            if stats["ocr_generated"] > 0:
                self.save_ocr_samples(ocr_data)
            if stats["metadata_updated"] > 0:
                self.save_metadata(metadata)
        
        # 输出结果
        logger.info(f"\n📊 处理结果:")
        logger.info(f"模式: {'预览模式' if dry_run else '执行模式'}")
        logger.info(f"处理文件: {stats['processed']} 个")
        logger.info(f"生成OCR: {stats['ocr_generated']} 个")
        logger.info(f"更正元数据: {stats['metadata_updated']} 个")
        logger.info(f"错误文件: {stats['errors']} 个")
        
        return stats

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="视频帧处理工具")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际修改文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    processor = VideoFrameProcessor()
    
    if args.dry_run:
        logger.info("🔍 预览模式：检查需要处理的视频帧...")
    else:
        logger.info("⚠️  警告：这将生成OCR并更新元数据！")
        confirm = input("确认执行吗？(y/N): ")
        if confirm.lower() != 'y':
            logger.info("操作已取消")
            return
    
    result = await processor.process_video_frames(dry_run=args.dry_run)
    
    if args.dry_run:
        logger.info("✅ 预览完成，使用不带 --dry-run 参数执行实际操作")
    else:
        logger.info("✅ 视频帧处理完成")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())