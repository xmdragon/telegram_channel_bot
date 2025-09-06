"""
混合尾部过滤器 - 极简化版本
只使用向量匹配，不降级，不硬编码

Linus哲学：消除所有特殊情况和不必要的复杂性
Author: Claude
Updated: 2025-09-06
"""

import logging
import re
from typing import Tuple, Dict, Optional, List
from app.services.filters.tail_vector_filter import get_tail_vector_filter

logger = logging.getLogger(__name__)


class HybridTailFilter:
    """极简混合尾部过滤器
    
    只做一件事：使用向量匹配过滤尾部内容
    没有硬编码，没有降级，没有特殊逻辑
    """
    
    def __init__(self, vector_threshold: float = 0.15):
        """初始化混合过滤器
        
        Args:
            vector_threshold: 向量相似度阈值
        """
        self.vector_threshold = vector_threshold
        self.vector_filter = get_tail_vector_filter()
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'vector_filtered': 0,
            'lines_removed': 0
        }
        
        # 检查向量过滤器初始化状态
        if self.vector_filter.is_initialized:
            logger.info(f"✅ 混合尾部过滤器初始化完成 - 向量阈值: {vector_threshold}")
            logger.info(f"   向量过滤器状态: 正常 ({len(self.vector_filter.tail_samples)}个样本)")
        else:
            logger.error(f"❌ 混合尾部过滤器初始化异常 - 向量过滤器未正确初始化")
    
    def filter_message(self, content: str, has_media: bool = False) -> Tuple[str, bool, Optional[str], Dict]:
        """
        执行尾部过滤 - 极简版本
        
        Args:
            content: 完整消息内容
            has_media: 是否有媒体文件（未使用，保留接口兼容）
            
        Returns:
            (过滤后内容, 是否过滤了尾部, 尾部内容, 分析详情)
        """
        self.stats['total_processed'] += 1
        
        if not content or not content.strip():
            return content, False, None, {'reason': '内容为空'}
        
        # 检查向量过滤器是否初始化
        if not self.vector_filter.is_initialized:
            logger.warning("⚠️ 向量过滤器未初始化，跳过过滤")
            return content, False, None, {'reason': '过滤器未初始化'}
        
        # 将连续5个或更多空格转换为换行符
        if re.search(r' {5,}', content):
            content = re.sub(r' {5,}', '\n', content)
            logger.debug("检测到连续空格，已转换为换行符")
        
        lines = content.split('\n')
        if len(lines) < 2:
            return content, False, None, {'reason': '内容行数不足'}
        
        # 极简向量过滤
        filtered_lines, removed_lines = self._simple_vector_filter(lines)
        
        if removed_lines:
            self.stats['vector_filtered'] += 1
            self.stats['lines_removed'] += len(removed_lines)
            
            filtered_content = '\n'.join(filtered_lines)
            removed_content = '\n'.join(removed_lines)
            
            logger.info(f"✅ 混合过滤成功: {len(content)} -> {len(filtered_content)} 字符")
            logger.info(f"   移除了 {len(removed_lines)} 行推广内容")
            
            analysis = {
                'method': 'vector',
                'removed_lines_count': len(removed_lines),
                'filter_ratio': len(removed_content) / len(content)
            }
            
            return filtered_content, True, removed_content, analysis
        else:
            return content, False, None, {'no_promotion_detected': True}
    
    def _simple_vector_filter(self, lines: List[str]) -> Tuple[List[str], List[str]]:
        """极简向量过滤 - 从尾部往前扫描
        
        Args:
            lines: 文本行列表
            
        Returns:
            (保留的行, 移除的行)
        """
        kept_lines = []
        removed_lines = []
        
        # 从尾部往前找到第一个非推广内容
        filter_start_index = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            
            if not line:  # 空行跳过
                continue
            
            # 使用向量判断
            is_tail, similarity = self.vector_filter.is_tail_content(line)
            
            if not is_tail:
                # 找到非推广内容，停止过滤
                filter_start_index = i + 1
                logger.debug(f"找到正文边界，第{i}行后开始过滤")
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
                        logger.debug(f"移除推广内容 (相似度: {similarity:.3f}): {line_stripped[:50]}...")
                    else:
                        # 向量判断不是推广，保留
                        kept_lines.append(line)
        
        return kept_lines, removed_lines
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return self.stats.copy()


# 单例实例
_hybrid_filter_instance = None


def get_hybrid_tail_filter() -> HybridTailFilter:
    """获取混合尾部过滤器单例"""
    global _hybrid_filter_instance
    if _hybrid_filter_instance is None:
        _hybrid_filter_instance = HybridTailFilter()
    return _hybrid_filter_instance