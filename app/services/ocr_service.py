"""
重构后的OCR服务 - 模块化设计
协调OCR核心、图像处理、二维码检测和广告分析等模块
"""
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from .ocr import OCRCore, ImageProcessor, QRDetector, AdAnalyzer, CacheManager

logger = logging.getLogger(__name__)


class OCRService:
    """重构后的OCR服务类 - 协调各个专门模块"""
    
    def __init__(self):
        # 初始化各个专门模块
        self.ocr_core = OCRCore()
        self.image_processor = ImageProcessor()
        self.qr_detector = QRDetector()
        self.ad_analyzer = AdAnalyzer()
        self.cache_manager = CacheManager()
        
        # 线程池复用OCR核心的线程池
        self.thread_pool = self.ocr_core.thread_pool
        
        # 初始化状态
        self.initialized = self.ocr_core.initialized
        
        logger.info("✅ OCR服务重构完成 - 模块化架构已启用")
    
    async def extract_image_content(self, image_path: str) -> Dict[str, Any]:
        """
        从图片中提取文字和二维码内容
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            包含文字和二维码信息的字典
        """
        if not Path(image_path).exists():
            logger.warning(f"图片文件不存在: {image_path}")
            return self._empty_result()
        
        try:
            # 检查缓存
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            image_hash = self.cache_manager.calculate_image_hash(image_data)
            cached_result = await self.cache_manager.get(image_hash)
            
            if cached_result:
                logger.debug(f"使用缓存的OCR结果: {image_path}")
                return cached_result
            
            # 并行执行文字提取和二维码检测
            text_task = self._extract_text_async(image_path)
            qr_task = self._detect_qrcodes_async(image_path)
            
            # 等待两个任务完成
            texts, qr_codes = await asyncio.gather(text_task, qr_task)
            
            # 合并所有文字内容
            all_texts = texts.copy()
            for qr in qr_codes:
                if qr.get('data'):
                    all_texts.append(qr['data'])
            
            combined_text = ' '.join(all_texts)
            
            # 分析广告内容
            has_ad_content, ad_score, ad_indicators = self.ad_analyzer.analyze_ad_content(
                texts, qr_codes, combined_text
            )
            
            result = {
                'texts': texts,
                'qr_codes': qr_codes,
                'combined_text': combined_text,
                'has_ad_content': has_ad_content,
                'ad_score': ad_score,
                'ad_indicators': ad_indicators
            }
            
            # 更新缓存
            await self.cache_manager.set(image_hash, result)
            
            logger.info(f"图片内容提取完成: 文字{len(texts)}条, 二维码{len(qr_codes)}个, 广告分数{ad_score:.2f}")
            
            # 保存OCR样本（异步执行，不影响主流程）
            try:
                asyncio.create_task(self._save_ocr_sample(
                    image_path=image_path,
                    image_hash=image_hash,
                    texts=texts,
                    qr_codes=[qr.get('data', '') for qr in qr_codes if qr.get('data')],
                    ad_score=ad_score,
                    is_ad=has_ad_content,
                    keywords_detected=ad_indicators
                ))
            except Exception as e:
                logger.debug(f"保存OCR样本失败（不影响主流程）: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"图片内容提取失败: {e}")
            return self._empty_result()
    
    async def _extract_text_async(self, image_path: str) -> List[str]:
        """异步文字提取"""
        if self.ocr_core.is_available():
            # 使用真实OCR引擎
            return await asyncio.get_event_loop().run_in_executor(
                self.thread_pool, self.ocr_core.extract_text_sync, image_path
            )
        else:
            # 使用图像特征分析回退方案
            return await asyncio.get_event_loop().run_in_executor(
                self.thread_pool, self.image_processor.extract_text_features_fallback, image_path
            )
    
    async def _detect_qrcodes_async(self, image_path: str) -> List[Dict[str, Any]]:
        """异步二维码检测"""
        return await asyncio.get_event_loop().run_in_executor(
            self.thread_pool, self.qr_detector.detect_qrcodes_sync, image_path
        )
    
    def analyze_image_for_ads(self, texts: List[str], qr_codes: List[Dict]) -> Dict[str, Any]:
        """
        专门用于广告检测的图片内容分析
        
        Args:
            texts: 文字列表
            qr_codes: 二维码列表
            
        Returns:
            广告分析结果
        """
        return self.ad_analyzer.analyze_for_ads(texts, qr_codes)
    
    async def batch_extract_content(self, image_paths: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        批量提取多张图片的内容
        
        Args:
            image_paths: 图片路径列表
            
        Returns:
            以图片路径为key的结果字典
        """
        tasks = [self.extract_image_content(path) for path in image_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = {}
        for i, result in enumerate(results):
            path = image_paths[i]
            if isinstance(result, Exception):
                logger.error(f"批量OCR处理失败 {path}: {result}")
                output[path] = {**self._empty_result(), 'error': str(result)}
            else:
                output[path] = result
        
        return output
    
    def get_stats(self) -> Dict[str, Any]:
        """获取OCR服务统计信息"""
        cache_stats = self.cache_manager.get_stats()
        
        return {
            'initialized': self.initialized,
            'ocr_engine_available': self.ocr_core.is_available(),
            'thread_pool_workers': self.thread_pool._max_workers,
            'supported_languages': ['中文', '英文'] if self.initialized else [],
            'ad_patterns_count': self.ad_analyzer.get_pattern_count(),
            **cache_stats
        }
    
    async def clear_cache(self):
        """清除缓存"""
        await self.cache_manager.clear()
    
    def _empty_result(self) -> Dict[str, Any]:
        """返回空结果"""
        return {
            'texts': [],
            'qr_codes': [],
            'combined_text': '',
            'has_ad_content': False,
            'ad_score': 0.0,
            'ad_indicators': []
        }
    
    async def _save_ocr_sample(
        self,
        image_path: str,
        image_hash: str,
        texts: List[str],
        qr_codes: List[str],
        ad_score: float,
        is_ad: bool,
        keywords_detected: List[str],
        auto_rejected: bool = False,
        rejection_reason: str = "",
        message_id: Optional[int] = None,
        source_channel: Optional[str] = None
    ):
        """保存OCR识别样本"""
        try:
            # 延迟导入，避免循环依赖
            from app.services.ocr_sample_manager import ocr_sample_manager
            
            await ocr_sample_manager.save_sample(
                image_hash=image_hash,
                image_path=image_path,
                ocr_texts=texts,
                qr_codes=qr_codes,
                ad_score=ad_score,
                is_ad=is_ad,
                keywords_detected=keywords_detected,
                auto_rejected=auto_rejected,
                rejection_reason=rejection_reason,
                message_id=message_id,
                source_channel=source_channel
            )
            
        except Exception as e:
            logger.debug(f"保存OCR样本失败: {e}")
    
    def __del__(self):
        """析构函数，清理资源"""
        # OCR核心模块会处理线程池清理
        pass


# 全局OCR服务实例
ocr_service = OCRService()