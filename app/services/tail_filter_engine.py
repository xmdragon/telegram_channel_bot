"""
尾部过滤引擎 - 主要的过滤逻辑
整合语义分析和模式匹配，提供统一的过滤接口
"""

import logging
from typing import Tuple, Dict, Optional
from .filters.semantic_analyzer import SemanticAnalyzer
from .filters.pattern_matcher import PatternMatcher

logger = logging.getLogger(__name__)


class TailFilterEngine:
    """尾部过滤引擎 - 核心过滤逻辑"""
    
    def __init__(self):
        self.semantic_analyzer = SemanticAnalyzer()
        self.pattern_matcher = PatternMatcher()
    
    def filter_message(self, content: str, has_media: bool = False) -> Tuple[str, bool, Optional[str], Dict]:
        """
        过滤消息中的尾部内容
        
        Args:
            content: 完整消息内容
            has_media: 是否有媒体文件（图片、视频等）
            
        Returns:
            (过滤后内容, 是否过滤了尾部, 尾部内容, 分析详情)
        """
        logger.info(f"🔍 开始语义尾部过滤 - 输入内容长度: {len(content) if content else 0} 字符")
        if content:
            logger.debug(f"原始内容预览: {content[:200]}{'...' if len(content) > 200 else ''}")
        
        if not content:
            logger.debug("内容为空，跳过过滤")
            return content, False, None, {}
        
        lines = content.split('\n')
        if len(lines) < 3:
            logger.debug(f"内容行数不足({len(lines)}行)，跳过过滤")
            return content, False, None, {}
        
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
                
                # 额外检查：向前扩展查找连续的推广内容
                extended_split = self.pattern_matcher.find_extended_promo_boundary(lines, i, content)
                if extended_split < i:
                    # 找到了更早的推广开始点
                    extended_tail = '\n'.join(lines[extended_split:])
                    extended_score = self.semantic_analyzer.calculate_semantic_score(extended_tail, content)
                    if extended_score > semantic_score * 0.8:  # 扩展后得分不应下降太多
                        best_split_point = extended_split
                        best_score = extended_score
                        analysis['extended_split'] = extended_split
                        analysis['extended_score'] = extended_score
                        logger.debug(f"扩展推广边界: {i} -> {extended_split} (得分: {extended_score:.3f})")
        
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
            
            logger.info(f"✅ 语义尾部过滤成功: {len(content)} -> {len(filtered_content)} 字符 "
                       f"(过滤{filter_ratio:.1%}，得分{best_score:.2f})")
            
            return filtered_content, True, tail_content, analysis
        
        logger.debug(f"❌ 未检测到推广尾部，保留原始内容 (最佳得分: {best_score:.3f} < 0.5)")
        return content, False, None, analysis