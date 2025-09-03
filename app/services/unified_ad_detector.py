"""
统一广告检测器 - Linus式设计
6步骤统一广告判定流程：文本向量检测优先，媒体检测补充，自动训练数据收集

Author: Claude  
Created: 2025-09-03
"""

import logging
import time
import json
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class UnifiedAdDetector:
    """统一广告检测器 - 6步骤流程处理器"""
    
    def __init__(self):
        """初始化统一检测器"""
        self.step_timers = {}  # 各步骤处理时间统计
        self.detection_stats = {
            'total_processed': 0,
            'text_vector_detected': 0,
            'media_hash_detected': 0,
            'training_data_collected': 0,
            'auto_rejected': 0
        }
        
        # 初始化组件（懒加载）
        self._vector_detector = None
        self._image_detector = None
        self._media_manager = None
        self._config_manager = None
        
        logger.info("🎯 统一广告检测器初始化完成 - 6步骤流程")
    
    def _get_vector_detector(self):
        """懒加载向量检测器"""
        if self._vector_detector is None:
            from app.services.vector_ad_detector import get_vector_ad_detector
            self._vector_detector = get_vector_ad_detector()
        return self._vector_detector
    
    def _get_image_detector(self):
        """懒加载图片检测器"""
        if self._image_detector is None:
            from app.services.ad_image_detector import ad_image_detector
            self._image_detector = ad_image_detector
        return self._image_detector
    
    def _get_media_manager(self):
        """懒加载媒体管理器"""
        if self._media_manager is None:
            from app.services.training_media_manager import TrainingMediaManager
            self._media_manager = TrainingMediaManager()
        return self._media_manager
    
    def _get_config_manager(self):
        """懒加载配置管理器"""
        if self._config_manager is None:
            from app.services.config_manager import config_manager
            self._config_manager = config_manager
        return self._config_manager
    
    async def detect_advertisement(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        6步骤统一广告检测流程
        
        Args:
            content: 消息文本内容
            context: 消息上下文（包含媒体信息、消息ID等）
            
        Returns:
            Dict: 完整的检测结果
        """
        start_time = time.time()
        
        # 初始化检测结果
        detection_result = {
            'is_ad': False,
            'confidence': 0.0,
            'detection_method': 'none',
            'step_results': {},
            'training_data_collected': False,
            'should_reject': False,
            'reason': 'unknown',
            'processing_time_ms': 0.0
        }
        
        try:
            # 更新统计
            self.detection_stats['total_processed'] += 1
            
            # === Step 1: 文本向量检测（优先级最高） ===
            step1_result = await self._step1_text_vector_detection(content, context)
            detection_result['step_results']['step1'] = step1_result
            
            if step1_result['is_ad']:
                # 文本检测到广告，跳转到Step 3
                detection_result.update({
                    'is_ad': True,
                    'confidence': step1_result['confidence'],
                    'detection_method': 'text_vector',
                    'reason': f"文本向量检测: 相似度 {step1_result['similarity']:.3f}"
                })
                
                self.detection_stats['text_vector_detected'] += 1
                logger.info(f"🎯 Step1检测到广告 - 相似度: {step1_result['similarity']:.3f}")
                
                # 跳转到Step 3：训练数据收集
                await self._step3_training_data_collection(content, context, 'text_vector')
                detection_result['training_data_collected'] = True
                
            else:
                # === Step 2: 媒体检测 ===
                step2_result = await self._step2_media_detection(content, context)
                detection_result['step_results']['step2'] = step2_result
                
                if step2_result['is_ad']:
                    # 媒体检测到广告
                    detection_result.update({
                        'is_ad': True,
                        'confidence': step2_result['confidence'],
                        'detection_method': 'media_hash',
                        'reason': f"媒体检测: {step2_result['reason']}"
                    })
                    
                    self.detection_stats['media_hash_detected'] += 1
                    logger.info(f"🎯 Step2检测到广告 - {step2_result['reason']}")
                    
                    # 跳转到Step 3：训练数据收集
                    await self._step3_training_data_collection(content, context, 'media_hash')
                    detection_result['training_data_collected'] = True
            
            # === Step 4: 拒绝逻辑应用 ===
            if detection_result['is_ad']:
                should_reject = await self._step4_apply_rejection_logic()
                detection_result['should_reject'] = should_reject
                
                if should_reject:
                    self.detection_stats['auto_rejected'] += 1
            
            # === Step 5 & 6: 消息标记和存储在调用方处理 ===
            
        except Exception as e:
            logger.error(f"统一广告检测失败: {e}", exc_info=True)
            detection_result['reason'] = f"检测异常: {str(e)}"
        
        # 记录处理时间
        detection_result['processing_time_ms'] = (time.time() - start_time) * 1000
        
        return detection_result
    
    async def _step1_text_vector_detection(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 1: 文本向量检测"""
        step_start = time.time()
        result = {'is_ad': False, 'confidence': 0.0, 'similarity': 0.0, 'reason': 'no_text'}
        
        try:
            if not content or not content.strip():
                result['reason'] = 'empty_content'
                return result
            
            # 使用现有的向量检测器
            vector_detector = self._get_vector_detector()
            
            # 构造FilterContext对象（简化版）
            from app.services.filters.base import FilterContext
            filter_context = FilterContext(
                message_id=context.get('message_id', 'unknown'),
                channel_id=context.get('channel_id', 'unknown')
            )
            
            # 执行向量检测
            filter_result = await vector_detector.filter(content, filter_context)
            
            result.update({
                'is_ad': not filter_result.passed,
                'confidence': filter_result.confidence,
                'similarity': filter_result.confidence,
                'reason': filter_result.reason or 'vector_detection_complete',
                'details': filter_result.details
            })
            
        except Exception as e:
            logger.error(f"Step1文本向量检测失败: {e}")
            result['reason'] = f'detection_error: {str(e)}'
        
        finally:
            self.step_timers['step1'] = time.time() - step_start
        
        return result
    
    async def _step2_media_detection(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 2: 媒体检测"""
        step_start = time.time()
        result = {'is_ad': False, 'confidence': 0.0, 'reason': 'no_media'}
        
        try:
            media_files = context.get('media_files', [])
            if not media_files:
                result['reason'] = 'no_media_files'
                return result
            
            image_detector = self._get_image_detector()
            media_manager = self._get_media_manager()
            
            for media_file in media_files:
                media_type = media_file.get('media_type', '')
                file_path = media_file.get('local_path')
                
                if not file_path or not Path(file_path).exists():
                    continue
                
                try:
                    # 2.1 & 2.2: 图片或视频第一帧检测
                    visual_hashes = await self._extract_visual_hashes(
                        file_path, media_type, media_manager
                    )
                    
                    if visual_hashes:
                        # 与广告图片库比较
                        is_ad, similarity, match_id = await image_detector.is_known_ad(visual_hashes)
                        
                        if is_ad:
                            result.update({
                                'is_ad': True,
                                'confidence': similarity,
                                'reason': f'媒体哈希匹配 ({media_type}): 相似度 {similarity:.1f}%',
                                'match_id': match_id,
                                'visual_hashes': visual_hashes
                            })
                            return result
                
                except Exception as e:
                    logger.debug(f"媒体文件检测失败 {file_path}: {e}")
                    continue
            
            result['reason'] = 'media_checked_no_match'
            
        except Exception as e:
            logger.error(f"Step2媒体检测失败: {e}")
            result['reason'] = f'media_detection_error: {str(e)}'
        
        finally:
            self.step_timers['step2'] = time.time() - step_start
        
        return result
    
    async def _extract_visual_hashes(self, file_path: str, media_type: str, 
                                   media_manager) -> Optional[Dict]:
        """提取媒体文件的视觉哈希"""
        try:
            file_path = Path(file_path)
            
            if media_type.startswith('image/'):
                # 2.1: 图片直接计算哈希
                from app.services.visual_similarity import VisualSimilarityDetector
                detector = VisualSimilarityDetector()
                
                with open(file_path, 'rb') as f:
                    image_data = f.read()
                
                return detector.calculate_perceptual_hashes(image_data)
                
            elif media_type.startswith('video/'):
                # 2.2: 视频提取第一帧
                frame_data = media_manager.extract_video_frame(file_path)
                if frame_data:
                    from app.services.visual_similarity import VisualSimilarityDetector
                    detector = VisualSimilarityDetector()
                    return detector.calculate_perceptual_hashes(frame_data)
            
            # 2.3: 其他格式跳过
            return None
            
        except Exception as e:
            logger.debug(f"提取视觉哈希失败 {file_path}: {e}")
            return None
    
    async def _step3_training_data_collection(self, content: str, context: Dict[str, Any], 
                                            detection_method: str):
        """Step 3: 训练数据自动收集"""
        try:
            # 3.1: 收集文本向量
            if content and content.strip():
                await self._collect_text_vector(content, context, detection_method)
            
            # 3.2: 收集媒体文件
            media_files = context.get('media_files', [])
            if media_files:
                await self._collect_media_files(media_files, context, detection_method)
            
            self.detection_stats['training_data_collected'] += 1
            logger.info(f"✅ 训练数据收集完成: {detection_method}")
            
        except Exception as e:
            logger.error(f"训练数据收集失败: {e}")
    
    async def _collect_text_vector(self, content: str, context: Dict[str, Any], 
                                 detection_method: str):
        """收集文本向量到训练数据"""
        try:
            # 使用向量管理器添加向量
            from app.services.vector_manager import vector_manager
            from app.services.semantic_extractor import get_semantic_extractor
            
            extractor = get_semantic_extractor(768)
            content_vector = extractor.extract_vector(content)
            
            if content_vector:
                success = vector_manager.add_vector(
                    vector=content_vector,
                    content=content,
                    source=f"unified_detector_{detection_method}",
                    metadata={
                        'detection_method': detection_method,
                        'channel_id': context.get('channel_id'),
                        'message_id': context.get('message_id'),
                        'collected_at': datetime.now().isoformat()
                    }
                )
                
                if success:
                    logger.debug(f"文本向量已收集: {content[:50]}...")
                else:
                    logger.debug(f"文本向量重复，跳过收集")
                    
        except Exception as e:
            logger.error(f"文本向量收集失败: {e}")
    
    async def _collect_media_files(self, media_files: List[Dict], context: Dict[str, Any],
                                 detection_method: str):
        """收集媒体文件到训练数据"""
        try:
            media_manager = self._get_media_manager()
            
            for media_file in media_files:
                media_type = media_file.get('media_type', '')
                file_path = media_file.get('local_path')
                
                if not file_path or not Path(file_path).exists():
                    continue
                
                try:
                    # 保存媒体文件到训练目录
                    metadata = {
                        'detection_method': detection_method,
                        'channel_id': context.get('channel_id'),
                        'message_id': context.get('message_id'),
                        'media_type': media_type,
                        'collected_at': datetime.now().isoformat()
                    }
                    
                    success = await media_manager.save_training_media(
                        source_path=file_path,
                        message_id=context.get('message_id', 'unknown'),
                        media_type=media_type.split('/')[0] if '/' in media_type else media_type,
                        channel_id=context.get('channel_id', 'unknown'),
                        is_ad=True
                    )
                    
                    if success:
                        logger.debug(f"媒体文件已收集: {Path(file_path).name}")
                        
                except Exception as e:
                    logger.debug(f"媒体文件收集失败 {file_path}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"媒体文件收集失败: {e}")
    
    async def _step4_apply_rejection_logic(self) -> bool:
        """Step 4: 应用拒绝逻辑"""
        try:
            config_manager = self._get_config_manager()
            
            # 统一读取自动拒绝配置
            auto_reject_ads = await config_manager.get_config('review.auto_reject_ads', False)
            
            # 如果配置管理器返回False，直接读取配置文件确认
            if not auto_reject_ads:
                try:
                    from app.core.path_config import PathConfig
                    config_file = PathConfig.PROJECT_ROOT / 'data' / 'config' / 'system.json'
                    
                    if config_file.exists():
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                        raw_value = config_data.get('review.auto_reject_ads', {}).get('value', 'false')
                        auto_reject_ads = (raw_value == 'true')
                        logger.debug(f"直接读取配置文件: auto_reject_ads = {auto_reject_ads}")
                except Exception as e:
                    logger.debug(f"读取配置文件失败，使用默认值: {e}")
                    auto_reject_ads = False
            
            return auto_reject_ads
            
        except Exception as e:
            logger.error(f"应用拒绝逻辑失败: {e}")
            return False  # 异常时采用保守策略
    
    def get_detection_statistics(self) -> Dict[str, Any]:
        """获取检测统计信息"""
        return {
            'detection_stats': self.detection_stats.copy(),
            'step_timers': self.step_timers.copy(),
            'component_stats': self._get_component_stats()
        }
    
    def _get_component_stats(self) -> Dict[str, Any]:
        """获取组件统计信息"""
        stats = {}
        
        try:
            if self._vector_detector:
                stats['vector_detector'] = self._vector_detector.get_detection_stats()
        except:
            pass
            
        try:
            if self._image_detector:
                stats['image_detector'] = self._image_detector.get_statistics()
        except:
            pass
            
        return stats


# 全局统一检测器实例
_unified_ad_detector = None

def get_unified_ad_detector() -> UnifiedAdDetector:
    """获取统一广告检测器实例（单例）"""
    global _unified_ad_detector
    if _unified_ad_detector is None:
        _unified_ad_detector = UnifiedAdDetector()
    return _unified_ad_detector