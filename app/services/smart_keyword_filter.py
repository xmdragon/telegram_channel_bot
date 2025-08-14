"""
智能关键词定位过滤器
从匹配到的训练样本关键词开始过滤，并进行语义分析保护
"""
import re
import json
import logging
from typing import Tuple, Optional, List
from pathlib import Path
from app.services.semantic_analyzer import semantic_analyzer

logger = logging.getLogger(__name__)

class SmartKeywordFilter:
    """智能关键词定位过滤器"""
    
    def __init__(self):
        self.training_keywords = set()
        self.load_training_keywords()
    
    def load_training_keywords(self):
        """从训练数据中加载关键词"""
        try:
            from app.core.training_config import TrainingDataConfig
            
            # 加载尾部过滤样本
            tail_file = TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE
            if tail_file.exists():
                with open(tail_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    samples = data.get('samples', data) if isinstance(data, dict) else data
                    
                    for sample in samples:
                        if isinstance(sample, dict) and sample.get('tail_part'):
                            tail_text = sample['tail_part']
                        elif isinstance(sample, str):
                            tail_text = sample
                        else:
                            continue
                        
                        # 提取关键词
                        keywords = self._extract_keywords(tail_text)
                        self.training_keywords.update(keywords)
            
            logger.info(f"加载了 {len(self.training_keywords)} 个训练关键词")
            
        except Exception as e:
            logger.error(f"加载训练关键词失败: {e}")
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        keywords = []
        
        # 推广相关关键词
        promo_patterns = [
            r'订阅', r'訂閱', r'关注', r'關注', r'加入',
            r'投稿', r'爆料', r'商务', r'商務', r'联系', r'聯繫',
            r'频道', r'頻道', r'群组', r'群組', r'资讯',
            r'曝光台', r'导航', r'失联', r'备用'
        ]
        
        for pattern in promo_patterns:
            if re.search(pattern, text):
                keywords.append(pattern)
        
        return keywords
    
    def find_keyword_position(self, content: str) -> Tuple[Optional[int], Optional[str]]:
        """
        查找第一个匹配训练关键词的位置
        
        Args:
            content: 消息内容
            
        Returns:
            (行号, 匹配的关键词) 或 (None, None)
        """
        if not content:
            return None, None
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            for keyword in self.training_keywords:
                if re.search(keyword, line):
                    logger.debug(f"在第{i+1}行找到训练关键词: {keyword}")
                    return i, keyword
        
        return None, None
    
    def filter_with_semantic_check(self, content: str) -> Tuple[str, bool, Optional[str]]:
        """
        使用语义检查的智能过滤
        
        Args:
            content: 原始内容
            
        Returns:
            (过滤后内容, 是否进行了过滤, 被过滤的部分)
        """
        if not content:
            return content, False, None
        
        # 1. 查找关键词位置
        keyword_line, matched_keyword = self.find_keyword_position(content)
        
        if keyword_line is None:
            logger.debug("未找到训练关键词，跳过过滤")
            return content, False, None
        
        lines = content.split('\n')
        
        # 2. 分割内容
        keep_part = '\n'.join(lines[:keyword_line]).strip()
        filter_part = '\n'.join(lines[keyword_line:]).strip()
        
        logger.info(f"关键词定位: 第{keyword_line+1}行找到'{matched_keyword}'")
        logger.debug(f"保留部分长度: {len(keep_part)}, 待检查部分长度: {len(filter_part)}")
        
        # 3. 语义分析保护
        is_normal = semantic_analyzer.is_likely_normal_content(filter_part)
        
        if is_normal:
            logger.info("语义分析: 待过滤内容包含正常语义，放弃过滤")
            return content, False, None
        
        # 4. 安全检查
        if len(keep_part) < 20:
            # 如果整个消息都是推广内容，允许完全过滤
            normal_score_full, promo_score_full = semantic_analyzer.analyze_content_semantics(content)
            if promo_score_full > normal_score_full * 2:  # 推广得分明显更高
                logger.info("检测到纯推广内容，允许完全过滤")
                return "", True, content
            else:
                logger.warning("保留内容过短，放弃过滤")
                return content, False, None
        
        # 计算过滤比例
        filter_ratio = len(filter_part) / len(content)
        if filter_ratio > 0.7:
            logger.warning(f"过滤比例过大 ({filter_ratio:.1%})，放弃过滤")
            return content, False, None
        
        # 5. 执行过滤
        logger.info(f"执行关键词定位过滤: {len(content)} -> {len(keep_part)} 字符")
        return keep_part, True, filter_part

# 全局实例
smart_keyword_filter = SmartKeywordFilter()