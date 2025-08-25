"""
推广内容向量过滤器
基于向量相似度检测推广内容，避免误判
"""
import re
import logging
from typing import Tuple, Optional, List

from app.services.filters.base import BaseFilter, FilterResult, FilterContext
from app.services.promo_vector_manager import promo_vector_manager
from app.core.threshold_manager import threshold_manager

logger = logging.getLogger(__name__)

class PromoVectorFilter(BaseFilter):
    """推广内容向量过滤器"""
    
    def __init__(self):
        super().__init__("promo_vector_filter")
        self.description = "基于向量相似度检测推广内容"
        
        # 获取动态阈值
        self.similarity_threshold = threshold_manager.get_threshold(
            self.name, "similarity"
        )
        self.min_length_threshold = threshold_manager.get_threshold(
            self.name, "min_length"
        )
        
    def _split_into_segments(self, content: str) -> List[str]:
        """
        将内容分割成语义段落
        避免因一句推广内容过滤整篇文章
        
        改进策略：按段落/行分割，不再按句子分割
        保持推广内容的完整性
        """
        segments = []
        
        # 先按双换行分割（段落）
        paragraphs = content.split('\n\n')
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            # 再按单换行分割（处理单行的推广内容）
            lines = paragraph.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # 每行作为独立段落处理
                # 避免句号分割破坏推广内容完整性
                if len(line) >= self.min_length_threshold:
                    segments.append(line)
        
        return segments
    
    def _check_segment_promo(self, segment: str) -> Tuple[bool, float, str]:
        """
        检查单个段落是否为推广内容
        
        Returns:
            (是否推广, 最高相似度, 匹配样本)
        """
        if not segment or len(segment) < self.min_length_threshold:
            return False, 0.0, ""
            
        try:
            # 查找相似的推广样本
            similar_samples = promo_vector_manager.find_similar_samples(
                segment, 
                threshold=self.similarity_threshold,
                top_k=3
            )
            
            if not similar_samples:
                return False, 0.0, ""
            
            # 获取最高相似度
            best_match = similar_samples[0]
            similarity = best_match[1]
            matched_sample = best_match[0]
            
            # 记录检测结果
            logger.debug(
                f"段落推广检测: 相似度={similarity:.3f}, "
                f"阈值={self.similarity_threshold}, "
                f"段落长度={len(segment)}"
            )
            
            return similarity >= self.similarity_threshold, similarity, matched_sample[:50]
            
        except Exception as e:
            logger.error(f"段落推广检测失败: {e}")
            return False, 0.0, ""
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """
        执行推广内容向量过滤
        
        策略：
        1. 将内容分割成语义段落
        2. 逐个检测段落是否为推广
        3. 只移除确认为推广的段落
        4. 保留正常内容段落
        """
        if not content or not content.strip():
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0.0,
                reason=""
            )
        
        try:
            # 更新动态阈值
            self.similarity_threshold = threshold_manager.get_threshold(
                self.name, "similarity"
            )
            self.min_length_threshold = threshold_manager.get_threshold(
                self.name, "min_length"
            )
            
            # 检查是否有推广样本数据
            cache_stats = promo_vector_manager.get_cache_stats()
            if cache_stats['total_vectors'] == 0:
                logger.debug("没有推广样本向量，跳过向量过滤")
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    processing_time_ms=0.0,
                    reason="无推广样本数据",
                    confidence=0.0
                )
            
            # 分割内容为段落
            segments = self._split_into_segments(content)
            
            if not segments:
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    processing_time_ms=0.0,
                    reason="无有效段落",
                    confidence=0.0
                )
            
            # 逐个检测段落
            clean_segments = []
            promo_segments = []
            max_similarity = 0.0
            best_match = ""
            
            for segment in segments:
                is_promo, similarity, matched_sample = self._check_segment_promo(segment)
                
                if is_promo:
                    promo_segments.append({
                        'content': segment[:50] + "..." if len(segment) > 50 else segment,
                        'similarity': similarity,
                        'matched': matched_sample
                    })
                    
                    # 记录最高相似度
                    if similarity > max_similarity:
                        max_similarity = similarity
                        best_match = matched_sample
                else:
                    clean_segments.append(segment)
            
            # 判断过滤结果
            if not promo_segments:
                # 没有推广段落
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    processing_time_ms=0.0,
                    reason="",
                    confidence=0.0
                )
            
            # 构建过滤后内容
            filtered_content = "\n\n".join(clean_segments).strip()
            
            # 计算置信度
            confidence = max_similarity
            
            # 构建过滤原因
            reason = f"检测到{len(promo_segments)}个推广段落"
            if best_match:
                reason += f"（相似度{max_similarity:.2f}）"
            
            # 判断是否应该通过
            # 如果移除的推广内容比例太高，可能是误判
            original_length = len(content)
            filtered_length = len(filtered_content)
            removal_ratio = (original_length - filtered_length) / original_length if original_length > 0 else 0
            
            # 保护措施：如果移除内容超过80%且置信度不高，认为可能误判
            if removal_ratio > 0.8 and filtered_length < 50 and confidence < 0.9:
                logger.warning(
                    f"推广过滤移除内容过多（{removal_ratio:.1%}），"
                    f"置信度{confidence:.3f}不够高，可能误判，保留原内容"
                )
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    processing_time_ms=0.0,
                    reason=f"移除比例过高({removal_ratio:.1%})，保留原内容",
                    confidence=confidence
                )
            
            # 记录过滤统计
            logger.info(
                f"推广向量过滤: 移除{len(promo_segments)}个段落, "
                f"保留{len(clean_segments)}个段落, "
                f"最高相似度{max_similarity:.3f}"
            )
            
            return FilterResult(
                filtered_content=filtered_content,
                passed=False,  # 检测到推广内容
                processing_time_ms=0.0,
                reason=reason,
                confidence=confidence,
                details={
                    'promo_segments': len(promo_segments),
                    'clean_segments': len(clean_segments),
                    'max_similarity': max_similarity,
                    'removal_ratio': removal_ratio,
                    'matched_sample': best_match
                }
            )
            
        except Exception as e:
            logger.error(f"推广向量过滤失败: {e}")
            # 出错时不过滤内容
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0.0,
                reason=f"过滤器错误: {str(e)}",
                confidence=0.0
            )