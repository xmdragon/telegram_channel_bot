"""
OCR样本管理器
用于收集、存储和学习OCR识别样本，持续改进广告检测能力
"""
import json
import logging
import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import re

logger = logging.getLogger(__name__)

@dataclass
class OCRSample:
    """OCR样本数据结构"""
    id: str
    image_hash: str
    image_path: str
    ocr_texts: List[str]
    qr_codes: List[str]
    ad_score: float
    is_ad: bool
    keywords_detected: List[str]
    created_at: str
    auto_rejected: bool = False
    rejection_reason: str = ""
    message_id: Optional[int] = None
    source_channel: Optional[str] = None

class OCRSampleManager:
    """OCR样本管理器"""
    
    def __init__(self, samples_file: str = "data/ocr_samples.json"):
        self.samples_file = Path(samples_file)
        self.samples_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._cache = None
        self._cache_timestamp = None
        
    async def _load_data(self, force_reload: bool = False) -> Dict:
        """加载样本数据"""
        try:
            # 简单的缓存机制
            if not force_reload and self._cache and self._cache_timestamp:
                file_mtime = self.samples_file.stat().st_mtime if self.samples_file.exists() else 0
                if file_mtime <= self._cache_timestamp:
                    return self._cache
            
            if not self.samples_file.exists():
                # 如果文件不存在，创建默认结构
                default_data = {
                    "samples": [],
                    "learned_patterns": {
                        "high_risk_keywords": [],
                        "common_ad_phrases": [],
                        "qr_code_patterns": []
                    },
                    "statistics": {
                        "total_samples": 0,
                        "ad_samples": 0,
                        "non_ad_samples": 0,
                        "auto_rejected_samples": 0,
                        "high_score_samples": 0,
                        "last_updated": None,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    },
                    "version": "1.0"
                }
                await self._save_data(default_data)
                return default_data
            
            with open(self.samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 更新缓存
            self._cache = data
            self._cache_timestamp = self.samples_file.stat().st_mtime
            
            return data
            
        except Exception as e:
            logger.error(f"加载OCR样本数据失败: {e}")
            return {
                "samples": [],
                "learned_patterns": {"high_risk_keywords": [], "common_ad_phrases": [], "qr_code_patterns": []},
                "statistics": {"total_samples": 0, "ad_samples": 0, "non_ad_samples": 0}
            }
    
    async def _save_data(self, data: Dict) -> bool:
        """保存样本数据"""
        try:
            # 更新统计信息
            data["statistics"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 原子性写入
            temp_file = self.samples_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            temp_file.replace(self.samples_file)
            
            # 更新缓存
            self._cache = data
            self._cache_timestamp = self.samples_file.stat().st_mtime
            
            logger.info(f"OCR样本数据已保存到 {self.samples_file}")
            return True
            
        except Exception as e:
            logger.error(f"保存OCR样本数据失败: {e}")
            return False
    
    async def save_sample(
        self,
        image_hash: str,
        image_path: str,
        ocr_texts: List[str],
        qr_codes: List[str] = None,
        ad_score: float = 0.0,
        is_ad: bool = False,
        keywords_detected: List[str] = None,
        auto_rejected: bool = False,
        rejection_reason: str = "",
        message_id: Optional[int] = None,
        source_channel: Optional[str] = None
    ) -> bool:
        """保存OCR识别样本"""
        async with self._lock:
            try:
                data = await self._load_data()
                
                # 生成唯一ID
                sample_id = hashlib.md5(
                    f"{image_hash}_{datetime.now().isoformat()}".encode()
                ).hexdigest()[:12]
                
                # 创建样本
                sample = OCRSample(
                    id=sample_id,
                    image_hash=image_hash,
                    image_path=image_path,
                    ocr_texts=ocr_texts or [],
                    qr_codes=qr_codes or [],
                    ad_score=ad_score,
                    is_ad=is_ad,
                    keywords_detected=keywords_detected or [],
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    auto_rejected=auto_rejected,
                    rejection_reason=rejection_reason,
                    message_id=message_id,
                    source_channel=source_channel
                )
                
                # 添加到样本列表
                data["samples"].append(asdict(sample))
                
                # 更新统计信息
                stats = data["statistics"]
                stats["total_samples"] = len(data["samples"])
                stats["ad_samples"] = sum(1 for s in data["samples"] if s.get("is_ad", False))
                stats["non_ad_samples"] = stats["total_samples"] - stats["ad_samples"]
                stats["auto_rejected_samples"] = sum(1 for s in data["samples"] if s.get("auto_rejected", False))
                stats["high_score_samples"] = sum(1 for s in data["samples"] if s.get("ad_score", 0) >= 50)
                
                # 限制样本数量（最多保留10000个样本）
                if len(data["samples"]) > 10000:
                    # 保留最新的9000个样本
                    data["samples"] = sorted(
                        data["samples"], 
                        key=lambda x: x.get("created_at", ""), 
                        reverse=True
                    )[:9000]
                    logger.info(f"OCR样本数量超限，已清理到 {len(data['samples'])} 个")
                
                success = await self._save_data(data)
                
                if success:
                    logger.info(f"已保存OCR样本: {sample_id}, 广告分数: {ad_score}, 自动拒绝: {auto_rejected}")
                    
                return success
                
            except Exception as e:
                logger.error(f"保存OCR样本失败: {e}")
                return False
    
    async def get_samples(
        self, 
        limit: int = 100, 
        offset: int = 0,
        is_ad: Optional[bool] = None,
        auto_rejected: Optional[bool] = None,
        min_score: Optional[float] = None
    ) -> List[Dict]:
        """获取样本列表"""
        try:
            data = await self._load_data()
            samples = data.get("samples", [])
            
            # 筛选条件
            if is_ad is not None:
                samples = [s for s in samples if s.get("is_ad") == is_ad]
            
            if auto_rejected is not None:
                samples = [s for s in samples if s.get("auto_rejected") == auto_rejected]
                
            if min_score is not None:
                samples = [s for s in samples if s.get("ad_score", 0) >= min_score]
            
            # 按时间倒序排序
            samples = sorted(samples, key=lambda x: x.get("created_at", ""), reverse=True)
            
            # 分页
            return samples[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"获取OCR样本失败: {e}")
            return []
    
    async def get_statistics(self) -> Dict:
        """获取统计信息"""
        try:
            data = await self._load_data()
            return data.get("statistics", {})
        except Exception as e:
            logger.error(f"获取OCR统计信息失败: {e}")
            return {}
    
    async def delete_sample(self, sample_id: str) -> bool:
        """删除样本"""
        async with self._lock:
            try:
                data = await self._load_data()
                original_count = len(data["samples"])
                
                # 删除指定样本
                data["samples"] = [s for s in data["samples"] if s.get("id") != sample_id]
                
                if len(data["samples"]) < original_count:
                    # 更新统计信息
                    stats = data["statistics"]
                    stats["total_samples"] = len(data["samples"])
                    stats["ad_samples"] = sum(1 for s in data["samples"] if s.get("is_ad", False))
                    stats["non_ad_samples"] = stats["total_samples"] - stats["ad_samples"]
                    stats["auto_rejected_samples"] = sum(1 for s in data["samples"] if s.get("auto_rejected", False))
                    stats["high_score_samples"] = sum(1 for s in data["samples"] if s.get("ad_score", 0) >= 50)
                    
                    success = await self._save_data(data)
                    if success:
                        logger.info(f"已删除OCR样本: {sample_id}")
                    return success
                else:
                    logger.warning(f"未找到OCR样本: {sample_id}")
                    return False
                    
            except Exception as e:
                logger.error(f"删除OCR样本失败: {e}")
                return False
    
    async def learn_from_samples(self) -> Dict[str, Any]:
        """从样本中学习新的广告模式"""
        try:
            data = await self._load_data()
            samples = data.get("samples", [])
            
            # 分析广告样本
            ad_samples = [s for s in samples if s.get("is_ad", False)]
            
            if len(ad_samples) < 10:
                return {"success": False, "message": "广告样本数量不足，需要至少10个样本"}
            
            # 提取高频关键词
            all_texts = []
            for sample in ad_samples:
                all_texts.extend(sample.get("ocr_texts", []))
                all_texts.extend(sample.get("qr_codes", []))
            
            # 统计关键词频率
            keyword_freq = {}
            for text in all_texts:
                if not text or len(text.strip()) < 2:
                    continue
                
                # 提取数字+字符组合（可能是平台名称）
                patterns = [
                    r'[A-Za-z0-9]{2,}(?:娱乐|平台|官网)',
                    r'(?:微信|QQ|客服)[:：\s]*[A-Za-z0-9_-]+',
                    r'[0-9]+[万萬uU]',
                    r'USDT|泰达币|虚拟币',
                    r'(?:充值|提款|返水|优惠|首充)',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    for match in matches:
                        keyword = match.strip().lower()
                        if len(keyword) >= 2:
                            keyword_freq[keyword] = keyword_freq.get(keyword, 0) + 1
            
            # 选取高频关键词（出现次数>=3）
            new_keywords = [
                keyword for keyword, freq in keyword_freq.items() 
                if freq >= 3 and keyword not in data["learned_patterns"]["high_risk_keywords"]
            ]
            
            # 更新学习到的模式
            if new_keywords:
                data["learned_patterns"]["high_risk_keywords"].extend(new_keywords[:20])  # 最多添加20个
                await self._save_data(data)
                
                logger.info(f"从OCR样本中学习到 {len(new_keywords)} 个新关键词: {new_keywords}")
                
                return {
                    "success": True,
                    "new_keywords": new_keywords,
                    "total_samples": len(samples),
                    "ad_samples": len(ad_samples),
                    "message": f"成功学习到 {len(new_keywords)} 个新关键词"
                }
            else:
                return {
                    "success": True,
                    "new_keywords": [],
                    "total_samples": len(samples),
                    "ad_samples": len(ad_samples),
                    "message": "未发现新的关键词模式"
                }
                
        except Exception as e:
            logger.error(f"OCR样本学习失败: {e}")
            return {"success": False, "message": f"学习失败: {str(e)}"}
    
    async def export_for_training(self, output_file: Optional[str] = None) -> str:
        """导出用于训练的数据"""
        try:
            data = await self._load_data()
            samples = data.get("samples", [])
            
            # 准备训练数据
            training_data = {
                "ad_texts": [],
                "non_ad_texts": [],
                "keywords": data.get("learned_patterns", {}).get("high_risk_keywords", []),
                "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_samples": len(samples)
            }
            
            for sample in samples:
                texts = sample.get("ocr_texts", []) + sample.get("qr_codes", [])
                if sample.get("is_ad", False):
                    training_data["ad_texts"].extend(texts)
                else:
                    training_data["non_ad_texts"].extend(texts)
            
            # 保存到文件
            if not output_file:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = f"data/ocr_training_export_{timestamp}.json"
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(training_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"OCR训练数据已导出到: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"导出OCR训练数据失败: {e}")
            raise

# 全局实例
ocr_sample_manager = OCRSampleManager()