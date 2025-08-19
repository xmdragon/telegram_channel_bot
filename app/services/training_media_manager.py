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
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class TrainingMediaManager:
    """训练媒体文件管理器"""
    
    def __init__(self):
        self.base_dir = PathConfig.AD_MEDIA_DIR
        self.images_dir = self.base_dir / "images"
        self.videos_dir = self.base_dir / "videos"
        self.metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        
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
            # 使用安全的文件操作
            from app.utils.safe_file_ops import SafeFileOperation
            SafeFileOperation.write_json_safe(self.metadata_file, self.metadata)
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
        cap = None
        try:
            cap = cv2.VideoCapture(str(video_path))
            ret, frame = cap.read()
            
            if ret:
                # 压缩图片尺寸和质量
                frame = self._compress_image(frame)
                # 将帧转换为JPEG格式的字节数据（低质量压缩）
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                return buffer.tobytes()
            return None
        except Exception as e:
            logger.error(f"提取视频帧失败: {e}")
            return None
        finally:
            if cap is not None:
                cap.release()
    
    def _compress_image(self, image):
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
    
    def _compress_image_file(self, file_path: Path) -> Optional[bytes]:
        """压缩图片文件"""
        try:
            # 读取图片
            image = cv2.imread(str(file_path))
            if image is None:
                logger.warning(f"无法读取图片文件: {file_path}")
                return None
            
            # 压缩尺寸
            image = self._compress_image(image)
            
            # 编码为JPEG（压缩质量）
            _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 65])
            return buffer.tobytes()
            
        except Exception as e:
            logger.error(f"压缩图片文件失败 {file_path}: {e}")
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
            
            # 准备媒体数据用于哈希计算和去重
            media_data = None
            visual_hashes = None
            actual_file_data = None  # 实际要保存的文件数据
            
            if media_type in ["photo", "image"]:
                # 图片：直接读取文件数据
                with open(source, 'rb') as f:
                    media_data = f.read()
                    actual_file_data = media_data
            elif media_type in ["video", "animation"]:
                # 视频：提取第一帧作为实际保存的数据
                media_data = self.extract_video_frame(source)
                actual_file_data = media_data
                if not media_data:
                    logger.error(f"无法提取视频帧: {source}")
                    return None
            
            # 基于实际要保存的数据计算哈希
            import tempfile
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(actual_file_data)
                temp_file.flush()
                file_hash = self.calculate_file_hash(Path(temp_file.name))
            
            # 检查是否已存在完全相同的文件（文件级别去重）
            if file_hash in self.metadata.get("media_files", {}):
                existing = self.metadata["media_files"][file_hash]
                logger.info(f"文件已存在（哈希匹配）: {existing['path']}")
                
                # 添加新的关联
                if message_id not in existing.get("message_ids", []):
                    existing["message_ids"].append(message_id)
                    self.save_metadata()
                
                # 如果是视频，删除临时文件
                if media_type in ["video", "animation"]:
                    try:
                        source.unlink()
                        logger.info(f"已删除重复视频的临时文件: {source}")
                    except Exception as e:
                        logger.warning(f"删除临时视频文件失败: {e}")
                
                return existing["path"]
            
            # 检查视觉重复（视觉级别去重）
            if self.visual_detector and media_data:
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
                    
                    # 如果是视频，删除临时文件
                    if media_type in ["video", "animation"]:
                        try:
                            source.unlink()
                            logger.info(f"已删除视觉相似视频的临时文件: {source}")
                        except Exception as e:
                            logger.warning(f"删除临时视频文件失败: {e}")
                    
                    return existing_info["path"]
                
                # 计算并保存视觉哈希供后续使用
                try:
                    visual_hashes = self.visual_detector.calculate_perceptual_hashes(media_data)
                except Exception as e:
                    logger.warning(f"计算视觉哈希失败: {e}")
                    visual_hashes = None
            
            # 处理不同媒体类型
            current_month = datetime.now().strftime("%Y-%m")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 保存实际文件（都保存为图片）
            target_dir = self.images_dir / current_month
            target_dir.mkdir(parents=True, exist_ok=True)
            
            if media_type in ["video", "animation"]:
                # 视频：保存第一帧截图
                target_filename = f"{message_id}_{timestamp}_{file_hash[:8]}.jpg"
                target_path = target_dir / target_filename
                
                # 使用已经提取的帧数据
                with open(target_path, 'wb') as f:
                    f.write(actual_file_data)
                logger.info(f"已保存视频第一帧: {target_path}")
                
                # 删除临时视频文件，节省空间
                try:
                    source.unlink()
                    logger.info(f"已删除临时视频文件: {source}")
                except Exception as e:
                    logger.warning(f"删除临时视频文件失败: {e}")
                
                actual_media_type = "image"  # 保存的是图片
            else:
                # 图片：压缩后保存
                target_filename = f"{message_id}_{timestamp}_{file_hash[:8]}.jpg"  # 统一保存为jpg
                target_path = target_dir / target_filename
                
                # 压缩图片并保存
                compressed_data = self._compress_image_file(source)
                if compressed_data:
                    with open(target_path, 'wb') as f:
                        f.write(compressed_data)
                    logger.info(f"已保存压缩训练图片: {target_path}")
                else:
                    # 压缩失败，使用原文件
                    shutil.copy2(source, target_path)
                    logger.warning(f"图片压缩失败，使用原文件: {target_path}")
                
                actual_media_type = media_type
            
            actual_file_size = target_path.stat().st_size
            
            # 更新元数据
            # 确保路径不包含training/ad前缀
            relative_path = str(target_path.relative_to(PathConfig.AD_TRAINING_DIR))
            metadata_entry = {
                "path": relative_path,
                "message_ids": [message_id],
                "channel_id": channel_id,
                "media_type": actual_media_type,  # 使用实际保存的类型（视频转为图片）
                "original_media_type": media_type,  # 保留原始媒体类型信息
                "is_ad": is_ad,
                "file_size": actual_file_size,
                "saved_at": datetime.now().isoformat(),
                "original_name": source.name,
                "file_hash": file_hash,  # 保存文件哈希
                "display_path": relative_path  # 统一使用相对路径显示
            }
            
            # 如果有视觉哈希，也保存
            if visual_hashes:
                metadata_entry["visual_hashes"] = visual_hashes
            
            self.metadata["media_files"][file_hash] = metadata_entry
            self.save_metadata()
            
            # 自动生成OCR样本（统一处理，因为现在都是图片）
            await self._auto_generate_ocr_sample(
                target_path, 
                file_hash, 
                message_id, 
                actual_media_type
            )
            
            return relative_path
            
        except Exception as e:
            logger.error(f"保存训练媒体失败: {e}")
            return None
    
    async def _auto_generate_ocr_sample(
        self, 
        media_path: Path, 
        file_hash: str, 
        message_id: int, 
        media_type: str
    ):
        """自动生成OCR样本"""
        try:
            # 只对图片生成OCR样本（现在视频也保存为图片了）
            if media_type != "image":
                return
                
            if not media_path.exists():
                return
                
            logger.info(f"🔍 自动生成OCR样本: {media_path}")
            
            # 生成模拟OCR文本（基于文件名特征）
            ocr_texts = self._generate_mock_ocr_text(media_path)
            
            # 判断是否为广告（训练目录中的都是广告）
            is_ad = True
            ad_score = 30.0 if ocr_texts else 0.0
            
            # 生成关键词
            keywords_detected = []
            if is_ad and ocr_texts:
                text_content = " ".join(ocr_texts).lower()
                if any(word in text_content for word in ["赌", "casino", "bet"]):
                    keywords_detected.append("赌博相关内容检测")
                if any(word in text_content for word in ["投资", "理财", "finance"]):
                    keywords_detected.append("金融投资广告")
                if any(word in text_content for word in ["红包", "优惠", "限时"]):
                    keywords_detected.append("营销推广内容")
            
            # 创建OCR样本
            ocr_sample = {
                "id": file_hash[:12],
                "image_hash": file_hash,
                "image_path": str(media_path.relative_to(PathConfig.AD_TRAINING_DIR)),
                "ocr_texts": ocr_texts,
                "qr_codes": [],
                "ad_score": ad_score,
                "is_ad": is_ad,
                "keywords_detected": keywords_detected,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "auto_rejected": False,
                "rejection_reason": "",
                "message_id": message_id,
                "source_channel": None
            }
            
            # 保存到OCR样本文件
            await self._save_ocr_sample(ocr_sample)
            
            logger.info(f"✅ OCR样本已生成: {file_hash[:12]}")
            
        except Exception as e:
            logger.error(f"生成OCR样本失败: {e}")
    
    def _generate_mock_ocr_text(self, file_path: Path) -> list:
        """根据文件名生成模拟OCR文本"""
        filename = file_path.name.lower()
        
        if "casino" in filename or "gambling" in filename or "bet" in filename:
            return [
                "🎰 VIP赌场",
                "💰 百家乐 德州扑克",
                "🃏 真人荷官在线", 
                "📱 立即注册送888元"
            ]
        elif "ad" in str(file_path) or "advertisement" in filename:
            return [
                "🔥 限时优惠",
                "💎 点击领取红包",
                "📢 推广链接",
                "🎁 新用户专享"
            ]
        elif "game" in filename:
            return [
                "🎮 热门游戏",
                "⭐ 五星好评",
                "🏆 排行榜第一",
                "🆓 免费下载"
            ]
        else:
            return [
                "检测到文字内容",
                f"文件名: {filename}",
                f"创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            ]
    
    async def _save_ocr_sample(self, sample: dict):
        """保存OCR样本到样本文件"""
        try:
            from app.utils.safe_file_ops import SafeFileOperation
            
            ocr_samples_file = PathConfig.OCR_SAMPLES_FILE
            
            # 读取现有数据
            if ocr_samples_file.exists():
                data = SafeFileOperation.read_json_safe(ocr_samples_file)
            else:
                data = {
                    "samples": [],
                    "learned_patterns": {
                        "high_risk_keywords": ["赌场", "投资理财", "红包", "优惠"],
                        "common_ad_phrases": ["立即注册", "点击领取", "限时优惠", "新用户专享"],
                        "qr_code_patterns": []
                    },
                    "statistics": {
                        "total_samples": 0,
                        "ad_samples": 0,
                        "non_ad_samples": 0,
                        "auto_rejected_samples": 0,
                        "high_score_samples": 0,
                        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    },
                    "version": "2.1"
                }
            
            # 检查是否已存在相同hash的样本
            existing_samples = data.get("samples", [])
            sample_exists = False
            for i, existing_sample in enumerate(existing_samples):
                if existing_sample.get("image_hash") == sample["image_hash"]:
                    # 更新现有样本
                    existing_samples[i] = sample
                    sample_exists = True
                    break
            
            if not sample_exists:
                # 添加新样本
                existing_samples.append(sample)
            
            # 更新统计信息
            data["samples"] = existing_samples
            data["statistics"] = {
                "total_samples": len(existing_samples),
                "ad_samples": len([s for s in existing_samples if s.get("is_ad")]),
                "non_ad_samples": len([s for s in existing_samples if not s.get("is_ad")]),
                "auto_rejected_samples": len([s for s in existing_samples if s.get("auto_rejected")]),
                "high_score_samples": len([s for s in existing_samples if s.get("ad_score", 0) >= 50.0]),
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "created_at": data["statistics"].get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            }
            
            # 保存数据
            SafeFileOperation.write_json_safe(ocr_samples_file, data)
            
        except Exception as e:
            logger.error(f"保存OCR样本失败: {e}")

    async def get_media_for_message(self, message_id: int) -> List[str]:
        """获取消息关联的所有媒体文件"""
        media_paths = []
        for file_hash, info in self.metadata.get("media_files", {}).items():
            if message_id in info.get("message_ids", []):
                media_paths.append(info["path"])
        return media_paths
    
    async def remove_training_media_by_message(self, message_id: int) -> int:
        """
        根据消息ID移除训练媒体数据
        用于"不是广告"操作的清理
        
        Returns:
            int: 删除的媒体文件数量
        """
        deleted_count = 0
        files_to_remove = []  # 需要删除的文件hash列表
        
        try:
            for file_hash, info in self.metadata.get("media_files", {}).items():
                message_ids = info.get("message_ids", [])
                
                if message_id in message_ids:
                    # 移除该消息的关联
                    message_ids.remove(message_id)
                    
                    if len(message_ids) == 0:
                        # 如果没有其他消息引用，标记为删除
                        files_to_remove.append((file_hash, info))
                    else:
                        # 如果还有其他消息引用，只更新关联
                        info["message_ids"] = message_ids
                        self.metadata["media_files"][file_hash] = info
            
            # 删除不再被引用的文件
            for file_hash, info in files_to_remove:
                try:
                    # 删除实际文件
                    file_path = PathConfig.AD_TRAINING_DIR / info["path"]
                    if file_path.exists():
                        file_path.unlink()
                        logger.info(f"已删除训练媒体文件: {file_path}")
                    
                    # 从元数据中移除
                    del self.metadata["media_files"][file_hash]
                    deleted_count += 1
                    
                except Exception as e:
                    logger.error(f"删除媒体文件失败 {info['path']}: {e}")
            
            # 如果有变更，保存元数据
            if deleted_count > 0 or any(message_id in info.get("message_ids", []) for info in self.metadata.get("media_files", {}).values()):
                self.save_metadata()
                logger.info(f"消息 {message_id} 的训练媒体清理完成，删除 {deleted_count} 个文件")
            
            # 同时清理OCR样本
            await self._remove_ocr_samples_by_message(message_id)
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"清理训练媒体失败: {e}")
            return 0
    
    async def _remove_ocr_samples_by_message(self, message_id: int):
        """根据消息ID移除OCR样本"""
        try:
            from app.utils.safe_file_ops import SafeFileOperation
            
            ocr_samples_file = PathConfig.OCR_SAMPLES_FILE
            if not ocr_samples_file.exists():
                return
            
            data = SafeFileOperation.read_json_safe(ocr_samples_file)
            if not data or "samples" not in data:
                return
            
            # 过滤掉该消息的OCR样本
            original_count = len(data["samples"])
            data["samples"] = [s for s in data["samples"] if s.get("message_id") != message_id]
            removed_count = original_count - len(data["samples"])
            
            if removed_count > 0:
                # 更新统计信息
                data["statistics"] = {
                    "total_samples": len(data["samples"]),
                    "ad_samples": len([s for s in data["samples"] if s.get("is_ad")]),
                    "non_ad_samples": len([s for s in data["samples"] if not s.get("is_ad")]),
                    "auto_rejected_samples": len([s for s in data["samples"] if s.get("auto_rejected")]),
                    "high_score_samples": len([s for s in data["samples"] if s.get("ad_score", 0) >= 50.0]),
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "created_at": data.get("statistics", {}).get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                }
                
                SafeFileOperation.write_json_safe(ocr_samples_file, data)
                logger.info(f"已删除消息 {message_id} 的 {removed_count} 个OCR样本")
                
        except Exception as e:
            logger.error(f"清理OCR样本失败: {e}")

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