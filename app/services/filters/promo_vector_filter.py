"""
推广内容向量过滤器
基于向量相似度检测推广内容，避免误判
"""
import re
import logging
from typing import Tuple, Optional, List, Dict

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
        将内容按行分割成独立段落 - Linus式简化版本
        
        核心改进：
        1. 按行优先分割（符合Telegram消息实际结构）
        2. 连续空格转换为行分隔符
        3. 每行独立处理，避免误合并
        """
        segments = []
        
        # 🚀 第一步：将连续空格转换为行分隔符（不是段落分隔符）
        import re
        if re.search(r' {5,}', content):
            content = re.sub(r' {5,}', '\n', content)
            logger.debug(f"推广向量过滤器：连续空格转换为行分隔符")
        
        # 🎯 第二步：直接按行分割（Linus式简化）
        lines = content.split('\n')
        
        # 🧹 第三步：清理并过滤短行
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 每行作为独立段落处理，避免误合并
            if len(line) >= self.min_length_threshold:
                segments.append(line)
        
        logger.debug(f"推广向量过滤器：分割为 {len(segments)} 个段落")
        return segments
    
    
    
    def _check_segment_promo(self, segment: str, position_ratio: float = 0.5) -> Tuple[bool, float, str]:
        """
        检查单个段落是否为推广内容
        
        改进算法：添加上下文理解和多维度特征分析
        
        Returns:
            (是否推广, 最高相似度, 匹配样本)
        """
        if not segment or len(segment) < self.min_length_threshold:
            return False, 0.0, ""
        
        try:
            # 🧠 第一步：训练样本检查
            cache_stats = promo_vector_manager.get_cache_stats()
            sample_count = cache_stats.get('total_vectors', 0)
            
            # 🚀 Linus式简化：无训练样本时跳过向量过滤
            if sample_count == 0:
                logger.debug(f"无训练样本，跳过向量过滤")
                return False, 0.0, ""
            
            # 🔍 第二步：纯向量相似度检测
            similar_samples = promo_vector_manager.find_similar_samples(
                segment, 
                threshold=self.similarity_threshold,
                top_k=3
            )
            
            vector_similarity = 0.0
            matched_sample = ""
            
            if similar_samples:
                best_match = similar_samples[0]
                vector_similarity = best_match[1]
                matched_sample = best_match[0]
            
            # 🎯 第三步：纯向量判断 - 基于相似度和位置权重
            final_decision, final_confidence = self._make_vector_decision(
                vector_similarity, position_ratio
            )
            
            # 📊 记录分析结果
            logger.debug(
                f"推广内容向量分析: "
                f"向量相似度={vector_similarity:.3f}, "
                f"最终判断={final_decision}, "
                f"置信度={final_confidence:.3f}, "
                f"样本数={sample_count}"
            )
            
            return final_decision, final_confidence, matched_sample[:50]
            
        except Exception as e:
            logger.error(f"段落推广检测失败: {e}")
            return False, 0.0, ""
    
    
    def _make_vector_decision(self, vector_similarity: float, position_ratio: float = 0.5) -> Tuple[bool, float]:
        """
        🚀 Linus式决策 + 位置权重优化
        
        核心改进：
        1. 基础相似度检测
        2. 位置权重调整阈值（前半部分更严格，后半部分更敏感）
        3. 保护正文内容，精确识别推广
        
        Args:
            vector_similarity: 向量相似度
            position_ratio: 位置比例（0.0=开头, 1.0=结尾）
            
        Returns:
            (是否推广内容, 调整后相似度)
        """
        # 🎯 位置权重阈值调整
        base_threshold = self.similarity_threshold
        
        if position_ratio <= 0.5:
            # 前半部分：提高阈值，保护正文内容
            adjusted_threshold = min(0.85, base_threshold + 0.1)
            logger.debug(f"前半部分位置({position_ratio:.2f})，阈值调整为{adjusted_threshold:.3f}")
        else:
            # 后半部分：降低阈值，敏感识别推广
            adjusted_threshold = max(0.65, base_threshold - 0.1)
            logger.debug(f"后半部分位置({position_ratio:.2f})，阈值调整为{adjusted_threshold:.3f}")
        
        # 简单有效的判断
        is_promo = vector_similarity >= adjusted_threshold
        
        return is_promo, vector_similarity
    
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
            
            # 逐个检测段落（添加位置权重）
            clean_segments = []
            promo_segments = []
            max_similarity = 0.0
            best_match = ""
            total_segments = len(segments)
            
            for i, segment in enumerate(segments):
                # 🎯 计算位置比例（0.0=开头, 1.0=结尾）
                position_ratio = i / (total_segments - 1) if total_segments > 1 else 0.5
                
                is_promo, similarity, matched_sample = self._check_segment_promo(segment, position_ratio)
                
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
            
            # 🎯 Linus式逻辑：只有过滤后没有有效内容才拒绝
            # 如果还有有效内容，说明过滤成功，应该通过
            has_valid_content = bool(filtered_content.strip())
            
            return FilterResult(
                filtered_content=filtered_content,
                passed=has_valid_content,  # 有有效内容就通过，没有才拒绝
                processing_time_ms=0.0,
                reason=reason,
                confidence=confidence,
                details={
                    'promo_segments': len(promo_segments),
                    'clean_segments': len(clean_segments),
                    'max_similarity': max_similarity,
                    'removal_ratio': removal_ratio,
                    'matched_sample': best_match,
                    'has_valid_content': has_valid_content
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