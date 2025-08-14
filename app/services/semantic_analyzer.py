"""
语义分析器 - 区分正常内容和推广内容
"""
import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class SemanticAnalyzer:
    """语义分析器，用于判断文本的语义性质"""
    
    def __init__(self):
        # 正常内容特征
        self.normal_indicators = {
            # 时间表达
            'time_expressions': [
                r'\d{4}年\d{1,2}月', r'第\d+季度', r'\d+月\d+日',
                r'今年', r'去年', r'本月', r'上月', r'近期', r'最近'
            ],
            
            # 数据统计
            'statistics': [
                r'\d+名', r'\d+例', r'\d+起', r'\d+件', r'\d+人',
                r'\d+%', r'\d+万', r'\d+亿', r'\d+千', r'约\d+'
            ],
            
            # 官方机构
            'official_entities': [
                r'政府', r'部门', r'卫生部', r'教育部', r'公安部',
                r'法院', r'检察院', r'委员会', r'管理局',
                r'医院', r'学校', r'大学', r'研究所'
            ],
            
            # 事件描述
            'event_descriptions': [
                r'发生了', r'报告显示', r'据.*称', r'消息.*',
                r'调查.*', r'发现.*', r'确认.*', r'宣布.*',
                r'表示.*', r'指出.*', r'强调.*', r'要求.*'
            ],
            
            # 新闻关键词
            'news_keywords': [
                r'报道', r'新闻', r'消息', r'通报', r'公告',
                r'声明', r'通知', r'公布', r'发布'
            ]
        }
        
        # 推广内容特征
        self.promo_indicators = {
            # 祈使句
            'imperatives': [
                r'订阅', r'訂閱', r'关注', r'關注', r'加入',
                r'点击', r'扫码', r'联系', r'聯繫', r'投稿'
            ],
            
            # 联系方式
            'contact_info': [
                r'微信[:：]', r'QQ[:：]', r'电话[:：]', r'手机[:：]',
                r'@\w+', r't\.me/', r'telegram\.me/'
            ],
            
            # 推广用词
            'promo_words': [
                r'频道', r'頻道', r'群组', r'群組',
                r'商务', r'商務', r'合作', r'代理',
                r'爆料', r'曝光台', r'资讯'
            ],
            
            # 纯符号
            'pure_symbols': [
                r'^[📢📣🔔💬❤️🔗☎️😍✉️📮]+$',
                r'^[👇⬇️↓▼⤵️]+$',
                r'^[-=_—➖▪▫◆◇■□●○•～~]{3,}$'
            ]
        }
    
    def analyze_content_semantics(self, text: str) -> Tuple[float, float]:
        """
        分析文本语义
        
        Args:
            text: 要分析的文本
            
        Returns:
            (正常内容得分, 推广内容得分)
        """
        logger.debug(f"🤖 语义分析器开始分析 - 文本长度: {len(text) if text else 0}")
        if text:
            logger.debug(f"分析文本: {text[:100]}{'...' if len(text) > 100 else ''}")
        
        if not text:
            logger.debug("文本为空，返回(0.0, 0.0)")
            return 0.0, 0.0
        
        # 计算正常内容得分
        normal_score = self._calculate_normal_score(text)
        logger.debug(f"正常内容得分: {normal_score:.3f}")
        
        # 计算推广内容得分
        promo_score = self._calculate_promo_score(text)
        logger.debug(f"推广内容得分: {promo_score:.3f}")
        
        logger.info(f"📈 语义分析结果: 正常={normal_score:.3f}, 推广={promo_score:.3f}")
        return normal_score, promo_score
    
    def _calculate_normal_score(self, text: str) -> float:
        """计算正常内容得分"""
        score = 0.0
        
        for category, patterns in self.normal_indicators.items():
            matches = 0
            for pattern in patterns:
                matches += len(re.findall(pattern, text, re.IGNORECASE))
            
            if matches > 0:
                if category == 'time_expressions':
                    score += min(matches * 2, 5)  # 时间表达权重高
                elif category == 'statistics':
                    score += min(matches * 3, 8)  # 数据统计权重最高
                elif category == 'official_entities':
                    score += min(matches * 2, 4)
                elif category == 'event_descriptions':
                    score += min(matches * 1.5, 6)
                elif category == 'news_keywords':
                    score += min(matches * 1, 3)
        
        # 检查完整句子结构
        sentences = re.split(r'[。！？\.\!\?]', text)
        complete_sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        if len(complete_sentences) > 0:
            score += min(len(complete_sentences) * 2, 6)
        
        return score
    
    def _calculate_promo_score(self, text: str) -> float:
        """计算推广内容得分"""
        score = 0.0
        
        for category, patterns in self.promo_indicators.items():
            matches = 0
            for pattern in patterns:
                matches += len(re.findall(pattern, text, re.IGNORECASE))
            
            if matches > 0:
                if category == 'imperatives':
                    score += min(matches * 4, 10)  # 祈使句权重最高
                elif category == 'contact_info':
                    score += min(matches * 3, 8)
                elif category == 'promo_words':
                    score += min(matches * 2, 6)
                elif category == 'pure_symbols':
                    score += min(matches * 1, 3)
        
        # 检查是否主要是链接和符号
        lines = text.split('\n')
        link_symbol_lines = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 检查是否主要是链接、@用户名或符号
            if (re.search(r'^[📢📣🔔💬❤️🔗☎️😍✉️📮@]', line) or
                re.search(r't\.me/', line) or
                re.search(r'^@\w+', line)):
                link_symbol_lines += 1
        
        if len(lines) > 0:
            link_ratio = link_symbol_lines / len(lines)
            if link_ratio > 0.5:  # 超过一半是链接/符号行
                score += 5
        
        return score
    
    def is_likely_normal_content(self, text: str, threshold_ratio: float = 1.2) -> bool:
        """
        判断文本是否更可能是正常内容
        
        Args:
            text: 要分析的文本
            threshold_ratio: 正常内容得分需要超过推广得分的倍数
            
        Returns:
            True if likely normal content
        """
        normal_score, promo_score = self.analyze_content_semantics(text)
        
        logger.debug(f"语义分析 - 正常得分: {normal_score:.1f}, 推广得分: {promo_score:.1f}")
        
        # 如果推广得分为0，且正常得分>0，认为是正常内容
        if promo_score == 0 and normal_score > 0:
            return True
        
        # 如果正常得分明显高于推广得分，认为是正常内容
        if promo_score > 0:
            return normal_score > promo_score * threshold_ratio
        
        return False

# 全局实例
semantic_analyzer = SemanticAnalyzer()