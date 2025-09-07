"""
ONNX语义尾部过滤器 - 极简版本
纯语义判断，无复杂逻辑

Linus原则：消除所有不必要的复杂性
Author: Claude (ONNX简化重构)  
Updated: 2025-09-07
"""

import re
import logging
from typing import List, Tuple, Dict, Optional

from .tail_vector_filter import get_tail_vector_filter

logger = logging.getLogger(__name__)


class HybridTailFilter:
    """极简ONNX语义尾部过滤器
    
    只做一件事：使用ONNX语义模型进行尾部内容识别
    无保护机制，无复杂逻辑，相信语义模型的判断
    """
    
    def __init__(self):
        """初始化混合过滤器"""
        self.vector_filter = get_tail_vector_filter()
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'filtered': 0,
            'lines_removed': 0
        }
        
        if self.vector_filter.is_initialized:
            logger.info("✅ ONNX语义尾部过滤器初始化成功")
        else:
            logger.error("❌ ONNX语义尾部过滤器初始化失败")
    
    def filter_message(self, content: str, has_media: bool = False) -> Tuple[str, bool, Optional[str], Dict]:
        """
        执行尾部过滤 - 极简版本
        
        Args:
            content: 完整消息内容
            has_media: 是否有媒体文件（保留接口兼容，实际未使用）
            
        Returns:
            (过滤后内容, 是否过滤了尾部, 尾部内容, 分析详情)
        """
        self.stats['total_processed'] += 1
        
        if not content or not content.strip():
            return content, False, None, {'reason': '内容为空'}
        
        # 检查ONNX语义过滤器是否初始化
        if not self.vector_filter.is_initialized:
            logger.warning("⚠️ ONNX语义过滤器未初始化，跳过过滤")
            return content, False, None, {'reason': 'ONNX过滤器未初始化'}
        
        # 将连续5个或更多空格转换为换行符
        if re.search(r' {5,}', content):
            content = re.sub(r' {5,}', '\n', content)
            logger.debug("检测到连续空格，已转换为换行符")
        
        lines = content.split('\n')
        if len(lines) < 2:
            return content, False, None, {'reason': '内容行数不足'}
        
        # 纯ONNX语义过滤：从尾部往前扫描
        filtered_lines, removed_lines = self._semantic_filter(lines)
        
        if removed_lines:
            self.stats['filtered'] += 1
            self.stats['lines_removed'] += len(removed_lines)
            
            filtered_content = '\n'.join(filtered_lines)
            removed_content = '\n'.join(removed_lines)
            
            logger.info(f"✅ ONNX语义过滤成功: {len(content)} -> {len(filtered_content)} 字符")
            logger.info(f"   移除了 {len(removed_lines)} 行推广内容")
            
            analysis = {
                'method': 'ONNX_semantic',
                'removed_lines_count': len(removed_lines),
                'filter_ratio': len(removed_content) / len(content),
                'model_type': 'ONNX'
            }
            
            return filtered_content, True, removed_content, analysis
        else:
            return content, False, None, {'no_promotion_detected': True, 'model_type': 'ONNX'}
    
    def _semantic_filter(self, lines: List[str]) -> Tuple[List[str], List[str]]:
        """纯ONNX语义过滤 - 从尾部往前扫描
        
        Args:
            lines: 文本行列表
            
        Returns:
            (保留的行, 移除的行)
        """
        kept_lines = []
        removed_lines = []
        
        # 从尾部往前扫描，找到第一个非推广内容
        filter_start_index = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            
            if not line:  # 空行跳过
                continue
            
            # 使用ONNX语义判断
            is_tail, similarity = self.vector_filter.is_tail_content(line)
            
            if not is_tail:
                # 找到非推广内容，停止过滤
                filter_start_index = i + 1
                logger.debug(f"ONNX语义边界：第{i}行后开始过滤")
                break
        
        # 构建结果
        for i, line in enumerate(lines):
            if i < filter_start_index:
                kept_lines.append(line)
            else:
                line_stripped = line.strip()
                if not line_stripped:
                    # 过滤范围内的空行也移除
                    removed_lines.append(line)
                else:
                    # 再次检查是否为推广内容
                    is_tail, similarity = self.vector_filter.is_tail_content(line_stripped)
                    if is_tail:
                        removed_lines.append(line)
                        logger.debug(f"移除推广内容 (ONNX相似度: {similarity:.3f}): {line_stripped[:50]}...")
                    else:
                        # ONNX语义判断不是推广，保留
                        kept_lines.append(line)
        
        return kept_lines, removed_lines
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        stats = self.stats.copy()
        if self.vector_filter:
            vector_stats = self.vector_filter.get_statistics()
            stats.update({
                'vector_filter_initialized': vector_stats.get('initialized', False),
                'sample_count': vector_stats.get('sample_count', 0),
                'threshold': vector_stats.get('threshold', 0),
                'model_type': vector_stats.get('model_type', 'Unknown')
            })
        return stats


# 单例实例
_hybrid_filter_instance = None


def get_hybrid_tail_filter() -> HybridTailFilter:
    """获取混合尾部过滤器单例"""
    global _hybrid_filter_instance
    if _hybrid_filter_instance is None:
        _hybrid_filter_instance = HybridTailFilter()
    return _hybrid_filter_instance