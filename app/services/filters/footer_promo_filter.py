"""
尾部推广链接过滤器
专门检测和过滤消息尾部的推广链接，基于分隔符模式和语义分析

Author: Claude
Created: 2025-08-16
"""

import re
import time
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from .base import BaseFilter, FilterResult, FilterContext
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class FooterPromoFilter(BaseFilter):
    """尾部推广链接过滤器
    
    检测和过滤：
    - 基于分隔符的尾部内容检测
    - 推广链接列表识别
    - Markdown格式链接过滤
    - 语义分析推广内容
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("footer_promo_filter", config)
        
        # 分隔符模式
        self.separator_patterns = []
        self.load_separator_patterns()
        
        # 训练数据
        self.training_samples = []
        self.load_training_data()
        
        # 推广关键词
        self.promo_keywords = [
            '订阅', '订閱', '关注', '關注', '加入', '投稿', '爆料',
            '商务', '商務', '联系', '聯繫', '频道', '頻道', '群组',
            'channel', 'group', 'subscribe', '导航', '備用', '官方',
            '联系方式', '聯繫方式', '合作', '推广', '推廣'
        ]
        
        # 推广模式
        self.promo_patterns = [
            r'[\d\w]*订阅[\d\w]*[:：]?\s*[@\w]+',  # 订阅: @channel
            r'[\d\w]*投稿[\d\w]*[:：]?\s*[@\w]+',  # 投稿: @someone
            r'[\d\w]*商务[\d\w]*[:：]?\s*[@\w]+',  # 商务: @someone
            r'[\d\w]*联系[\d\w]*[:：]?\s*[@\w]+',  # 联系: @someone
            r'[\d\w]*频道[\d\w]*[:：]?\s*[@\w]+',  # 频道: @channel
        ]
        
        # 链接模式 - 检测连续的链接列表
        self.link_list_patterns = [
            r'(\[([^\]]*)\]\(([^\)]+)\)\s*){2,}',  # 2个或更多连续的Markdown链接
            r'([@\w]+\s*[：:]\s*[@\w]+\s*){2,}',   # 2个或更多连续的@用户名模式
            r'(https?://[^\s]+\s*){2,}',           # 2个或更多连续的URL
        ]
        
        # 默认阈值
        self.separator_threshold = 0.6  # 分隔符置信度阈值
        self.semantic_threshold = 0.5   # 语义分析阈值
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'separator_detected': 0,
            'footer_content_removed': 0,
            'link_lists_detected': 0,
            'semantic_matches': 0
        }
    
    def load_separator_patterns(self):
        """加载分隔符模式"""
        try:
            separator_file = PathConfig.DATA_DIR / "training/tail/separator_patterns.json"
            if separator_file.exists():
                with open(separator_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.separator_patterns = [p['regex'] for p in data.get('patterns', [])]
                    logger.info(f"加载了 {len(self.separator_patterns)} 个分隔符模式")
            else:
                # 使用默认分隔符模式
                self.separator_patterns = self._get_default_separators()
                logger.warning("分隔符模式文件不存在，使用默认模式")
        except Exception as e:
            logger.error(f"加载分隔符模式失败: {e}")
            self.separator_patterns = self._get_default_separators()
    
    def load_training_data(self):
        """加载训练数据用于相似度匹配"""
        try:
            # 尝试加载推广链接训练数据
            training_dir = PathConfig.DATA_DIR / "training/promo"
            if training_dir.exists():
                for file_path in training_dir.glob("*.json"):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            self.training_samples.extend(data)
                        elif isinstance(data, dict) and 'samples' in data:
                            self.training_samples.extend(data['samples'])
                
                logger.info(f"加载了 {len(self.training_samples)} 个训练样本")
            
            # 如果没有训练数据，创建一些基础样本
            if not self.training_samples:
                self.training_samples = self._get_default_training_samples()
                logger.info("使用默认训练样本")
                
        except Exception as e:
            logger.error(f"加载训练数据失败: {e}")
            self.training_samples = self._get_default_training_samples()
    
    def _get_default_training_samples(self) -> List[Dict[str, Any]]:
        """获取默认训练样本"""
        return [
            {
                "content": "📣 订阅📡东南亚曝光台\n🔗  t.me/dny9527\n☎️ 投稿曝料：@stan0505",
                "is_promo": True,
                "category": "channel_subscription"
            },
            {
                "content": "🔔 频道导航：@channellist\n💬 商务合作：@business\n📱 投稿爆料：@submit",
                "is_promo": True,
                "category": "multi_contact"
            },
            {
                "content": "订阅我们的频道获取最新消息\n联系方式：@contact_us",
                "is_promo": True,
                "category": "simple_promo"
            }
        ]
    
    def _get_default_separators(self) -> List[str]:
        """获取默认分隔符模式"""
        return [
            r'━{3,}',      # 横线分隔符（3个以上）
            r'═{3,}',      # 双线分隔符
            r'─{3,}',      # 细线分隔符
            r'▬{3,}',      # 粗线分隔符
            r'-{5,}',      # 短横线（5个以上）
            r'={5,}',      # 等号线
            r'\*{5,}',     # 星号线
            r'\+{3,}',     # 加号线
            r'<{3,}',      # 小于号
            r'>{3,}',      # 大于号
            r'🔜{2,}',     # emoji分隔符
            r'[📢📣🔔]{2,}', # 通知类emoji
        ]
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """预检查是否需要处理"""
        if not content or len(content) < 50:  # 降低最小长度限制
            return False
        
        # 快速检查是否包含分隔符
        has_separator = any(re.search(pattern, content) for pattern in self.separator_patterns[:5])
        
        # 快速检查是否包含推广关键词
        has_promo_keywords = any(keyword in content for keyword in self.promo_keywords[:5])
        
        # 快速检查是否包含链接列表
        has_link_list = any(re.search(pattern, content) for pattern in self.link_list_patterns)
        
        # 基于训练数据的快速相似度检查
        has_training_similarity = self._quick_similarity_check(content)
        
        return has_separator or has_promo_keywords or has_link_list or has_training_similarity
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """过滤尾部推广链接"""
        start_time = time.time()
        
        if not content:
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0,
                reason="空内容"
            )
        
        try:
            # 检测分隔符位置
            separator_result = self._detect_separators(content)
            
            # 分析内容语义
            semantic_result = self._analyze_semantic_content(content, separator_result)
            
            # 执行过滤
            filtered_content, modifications = self._filter_footer_content(
                content, separator_result, semantic_result
            )
            
            # 计算处理时间
            processing_time = (time.time() - start_time) * 1000
            
            # 更新统计
            self.stats['total_processed'] += 1
            if separator_result['found']:
                self.stats['separator_detected'] += 1
            if semantic_result['has_promo']:
                self.stats['semantic_matches'] += 1
            if len(filtered_content) < len(content):
                self.stats['footer_content_removed'] += 1
            
            # 构建结果
            filter_result = FilterResult(
                filtered_content=filtered_content,
                passed=True,  # 不阻止消息通过，只是清理内容
                processing_time_ms=processing_time,
                reason=f"检测到尾部推广内容" if len(filtered_content) < len(content) else None,
                confidence=max(separator_result['confidence'], semantic_result['confidence']),
                details={
                    'separator_detected': separator_result['found'],
                    'separator_position': separator_result.get('position'),
                    'semantic_matches': semantic_result['matches'],
                    'original_length': len(content),
                    'filtered_length': len(filtered_content),
                    'removed_content_length': len(content) - len(filtered_content)
                },
                should_early_stop=False,
                modifications=modifications
            )
            
            if len(filtered_content) < len(content):
                logger.info(f"过滤尾部推广内容: {len(content)} -> {len(filtered_content)} 字符")
            
            return filter_result
            
        except Exception as e:
            logger.error(f"尾部推广过滤失败: {e}")
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=(time.time() - start_time) * 1000,
                reason=f"处理异常: {str(e)}",
                confidence=0.0
            )
    
    def _detect_separators(self, content: str) -> Dict[str, Any]:
        """检测分隔符"""
        result = {
            'found': False,
            'position': -1,
            'separator_type': None,
            'separator_text': None
        }
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # 检查每个分隔符模式
            for pattern in self.separator_patterns:
                if re.search(pattern, line_stripped):
                    result.update({
                        'found': True,
                        'position': i,
                        'separator_type': pattern,
                        'separator_text': line_stripped
                    })
                    return result  # 找到第一个分隔符就返回
        
        return result
    
    
    def _quick_similarity_check(self, content: str) -> bool:
        """基于训练数据的快速相似度检查"""
        if not self.training_samples:
            return False
        
        # 简单的关键词重叠检查
        content_lower = content.lower()
        for sample in self.training_samples[:5]:  # 只检查前5个样本
            if sample.get('is_promo', False):
                sample_content = sample.get('content', '').lower()
                
                # 计算关键词重叠
                sample_keywords = set(re.findall(r'[@＠]\w+|[订订閱阅订][阅閱]|[频频頻道道]|[投投][稿稿]|[商商務务][务務]', sample_content))
                content_keywords = set(re.findall(r'[@＠]\w+|[订订閱阅订][阅閱]|[频频頻道道]|[投投][稿稿]|[商商務务][务務]', content_lower))
                
                if sample_keywords and content_keywords:
                    overlap = len(sample_keywords & content_keywords) / len(sample_keywords | content_keywords)
                    if overlap > 0.3:  # 30%重叠度
                        return True
        
        return False
    
    def _analyze_semantic_content(self, content: str, separator_result: Dict[str, Any]) -> Dict[str, Any]:
        """分析内容语义"""
        result = {
            'has_promo': False,
            'confidence': 0.0,
            'matches': [],
            'promo_section': None
        }
        
        # 确定分析区域
        if separator_result['found'] and separator_result['position'] >= 0:
            # 分析分隔符后的内容
            lines = content.split('\n')
            start_pos = separator_result['position'] + 1
            promo_section = '\n'.join(lines[start_pos:])
        else:
            # 分析最后1/3的内容
            lines = content.split('\n')
            start_pos = max(0, len(lines) * 2 // 3)
            promo_section = '\n'.join(lines[start_pos:])
        
        if not promo_section.strip():
            return result
        
        result['promo_section'] = promo_section
        
        # 检测推广模式
        confidence_scores = []
        
        # 1. 关键词匹配
        keyword_matches = 0
        for keyword in self.promo_keywords:
            if keyword in promo_section:
                keyword_matches += 1
                result['matches'].append(f"关键词: {keyword}")
        
        if keyword_matches > 0:
            keyword_confidence = min(keyword_matches / 3.0, 0.4)
            confidence_scores.append(keyword_confidence)
        
        # 2. 推广模式匹配
        pattern_matches = 0
        for pattern in self.promo_patterns:
            if re.search(pattern, promo_section):
                pattern_matches += 1
                result['matches'].append(f"模式匹配: {pattern}")
        
        if pattern_matches > 0:
            pattern_confidence = min(pattern_matches / 2.0, 0.3)
            confidence_scores.append(pattern_confidence)
        
        # 3. 链接列表检测
        link_list_matches = 0
        for pattern in self.link_list_patterns:
            matches = re.findall(pattern, promo_section)
            if matches:
                link_list_matches += len(matches)
                result['matches'].append(f"链接列表: {len(matches)}个")
                self.stats['link_lists_detected'] += 1
        
        if link_list_matches > 0:
            link_confidence = min(link_list_matches / 3.0, 0.4)
            confidence_scores.append(link_confidence)
        
        # 4. @用户名密度检测
        at_mentions = re.findall(r'@\w+', promo_section)
        if len(at_mentions) >= 2:
            mention_confidence = min(len(at_mentions) / 5.0, 0.3)
            confidence_scores.append(mention_confidence)
            result['matches'].append(f"@用户名: {len(at_mentions)}个")
        
        # 5. 基于训练数据的相似度匹配
        training_confidence = self._calculate_training_similarity(promo_section)
        if training_confidence > 0.3:
            confidence_scores.append(training_confidence)
            result['matches'].append(f"训练数据匹配: {training_confidence:.2f}")
        
        # 计算综合置信度
        if confidence_scores:
            result['confidence'] = min(sum(confidence_scores), 1.0)
            result['has_promo'] = result['confidence'] > self.semantic_threshold
        
        return result
    
    def _calculate_training_similarity(self, text: str) -> float:
        """计算与训练数据的相似度"""
        if not self.training_samples or not text.strip():
            return 0.0
        
        text_lower = text.lower()
        max_similarity = 0.0
        
        for sample in self.training_samples:
            if not sample.get('is_promo', False):
                continue
            
            sample_content = sample.get('content', '').lower()
            if not sample_content:
                continue
            
            # 计算多种相似度指标
            similarities = []
            
            # 1. 关键词重叠度
            text_keywords = set(re.findall(r'[@＠]\w+|[订订閱阅订][阅閱]|[频频頻道道]|[投投][稿稿]|[商商務务][务務]|[联聯联][系係系]', text_lower))
            sample_keywords = set(re.findall(r'[@＠]\w+|[订订閱阅订][阅閱]|[频频頻道道]|[投投][稿稿]|[商商務务][务務]|[联聯联][系係系]', sample_content))
            
            if text_keywords and sample_keywords:
                keyword_similarity = len(text_keywords & sample_keywords) / len(text_keywords | sample_keywords)
                similarities.append(keyword_similarity * 0.4)
            
            # 2. 字符n-gram相似度（简化版）
            text_ngrams = self._get_character_ngrams(text_lower, 3)
            sample_ngrams = self._get_character_ngrams(sample_content, 3)
            
            if text_ngrams and sample_ngrams:
                ngram_similarity = len(text_ngrams & sample_ngrams) / len(text_ngrams | sample_ngrams)
                similarities.append(ngram_similarity * 0.3)
            
            # 3. 结构相似度（行数、@符号数量等）
            text_lines = len(text.strip().split('\n'))
            sample_lines = len(sample_content.strip().split('\n'))
            text_ats = len(re.findall(r'[@＠]', text))
            sample_ats = len(re.findall(r'[@＠]', sample_content))
            
            structure_similarity = 0.0
            if max(text_lines, sample_lines) > 0:
                structure_similarity += 0.15 * (1 - abs(text_lines - sample_lines) / max(text_lines, sample_lines))
            if max(text_ats, sample_ats) > 0:
                structure_similarity += 0.15 * (1 - abs(text_ats - sample_ats) / max(text_ats, sample_ats))
            
            similarities.append(structure_similarity)
            
            # 计算总相似度
            total_similarity = sum(similarities)
            max_similarity = max(max_similarity, total_similarity)
        
        return min(max_similarity, 1.0)
    
    def _get_character_ngrams(self, text: str, n: int) -> set:
        """获取字符n-gram集合"""
        if len(text) < n:
            return {text}
        
        ngrams = set()
        for i in range(len(text) - n + 1):
            ngram = text[i:i + n]
            if not ngram.isspace():  # 跳过纯空白的n-gram
                ngrams.add(ngram)
        
        return ngrams
    
    def _filter_footer_content(self, content: str, separator_result: Dict[str, Any], 
                            semantic_result: Dict[str, Any]) -> Tuple[str, List[str]]:
        """过滤推广内容"""
        modifications = []
        
        # 如果没有检测到推广内容，直接返回
        if not separator_result['found'] and not semantic_result['has_promo']:
            return content, modifications
        
        lines = content.split('\n')
        
        # 确定过滤位置
        if separator_result['found']:
            # 基于分隔符过滤
            cut_position = separator_result['position']
            filtered_lines = lines[:cut_position]
            
            removed_lines = len(lines) - cut_position
            modifications.append(f"基于分隔符移除尾部 {removed_lines} 行内容")
            logger.info(f"基于分隔符过滤: 移除第 {cut_position} 行之后的内容")
            
        elif semantic_result['has_promo'] and semantic_result['confidence'] > self.semantic_threshold:
            # 基于语义分析过滤
            # 找到推广内容开始位置
            cut_position = self._find_promo_start_position(lines, semantic_result)
            filtered_lines = lines[:cut_position]
            
            removed_lines = len(lines) - cut_position
            modifications.append(f"基于语义分析移除尾部 {removed_lines} 行推广内容")
            logger.info(f"基于语义分析过滤: 移除第 {cut_position} 行之后的内容")
            
        else:
            # 不过滤
            return content, modifications
        
        # 构建过滤后的内容
        filtered_content = '\n'.join(filtered_lines).rstrip()
        
        # 清理多余的空行
        filtered_content = re.sub(r'\n\s*\n\s*$', '', filtered_content)
        
        return filtered_content, modifications
    
    def _find_promo_start_position(self, lines: List[str], semantic_result: Dict[str, Any]) -> int:
        """找到推广内容开始位置"""
        total_lines = len(lines)
        
        # 从后往前查找第一个包含推广内容的行
        for i in range(total_lines - 1, -1, -1):
            line = lines[i]
            
            # 检查是否包含推广关键词
            has_promo_keyword = any(keyword in line for keyword in self.promo_keywords)
            
            # 检查是否包含@用户名
            has_at_mention = bool(re.search(r'@\w+', line))
            
            # 检查是否包含链接
            has_link = bool(re.search(r'\[([^\]]*)\]\(([^\)]+)\)', line))
            
            if has_promo_keyword or (has_at_mention and has_link):
                # 找到推广内容的开始，尝试向前查找更多上下文
                start_pos = i
                
                # 向前查找2-3行，看是否有相关内容
                for j in range(max(0, i - 3), i):
                    prev_line = lines[j].strip()
                    if prev_line and (
                        any(keyword in prev_line for keyword in self.promo_keywords[:3]) or
                        bool(re.search(r'@\w+', prev_line))
                    ):
                        start_pos = j
                        break
                
                return start_pos
        
        # 如果没找到明确的开始位置，从最后1/4开始
        return max(0, total_lines * 3 // 4)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取过滤器统计信息"""
        base_stats = super().get_stats()
        base_stats.update(self.stats)
        
        # 计算效率指标
        if self.stats['total_processed'] > 0:
            base_stats['separator_detection_rate'] = self.stats['separator_detected'] / self.stats['total_processed']
            base_stats['semantic_match_rate'] = self.stats['semantic_matches'] / self.stats['total_processed']
            base_stats['filter_rate'] = self.stats['footer_content_removed'] / self.stats['total_processed']
        
        return base_stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        super().reset_stats()
        self.stats = {
            'total_processed': 0,
            'separator_detected': 0,
            'footer_content_removed': 0,
            'link_lists_detected': 0,
            'semantic_matches': 0
        }
    
    def update_thresholds(self, separator_threshold: Optional[float] = None,
                         semantic_threshold: Optional[float] = None) -> None:
        """更新阈值"""
        if separator_threshold is not None:
            self.separator_threshold = max(0.0, min(1.0, separator_threshold))
            logger.info(f"更新分隔符阈值: {self.separator_threshold}")
        
        if semantic_threshold is not None:
            self.semantic_threshold = max(0.0, min(1.0, semantic_threshold))
            logger.info(f"更新语义阈值: {self.semantic_threshold}")