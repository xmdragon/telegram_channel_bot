"""
模式匹配器 - 专门处理正则匹配和模式检测
检测推广内容的结构特征和主题切换
"""

import re
import logging
from typing import Set

logger = logging.getLogger(__name__)


class PatternMatcher:
    """模式匹配器 - 检测推广内容的结构特征"""
    
    def __init__(self):
        # 推广相关的动词和短语
        self.promo_verbs = {
            '订阅', '加入', '关注', '投稿', '联系', '点击', 
            '添加', '扫码', '爆料', '澄清', '合作', '对接',
            '咨询', '报名', '领取', '免费', '欢迎'
        }
    
    def detect_topic_switch(self, main_content: str, tail: str) -> bool:
        """
        检测是否存在主题切换
        
        Args:
            main_content: 主要内容
            tail: 尾部内容
            
        Returns:
            True表示检测到主题切换
        """
        # 检查是否突然出现大量推广词汇
        main_promo_count = sum(1 for verb in self.promo_verbs if verb in main_content)
        tail_promo_count = sum(1 for verb in self.promo_verbs if verb in tail)
        
        # 如果尾部的推广词密度远高于正文，说明有主题切换
        if len(tail) > 0:
            tail_density = tail_promo_count / len(tail)
            main_density = main_promo_count / len(main_content) if len(main_content) > 0 else 0
            
            if tail_density > main_density * 3:  # 尾部推广词密度是正文的3倍以上
                return True
        
        # 检查是否突然出现联系方式
        contact_pattern = r'[@][\w]+|t\.me/|https?://'
        main_contacts = len(re.findall(contact_pattern, main_content))
        tail_contacts = len(re.findall(contact_pattern, tail))
        
        # 正文没有联系方式，尾部突然出现多个
        if main_contacts == 0 and tail_contacts >= 2:
            return True
        
        return False
    
    def find_extended_promo_boundary(self, lines: list, start_point: int, full_content: str) -> int:
        """
        向前扩展查找推广内容的真正边界
        
        Args:
            lines: 消息行列表
            start_point: 当前找到的分割点
            full_content: 完整内容
            
        Returns:
            扩展后的分割点（可能等于原分割点）
        """
        # 向前查找最多5行
        for i in range(max(0, start_point - 5), start_point):
            line = lines[i].strip()
            if not line:  # 空行，可能是分隔符
                continue
                
            # 检查这行是否包含推广特征
            line_score = 0.0
            
            # 特殊符号和装饰（如星号、箭头等）
            if re.search(r'[★☆⭐🌟✨💫⚡🔥🎯🎪🎨🎭🎪🔔📣📢🎺📯]', line):
                line_score += 0.3
            if re.search(r'[🚩🚪🚪🔤]', line):  # 消息#7987中的特殊符号
                line_score += 0.4
            if re.search(r'\*+', line):  # 星号装饰
                line_score += 0.2
            
            # 推广关键词
            promo_keywords = ['频道', '群组', '交流', '投稿', '爆料', '商务', '合作', '订阅', '关注']
            for keyword in promo_keywords:
                if keyword in line:
                    line_score += 0.2
                    
            # 如果这行有足够的推广特征，扩展边界
            if line_score > 0.4:
                return i
                
        return start_point