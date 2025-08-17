"""
智能过滤引擎模块
使用学习到的模式进行智能过滤
"""
import re
import json
import logging
from typing import Tuple, Optional

from .pattern_learner import PatternLearner
from .feature_extractor import FeatureExtractor

logger = logging.getLogger(__name__)


class IntelligentFilterEngine:
    """
    智能过滤引擎 - 使用学习到的模式进行过滤
    """
    
    def __init__(self):
        self.pattern_learner = PatternLearner()
        self.feature_extractor = FeatureExtractor()
        self.min_confidence_threshold = 0.5  # 降低阈值提高敏感度
        self.max_filter_ratio = 0.45  # 最多过滤45%的内容，允许更大尾部
    
    def filter_message(self, message: str) -> Tuple[str, bool, Optional[str]]:
        """
        智能过滤消息
        
        Args:
            message: 原始消息
            
        Returns:
            (过滤后内容, 是否过滤了内容, 被过滤的部分)
        """
        if not message:
            return message, False, None
        
        lines = message.split('\n')
        best_split_point = -1
        best_score = 0.0
        best_tail = None
        exact_match_found = False
        
        # 从后向前扫描，寻找最佳分割点
        for i in range(len(lines) - 1, max(0, len(lines) - 20), -1):
            # 获取候选尾部
            tail_candidate = '\n'.join(lines[i:])
            
            # 0. 检查是否有完全匹配的训练样本（直接过滤，不受阈值限制）
            if self._has_exact_match(tail_candidate):
                logger.info(f"找到完全匹配的训练样本，直接过滤")
                if self._is_safe_to_filter(message, i, tail_candidate):
                    best_split_point = i
                    best_tail = tail_candidate
                    exact_match_found = True
                    best_score = 1.0  # 完全匹配给予最高分数
                    break  # 找到完全匹配就停止扫描
            
            # 计算位置比例
            position_ratio = i / len(lines)
            
            # 匹配模式（仅当没有完全匹配时才使用阈值）
            pattern, score = self.pattern_learner.match_pattern(tail_candidate, position_ratio)
            
            # 高相似度直接通过（不受阈值限制）
            if score > 0.9:  # 90%以上相似度
                if self._is_safe_to_filter(message, i, tail_candidate):
                    best_score = score
                    best_split_point = i
                    best_tail = tail_candidate
                    exact_match_found = True
                    break
            
            # 部分匹配情况使用阈值判断
            if score > self.min_confidence_threshold and score > best_score:
                # 安全检查
                if self._is_safe_to_filter(message, i, tail_candidate):
                    best_score = score
                    best_split_point = i
                    best_tail = tail_candidate
        
        # 应用过滤
        if best_split_point > 0 and best_tail:
            filtered = '\n'.join(lines[:best_split_point]).rstrip()
            
            # 完全匹配或高相似度情况跳过比例检查
            if not exact_match_found:
                # 最终安全检查（仅对部分匹配情况）
                filter_ratio = 1 - len(filtered) / len(message)
                if filter_ratio > self.max_filter_ratio:
                    logger.warning(f"过滤比例过大 ({filter_ratio:.1%})，取消过滤")
                    return message, False, None
            
            logger.info(f"成功过滤尾部，置信度: {best_score:.2f}，完全匹配: {exact_match_found}")
            return filtered, True, best_tail
        
        return message, False, None
    
    def _has_exact_match(self, text: str) -> bool:
        """
        检查是否有完全匹配的训练样本
        
        Args:
            text: 待检查的文本
            
        Returns:
            是否有完全匹配
        """
        if not text:
            return False
            
        text_stripped = text.strip()
        
        # 检查所有已学习的模式中是否有原始训练数据
        # 这里需要访问原始训练数据，暂时使用pattern learner的方式
        try:
            from app.core.path_config import PathConfig
            import json
            
            # 检查尾部过滤样本
            tail_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
            if tail_file.exists():
                with open(tail_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    samples = data.get('samples', data) if isinstance(data, dict) else data
                    
                    for sample in samples:
                        if isinstance(sample, dict) and sample.get('tail_part'):
                            sample_text = sample['tail_part'].strip()
                        elif isinstance(sample, str):
                            sample_text = sample.strip()
                        else:
                            continue
                            
                        # 完全匹配或高度重合
                        if text_stripped == sample_text:
                            return True
                        elif sample_text in text_stripped or text_stripped in sample_text:
                            # 计算重合度
                            shorter = min(len(text_stripped), len(sample_text))
                            longer = max(len(text_stripped), len(sample_text))
                            if shorter >= longer * 0.8:  # 80%以上重合
                                return True
                                
        except Exception as e:
            logger.warning(f"检查完全匹配时出错: {e}")
        
        return False
    
    def _is_safe_to_filter(self, message: str, split_point: int, tail: str) -> bool:
        """
        安全检查，确保不会破坏正文
        """
        lines = message.split('\n')
        
        # 检查剩余内容长度
        remaining = '\n'.join(lines[:split_point])
        if len(remaining) < 50:
            return False
        
        # 检查是否包含重要信息
        important_patterns = [
            r'\d{4}年\d{1,2}月\d{1,2}日',  # 日期
            r'\d+[亿万]',  # 金额
            r'[^，。！？]{50,}',  # 长句子（可能是正文）
        ]
        
        for pattern in important_patterns:
            if re.search(pattern, tail):
                # 尾部包含重要信息，可能不安全
                return False
        
        return True