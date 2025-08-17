"""
语义分析器 - 专门处理文本语义得分计算
基于语义特征判断文本是否为推广内容
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SemanticAnalyzer:
    """语义分析器 - 计算文本的推广语义得分"""
    
    def __init__(self):
        # 推广相关的动词和短语
        self.promo_verbs = {
            '订阅', '加入', '关注', '投稿', '联系', '点击', 
            '添加', '扫码', '爆料', '澄清', '合作', '对接',
            '咨询', '报名', '领取', '免费', '欢迎'
        }
        
        # 频道/群组标识
        self.channel_indicators = {
            '频道', '群组', '群聊', '交流群', '讨论群', 
            '官方', '客服', '商务', '招商', '失联导航',
            '投稿', '爆料', '澄清', '合作'
        }
        
        # 行动号召模式
        self.cta_patterns = [
            r'欢迎.{0,5}投稿',
            r'欢迎.{0,5}爆料',
            r'商务.{0,5}合作', 
            r'免费.{0,5}爆料',
            r'点击.{0,5}加入',
            r'扫码.{0,5}添加',
            r'订阅.{0,5}频道',
            r'关注.{0,5}我们',
            r'联系.{0,5}客服',
            r'添加.{0,5}微信',
            r'进群.{0,5}交流'
        ]
        
        # 白名单：这些词出现时降低尾部判定概率
        self.whitelist_terms = {
            # 学术和引用相关
            '参考文献', '注释', '来源', '引用', '出处', '资料',
            # 逻辑连接词
            '因此', '所以', '总之', '综上所述', '结论', '总结',
            '由此可见', '换句话说', '也就是说', '简而言之',
            # 内容延续
            '如下', '以下', '下面', '接下来', '继续',
            # 解释说明
            '例如', '比如', '譬如', '举例', '说明'
        }
        
        # 强推广信号词
        self.strong_promo_signals = {
            '官方频道', '官方群', '订阅频道', '加入群组',
            '投稿爆料', '商务合作', '免费领取', '点击领取',
            '扫码添加', '联系客服', '招商代理'
        }
    
    def calculate_semantic_score(self, text: str, full_content: Optional[str] = None) -> float:
        """
        计算语义得分（0-1）
        
        Args:
            text: 待分析的文本（可能的尾部）
            full_content: 完整内容（用于计算相关性）
            
        Returns:
            语义得分，越高越可能是推广尾部
        """
        if not text:
            return 0.0
        
        logger.debug(f"📊 计算语义得分 - 文本长度: {len(text)}")
        logger.debug(f"分析文本: {text[:100]}{'...' if len(text) > 100 else ''}")
            
        score = 0.0
        text_lower = text.lower()
        
        # 1. 强信号检测（权重0.4）
        strong_signal_count = sum(1 for signal in self.strong_promo_signals if signal in text)
        if strong_signal_count > 0:
            score += min(0.4, strong_signal_count * 0.2)
            logger.debug(f"强信号得分: {min(0.4, strong_signal_count * 0.2)}")
        
        # 2. 推广动词检测（权重0.25）
        verb_count = sum(1 for verb in self.promo_verbs if verb in text)
        if verb_count > 0:
            verb_score = min(0.25, verb_count * 0.08)
            score += verb_score
            logger.debug(f"动词得分: {verb_score}")
        
        # 3. 行动号召(CTA)检测（权重0.2）
        cta_count = sum(1 for pattern in self.cta_patterns if re.search(pattern, text))
        if cta_count > 0:
            cta_score = min(0.2, cta_count * 0.1)
            score += cta_score
            logger.debug(f"CTA得分: {cta_score}")
        
        # 4. 频道标识检测（权重0.15）
        channel_count = sum(1 for term in self.channel_indicators if term in text)
        if channel_count > 0:
            channel_score = min(0.15, channel_count * 0.05)
            score += channel_score
            logger.debug(f"频道标识得分: {channel_score}")
        
        # 5. 白名单惩罚（减分）
        whitelist_count = sum(1 for term in self.whitelist_terms if term in text)
        if whitelist_count > 0:
            penalty = min(0.3, whitelist_count * 0.1)
            score -= penalty
            logger.debug(f"白名单惩罚: -{penalty}")
        
        # 6. 联系方式和链接检测（权重0.3）
        contact_patterns = [
            (r'@\w+', 0.1),           # Telegram用户名
            (r't\.me/\w+', 0.15),     # Telegram链接
            (r'https?://t\.me/', 0.15), # 完整Telegram链接
            (r'https?://', 0.05),     # 其他链接
            (r'微信[:：]', 0.08),      # 微信
            (r'QQ[:：]', 0.05)        # QQ
        ]
        
        contact_score = 0.0
        lines = text.split('\n')
        
        for pattern, weight in contact_patterns:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            if matches > 0:
                contact_score += min(weight * 2, matches * weight)
        
        # 额外加分：多种联系方式并存
        unique_patterns = sum(1 for pattern, _ in contact_patterns if re.search(pattern, text, re.IGNORECASE))
        if unique_patterns >= 2:
            contact_score += 0.1
            logger.debug(f"多种联系方式加分: 0.1")
        
        score += min(0.3, contact_score)
        if contact_score > 0:
            logger.debug(f"联系方式得分: {min(0.3, contact_score):.3f}")
        
        # 7. 主题相关性（如果提供了完整内容）
        if full_content:
            relevance = self.calculate_relevance(text, full_content)
            # 相关性越低，越可能是尾部（权重0.2）
            relevance_score = (1 - relevance) * 0.2
            score += relevance_score
            logger.debug(f"相关性得分: {relevance_score} (相关性: {relevance:.2f})")
        
        # 确保得分在0-1范围内
        final_score = max(0, min(1, score))
        logger.info(f"📈 语义得分计算完成: {final_score:.3f} (文本长度: {len(text)})")
        
        return final_score
    
    def calculate_relevance(self, tail: str, full_content: str) -> float:
        """
        计算尾部与正文的相关性（0-1）
        
        Args:
            tail: 尾部内容
            full_content: 完整内容
            
        Returns:
            相关性得分，越高说明越相关（不太可能是推广）
        """
        if not tail or not full_content:
            return 0.5  # 无法判断时返回中性值
        
        # 获取主要内容（去掉尾部）
        main_content = full_content.replace(tail, '').strip()
        if not main_content:
            return 0.5
        
        # 提取主要内容的关键词（中文词组）
        main_words = re.findall(r'[\u4e00-\u9fa5]{2,4}', main_content)
        if not main_words:
            return 0.5
        
        # 计算词频
        main_word_freq = {}
        for word in main_words:
            # 过滤掉太常见的词
            if word not in {'的', '是', '在', '了', '和', '与', '或', '但', '而', '等', '这', '那', '有', '无'}:
                main_word_freq[word] = main_word_freq.get(word, 0) + 1
        
        if not main_word_freq:
            return 0.5
        
        # 获取高频词（前10个）
        sorted_words = sorted(main_word_freq.items(), key=lambda x: x[1], reverse=True)
        top_words = [word for word, _ in sorted_words[:10]]
        
        # 检查尾部包含多少高频词
        tail_words = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', tail))
        common_count = sum(1 for word in top_words if word in tail_words)
        
        # 计算相关性
        relevance = common_count / len(top_words) if top_words else 0
        
        # 特殊情况：如果尾部包含新闻/文章的核心主题词，提高相关性
        # 比如正文讲"柬埔寨"，尾部也提到"柬埔寨"，可能是相关内容
        if sorted_words and sorted_words[0][1] > 5:  # 最高频词出现超过5次
            top_theme = sorted_words[0][0]
            if top_theme in tail:
                relevance = min(1.0, relevance + 0.3)
        
        return relevance
    
    def is_likely_promotion(self, text: str, semantic_score: float) -> bool:
        """
        基于语义得分判断是否可能是推广
        
        Args:
            text: 文本内容
            semantic_score: 语义得分
            
        Returns:
            是否可能是推广
        """
        # 特殊情况：非常短的文本不太可能是有效的推广
        if len(text) < 20:
            return False
        
        # 阈值判断现在由调用方（TailFilter）处理
        # 这里只返回综合判断结果，不再硬编码阈值
        if semantic_score > 0.7:
            return True  # 高置信度
        elif semantic_score > 0.3:  # 降低内部阈值，让外部阈值管理器决定
            # 中等置信度，需要额外检查
            # 检查是否有明确的联系方式
            has_contact = bool(re.search(r'@\w+|t\.me/', text))
            has_promo_verb = any(verb in text for verb in self.promo_verbs)
            return has_contact and has_promo_verb
        else:
            return False  # 低置信度