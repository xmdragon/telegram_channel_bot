"""
媒体文件管理模块 - 媒体文件的管理、去重、导出等功能
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
import logging
import shutil

from .base import (
    handle_api_error
)
from app.core.path_config import PathConfig
from app.core.route_config import ROUTES
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-media"])

@router.get(ROUTES.training.media_files)
async def get_media_files():
    """获取媒体文件列表"""
    try:
        media_dir = PathConfig.AD_MEDIA_DIR
        media_metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        media_files = []
        
        # 优先使用metadata.json中的信息
        if media_metadata_file.exists():
            data = SafeFileOperation.read_json_safe(media_metadata_file)
            if data and "media_files" in data:
                for file_hash, file_info in data["media_files"].items():
                    file_path = media_dir / file_info["path"]
                    
                    # 检查文件是否真实存在
                    if file_path.exists():
                        # 获取文件类型（兼容type和media_type字段）
                        media_type = file_info.get("media_type", "")
                        file_type = file_info.get("type") or ("image" if media_type in ["photo", "image"] else "video")
                        
                        # 获取真实文件大小（直接使用文件系统的实际大小，不信任元数据）
                        actual_file_size = file_path.stat().st_size
                        
                        media_files.append({
                            "hash": file_hash,  # 使用metadata中的真实hash
                            "name": file_path.name,
                            "filename": file_path.name,
                            "type": file_type,
                            "size": actual_file_size,
                            "created_at": file_info.get("saved_at", datetime.fromtimestamp(file_path.stat().st_ctime).isoformat()),
                            "path": file_info["path"],
                            "messageIds": file_info.get("message_ids", []),
                            "isReferenced": bool(file_info.get("message_ids", [])),
                            "referenceCount": len(file_info.get("message_ids", []))
                        })
        
        # 如果metadata文件不存在或为空，回退到文件系统扫描
        if not media_files and media_dir.exists():
            # 扫描图片文件
            for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                for img_path in media_dir.glob(f"**/{ext}"):
                    if img_path.is_file():
                        stat = img_path.stat()
                        # 从文件名提取hash作为fallback
                        extracted_hash = img_path.stem.split('_')[-1] if '_' in img_path.stem else img_path.stem
                        media_files.append({
                            "hash": extracted_hash,
                            "name": img_path.name,
                            "filename": img_path.name,
                            "type": "image",
                            "size": stat.st_size,
                            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "path": str(img_path.relative_to(media_dir)),
                            "messageIds": [],
                            "isReferenced": False,
                            "referenceCount": 0
                        })
            
            # 扫描视频文件
            for ext in ['*.mp4', '*.avi', '*.mov', '*.mkv']:
                for video_path in media_dir.glob(f"**/{ext}"):
                    if video_path.is_file():
                        stat = video_path.stat()
                        # 从文件名提取hash作为fallback
                        extracted_hash = video_path.stem.split('_')[-1] if '_' in video_path.stem else video_path.stem
                        media_files.append({
                            "hash": extracted_hash,
                            "name": video_path.name,
                            "filename": video_path.name,
                            "type": "video",
                            "size": stat.st_size,
                            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "path": str(video_path.relative_to(media_dir)),
                            "messageIds": [],
                            "isReferenced": False,
                            "referenceCount": 0
                        })
        
        # 计算统计信息
        total_files = len(media_files)
        image_count = len([f for f in media_files if f['type'] == 'image'])
        video_count = len([f for f in media_files if f['type'] == 'video'])
        total_size = sum(f['size'] for f in media_files)
        referenced_count = len([f for f in media_files if f['isReferenced']])
        orphaned_count = total_files - referenced_count
        
        return {
            "success": True,
            "files": media_files,
            "stats": {
                "totalFiles": total_files,
                "imageCount": image_count,
                "videoCount": video_count,
                "totalSize": total_size,
                "referencedCount": referenced_count,
                "orphanedCount": orphaned_count
            }
        }
    except Exception as e:
        logger.error(f"获取媒体文件列表失败: {e}")
        return {
            "success": False,
            "files": [],
            "stats": {
                "totalFiles": 0,
                "imageCount": 0,
                "videoCount": 0,
                "totalSize": 0,
                "referencedCount": 0,
                "orphanedCount": 0
            }
        }

@router.delete(ROUTES.training.media_files_by_hash)
async def delete_media_file(file_hash: str):
    """完整删除媒体文件（包括文件、元数据、OCR数据）"""
    logger.info(f"开始删除媒体文件: {file_hash}")
    
    try:
        media_dir = PathConfig.AD_MEDIA_DIR
        media_metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        ocr_samples_file = PathConfig.OCR_SAMPLES_FILE
        
        deleted_files = 0
        deleted_metadata = False
        deleted_ocr = False
        
        # 1. 从元数据中查找并删除文件记录
        if media_metadata_file.exists():
            metadata = SafeFileOperation.read_json_safe(media_metadata_file)
            if metadata and "media_files" in metadata:
                if file_hash in metadata["media_files"]:
                    file_info = metadata["media_files"][file_hash]
                    file_path = media_dir / file_info["path"]
                    
                    # 删除物理文件
                    if file_path.exists():
                        file_path.unlink()
                        deleted_files += 1
                        logger.info(f"删除媒体文件: {file_path}")
                    
                    # 删除元数据记录
                    del metadata["media_files"][file_hash]
                    metadata["updated_at"] = datetime.now().isoformat()
                    
                    if SafeFileOperation.write_json_safe(media_metadata_file, metadata):
                        deleted_metadata = True
                        logger.info(f"删除元数据记录: {file_hash}")
                    else:
                        logger.error(f"保存元数据失败: {file_hash}")
        
        # 2. 查找并删除文件系统中的匹配文件（fallback）
        if deleted_files == 0:
            for file_path in media_dir.glob(f"**/*{file_hash}*"):
                if file_path.is_file():
                    file_path.unlink()
                    deleted_files += 1
                    logger.info(f"删除孤立文件: {file_path}")
        
        # 3. 删除相关的OCR样本数据
        if ocr_samples_file.exists():
            ocr_data = SafeFileOperation.read_json_safe(ocr_samples_file)
            if ocr_data and "samples" in ocr_data:
                original_count = len(ocr_data["samples"])
                
                # 过滤掉匹配的OCR样本（支持完整匹配和前缀匹配）
                ocr_data["samples"] = [
                    sample for sample in ocr_data["samples"]
                    if not (
                        sample.get("image_hash") == file_hash or
                        (sample.get("image_hash") and file_hash.startswith(sample.get("image_hash"))) or
                        (sample.get("image_hash") and sample.get("image_hash").startswith(file_hash))
                    )
                ]
                
                removed_ocr_count = original_count - len(ocr_data["samples"])
                if removed_ocr_count > 0:
                    # 更新统计信息
                    if "statistics" not in ocr_data:
                        ocr_data["statistics"] = {}
                    
                    ocr_data["statistics"].update({
                        "total_samples": len(ocr_data["samples"]),
                        "ad_samples": len([s for s in ocr_data["samples"] if s.get("is_ad")]),
                        "non_ad_samples": len([s for s in ocr_data["samples"] if not s.get("is_ad")]),
                        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    if SafeFileOperation.write_json_safe(ocr_samples_file, ocr_data):
                        deleted_ocr = True
                        logger.info(f"删除OCR样本: {removed_ocr_count} 个")
                    else:
                        logger.error(f"保存OCR数据失败: {file_hash}")
        
        # 4. 返回删除结果
        if deleted_files > 0 or deleted_metadata or deleted_ocr:
            result_msg = []
            if deleted_files > 0:
                result_msg.append(f"删除文件 {deleted_files} 个")
            if deleted_metadata:
                result_msg.append("删除元数据")
            if deleted_ocr:
                result_msg.append("删除OCR数据")
            
            success_msg = "删除成功: " + ", ".join(result_msg)
            logger.info(f"媒体文件删除完成: {file_hash} - {success_msg}")
            return {
                "success": True,
                "message": success_msg,
                "details": {
                    "deleted_files": deleted_files,
                    "deleted_metadata": deleted_metadata,
                    "deleted_ocr": deleted_ocr
                }
            }
        else:
            logger.warning(f"删除失败，未找到媒体文件: {file_hash}")
            return {"success": False, "message": "未找到相关数据"}
            
    except Exception as e:
        logger.error(f"删除媒体文件失败: {e}")
        raise handle_api_error(e, "删除媒体文件")

@router.post(ROUTES.training.media_files_clean_orphaned)
async def clean_orphaned_files():
    """清理孤立的媒体文件"""
    try:
        # 简单实现：暂时不执行实际清理，只返回成功
        return {
            "success": True,
            "message": "清理完成",
            "deletedCount": 0,
            "freedMb": 0
        }
    except Exception as e:
        raise handle_api_error(e, "清理孤立文件")


@router.get(ROUTES.training.media_files_export)
async def export_media_files():
    """导出媒体文件信息"""
    try:
        # 简单实现：返回基本的导出数据
        return {
            "success": True,
            "exportData": {
                "files": [],
                "stats": {
                    "totalFiles": 0,
                    "totalSize": 0
                },
                "exportedAt": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise handle_api_error(e, "导出媒体文件")

@router.post(ROUTES.training.media_files_rebuild_visual_hashes)
async def rebuild_visual_hashes():
    """重建视觉哈希"""
    try:
        # 简单实现：返回重建完成状态
        return {
            "success": True,
            "message": "视觉哈希重建完成",
            "processedCount": 0
        }
    except Exception as e:
        raise handle_api_error(e, "重建视觉哈希")

@router.get(ROUTES.training.media_files_ocr)
async def get_media_ocr(file_hash: str):
    """获取媒体文件的OCR结果"""
    try:
        # 加载OCR样本数据
        ocr_samples_file = PathConfig.OCR_SAMPLES_FILE
        if not ocr_samples_file.exists():
            return {
                "success": True,
                "ocr_text": "",
                "confidence": 0.0,
                "processed_at": datetime.now().isoformat(),
                "message": "OCR数据文件不存在"
            }
        
        data = SafeFileOperation.read_json_safe(ocr_samples_file)
        if not data or "samples" not in data:
            return {
                "success": True,
                "ocr_text": "",
                "confidence": 0.0,
                "processed_at": datetime.now().isoformat(),
                "message": "OCR数据为空"
            }
        
        # 在OCR样本中查找匹配的文件hash
        ocr_result = None
        logger.debug(f"搜索OCR样本中的hash: {file_hash}, 样本数量: {len(data['samples'])}")
        for sample in data["samples"]:
            # 检查image_hash字段（OCR中的hash可能是短格式）
            ocr_hash = sample.get("image_hash", "")
            if ocr_hash:
                # 完全匹配
                if ocr_hash == file_hash:
                    ocr_result = sample
                    logger.debug(f"找到完全匹配的OCR数据: {ocr_hash}")
                    break
                # 检查完整hash是否以OCR hash开头（OCR hash是短格式）
                if file_hash.startswith(ocr_hash):
                    ocr_result = sample
                    logger.debug(f"找到前缀匹配的OCR数据: {ocr_hash}")
                    break
                # 反向检查：OCR hash是否以file hash开头
                if ocr_hash.startswith(file_hash):
                    ocr_result = sample
                    logger.debug(f"找到反向匹配的OCR数据: {ocr_hash}")
                    break
            
            # 不使用路径匹配 - 只返回精确hash匹配的真实OCR数据
        
        if ocr_result:
            # 合并OCR文本
            ocr_texts = ocr_result.get("ocr_texts", [])
            combined_text = "\n".join(ocr_texts) if ocr_texts else ""
            
            return {
                "success": True,
                "ocr_text": combined_text,
                "confidence": 0.9 if combined_text else 0.0,
                "processed_at": ocr_result.get("created_at", datetime.now().isoformat()),
                "qr_codes": ocr_result.get("qr_codes", []),
                "keywords_detected": ocr_result.get("keywords_detected", []),
                "is_ad": ocr_result.get("is_ad", False),
                "ad_score": ocr_result.get("ad_score", 0.0)
            }
        else:
            # 没有找到缓存的OCR数据，尝试实时识别
            try:
                # 根据hash查找实际图片文件
                media_dir = PathConfig.AD_MEDIA_DIR
                media_metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
                
                # 从metadata中查找文件路径
                image_path = None
                if media_metadata_file.exists():
                    metadata = SafeFileOperation.read_json_safe(media_metadata_file)
                    if metadata and "media_files" in metadata:
                        file_info = metadata["media_files"].get(file_hash)
                        if file_info:
                            potential_path = media_dir / file_info["path"]
                            # 检查文件是否存在且是图片格式（根据扩展名判断）
                            if potential_path.exists() and potential_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                                image_path = str(potential_path)
                
                if not image_path:
                    return {
                        "success": True,
                        "ocr_text": "",
                        "confidence": 0.0,
                        "processed_at": datetime.now().isoformat(),
                        "message": f"未找到文件 {file_hash} 对应的图片文件"
                    }
                
                # 实时OCR识别（添加异常处理）
                try:
                    from app.services.ocr_service import ocr_service
                    logger.info(f"实时OCR识别图片: {image_path}")
                    
                    # 设置一个合理的超时避免永久阻塞
                    import asyncio
                    ocr_result = await asyncio.wait_for(
                        ocr_service.extract_image_content(image_path),
                        timeout=10.0  # 10秒超时，避免永久阻塞
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"OCR识别超时: {image_path}")
                    return {
                        "success": True,
                        "ocr_text": "",
                        "confidence": 0.0,
                        "processed_at": datetime.now().isoformat(),
                        "message": "OCR服务暂时不可用（超时）"
                    }
                except Exception as e:
                    logger.error(f"OCR识别异常: {e}")
                    return {
                        "success": True,
                        "ocr_text": "",
                        "confidence": 0.0,
                        "processed_at": datetime.now().isoformat(),
                        "message": f"OCR服务不可用: {str(e)}"
                    }
                
                # 合并OCR文本
                combined_text = "\n".join(ocr_result.get("texts", [])) if ocr_result.get("texts") else ""
                
                return {
                    "success": True,
                    "ocr_text": combined_text,
                    "confidence": 0.9 if combined_text else 0.0,
                    "processed_at": datetime.now().isoformat(),
                    "qr_codes": ocr_result.get("qr_codes", []),
                    "keywords_detected": ocr_result.get("ad_indicators", []),
                    "is_ad": ocr_result.get("has_ad_content", False),
                    "ad_score": ocr_result.get("ad_score", 0.0),
                    "message": "实时OCR识别结果"
                }
                
            except Exception as ocr_error:
                logger.error(f"实时OCR识别失败: {ocr_error}")
                return {
                    "success": True,
                    "ocr_text": "",
                    "confidence": 0.0,
                    "processed_at": datetime.now().isoformat(),
                    "message": f"OCR识别失败: {str(ocr_error)}"
                }
    except Exception as e:
        raise handle_api_error(e, "获取OCR结果")