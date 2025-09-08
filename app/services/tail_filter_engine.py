"""
尾部过滤引擎 - 极简化版本
只使用混合向量过滤器，不降级

Linus哲学：消除所有不必要的复杂性
"""

import logging
from typing import Tuple, Dict, Optional

logger = logging.getLogger(__name__)

# 延迟导入混合向量过滤器，避免循环导入
HYBRID_FILTER_AVAILABLE = None  # None表示未检查


class TailFilterEngine:
    """极简尾部过滤引擎
    
    只做一件事：调用混合向量过滤器
    没有降级，没有复杂逻辑
    """
    
    def __init__(self):
        self.hybrid_filter = None
        self._check_and_init_hybrid_filter()
    
    def _check_and_init_hybrid_filter(self):
        """延迟检查和初始化混合过滤器"""
        global HYBRID_FILTER_AVAILABLE
        
        if HYBRID_FILTER_AVAILABLE is None:
            # 第一次检查，尝试导入
            try:
                from .filters.hybrid_tail_filter import get_hybrid_tail_filter
                HYBRID_FILTER_AVAILABLE = True
                logger.info("✅ 混合向量过滤器可用")
            except ImportError as e:
                HYBRID_FILTER_AVAILABLE = False
                logger.error(f"❌ 混合向量过滤器不可用: {e}")
        
        if HYBRID_FILTER_AVAILABLE:
            try:
                from .filters.hybrid_tail_filter import get_hybrid_tail_filter
                self.hybrid_filter = get_hybrid_tail_filter()
                logger.info("✅ 尾部过滤引擎初始化成功")
            except Exception as e:
                logger.error(f"❌ 混合向量过滤器初始化失败: {e}")
                self.hybrid_filter = None
        else:
            logger.warning("❌ 混合向量过滤器不可用，尾部过滤将被禁用")
    
    def filter_message(self, content: str, has_media: bool = False) -> Tuple[str, bool, Optional[str], Dict]:
        """
        过滤消息中的尾部内容
        
        Args:
            content: 完整消息内容
            has_media: 是否有媒体文件
            
        Returns:
            (过滤后内容, 是否过滤了尾部, 尾部内容, 分析详情)
        """
        # 如果过滤器不可用，直接返回原内容
        if not self.hybrid_filter:
            return content, False, None, {'reason': '过滤器未初始化'}
        
        # 空内容直接返回
        if not content:
            return content, False, None, {'reason': '内容为空'}
        
        try:
            # 调用混合向量过滤器
            filtered_content, was_filtered, removed_tail, analysis = \
                self.hybrid_filter.filter_message(content, has_media)
            
            if was_filtered:
                logger.info(f"✅ 向量过滤成功: {len(content)} -> {len(filtered_content)} 字符")
                analysis['engine_method'] = 'hybrid_vector'
            else:
                analysis['engine_method'] = 'hybrid_vector_no_filter'
            
            return filtered_content, was_filtered, removed_tail, analysis
            
        except Exception as e:
            # 出错就返回原内容
            logger.error(f"❌ 向量过滤失败: {e}")
            return content, False, None, {'error': str(e), 'engine_method': 'error'}