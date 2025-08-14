"""
混合智能判断的尾部过滤器
结合语义、结构、位置和相关性多个维度进行综合判断
"""

import re
import logging
from typing import Dict, Tuple, Optional, List

from app.services.semantic_tail_filter import SemanticTailFilter
from app.services.intelligent_tail_filter import intelligent_tail_filter

logger = logging.getLogger(__name__)


class HybridTailFilter:
    """混合智能判断的尾部过滤器"""
    
    def __init__(self):
        self.semantic_filter = SemanticTailFilter()
        self.structural_filter = intelligent_tail_filter
        self.threshold = 0.6  # 综合得分阈值
        self.max_tail_ratio = 0.5  # 尾部最大占比（提高到50%）
        self.min_tail_length = 20  # 最小尾部长度
    
    def filter_message(self, content: str) -> Tuple[str, bool, Optional[str]]:
        """
        综合多维度判断并过滤消息尾部
        
        Args:
            content: 完整消息内容
            
        Returns:
            (过滤后内容, 是否有尾部, 尾部内容)
        """
        if not content or len(content) < 30:  # 降低最小长度要求
            return content, False, None
        
        lines = content.split('\n')
        if len(lines) < 2:
            return content, False, None
        
        best_score = 0
        best_split = len(lines)
        best_tail = None
        
        # 策略1：先查找明显的分隔符
        separator_line = self._find_separator_line(lines)
        if separator_line != -1:
            tail_candidate = '\n'.join(lines[separator_line:])
            if len(tail_candidate) >= self.min_tail_length:
                scores = self.calculate_scores(tail_candidate, content, separator_line, lines)
                final_score = self.weighted_score(scores)
                logger.debug(f"分隔符位置 {separator_line}, 得分: {final_score:.3f}")
                
                if final_score > self.threshold:
                    best_score = final_score
                    best_split = separator_line
                    best_tail = tail_candidate
        
        # 策略2：智能扫描（从后向前）
        scan_start = len(lines) - 1
        scan_end = max(0, len(lines) - 15)  # 最多扫描15行
        
        for i in range(scan_start, scan_end, -1):
            tail_candidate = '\n'.join(lines[i:])
            
            # 跳过太短的内容
            if len(tail_candidate) < self.min_tail_length:
                continue
            
            # 快速预检：如果没有任何推广特征，跳过
            if not self._has_promo_features(tail_candidate):
                continue
            
            # 计算四个维度的得分
            scores = self.calculate_scores(tail_candidate, content, i, lines)
            
            # 综合得分
            final_score = self.weighted_score(scores)
            
            logger.debug(f"位置 {i}/{len(lines)}, 综合得分: {final_score:.3f}, "
                        f"语义: {scores.get('semantic', 0):.2f}, "
                        f"结构: {scores.get('structural', 0):.2f}, "
                        f"位置: {scores.get('position', 0):.2f}, "
                        f"相关性: {scores.get('relevance', 0):.2f}")
            
            if final_score > best_score and final_score > self.threshold:
                best_score = final_score
                best_split = i
                best_tail = tail_candidate
                
                # 如果得分很高，提前结束
                if final_score > 0.85:
                    logger.debug(f"找到高置信度尾部，得分: {final_score:.3f}")
                    break
        
        # 安全检查：尾部不能超过全文的指定比例
        if best_tail:
            tail_ratio = len(best_tail) / len(content)
            if tail_ratio > self.max_tail_ratio:
                logger.debug(f"尾部占比过大: {tail_ratio:.2%}，取消过滤")
                return content, False, None
            
            clean_content = '\n'.join(lines[:best_split]).rstrip()
            
            # 确保剩余内容有意义
            if len(clean_content) < 30:  # 降低最小剩余内容要求
                logger.debug(f"过滤后内容太短: {len(clean_content)} 字符")
                return content, False, None
            
            logger.info(f"成功过滤尾部，得分: {best_score:.3f}, "
                       f"移除 {len(best_tail)} 字符")
            return clean_content, True, best_tail
        
        return content, False, None
    
    def calculate_scores(self, tail: str, full_content: str, position: int, lines: List[str]) -> Dict[str, float]:
        """
        计算四个维度的得分
        
        Args:
            tail: 尾部候选内容
            full_content: 完整内容
            position: 尾部起始位置（行号）
            lines: 所有行的列表
            
        Returns:
            各维度得分字典
        """
        scores = {}
        
        # 1. 语义得分（0-1）
        scores['semantic'] = self.semantic_filter.calculate_semantic_score(tail, full_content)
        
        # 2. 结构得分（0-1）
        structural_features = self.structural_filter.feature_extractor.extract_features(tail)
        scores['structural'] = self.structural_filter._calculate_feature_score(structural_features)
        
        # 3. 位置得分（0-1）- 越靠后越可能是尾部
        # 使用非线性函数，让靠后的位置得分更高
        relative_position = (len(lines) - position) / min(15, len(lines))
        scores['position'] = min(1.0, relative_position ** 0.7)  # 平方根函数，使得分布更平滑
        
        # 4. 相关性得分（0-1）- 与正文相关性越低越可能是尾部
        relevance = self.semantic_filter.calculate_relevance(tail, full_content)
        scores['relevance'] = 1 - relevance
        
        return scores
    
    def weighted_score(self, scores: Dict[str, float]) -> float:
        """
        计算加权综合得分
        
        Args:
            scores: 各维度得分
            
        Returns:
            综合得分（0-1）
        """
        # 动态权重：根据各维度的得分情况调整权重
        semantic_score = scores.get('semantic', 0)
        structural_score = scores.get('structural', 0)
        
        # 如果语义得分很高，增加其权重
        if semantic_score > 0.7:
            weights = {
                'semantic': 0.45,     # 语义很强时权重更高
                'structural': 0.20,
                'relevance': 0.25,
                'position': 0.10
            }
        # 如果结构得分很高，平衡权重
        elif structural_score > 0.7:
            weights = {
                'semantic': 0.30,
                'structural': 0.35,   # 结构特征明显
                'relevance': 0.20,
                'position': 0.15
            }
        # 默认权重
        else:
            weights = {
                'semantic': 0.35,     # 语义最重要
                'structural': 0.25,   # 结构特征
                'relevance': 0.25,    # 相关性
                'position': 0.15      # 位置
            }
        
        total = sum(scores.get(key, 0) * weight for key, weight in weights.items())
        return min(1.0, total)  # 确保不超过1
    
    def _find_separator_line(self, lines: List[str]) -> int:
        """
        查找明显的分隔符行
        
        Args:
            lines: 文本行列表
            
        Returns:
            分隔符所在行号，未找到返回-1
        """
        separator_patterns = [
            r'^[-=*#_~—]{3,}$',  # 常见分隔符
            r'^[─━═]+$',  # 中文分隔线
            r'^\s*[📣🔔😍👌💬🔗📢]{3,}\s*$',  # emoji分隔
            r'^\.{3,}$',  # 省略号分隔
        ]
        
        # 从后向前查找，但不查找最后20%的内容（避免找到底部装饰）
        search_end = max(len(lines) // 2, len(lines) - 20)
        
        for i in range(len(lines) - 1, search_end, -1):
            line = lines[i].strip()
            for pattern in separator_patterns:
                if re.match(pattern, line):
                    logger.debug(f"找到分隔符在第 {i} 行: {line[:30]}")
                    return i
        
        return -1
    
    def _has_promo_features(self, text: str) -> bool:
        """
        快速检查是否包含推广特征
        
        Args:
            text: 待检查文本
            
        Returns:
            是否包含推广特征
        """
        # 快速检查是否包含基本的推广元素
        promo_indicators = [
            '@',  # Telegram用户名
            't.me/',  # Telegram链接
            'http',  # 网址
            '订阅', '加入', '投稿', '联系',  # 常见推广词
            '频道', '群组', '客服', '商务',  # 频道相关
            '🔔', '📣', '☎️', '💬'  # 常见推广emoji
        ]
        
        return any(indicator in text for indicator in promo_indicators)
    
    def get_filter_stats(self) -> Dict:
        """获取过滤器统计信息"""
        stats = {
            'threshold': self.threshold,
            'max_tail_ratio': self.max_tail_ratio,
            'min_tail_length': self.min_tail_length,
            'structural_samples': self.structural_filter.get_statistics()['total_samples'],
            'learned_keywords': self.structural_filter.get_statistics()['learned_keywords']
        }
        return stats


# 创建全局实例
hybrid_tail_filter = HybridTailFilter()