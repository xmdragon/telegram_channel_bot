"""
基于语义的智能尾部过滤器
通过理解文本语义来判断是否为推广尾部
"""

import re
import logging
from typing import Dict, Set, Optional, Tuple

logger = logging.getLogger(__name__)


class SemanticTailFilter:
    """基于语义的智能尾部过滤器"""
    
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
        logger.debug(f"最终语义得分: {final_score:.3f}")
        
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
        
        # 基于得分的阈值判断
        if semantic_score > 0.7:
            return True  # 高置信度
        elif semantic_score > 0.5:
            # 中等置信度，需要额外检查
            # 检查是否有明确的联系方式
            has_contact = bool(re.search(r'@\w+|t\.me/', text))
            has_promo_verb = any(verb in text for verb in self.promo_verbs)
            return has_contact and has_promo_verb
        else:
            return False  # 低置信度
    
    def _find_extended_promo_boundary(self, lines: list, start_point: int, full_content: str) -> int:
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
    
    def filter_message(self, content: str, has_media: bool = False) -> tuple:
        """
        过滤消息中的尾部内容
        
        Args:
            content: 完整消息内容
            has_media: 是否有媒体文件（图片、视频等）
            
        Returns:
            (过滤后内容, 是否过滤了尾部, 尾部内容, 分析详情)
        """
        if not content:
            return content, False, None, {}
        
        lines = content.split('\n')
        if len(lines) < 3:
            return content, False, None, {}
        
        # 从后往前扫描，寻找推广尾部的开始位置
        best_split_point = None
        best_score = 0.0
        analysis = {'scanned_lines': []}
        
        # 最多检查最后15行或全部行数的一半，取较小值
        max_scan_lines = min(15, len(lines) // 2 + 1)
        
        for i in range(len(lines) - 1, max(0, len(lines) - max_scan_lines - 1), -1):
            # 从第i行开始到末尾的内容
            tail_candidate = '\n'.join(lines[i:])
            
            # 计算语义得分
            semantic_score = self.calculate_semantic_score(tail_candidate, content)
            
            # 记录分析详情
            line_analysis = {
                'line_start': i,
                'content_preview': tail_candidate[:100] + '...' if len(tail_candidate) > 100 else tail_candidate,
                'semantic_score': semantic_score
            }
            analysis['scanned_lines'].append(line_analysis)
            
            # 如果得分足够高，这可能是一个好的分割点
            if semantic_score > 0.4 and semantic_score > best_score:
                best_score = semantic_score
                best_split_point = i
                analysis['best_split'] = i
                analysis['best_score'] = semantic_score
                
                # 额外检查：向前扩展查找连续的推广内容
                extended_split = self._find_extended_promo_boundary(lines, i, content)
                if extended_split < i:
                    # 找到了更早的推广开始点
                    extended_tail = '\n'.join(lines[extended_split:])
                    extended_score = self.calculate_semantic_score(extended_tail, content)
                    if extended_score > semantic_score * 0.8:  # 扩展后得分不应下降太多
                        best_split_point = extended_split
                        best_score = extended_score
                        analysis['extended_split'] = extended_split
                        analysis['extended_score'] = extended_score
                        logger.debug(f"扩展推广边界: {i} -> {extended_split} (得分: {extended_score:.3f})")
        
        # 判断是否找到尾部（阈值0.5，提高识别敏感度）
        if best_split_point is not None and best_score > 0.5:
            filtered_content = '\n'.join(lines[:best_split_point]).strip()
            tail_content = '\n'.join(lines[best_split_point:]).strip()
            
            # 安全检查：过滤后的内容不能太短（但有媒体时允许完全过滤）
            if len(filtered_content) < 30 and not has_media:
                # 检查是否整条都是推广
                full_score = self.calculate_semantic_score(content)
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
            
            logger.info(f"语义尾部过滤成功: {len(content)} -> {len(filtered_content)} 字符 "
                       f"(过滤{filter_ratio:.1%}，得分{best_score:.2f})")
            
            return filtered_content, True, tail_content, analysis
        
        return content, False, None, analysis


# 全局实例
semantic_tail_filter = SemanticTailFilter()