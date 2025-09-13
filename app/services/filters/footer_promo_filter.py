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
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'separator_detected': 0,
            'footer_content_removed': 0
        }
    
    def load_separator_patterns(self):
        """加载分隔符模式"""
        try:
            separator_file = PathConfig.SEPARATOR_PATTERNS_FILE
            if separator_file.exists():
                with open(separator_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.separator_patterns = [p['regex'] for p in data.get('patterns', [])]
                    logger.info(f"加载了 {len(self.separator_patterns)} 个分隔符模式")
            else:
                logger.warning("分隔符模式文件不存在，分隔符检测将不可用")
                self.separator_patterns = []
        except Exception as e:
            logger.error(f"加载分隔符模式失败: {e}")
            self.separator_patterns = []
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """预检查是否需要处理"""
        if not content or len(content) < 50:
            return False
        
        # 只检查是否包含分隔符
        if not self.separator_patterns:
            return False
        
        return any(re.search(pattern, content) for pattern in self.separator_patterns)
    
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
            
            # 执行过滤
            filtered_content, modifications = self._filter_footer_content(
                content, separator_result
            )
            
            # 计算处理时间
            processing_time = (time.time() - start_time) * 1000
            
            # 更新统计
            self.stats['total_processed'] += 1
            if separator_result['found']:
                self.stats['separator_detected'] += 1
            if len(filtered_content) < len(content):
                self.stats['footer_content_removed'] += 1
            
            # 构建结果
            filter_result = FilterResult(
                filtered_content=filtered_content,
                passed=True,  # 不阻止消息通过，只是清理内容
                processing_time_ms=processing_time,
                reason=f"检测到尾部推广内容" if len(filtered_content) < len(content) else None,
                details={
                    'separator_detected': separator_result['found'],
                    'separator_position': separator_result.get('position'),
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
    
    def _filter_footer_content(self, content: str, separator_result: Dict[str, Any]) -> Tuple[str, List[str]]:
        """过滤推广内容"""
        modifications = []
        
        # 如果没有检测到分隔符，直接返回
        if not separator_result['found']:
            return content, modifications
        
        # 基于分隔符过滤（按字符位置截断）
        separator_text = separator_result['separator_text']
        separator_pos = content.find(separator_text)
        
        logger.info(f"分隔符检测: separator_text='{separator_text}', position={separator_pos}")
        
        if separator_pos != -1:
            # 从分隔符位置截断到结尾
            filtered_content = content[:separator_pos].rstrip()
            removed_chars = len(content) - len(filtered_content)
            modifications.append(f"基于分隔符截断，移除了 {removed_chars} 个字符")
            logger.info(f"基于分隔符过滤: 从位置 {separator_pos} 截断内容")
            
            # 清理多余的空行
            filtered_content = re.sub(r'\n\s*\n\s*$', '', filtered_content)
            return filtered_content, modifications
        else:
            logger.warning(f"分隔符文本在内容中未找到: '{separator_text}'")
            return content, modifications
    
    
    def get_stats(self) -> Dict[str, Any]:
        """获取过滤器统计信息"""
        base_stats = super().get_stats()
        base_stats.update(self.stats)
        
        # 计算效率指标
        if self.stats['total_processed'] > 0:
            base_stats['separator_detection_rate'] = self.stats['separator_detected'] / self.stats['total_processed']
            base_stats['filter_rate'] = self.stats['footer_content_removed'] / self.stats['total_processed']
        
        return base_stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        super().reset_stats()
        self.stats = {
            'total_processed': 0,
            'separator_detected': 0,
            'footer_content_removed': 0
        }
    
