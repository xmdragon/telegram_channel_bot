"""
尾部过滤引擎 - 主要的过滤逻辑
整合混合过滤器（向量+语义）、语义分析和模式匹配，提供统一的过滤接口

升级说明：
- 优先使用混合向量过滤器（更准确）
- 降级到原有语义分析（兼容性保证）
- 保持API兼容性
"""

import logging
from typing import Tuple, Dict, Optional
from .filters.semantic_analyzer import SemanticAnalyzer
from .filters.pattern_matcher import PatternMatcher

# 尝试导入新的混合过滤器
try:
    from .filters.hybrid_tail_filter import get_hybrid_tail_filter
    HYBRID_FILTER_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("✅ 混合向量过滤器可用")
except ImportError as e:
    HYBRID_FILTER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️ 混合向量过滤器不可用，使用传统方法: {e}")

logger = logging.getLogger(__name__)


class TailFilterEngine:
    """尾部过滤引擎 - 核心过滤逻辑
    
    升级版：
    1. 优先使用混合向量过滤器（基于53+训练样本）
    2. 降级使用语义分析器（兼容性保证）
    3. 保持完全的API兼容性
    """
    
    def __init__(self):
        self.semantic_analyzer = SemanticAnalyzer()
        self.pattern_matcher = PatternMatcher()
        
        # 初始化混合过滤器
        if HYBRID_FILTER_AVAILABLE:
            try:
                self.hybrid_filter = get_hybrid_tail_filter()
                logger.info("✅ 混合向量过滤器初始化成功")
            except Exception as e:
                logger.error(f"❌ 混合向量过滤器初始化失败: {e}")
                self.hybrid_filter = None
        else:
            self.hybrid_filter = None
    
    def filter_message(self, content: str, has_media: bool = False) -> Tuple[str, bool, Optional[str], Dict]:
        """
        过滤消息中的尾部内容
        
        Args:
            content: 完整消息内容
            has_media: 是否有媒体文件（图片、视频等）
            
        Returns:
            (过滤后内容, 是否过滤了尾部, 尾部内容, 分析详情)
        """
        logger.info(f"🔍 开始尾部过滤 - 输入内容长度: {len(content) if content else 0} 字符")
        if content:
            logger.debug(f"原始内容预览: {content[:200]}{'...' if len(content) > 200 else ''}")
        
        if not content:
            logger.debug("内容为空，跳过过滤")
            return content, False, None, {}
        
        # 优先使用混合向量过滤器
        if self.hybrid_filter:
            try:
                logger.debug("🚀 使用混合向量过滤器")
                filtered_content, was_filtered, removed_tail, analysis = self.hybrid_filter.filter_message(content, has_media)
                
                if was_filtered:
                    logger.info(f"✅ 混合向量过滤成功")
                    analysis['engine_method'] = 'hybrid_vector'
                    return filtered_content, was_filtered, removed_tail, analysis
                else:
                    logger.debug("混合向量过滤器未检测到推广内容")
                    analysis['engine_method'] = 'hybrid_vector_no_filter'
                    return filtered_content, was_filtered, removed_tail, analysis
                    
            except Exception as e:
                logger.error(f"❌ 混合向量过滤失败，降级到传统方法: {e}")
                # 继续使用传统方法
        
        # 降级到传统语义分析方法
        logger.debug("🔄 降级到传统语义分析方法")
        
        lines = content.split('\n')
        if len(lines) < 3:
            logger.debug(f"内容行数不足({len(lines)}行)，跳过过滤")
            return content, False, None, {'engine_method': 'semantic_skipped'}
        
        # 从后往前扫描，寻找推广尾部的开始位置
        best_split_point = None
        best_score = 0.0
        analysis = {'scanned_lines': []}
        
        logger.debug(f"开始扫描 - 总行数: {len(lines)}, 准备检查后{min(15, len(lines) // 2 + 1)}行")
        
        # 最多检查最后15行或全部行数的一半，取较小值
        max_scan_lines = min(15, len(lines) // 2 + 1)
        
        for i in range(len(lines) - 1, max(0, len(lines) - max_scan_lines - 1), -1):
            # 从第i行开始到末尾的内容
            tail_candidate = '\n'.join(lines[i:])
            
            # 计算语义得分
            semantic_score = self.semantic_analyzer.calculate_semantic_score(tail_candidate, content)
            logger.debug(f"扫描第{i}行开始的尾部候选 - 得分: {semantic_score:.3f}, 内容: {tail_candidate[:50]}{'...' if len(tail_candidate) > 50 else ''}")
            
            # 记录分析详情
            line_analysis = {
                'line_start': i,
                'content_preview': tail_candidate[:100] + '...' if len(tail_candidate) > 100 else tail_candidate,
                'semantic_score': semantic_score
            }
            analysis['scanned_lines'].append(line_analysis)
            
            # 如果得分足够高，这可能是一个好的分割点
            if semantic_score > 0.4 and semantic_score > best_score:
                logger.debug(f"✅ 找到更好的分割点 - 行{i}, 得分: {semantic_score:.3f} > {best_score:.3f}")
                best_score = semantic_score
                best_split_point = i
                analysis['best_split'] = i
                analysis['best_score'] = semantic_score
                
                # Linus式修复：删除有问题的边界扩展机制
                # 这个"向前扩展"逻辑会误删正文内容，违反了"消除特殊情况"原则
                # 
                # 原问题：find_extended_promo_boundary会基于关键词机械匹配向前扩展5行
                # 导致包含"爆料"等词的正文被错误过滤
                # 
                # 正确的方案：如果语义分析已经找到了正确的分割点，就不需要"扩展"
                # 好的算法不应该需要这种补丁式的后处理
                #
                # TODO: 长期方案是基于语义理解重写整个检测逻辑
                logger.debug(f"跳过边界扩展检查 - 使用原始分割点 {i} (Linus式简化)")
        
        # 判断是否找到尾部（阈值决策现在由TailFilter处理）
        logger.debug(f"扫描完成 - 最佳分割点: {best_split_point}, 最佳得分: {best_score:.3f}")
        
        # 返回结果，不再在此处进行阈值判断
        if best_split_point is not None and best_score > 0.0:
            filtered_content = '\n'.join(lines[:best_split_point]).strip()
            tail_content = '\n'.join(lines[best_split_point:]).strip()
            
            logger.info(f"🎯 检测到推广尾部 - 分割点: 第{best_split_point}行, 得分: {best_score:.3f}")
            logger.debug(f"过滤后内容长度: {len(filtered_content)}, 尾部内容长度: {len(tail_content)}")
            logger.debug(f"过滤后内容预览: {filtered_content[:100]}{'...' if len(filtered_content) > 100 else ''}")
            logger.debug(f"移除的尾部内容: {tail_content[:100]}{'...' if len(tail_content) > 100 else ''}")
            
            # 安全检查：过滤后的内容不能太短（但有媒体时允许完全过滤）
            if len(filtered_content) < 30 and not has_media:
                # 检查是否整条都是推广
                full_score = self.semantic_analyzer.calculate_semantic_score(content)
                if full_score > 0.8:
                    # 允许完全过滤纯推广内容
                    logger.info(f"检测到纯推广内容，完全过滤: {len(content)} -> 0 字符")
                    return "", True, content, analysis
                else:
                    # 保留原文，避免误删有价值的正常内容
                    logger.warning(f"过滤后内容过短且包含正常内容，保留原文: {len(filtered_content)} < 30")
                    return content, False, None, analysis
            elif len(filtered_content) < 30 and has_media:
                # 有媒体的情况下，允许完全过滤文本内容
                logger.info(f"有媒体消息，允许完全过滤文本: {len(content)} -> {len(filtered_content)} 字符")
            
            # 计算过滤比例，有媒体时不限制过滤比例
            filter_ratio = len(tail_content) / len(content) if content else 0
            if not has_media:
                # 没有媒体时才检查过滤比例
                # 如果推广特征非常明显（得分>0.8），允许更大的过滤比例
                max_filter_ratio = 0.85 if best_score > 0.8 else 0.7
                if filter_ratio > max_filter_ratio:
                    logger.warning(f"过滤比例过大 ({filter_ratio:.1%})，超过限制 {max_filter_ratio:.1%}，保留原文")
                    return content, False, None, analysis
            else:
                logger.debug(f"有媒体消息，不限制过滤比例: {filter_ratio:.1%}")
            
            logger.info(f"✅ 传统语义过滤成功: {len(content)} -> {len(filtered_content)} 字符 "
                       f"(过滤{filter_ratio:.1%}，得分{best_score:.2f})")
            
            analysis['engine_method'] = 'semantic_fallback'
            return filtered_content, True, tail_content, analysis
        
        logger.debug(f"❌ 传统方法未检测到推广尾部，保留原始内容 (最佳得分: {best_score:.3f})")
        analysis['engine_method'] = 'semantic_no_filter'
        return content, False, None, analysis