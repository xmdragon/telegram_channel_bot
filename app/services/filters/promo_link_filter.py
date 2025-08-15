"""
推广链接过滤器
实现深度推广链接检测

Author: Claude
Created: 2025-08-15
"""

import re
import time
import base64
import logging
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse, parse_qs

from .base import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)


class PromoLinkFilter(BaseFilter):
    """推广链接过滤器
    
    检测和过滤：
    - 短链接 (bit.ly, tinyurl.com等)
    - 变形链接和隐藏推广
    - Base64编码链接
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("promo_link_filter", config)
        
        # 已知短链接服务域名
        self.short_link_domains = {
            'bit.ly', 'tinyurl.com', 'goo.gl', 't.co', 'ow.ly', 
            'short.link', 'tiny.cc', 'is.gd', 'buff.ly', 
            'rebrand.ly', 'clck.ru', 'v.gd', 'qr.ae',
            # 中文短链接服务
            'dwz.cn', 'suo.im', 'mrw.so', 'url.cn', 't.cn',
            # 赌博推广常用短链接
            'y3.gg', 'y3.tv', 'yh.gg', 'yl.gg'
        }
        
        # 可疑域名模式
        self.suspicious_domain_patterns = [
            r'[a-z]{1,3}\.[a-z]{2}$',  # 超短域名如 a.gg
            r'[0-9]+[a-z]{1,2}\.[a-z]{2,3}$',  # 数字+字母域名
            r'y[0-9].*\.(gg|tv|me)$',  # y+数字的赌博域名
            r'[a-z]{1,2}[0-9]+\.(com|net|org)$',  # 字母+数字域名
        ]
        
        # 推广关键词
        self.promo_keywords = [
            '注册', '登录', '下载', '点击', '访问', '进入',
            '加入', '订阅', '关注', '联系', '咨询', 
            '优惠', '折扣', '返利', '奖励', '福利'
        ]
        
        # 统计信息
        self.stats = {
            'total_links_detected': 0,
            'short_links_detected': 0,
            'suspicious_links_detected': 0,
            'base64_links_detected': 0,
            'hidden_links_detected': 0,
            'promo_context_detected': 0
        }
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """预检查是否包含链接"""
        if not content:
            return False
        
        # 快速检查是否包含http链接或可能的Base64编码
        has_http_link = bool(re.search(r'https?://', content, re.IGNORECASE))
        has_base64 = bool(re.search(r'[A-Za-z0-9+/]{20,}={0,2}', content))
        
        return has_http_link or has_base64
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """过滤推广链接"""
        start_time = time.time()
        
        if not content:
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0,
                reason="空内容"
            )
        
        try:
            # 检测各种类型的推广链接
            detection_results = await self._comprehensive_link_detection(content, context)
            
            # 处理检测结果
            filtered_content, modifications = self._process_detection_results(content, detection_results)
            
            # 计算处理时间
            processing_time = (time.time() - start_time) * 1000
            
            # 判断是否检测到推广链接
            has_promo_links = any(result['is_promo'] for result in detection_results['detected_links'])
            
            # 构建结果
            filter_result = FilterResult(
                filtered_content=filtered_content,
                passed=True,  # 不设置Early Stop，继续后续过滤
                processing_time_ms=processing_time,
                reason=f"检测到{len([r for r in detection_results['detected_links'] if r['is_promo']])}个推广链接" if has_promo_links else None,
                confidence=max([r['confidence'] for r in detection_results['detected_links']], default=0.0),
                details={
                    'total_links': detection_results['total_links'],
                    'promo_links': len([r for r in detection_results['detected_links'] if r['is_promo']]),
                    'detection_results': detection_results,
                    'original_length': len(content),
                    'filtered_length': len(filtered_content)
                },
                should_early_stop=False,  # 不设置Early Stop，继续后续过滤
                modifications=modifications
            )
            
            if has_promo_links:
                logger.info(f"检测到推广链接: {len([r for r in detection_results['detected_links'] if r['is_promo']])}个")
            
            return filter_result
            
        except Exception as e:
            logger.error(f"推广链接过滤失败: {e}")
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=(time.time() - start_time) * 1000,
                reason=f"处理异常: {str(e)}",
                confidence=0.0
            )
    
    async def _comprehensive_link_detection(self, content: str, context: FilterContext) -> Dict[str, Any]:
        """综合链接检测"""
        # TODO: 这是一个框架实现，需要后续完善具体的检测逻辑
        
        detected_links = []
        total_links = 0
        
        # 1. 基础HTTP链接检测
        http_links = self._extract_http_links(content)
        total_links += len(http_links)
        
        for link in http_links:
            detection_result = await self._analyze_single_link(link, content)
            detected_links.append(detection_result)
        
        # 2. Base64编码链接检测
        # TODO: 实现Base64编码链接的检测和解码
        base64_links = self._detect_base64_links(content)
        self.stats['base64_links_detected'] += len(base64_links)
        
        for encoded_link in base64_links:
            # TODO: 解码Base64链接并分析
            detection_result = {
                'url': encoded_link,
                'type': 'base64_encoded',
                'is_promo': True,  # Base64编码的链接通常是推广
                'confidence': 0.8,
                'reasons': ['Base64编码隐藏']
            }
            detected_links.append(detection_result)
        
        # 3. 隐藏链接检测
        # TODO: 检测通过特殊字符、零宽字符等隐藏的链接
        hidden_links = self._detect_hidden_links(content)
        self.stats['hidden_links_detected'] += len(hidden_links)
        
        # 4. 变形链接检测
        # TODO: 检测通过点号替换、字符插入等变形的链接
        disguised_links = self._detect_disguised_links(content)
        
        return {
            'total_links': total_links,
            'detected_links': detected_links,
            'base64_links': base64_links,
            'hidden_links': hidden_links,
            'disguised_links': disguised_links
        }
    
    def _extract_http_links(self, content: str) -> List[str]:
        """提取HTTP链接"""
        # 匹配HTTP/HTTPS链接
        link_pattern = re.compile(r'https?://[^\s\)\]\}]+', re.IGNORECASE)
        links = link_pattern.findall(content)
        
        self.stats['total_links_detected'] += len(links)
        return links
    
    async def _analyze_single_link(self, url: str, content: str) -> Dict[str, Any]:
        """分析单个链接"""
        # TODO: 这里需要实现更复杂的链接分析逻辑
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            is_promo = False
            confidence = 0.0
            reasons = []
            link_type = 'normal'
            
            # 1. 检查是否是短链接
            if domain in self.short_link_domains:
                is_promo = True
                confidence = 0.9
                reasons.append(f'已知短链接服务: {domain}')
                link_type = 'short_link'
                self.stats['short_links_detected'] += 1
            
            # 2. 检查可疑域名模式
            for pattern in self.suspicious_domain_patterns:
                if re.match(pattern, domain):
                    is_promo = True
                    confidence = max(confidence, 0.7)
                    reasons.append(f'可疑域名模式: {pattern}')
                    link_type = 'suspicious'
                    self.stats['suspicious_links_detected'] += 1
                    break
            
            # 3. 检查链接周围的推广上下文
            promo_context = self._check_promo_context(url, content)
            if promo_context['has_promo_context']:
                is_promo = True
                confidence = max(confidence, promo_context['confidence'])
                reasons.extend(promo_context['reasons'])
                self.stats['promo_context_detected'] += 1
            
            # 4. TODO: 检查URL参数中的推广标识
            # 例如: ?ref=promo, ?utm_source=ad 等
            promo_params = self._check_promo_params(parsed)
            if promo_params['has_promo_params']:
                is_promo = True
                confidence = max(confidence, 0.6)
                reasons.extend(promo_params['reasons'])
            
            # 5. TODO: 检查是否是已知的推广/赌博网站
            # 这里可以维护一个黑名单数据库
            if self._is_known_promo_domain(domain):
                is_promo = True
                confidence = 0.95
                reasons.append('已知推广域名')
            
            return {
                'url': url,
                'domain': domain,
                'type': link_type,
                'is_promo': is_promo,
                'confidence': confidence,
                'reasons': reasons
            }
            
        except Exception as e:
            logger.error(f"分析链接失败: {url} - {e}")
            return {
                'url': url,
                'type': 'error',
                'is_promo': False,
                'confidence': 0.0,
                'reasons': [f'分析失败: {str(e)}']
            }
    
    def _check_promo_context(self, url: str, content: str) -> Dict[str, Any]:
        """检查链接周围的推广上下文"""
        # 查找链接在内容中的位置
        url_pos = content.find(url)
        if url_pos == -1:
            return {'has_promo_context': False, 'confidence': 0.0, 'reasons': []}
        
        # 提取链接前后的文字（前后各50个字符）
        start_pos = max(0, url_pos - 50)
        end_pos = min(len(content), url_pos + len(url) + 50)
        context = content[start_pos:end_pos]
        
        has_promo = False
        confidence = 0.0
        reasons = []
        
        # 检查推广关键词
        for keyword in self.promo_keywords:
            if keyword in context:
                has_promo = True
                confidence = max(confidence, 0.6)
                reasons.append(f'包含推广关键词: {keyword}')
        
        # TODO: 检查其他推广模式
        # - 表情符号 + 链接
        # - "点击这里" + 链接
        # - 优惠信息 + 链接
        
        return {
            'has_promo_context': has_promo,
            'confidence': confidence,
            'reasons': reasons
        }
    
    def _check_promo_params(self, parsed_url) -> Dict[str, Any]:
        """检查URL参数中的推广标识"""
        # TODO: 实现URL参数分析
        # 检查常见的推广参数:
        # - utm_source, utm_medium, utm_campaign
        # - ref, referrer
        # - promo, promotion
        # - affiliate, aff
        
        query_params = parse_qs(parsed_url.query)
        promo_param_keys = ['utm_source', 'utm_medium', 'ref', 'referrer', 'promo', 'aff', 'affiliate']
        
        has_promo_params = False
        reasons = []
        
        for key in promo_param_keys:
            if key in query_params:
                has_promo_params = True
                reasons.append(f'推广参数: {key}={query_params[key]}')
        
        return {
            'has_promo_params': has_promo_params,
            'reasons': reasons
        }
    
    def _is_known_promo_domain(self, domain: str) -> bool:
        """检查是否是已知的推广域名"""
        # TODO: 维护一个推广域名黑名单
        # 这里可以连接到外部数据库或API
        
        known_promo_domains = {
            # 赌博相关域名
            'y3ylc.com', 'yabo.com', 'bet365.com',
            # 其他推广域名...
        }
        
        return domain.lower() in known_promo_domains
    
    def _detect_base64_links(self, content: str) -> List[str]:
        """检测Base64编码的链接"""
        # TODO: 实现Base64编码链接检测
        # 1. 查找可能的Base64字符串
        # 2. 尝试解码
        # 3. 检查解码结果是否是有效URL
        
        base64_pattern = re.compile(r'[A-Za-z0-9+/]{20,}={0,2}')
        potential_base64 = base64_pattern.findall(content)
        
        decoded_links = []
        for b64_str in potential_base64:
            try:
                decoded = base64.b64decode(b64_str).decode('utf-8')
                if decoded.startswith(('http://', 'https://')):
                    decoded_links.append(b64_str)
                    logger.info(f"检测到Base64编码链接: {b64_str[:20]}... -> {decoded[:50]}...")
            except Exception:
                # 解码失败，不是有效的Base64
                continue
        
        return decoded_links
    
    def _detect_hidden_links(self, content: str) -> List[str]:
        """检测隐藏链接"""
        # TODO: 实现隐藏链接检测
        # 1. 零宽字符分隔的链接
        # 2. 特殊Unicode字符
        # 3. HTML实体编码
        
        hidden_links = []
        
        # 检查零宽字符
        zero_width_chars = ['\u200b', '\u200c', '\u200d', '\ufeff']
        for char in zero_width_chars:
            if char in content:
                # TODO: 进一步分析零宽字符附近的内容
                logger.debug(f"检测到零宽字符: {repr(char)}")
        
        return hidden_links
    
    def _detect_disguised_links(self, content: str) -> List[str]:
        """检测变形链接"""
        # TODO: 实现变形链接检测
        # 1. 点号被替换为其他字符 (hxxp://, http[.]com)
        # 2. 字符插入 (h t t p : / /)
        # 3. 字符替换 (使用相似字符)
        
        disguised_patterns = [
            r'hxxps?://[^\s]+',  # hxxp://替换
            r'https?\[.\][^\s]+',  # http[.]替换
            r'h\s*t\s*t\s*p\s*[:\s]*\/\s*\/[^\s]+',  # 字符分隔
        ]
        
        disguised_links = []
        for pattern in disguised_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            disguised_links.extend(matches)
        
        return disguised_links
    
    def _process_detection_results(self, content: str, detection_results: Dict[str, Any]) -> Tuple[str, List[str]]:
        """处理检测结果，生成过滤后的内容"""
        filtered_content = content
        modifications = []
        
        # 移除检测到的推广链接
        for link_info in detection_results['detected_links']:
            if link_info['is_promo'] and link_info['confidence'] > 0.7:
                original_url = link_info['url']
                
                # 移除链接
                filtered_content = filtered_content.replace(original_url, '')
                modifications.append(f"移除推广链接: {original_url[:50]}...")
                logger.info(f"移除推广链接: {original_url} (置信度: {link_info['confidence']:.2f})")
        
        # TODO: 处理Base64编码链接
        for encoded_link in detection_results['base64_links']:
            filtered_content = filtered_content.replace(encoded_link, '')
            modifications.append(f"移除Base64编码链接: {encoded_link[:20]}...")
        
        # 清理多余的空格和换行
        filtered_content = re.sub(r'\s+', ' ', filtered_content)
        filtered_content = re.sub(r'\n\s*\n', '\n', filtered_content)
        filtered_content = filtered_content.strip()
        
        return filtered_content, modifications
    
    def get_stats(self) -> Dict[str, Any]:
        """获取过滤器统计信息"""
        base_stats = super().get_stats()
        base_stats.update(self.stats)
        return base_stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        super().reset_stats()
        self.stats = {
            'total_links_detected': 0,
            'short_links_detected': 0,
            'suspicious_links_detected': 0,
            'base64_links_detected': 0,
            'hidden_links_detected': 0,
            'promo_context_detected': 0
        }