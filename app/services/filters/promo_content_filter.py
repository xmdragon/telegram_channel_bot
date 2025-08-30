"""
推广内容过滤器
基于分隔符模式和语义分析检测并过滤推广内容

Author: Claude
Created: 2025-08-24
"""

import re
import time
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from .base import BaseFilter, FilterResult, FilterContext
from app.core.path_config import PathConfig
from app.core.threshold_manager import threshold_manager

logger = logging.getLogger(__name__)


class PromoContentFilter(BaseFilter):
    """推广内容过滤器
    
    检测和过滤：
    - 基于分隔符的推广内容边界识别
    - 内嵌推广模式检测
    - 语义分析推广内容
    - 连带分隔符一起过滤
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("promo_content_filter", config)
        
        # 加载配置文件
        self.embedded_patterns = []
        self.context_patterns = []
        self.separator_list = []
        self.load_embedded_patterns()
        
        # 分隔符模式
        self.separator_patterns = []
        self.load_separator_patterns()
        
        # 动态阈值（从ThresholdManager获取）
        self.filter_name = "promo_content_filter"
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'embedded_pattern_detected': 0,
            'separator_based_filtered': 0,
            'semantic_filtered': 0,
            'content_removed': 0
        }
    
    def load_embedded_patterns(self):
        """加载内嵌推广模式配置"""
        try:
            pattern_file = PathConfig.DATA_DIR / "training/tail/embedded_promo_patterns.json"
            if pattern_file.exists():
                with open(pattern_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.embedded_patterns = data.get('patterns', [])
                    self.context_patterns = data.get('contexts', [])
                    self.separator_list = data.get('separators', [])
                    logger.info(f"加载了 {len(self.embedded_patterns)} 个内嵌推广模式")
            else:
                logger.warning("内嵌推广模式配置文件不存在，使用空配置")
                self.embedded_patterns = []
                self.context_patterns = []
                self.separator_list = []
        except Exception as e:
            logger.error(f"加载内嵌推广模式失败: {e}")
            self.embedded_patterns = []
            self.context_patterns = []
            self.separator_list = []
    
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
                logger.warning("分隔符模式文件不存在，使用空配置")
                self.separator_patterns = []
        except Exception as e:
            logger.error(f"加载分隔符模式失败: {e}")
            self.separator_patterns = []
    
    
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """预检查是否包含推广内容"""
        if not content or len(content) < 30:
            return False
        
        # 快速检查是否包含内嵌推广模式
        for pattern_info in self.embedded_patterns[:5]:  # 只检查前5个最重要的
            if re.search(pattern_info['pattern'], content, re.IGNORECASE):
                return True
        
        # 快速检查是否包含分隔符
        for separator in self.separator_list[:5]:
            if separator in content:
                return True
        
        return False
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """过滤推广内容"""
        start_time = time.time()
        
        # 更新动态阈值
        
        if not content:
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0,
                reason="空内容"
            )
        
        try:
            # 1. 检测内嵌推广模式
            embedded_result = self._detect_embedded_patterns(content)
            
            # 2. 检测分隔符边界
            separator_result = self._detect_separator_boundaries(content)
            
            # 3. 语义分析
            semantic_result = self._analyze_promo_semantics(
                content, embedded_result, separator_result
            )
            
            # 4. 执行过滤
            filtered_content, modifications = self._filter_promo_content(
                content, embedded_result, separator_result, semantic_result
            )
            
            # 计算处理时间
            processing_time = (time.time() - start_time) * 1000
            
            # 更新统计
            self._update_promo_stats(embedded_result, separator_result, semantic_result, 
                             len(content) != len(filtered_content))
            
            # 构建结果
            has_promo = (embedded_result['detected'] or 
                        separator_result['found'] or 
                        semantic_result['has_promo'])
            
            filter_result = FilterResult(
                filtered_content=filtered_content,
                passed=True,  # 不阻止消息通过，只清理内容
                processing_time_ms=processing_time,
                reason=f"检测到推广内容并过滤" if len(filtered_content) < len(content) else None,
                details={
                    'embedded_patterns_detected': embedded_result['matches'],
                    'separator_boundaries': separator_result['boundaries'],
                    'semantic_analysis': semantic_result['analysis'],
                    'original_length': len(content),
                    'filtered_length': len(filtered_content),
                    'removed_content_length': len(content) - len(filtered_content)
                },
                should_early_stop=False,
                modifications=modifications
            )
            
            if len(filtered_content) < len(content):
                logger.info(f"过滤推广内容: {len(content)} -> {len(filtered_content)} 字符")
            
            return filter_result
            
        except Exception as e:
            logger.error(f"推广内容过滤失败: {e}")
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=(time.time() - start_time) * 1000,
                reason=f"处理异常: {str(e)}",
                confidence=0.0
            )
    
    def _detect_embedded_patterns(self, content: str) -> Dict[str, Any]:
        """检测内嵌推广模式"""
        result = {
            'detected': False,
            'matches': [],
            'positions': []
        }
        
        for pattern_info in self.embedded_patterns:
            matches = list(re.finditer(pattern_info['pattern'], content, re.IGNORECASE))
            if matches:
                for match in matches:
                    result['matches'].append({
                        'pattern': pattern_info['pattern'],
                        'category': pattern_info.get('category', 'unknown'),
                        'text': match.group(),
                        'start': match.start(),
                        'end': match.end()
                    })
                    result['positions'].append((match.start(), match.end()))
                
                result['detected'] = True
        
        # 检查上下文模式
        for context in self.context_patterns:
            before_score = sum(1 for kw in context.get('before_keywords', []) if kw in content.lower())
            after_score = sum(1 for kw in context.get('after_keywords', []) if kw in content.lower())
            
            if before_score > 0 and after_score > 0:
                result['detected'] = True
                result['matches'].append({
                    'type': 'context',
                    'before_matches': before_score,
                    'after_matches': after_score
                })
        
        return result
    
    def _detect_separator_boundaries(self, content: str) -> Dict[str, Any]:
        """检测分隔符边界"""
        result = {
            'found': False,
            'boundaries': []
        }
        
        lines = content.split('\n')
        total_lines = len(lines)
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # 检查分隔符模式
            for pattern in self.separator_patterns:
                if re.search(pattern, line_stripped):
                    result['boundaries'].append({
                        'line_index': i,
                        'pattern': pattern,
                        'text': line_stripped
                    })
                    
                    result['found'] = True
            
            # 检查配置中的分隔符字符串
            for separator in self.separator_list:
                if separator in line_stripped:
                    result['boundaries'].append({
                        'line_index': i,
                        'separator': separator,
                        'text': line_stripped
                    })
                    
                    result['found'] = True
        
        # 不需要排序，找到第一个就用
        
        return result
    
    
    def _analyze_promo_semantics(self, content: str, embedded_result: Dict, separator_result: Dict) -> Dict[str, Any]:
        """语义分析推广内容"""
        result = {
            'has_promo': False,
            'analysis': {}
        }
        
        # 如果已经检测到明确的内嵌模式，直接返回
        if embedded_result['detected']:
            result['has_promo'] = True
            result['analysis']['basis'] = 'embedded_patterns'
            return result
        
        # 如果有分隔符，直接标记为推广内容
        if separator_result['found']:
            result['has_promo'] = True
            result['analysis']['basis'] = 'separator_detected'
        
        return result
    
    
    def _filter_promo_content(self, content: str, embedded_result: Dict, 
                            separator_result: Dict, semantic_result: Dict) -> Tuple[str, List[str]]:
        """过滤推广内容"""
        modifications = []
        filtered_content = content
        
        # 优先级1: 基于内嵌模式过滤
        if embedded_result['detected']:
            filtered_content = self._filter_by_embedded_patterns(filtered_content, embedded_result)
            modifications.append(f"移除{len(embedded_result['matches'])}个内嵌推广模式")
        
        # 优先级2: 基于分隔符边界过滤
        if separator_result['found']:
            
            best_boundary = separator_result['boundaries'][0]
            lines = filtered_content.split('\n')
            
            # 从分隔符开始切除（包含分隔符）
            cut_position = best_boundary['line_index']
            filtered_lines = lines[:cut_position]
            filtered_content = '\n'.join(filtered_lines).rstrip()
            
            removed_lines = len(lines) - cut_position
            modifications.append(f"基于分隔符移除尾部{removed_lines}行内容")
            
            self.stats['separator_based_filtered'] += 1
        
        # 清理多余的空行
        filtered_content = re.sub(r'\n\s*\n\s*$', '', filtered_content)
        filtered_content = filtered_content.strip()
        
        return filtered_content, modifications
    
    def _filter_by_embedded_patterns(self, content: str, embedded_result: Dict) -> str:
        """基于内嵌模式过滤"""
        filtered_content = content
        
        # 按位置倒序移除（避免位置偏移）
        positions = sorted(embedded_result['positions'], key=lambda x: x[0], reverse=True)
        
        for start, end in positions:
            # 移除匹配的内容
            filtered_content = filtered_content[:start] + filtered_content[end:]
        
        # 清理连续的空格和换行
        filtered_content = re.sub(r'\s+', ' ', filtered_content)
        filtered_content = re.sub(r'\n\s*\n', '\n', filtered_content)
        
        return filtered_content
    
    def _update_promo_stats(self, embedded_result: Dict, separator_result: Dict, 
                     semantic_result: Dict, content_removed: bool):
        """更新推广过滤统计信息"""
        self.stats['total_processed'] += 1
        
        if embedded_result['detected']:
            self.stats['embedded_pattern_detected'] += 1
        
        if separator_result['found']:
            self.stats['separator_based_filtered'] += 1
        
        if semantic_result['has_promo']:
            self.stats['semantic_filtered'] += 1
        
        if content_removed:
            self.stats['content_removed'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取过滤器统计信息"""
        base_stats = super().get_stats()
        base_stats.update(self.stats)
        
        # 计算效率指标
        if self.stats['total_processed'] > 0:
            base_stats['embedded_detection_rate'] = self.stats['embedded_pattern_detected'] / self.stats['total_processed']
            base_stats['semantic_filter_rate'] = self.stats['semantic_filtered'] / self.stats['total_processed']
            base_stats['content_removal_rate'] = self.stats['content_removed'] / self.stats['total_processed']
        
        return base_stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        super().reset_stats()
        self.stats = {
            'total_processed': 0,
            'embedded_pattern_detected': 0,
            'separator_based_filtered': 0,
            'semantic_filtered': 0,
            'content_removed': 0
        }