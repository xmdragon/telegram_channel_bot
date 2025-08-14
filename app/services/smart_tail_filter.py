"""
智能尾部过滤器
识别并移除消息尾部的频道标识，保留正常内容
注意：尾部过滤是移除原频道标识，不算广告
"""
import logging
import re
from typing import Tuple, Optional, List, Dict
from app.services.ad_detector import ad_detector
from app.services.ai_filter import ai_filter
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class SmartTailFilter:
    """智能尾部过滤器 - 纯数据驱动的机器学习"""
    
    def __init__(self):
        # 使用新的智能过滤器
        from app.services.intelligent_tail_filter import intelligent_tail_filter
        self.intelligent_filter = intelligent_tail_filter
        
        # 保留这些以保持兼容性
        self.ad_detector = ad_detector
        self.ai_filter = ai_filter
        self.known_tail_patterns = []  # 兼容旧代码
        self._load_tail_patterns()  # 加载训练数据
    
    def filter_tail_ads(self, content: str, channel_id: str = None) -> Tuple[str, bool, Optional[str]]:
        """
        过滤尾部频道标识 - 使用智能引擎
        
        Args:
            content: 原始消息内容
            channel_id: 频道ID（不再使用，仅为兼容）
            
        Returns:
            (过滤后内容, 是否包含尾部, 被过滤的尾部部分)
        """
        if not content:
            return content, False, None
        
        # 使用智能过滤器
        try:
            result = self.intelligent_filter.filter_message(content)
            if result[1]:  # 如果检测到尾部
                logger.info(f"智能过滤器检测到尾部，原长度: {len(content)}, 过滤后: {len(result[0])}")
                return result
        except Exception as e:
            logger.error(f"智能过滤器异常: {e}")
        
        # 0. 优先检查明显的emoji分隔符（最可靠的标识）
        emoji_separators = [
            r'😉{5,}',  # 连续的笑脸
            r'👑{5,}',  # 连续的皇冠
            r'🔥{5,}',  # 连续的火焰
            r'[😉☺️]{10,}',  # 混合表情
            r'[📣🔗✅💬😍]{3,}.*订阅',  # 表情+订阅组合
        ]
        
        for pattern in emoji_separators:
            import re
            match = re.search(pattern, content)
            if match:
                # 找到emoji分隔符，从这里开始都是尾部
                tail_start = match.start()
                if tail_start > len(content) * 0.3:  # 确保不会过度裁剪
                    clean_content = content[:tail_start].rstrip()
                    tail_part = content[tail_start:]
                    # 验证尾部确实包含推广内容
                    if self._is_likely_tail(tail_part):
                        logger.info(f"通过emoji分隔符检测到尾部，原长度: {len(content)}, 过滤后: {len(clean_content)}")
                        return clean_content, True, tail_part
        
        # 1. 然后检查已知的精确尾部模式
        result = self._filter_by_known_patterns(content, channel_id)
        if result[1]:
            # 添加安全检查：如果过滤后内容太少，可能是错误匹配
            if len(result[0]) < len(content) * 0.3 and len(content) > 200:
                logger.warning(f"过滤结果可能过度裁剪，跳过此匹配")
            else:
                logger.info(f"精确匹配到已知尾部，原长度: {len(content)}, 过滤后: {len(result[0])}")
                return result
        
        # 1. 使用混合智能过滤器（语义+结构）
        from app.services.hybrid_tail_filter import hybrid_tail_filter
        result = hybrid_tail_filter.filter_message(content)
        if result[1]:
            logger.info(f"混合智能过滤器检测到尾部，原长度: {len(content)}, 过滤后: {len(result[0])}")
            return result
        
        # 如果混合过滤器没有检测到，尝试AI（如果可用）
        if self.ai_filter and self.ai_filter.initialized:
            result = self._filter_by_ai_semantics(content, channel_id)
            if result[1]:
                logger.info(f"AI语义检测到尾部，原长度: {len(content)}, 过滤后: {len(result[0])}")
                return result
        
        # 智能过滤无法判断时，使用规则作为fallback
        
        # 1. 特殊格式检测（如 -------[链接] | [链接]）
        result = self._filter_by_special_format(content)
        if result[1]:
            logger.info(f"规则检测到特殊格式尾部，原长度: {len(content)}, 过滤后: {len(result[0])}")
            return result
        
        # 3. 链接密度检测
        result = self._filter_by_link_density(content)
        if result[1]:
            logger.info(f"规则检测到链接密集尾部，原长度: {len(content)}, 过滤后: {len(result[0])}")
            return result
        
        return content, False, None
    
    def _load_tail_patterns(self):
        """加载训练的尾部模式（主要用于向智能过滤器添加样本）"""
        import json
        import os
        from app.core.training_config import TrainingDataConfig
        
        try:
            # 加载尾部过滤样本
            tail_file = str(TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE)
            if os.path.exists(tail_file):
                with open(tail_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    samples = data.get('samples', data) if isinstance(data, dict) else data
                    
                    # 只提取tail_part供智能过滤器学习
                    tail_count = 0
                    for sample in samples:
                        if sample.get('tail_part'):
                            tail_pattern = sample['tail_part'].strip()
                            if tail_pattern:
                                self.known_tail_patterns.append(tail_pattern)
                                # 添加到智能过滤器
                                self.intelligent_filter.add_training_sample(tail_pattern)
                                tail_count += 1
                
                logger.info(f"加载了 {tail_count} 个尾部模式到智能过滤器")
                
            # 加载手动训练数据
            manual_file = str(TrainingDataConfig.MANUAL_TRAINING_FILE)
            if os.path.exists(manual_file):
                with open(manual_file, 'r', encoding='utf-8') as f:
                    manual_data = json.load(f)
                    for channel_id, channel_data in manual_data.items():
                        if 'samples' in channel_data:
                            channel_name = channel_data.get('channel_name', '')
                            for sample in channel_data['samples']:
                                if sample.get('tail'):
                                    tail_pattern = sample['tail'].strip()
                                    if tail_pattern and tail_pattern not in self.known_tail_patterns:
                                        self.known_tail_patterns.append(tail_pattern)
                                        
                                        # 按频道存储
                                        if channel_name:
                                            if channel_name not in self.channel_tail_patterns:
                                                self.channel_tail_patterns[channel_name] = []
                                            if tail_pattern not in self.channel_tail_patterns[channel_name]:
                                                self.channel_tail_patterns[channel_name].append(tail_pattern)
                
                logger.info(f"总共加载了 {len(self.known_tail_patterns)} 个唯一尾部模式")
                logger.info(f"覆盖 {len(self.channel_tail_patterns)} 个频道")
                
        except Exception as e:
            logger.error(f"加载尾部模式失败: {e}")
    
    def _filter_by_known_patterns(self, content: str, channel_id: str = None) -> Tuple[str, bool, Optional[str]]:
        """基于已知模式的智能匹配（增强版）"""
        if not content or not self.known_tail_patterns:
            return content, False, None
        
        # 添加安全检查：如果内容很短，直接返回
        if len(content) < 100:
            return content, False, None
        
        # 优先检查频道特定的模式
        patterns_to_check = []
        
        # 获取频道特定模式
        if channel_id:
            # 尝试通过频道ID查找
            for channel_name, patterns in self.channel_tail_patterns.items():
                if channel_id in channel_name or channel_name in str(channel_id):
                    patterns_to_check.extend(patterns)
        
        # 如果没有频道特定模式，使用所有已知模式
        if not patterns_to_check:
            patterns_to_check = self.known_tail_patterns
        
        # 检查每个模式
        for pattern in patterns_to_check:
            if not pattern:
                continue
                
            # 1. 尝试精确匹配（在内容末尾）
            if content.endswith(pattern):
                clean_content = content[:-len(pattern)].rstrip()
                return clean_content, True, pattern
            
            # 2. 智能部分匹配（处理细微差异）
            # 尝试忽略空格和换行的差异
            pattern_normalized = re.sub(r'\s+', ' ', pattern.strip())
            content_tail = content[-len(pattern)*2:] if len(content) > len(pattern)*2 else content
            content_normalized = re.sub(r'\s+', ' ', content_tail.strip())
            
            if pattern_normalized in content_normalized:
                # 找到匹配位置
                idx = content.rfind(pattern_normalized.split()[0] if pattern_normalized.split() else pattern_normalized)
                if idx > 0:
                    potential_tail = content[idx:]
                    clean_content = content[:idx].rstrip()
                    return clean_content, True, potential_tail
            
            # 2.5. 关键词匹配（如"博闻资讯"）
            # 检查模式中的关键特征词
            key_phrases = ['博闻资讯', '东南亚吃瓜', '订阅频道', '点击进群']
            for phrase in key_phrases:
                if phrase in pattern and phrase in content:
                    # 找到关键词的位置
                    phrase_idx = content.rfind(phrase)
                    if phrase_idx > len(content) * 0.5:  # 在后半部分
                        # 向前查找可能的开始位置（分隔符或换行）
                        start_idx = phrase_idx
                        for back_idx in range(phrase_idx - 1, max(0, phrase_idx - 50), -1):
                            if content[back_idx:back_idx+1] in ['\n', '|', '━', '═', '─', '▬']:
                                start_idx = back_idx
                                break
                        potential_tail = content[start_idx:]
                        if self._is_likely_tail(potential_tail):
                            clean_content = content[:start_idx].rstrip()
                            return clean_content, True, potential_tail
            
            # 3. 关键词序列匹配（提取模式中的关键词）
            # 提取模式中的关键词（中文词、英文单词、链接、用户名）
            keywords = []
            # 提取中文词（2个字以上）
            chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,}', pattern)
            keywords.extend(chinese_words)
            # 提取英文单词
            english_words = re.findall(r'\b[A-Za-z]{3,}\b', pattern)
            keywords.extend(english_words)
            # 提取链接和用户名
            pattern_links = re.findall(r'https?://[^\s\)]+|t\.me/[^\s\)]+', pattern)
            pattern_usernames = re.findall(r'@\w+', pattern)
            keywords.extend(pattern_links)
            keywords.extend(pattern_usernames)
            
            if len(keywords) >= 2:  # 至少有2个关键词
                # 检查内容中是否包含这些关键词的序列
                matched_count = 0
                last_match_idx = -1
                
                for keyword in keywords:
                    if keyword in content:
                        keyword_idx = content.rfind(keyword)
                        if keyword_idx > last_match_idx:  # 确保顺序
                            matched_count += 1
                            if last_match_idx == -1:
                                last_match_idx = keyword_idx
                
                # 如果匹配了80%以上的关键词
                if matched_count >= len(keywords) * 0.8 and last_match_idx > 0:
                    # 找到第一个关键词的位置作为尾部开始
                    first_keyword_idx = content.rfind(keywords[0])
                    # 向前查找可能的分隔符
                    search_start = max(0, first_keyword_idx - 100)
                    search_section = content[search_start:first_keyword_idx]
                    
                    # 查找分隔符
                    sep_patterns = [r'[-=*#_~。.]{3,}', r'\n{2,}', r'\|{2,}']
                    for sep_pattern in sep_patterns:
                        sep_match = re.search(sep_pattern, search_section)
                        if sep_match:
                            actual_start = search_start + sep_match.start()
                            potential_tail = content[actual_start:]
                            if self._is_likely_tail(potential_tail):
                                clean_content = content[:actual_start].rstrip()
                                return clean_content, True, potential_tail
                    
                    # 如果没找到分隔符，从第一个关键词开始
                    potential_tail = content[first_keyword_idx:]
                    if self._is_likely_tail(potential_tail):
                        clean_content = content[:first_keyword_idx].rstrip()
                        return clean_content, True, potential_tail
            
            # 4. 结构化匹配（基于分隔符）
            # 查找模式中的分隔符
            separator_matches = re.findall(r'[-=*#_~。.]{3,}|\|{2,}', pattern)
            for separator in separator_matches:
                # 在内容中查找相同或相似的分隔符
                # 允许分隔符长度有差异
                sep_char = separator[0]
                flexible_sep_pattern = re.escape(sep_char) + '{3,}'
                
                for match in re.finditer(flexible_sep_pattern, content):
                    idx = match.start()
                    potential_tail = content[idx:]
                    # 验证是否为推广内容
                    if self._is_likely_tail(potential_tail):
                        clean_content = content[:idx].rstrip()
                        return clean_content, True, potential_tail
        
        # 没有匹配到已知模式
        return content, False, None
    
    
    def _is_likely_tail(self, text: str) -> bool:
        """判断文本是否可能是尾部推广"""
        if not text:
            return False
        
        # 特征计数
        features = 0
        
        # 1. 包含@符号（Telegram用户名）
        if '@' in text:
            features += 2
        
        # 2. 包含链接
        if 'http' in text or 't.me' in text:
            features += 2
        
        # 3. 包含多个表情符号（推广内容常用表情装饰）
        emoji_count = len(re.findall(r'[\U0001F300-\U0001F9FF]', text))
        if emoji_count > 5:
            features += 1
        
        # 4. 包含emoji装饰
        emoji_pattern = r'[🛎✅🙋📣✉️😍📢🔔💬❤️🔗📌]'
        if re.search(emoji_pattern, text):
            features += 1
        
        # 5. 多行且每行都很短（典型的列表格式）
        lines = text.split('\n')
        if len(lines) >= 2:
            avg_line_length = sum(len(line) for line in lines) / len(lines)
            if avg_line_length < 30:  # 平均每行少于30字符
                features += 1
        
        # 特征得分大于等于3认为是尾部
        return features >= 3
    
    def _filter_by_ai_semantics(self, content: str, channel_id: str = None) -> Tuple[str, bool, Optional[str]]:
        """
        使用AI语义分析检测尾部边界
        不依赖固定规则，而是理解内容的语义变化
        """
        if not self.ai_filter or not self.ai_filter.initialized:
            return content, False, None
        
        lines = content.split('\n')
        if len(lines) < 3:
            return content, False, None
        
        try:
            # 1. 将内容分段（每3行为一段，保证有足够的上下文）
            segments = []
            segment_indices = []
            for i in range(0, len(lines), 2):
                segment = '\n'.join(lines[i:min(i+3, len(lines))])
                if segment.strip():  # 忽略空段
                    segments.append(segment)
                    segment_indices.append(i)
            
            if len(segments) < 2:
                return content, False, None
            
            # 2. 计算每个段落的语义嵌入
            embeddings = self.ai_filter.model.encode(segments)
            
            # 3. 计算相邻段落之间的语义相似度
            similarities = []
            for i in range(len(embeddings) - 1):
                sim = cosine_similarity([embeddings[i]], [embeddings[i+1]])[0][0]
                similarities.append(sim)
            
            # 4. 找到语义突变点（相似度突然下降的地方）
            if similarities:
                avg_similarity = np.mean(similarities)
                std_similarity = np.std(similarities)
                
                # 从后往前查找显著的语义变化
                for i in range(len(similarities) - 1, -1, -1):
                    # 如果相似度明显低于平均值（超过1个标准差）
                    if similarities[i] < avg_similarity - std_similarity:
                        # 检查这个分割点后的内容是否像推广
                        tail_start_idx = segment_indices[i+1]
                        potential_tail = '\n'.join(lines[tail_start_idx:])
                        
                        # 使用AI判断是否为推广内容
                        if self._is_promotional_content(potential_tail):
                            clean_content = '\n'.join(lines[:tail_start_idx]).rstrip()
                            return clean_content, True, potential_tail
            
            # 5. 如果没有明显的语义突变，检查最后部分是否为推广
            # 动态确定检查范围（最后20%的内容）
            check_from = max(len(lines) - max(3, len(lines) // 5), 0)
            for i in range(len(lines) - 1, check_from, -1):
                potential_tail = '\n'.join(lines[i:])
                if len(potential_tail) > 20 and self._is_promotional_content(potential_tail):
                    clean_content = '\n'.join(lines[:i]).rstrip()
                    # 确保不会过度删除
                    if len(clean_content) > len(content) * 0.5:
                        return clean_content, True, potential_tail
            
        except Exception as e:
            logger.error(f"AI语义检测失败: {e}")
        
        return content, False, None
    
    def _is_promotional_content(self, text: str) -> bool:
        """
        使用AI判断文本是否为推广内容
        不依赖固定关键词，而是理解语义
        """
        if not text or len(text) < 10:
            return False
        
        # 1. 快速检查明显的推广特征
        # 检查@username格式（Telegram用户名）
        username_pattern = r'@[a-zA-Z][a-zA-Z0-9_]{4,}'
        username_count = len(re.findall(username_pattern, text))
        if username_count >= 2:  # 2个或以上@用户名
            return True
        
        # 检查链接密度
        link_count = len(re.findall(r'https?://|t\.me/', text))
        text_length = len(text)
        if text_length > 0:
            link_density = link_count * 100 / text_length  # 链接字符占比
            if link_density > 5:  # 链接密度超过5%
                return True
        
        # @用户名 + 链接的组合（典型推广模式）
        if username_count >= 1 and link_count >= 1:
            return True
        
        # 2. 使用AI模型判断是否为广告/推广
        if self.ai_filter and self.ai_filter.initialized:
            try:
                # 计算与已知推广模式的相似度
                if hasattr(self.ai_filter, 'ad_embeddings') and self.ai_filter.ad_embeddings:
                    text_embedding = self.ai_filter.model.encode([text])[0]
                    
                    # 与广告样本比较
                    ad_similarities = []
                    for ad_emb in self.ai_filter.ad_embeddings[:10]:  # 比较前10个样本
                        sim = cosine_similarity([text_embedding], [ad_emb])[0][0]
                        ad_similarities.append(sim)
                    
                    if ad_similarities and max(ad_similarities) > 0.7:
                        return True
                
                # 使用AI广告检测器
                is_ad, confidence = self.ai_filter.is_advertisement(text)
                if confidence > 0.5:  # 进一步降低阈值
                    return is_ad
                    
            except Exception as e:
                logger.debug(f"AI推广判断失败: {e}")
        
        # 3. 基本特征检查（作为补充）
        # 计算链接密度
        link_count = len(re.findall(r'https?://|t\.me/', text))
        if link_count >= 2:  # 多个链接通常是推广
            return True
        
        # 检查是否包含频道列表特征
        if '|' in text and (link_count >= 1 or username_count >= 1):  # 用|分隔的链接或用户名
            return True
        
        # 检查emoji装饰 + 链接/用户名的组合
        emoji_pattern = r'[🛎✅🙋📣✉️😍📢🔔💬❤️🔗📌]'
        has_emoji = bool(re.search(emoji_pattern, text))
        if has_emoji and (link_count >= 1 or username_count >= 1):
            return True
        
        return False
    
    def _filter_by_special_format(self, content: str) -> Tuple[str, bool, Optional[str]]:
        """检测特殊格式的尾部标识（如 -------[链接] | [链接]）"""
        lines = content.split('\n')
        
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if not line:
                continue
            
            # 检测模式：分隔符后紧跟链接（在同一行）
            # 例如：-------[东南亚无https://t.me/...] | [博闻资讯](https://...)
            if re.search(r'^[-=*#._~]{3,}.*(\[.*\]|\(.*\)|https?://|t\.me/|@)', line):
                # 检查是否包含链接
                if re.search(r'https?://|t\.me/|@\w+', line):
                    # 从这一行开始到结尾都是尾部
                    potential_ad = '\n'.join(lines[i:])
                    clean_content = '\n'.join(lines[:i]).rstrip()
                    
                    # 如果清理后的内容不为空，认为找到了尾部
                    if clean_content:
                        return clean_content, True, potential_ad
            
            # 检测模式：[名称](链接) | [名称](链接) 格式
            # 或者多个链接用 | 分隔
            if '|' in line and (line.count('http') >= 2 or line.count('t.me') >= 2):
                # 检查前面是否有分隔符
                has_separator = False
                if i > 0:
                    prev_line = lines[i-1].strip()
                    if self._is_separator_line(prev_line):
                        has_separator = True
                        # 从分隔符开始都是尾部
                        potential_ad = '\n'.join(lines[i-1:])
                        clean_content = '\n'.join(lines[:i-1]).rstrip()
                    else:
                        # 从当前行开始都是尾部
                        potential_ad = '\n'.join(lines[i:])
                        clean_content = '\n'.join(lines[:i]).rstrip()
                else:
                    # 从当前行开始都是尾部
                    potential_ad = '\n'.join(lines[i:])
                    clean_content = '\n'.join(lines[:i]).rstrip()
                
                if clean_content:
                    return clean_content, True, potential_ad
        
        return content, False, None
    
    
    def _filter_by_semantic_split(self, content: str) -> Tuple[str, bool, Optional[str]]:
        """通过语义分割检测尾部标识"""
        if not self.ad_detector.initialized:
            return content, False, None
        
        # 按段落分割
        paragraphs = content.split('\n\n')
        
        if len(paragraphs) <= 1:
            return content, False, None
        
        # 分析段落间的语义连贯性
        for i in range(len(paragraphs) - 1, 0, -1):
            # 检查最后i个段落是否为广告
            potential_ad = '\n\n'.join(paragraphs[i:])
            main_content = '\n\n'.join(paragraphs[:i])
            
            # 计算语义相似度
            if main_content and potential_ad:
                try:
                    # 使用ad_detector的语义检查功能
                    coherence = self.ad_detector.check_semantic_coherence(
                        main_content,
                        [potential_ad]
                    )
                    
                    # 如果相似度很低，且包含广告特征
                    if coherence < 0.3 and self._has_ad_features(potential_ad):  # 降低阈值从0.4到0.3
                        logger.debug(f"语义分割检测到尾部标识，相似度: {coherence:.3f}")
                        return main_content, True, potential_ad
                
                except Exception as e:
                    logger.error(f"语义分割检测失败: {e}")
        
        return content, False, None
    
    def _filter_by_link_density(self, content: str) -> Tuple[str, bool, Optional[str]]:
        """通过链接密度检测尾部标识（优化版）"""
        lines = content.split('\n')
        
        # 特殊处理：检测单行多链接的情况
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if not line:
                continue
            
            # 检测单行是否包含多个链接
            link_count = len(re.findall(r'https?://[^\s]+|t\.me/[^\s]+|@\w+', line))
            link_density = self._calculate_line_link_density(line)
            
            # 单行包含2个以上链接，或链接密度超过0.3
            if link_count >= 2 or link_density > 0.3:
                # 检查是否有分隔符在前面
                has_separator_before = False
                for j in range(max(0, i-1), i):
                    if self._is_separator_line(lines[j]):
                        has_separator_before = True
                        break
                
                # 如果有分隔符，或者链接数量>=3，认为是尾部
                if has_separator_before or link_count >= 3:
                    potential_ad = '\n'.join(lines[i:])
                    if self._is_ad_section(potential_ad):
                        clean_content = '\n'.join(lines[:i]).rstrip()
                        return clean_content, True, potential_ad
        
        # 原有的连续多行检测逻辑（降低阈值）
        ad_start_idx = -1
        consecutive_link_lines = 0
        max_consecutive = 0
        
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            
            if not line:
                continue
            
            # 计算该行的链接密度
            link_density = self._calculate_line_link_density(line)
            
            if link_density > 0.3:  # 链接密度阈值降低到0.3
                consecutive_link_lines += 1
                if consecutive_link_lines > max_consecutive:
                    max_consecutive = consecutive_link_lines
                    ad_start_idx = i
            else:
                # 如果已经找到连续的链接密集行（降低到2行）
                if consecutive_link_lines >= 2:
                    # 验证是否为广告
                    potential_ad = '\n'.join(lines[ad_start_idx:])
                    if self._is_ad_section(potential_ad):
                        clean_content = '\n'.join(lines[:ad_start_idx]).rstrip()
                        return clean_content, True, potential_ad
                
                consecutive_link_lines = 0
        
        # 检查最后的连续链接行
        if consecutive_link_lines >= 2 and ad_start_idx >= 0:
            potential_ad = '\n'.join(lines[ad_start_idx:])
            if self._is_ad_section(potential_ad):
                clean_content = '\n'.join(lines[:ad_start_idx]).rstrip()
                return clean_content, True, potential_ad
        
        return content, False, None
    
    def _is_separator_line(self, line: str) -> bool:
        """检查是否为分隔符行（基于常见模式）"""
        line = line.strip()
        if not line:
            return False
        
        # 直接检查常见的分隔符模式
        import re
        separator_patterns = [
            r'^[-=*#_~━═─▬]{3,}$',  # 各种分隔符
            r'^[😉☺️👑🔥]{5,}$',    # emoji分隔符
        ]
        
        for pattern in separator_patterns:
            if re.match(pattern, line):
                return True
        return False
    
    def _calculate_line_link_density(self, line: str) -> float:
        """计算单行的链接密度"""
        if not line:
            return 0.0
        
        # 查找所有链接
        url_pattern = r'https?://[^\s]+|t\.me/[^\s]+|@\w+'
        urls = re.findall(url_pattern, line)
        
        if not urls:
            return 0.0
        
        # 计算链接字符占比
        url_chars = sum(len(url) for url in urls)
        total_chars = len(line)
        
        return url_chars / total_chars if total_chars > 0 else 0.0
    
    def _is_ad_section(self, text: str) -> bool:
        """判断文本段是否为广告（优化版，降低误判）"""
        if not text:
            return False
        
        # 1. 使用AI检测
        if self.ad_detector.initialized:
            is_ad, confidence = self.ad_detector.is_advertisement_ai(text)
            if confidence > 0.7:
                return is_ad
        
        # 2. 检查广告特征（调整权重）
        ad_score = 0.0
        
        # 链接数量（降低权重）
        url_count = len(re.findall(r'https?://[^\s]+|t\.me/[^\s]+', text))
        if url_count >= 3:
            ad_score += 0.3  # 降低权重
        elif url_count >= 2:
            ad_score += 0.2
        
        # 表情符号密度
        emoji_count = len(re.findall(r'[\U0001F300-\U0001F9FF]', text))
        if emoji_count > 5:
            ad_score += 0.2
        
        # 频道推广模式
        if re.search(r'[\U0001F300-\U0001F9FF]\s*\([^)]+\)', text):
            ad_score += 0.3
        
        # 联系方式
        if re.search(r'[@][\w]+|t\.me/\+?\w+', text):
            ad_score += 0.2
        
        # 特殊模式：分隔符后紧跟链接（强特征）
        if re.search(r'^[-=*#._~]{3,}.*https?://', text, re.MULTILINE):
            ad_score += 0.4
        
        # 包含多个频道链接用 | 分隔（强特征）
        if '|' in text and text.count('http') >= 2:
            ad_score += 0.3
        
        return ad_score >= 0.5  # 降低阈值到0.5
    
    async def learn_from_user_filter(self, channel_id: str, original: str, filtered: str):
        """
        从用户的手动过滤结果中学习
        记录用户认为的尾部模式，用于改进AI判断
        """
        if not self.ai_filter or not self.ai_filter.initialized:
            return
        
        try:
            # 提取被用户过滤掉的尾部
            if len(filtered) < len(original):
                # 找到尾部开始的位置
                tail_start = original.find(filtered) + len(filtered) if filtered in original else len(filtered)
                removed_tail = original[tail_start:].strip()
                
                if removed_tail and len(removed_tail) > 10:
                    logger.info(f"学习用户过滤的尾部模式（频道 {channel_id}）")
                    
                    # 让AI学习这个尾部模式
                    if channel_id:
                        # 收集该频道的尾部样本
                        samples = [removed_tail]
                        # 可以从数据库获取更多该频道的历史尾部样本
                        await self.ai_filter.learn_channel_pattern(channel_id, samples)
                    
                    # 更新广告样本库
                    if hasattr(self.ai_filter, 'ad_embeddings'):
                        tail_embedding = self.ai_filter.model.encode([removed_tail])[0]
                        self.ai_filter.ad_embeddings.append(tail_embedding)
                        # 限制样本数量
                        if len(self.ai_filter.ad_embeddings) > 100:
                            self.ai_filter.ad_embeddings = self.ai_filter.ad_embeddings[-100:]
                    
                    logger.info(f"已学习新的尾部模式，长度: {len(removed_tail)} 字符")
                    
        except Exception as e:
            logger.error(f"学习用户过滤失败: {e}")
    
    def _has_ad_features(self, text: str) -> bool:
        """检查文本是否包含广告特征"""
        if not text:
            return False
        
        features = {
            'has_links': bool(re.search(r'https?://|t\.me/', text)),
            'has_contact': bool(re.search(r'@\w+|联系|投稿|咨询', text)),
            'has_emojis': len(re.findall(r'[\U0001F300-\U0001F9FF]', text)) > 3,
            'has_channel_list': bool(re.search(r'[\U0001F300-\U0001F9FF]\s*\([^)]+\)', text))
        }
        
        # 如果有多个特征，可能是广告
        feature_count = sum(1 for v in features.values() if v)
        return feature_count >= 2
    
    def analyze_tail_content(self, content: str) -> Dict:
        """分析尾部内容的详细信息"""
        result = {
            'has_tail_ad': False,
            'ad_type': None,
            'confidence': 0.0,
            'ad_position': -1,
            'ad_length': 0
        }
        
        # 执行过滤
        clean_content, has_ad, ad_part = self.filter_tail_ads(content)
        
        if has_ad and ad_part:
            result['has_tail_ad'] = True
            result['ad_position'] = len(clean_content)
            result['ad_length'] = len(ad_part)
            
            # 分析广告类型
            if re.search(r'━{10,}|═{10,}|─{10,}', ad_part):
                result['ad_type'] = 'structured'  # 结构化广告
            elif len(re.findall(r'https?://|t\.me/', ad_part)) >= 3:
                result['ad_type'] = 'link_cluster'  # 链接聚集广告
            else:
                result['ad_type'] = 'embedded'  # 嵌入式广告
            
            # 计算置信度
            if self.ad_detector.initialized:
                _, confidence = self.ad_detector.is_advertisement_ai(ad_part)
                result['confidence'] = confidence
        
        return result


# 全局实例
smart_tail_filter = SmartTailFilter()