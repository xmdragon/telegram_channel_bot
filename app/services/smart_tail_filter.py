"""
智能尾部过滤器
识别并移除消息尾部的频道标识，保留正常内容
注意：尾部过滤是移除原频道标识，不算广告
"""
import logging
import re
from typing import Tuple, Optional, List, Dict
from app.services.ad_detector import ad_detector

logger = logging.getLogger(__name__)


class SmartTailFilter:
    """智能尾部过滤器 - 移除频道标识，不是广告"""
    
    def __init__(self):
        self.ad_detector = ad_detector
        # 常见的广告分隔符模式
        self.separator_patterns = [
            r'━{10,}',  # 横线分隔符
            r'═{10,}',  # 双线分隔符
            r'─{10,}',  # 细线分隔符
            r'▬{10,}',  # 粗线分隔符
            r'-{20,}',  # 短横线
            r'={20,}',  # 等号线
            r'\*{20,}', # 星号线
        ]
    
    def filter_tail_ads(self, content: str) -> Tuple[str, bool, Optional[str]]:
        """
        过滤尾部频道标识（不算广告）
        
        Args:
            content: 原始消息内容
            
        Returns:
            (过滤后内容, 是否包含广告, 被过滤的广告部分)
        """
        if not content:
            return content, False, None
        
        # 1. 尝试结构化广告检测（有明显分隔符）
        result = self._filter_by_separator(content)
        if result[1]:  # 找到广告
            logger.info(f"通过分隔符检测到尾部标识，原长度: {len(content)}, 过滤后: {len(result[0])}")
            return result
        
        # 2. 尝试语义分割检测
        result = self._filter_by_semantic_split(content)
        if result[1]:  # 找到广告
            logger.info(f"通过语义分割检测到尾部标识，原长度: {len(content)}, 过滤后: {len(result[0])}")
            return result
        
        # 3. 尝试链接密度检测
        result = self._filter_by_link_density(content)
        if result[1]:  # 找到广告
            logger.info(f"通过链接密度检测到尾部标识，原长度: {len(content)}, 过滤后: {len(result[0])}")
            return result
        
        return content, False, None
    
    def _filter_by_separator(self, content: str) -> Tuple[str, bool, Optional[str]]:
        """通过分隔符检测并过滤尾部标识"""
        # 查找所有分隔符位置
        separator_positions = []
        
        for pattern in self.separator_patterns:
            matches = list(re.finditer(pattern, content))
            for match in matches:
                separator_positions.append({
                    'pos': match.start(),
                    'pattern': pattern,
                    'text': match.group()
                })
        
        if not separator_positions:
            return content, False, None
        
        # 按位置排序
        separator_positions.sort(key=lambda x: x['pos'])
        
        # 从最后一个分隔符开始检查
        for sep in reversed(separator_positions):
            pos = sep['pos']
            
            # 获取分隔符后的内容
            after_separator = content[pos:].strip()
            
            # 检查分隔符后的内容是否为广告
            if self._is_ad_section(after_separator):
                # 返回分隔符前的内容
                clean_content = content[:pos].rstrip()
                ad_part = content[pos:]
                return clean_content, True, ad_part
        
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
        """通过链接密度检测尾部标识"""
        lines = content.split('\n')
        
        if len(lines) < 3:
            return content, False, None
        
        # 从后往前扫描，找到链接密集区
        ad_start_idx = -1
        consecutive_link_lines = 0
        max_consecutive = 0
        
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            
            if not line:
                continue
            
            # 计算该行的链接密度
            link_density = self._calculate_line_link_density(line)
            
            if link_density > 0.4:  # 链接密度阈值（从0.3提高到0.4）
                consecutive_link_lines += 1
                if consecutive_link_lines > max_consecutive:
                    max_consecutive = consecutive_link_lines
                    ad_start_idx = i
            else:
                # 如果已经找到连续的链接密集行
                if consecutive_link_lines >= 3:
                    # 验证是否为广告
                    potential_ad = '\n'.join(lines[ad_start_idx:])
                    if self._is_ad_section(potential_ad):
                        clean_content = '\n'.join(lines[:ad_start_idx]).rstrip()
                        return clean_content, True, potential_ad
                
                consecutive_link_lines = 0
        
        # 检查最后的连续链接行
        if consecutive_link_lines >= 3 and ad_start_idx >= 0:
            potential_ad = '\n'.join(lines[ad_start_idx:])
            if self._is_ad_section(potential_ad):
                clean_content = '\n'.join(lines[:ad_start_idx]).rstrip()
                return clean_content, True, potential_ad
        
        return content, False, None
    
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
        """判断文本段是否为广告"""
        if not text:
            return False
        
        # 1. 使用AI检测
        if self.ad_detector.initialized:
            is_ad, confidence = self.ad_detector.is_advertisement_ai(text)
            if confidence > 0.7:
                return is_ad
        
        # 2. 检查广告特征
        ad_score = 0.0
        
        # 链接数量
        url_count = len(re.findall(r'https?://[^\s]+|t\.me/[^\s]+', text))
        if url_count >= 3:
            ad_score += 0.4
        
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
        
        return ad_score >= 0.6  # 提高阈值从0.5到0.6，减少误判
    
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