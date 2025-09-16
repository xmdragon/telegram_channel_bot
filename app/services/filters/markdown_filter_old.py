"""
Markdown链接过滤器 - 简化版本

Author: Claude ()
Updated: 2025-09-11
"""

import re
import time
import logging
from typing import Dict, Any, Optional

from .base import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)


class MarkdownFilter(BaseFilter):
    """
    Markdown链接过滤器
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("markdown_filter", config)
        
        # 只保留核心的markdown正则
        self.markdown_pattern = re.compile(r'\[([^\]]*)\]\(([^\)]+)\)')
        
        # 简化的统计
        self.stats = {
            'entities_processed': 0,
            'markdown_processed': 0,
            'total_links_removed': 0
        }
    
    def _filter_by_entities(self, content: str, context: FilterContext) -> tuple[str, int]:
        """基于entities删除所有链接实体"""
        try:
            entities = context.get_metadata('entities')
            if not entities:
                return content, 0
            
            # 收集所有链接类型的实体
            link_entities = []
            for entity in entities:
                # 正确处理 Telethon 实体对象
                entity_class_name = entity.__class__.__name__
                if entity_class_name in ['MessageEntityUrl', 'MessageEntityTextUrl'] or hasattr(entity, 'url'):
                    link_entities.append({
                        'offset': entity.offset,
                        'length': entity.length
                    })
            
            if not link_entities:
                return content, 0
            
            # 按偏移量倒序排序，从后往前删除
            link_entities.sort(key=lambda x: x['offset'], reverse=True)
            
            filtered_content = content
            for entity in link_entities:
                start = entity['offset']
                end = start + entity['length']
                filtered_content = filtered_content[:start] + filtered_content[end:]
            
            return filtered_content.strip(), len(link_entities)
            
        except Exception as e:
            logger.error(f"entities过滤失败: {e}")
            logger.debug(f"实体类型: {[entity.__class__.__name__ for entity in entities] if entities else 'None'}")
            return content, 0
    
    def _filter_by_markdown(self, content: str) -> tuple[str, int]:
        """基于markdown格式处理链接 - 完全删除链接"""
        if not self.markdown_pattern.search(content):
            return content, 0
        
        # 计算原始链接数量
        original_links = len(self.markdown_pattern.findall(content))
        
        # 删除所有markdown链接：[文字](链接) -> 空字符串
        filtered_content = self.markdown_pattern.sub('', content)
        
        return filtered_content.strip(), original_links
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """预检查是否包含链接"""
        if not content:
            return False
        
        # 检查entities或markdown格式
        entities = context.get_metadata('entities')
        has_entities = entities and any(e.get('type') in ['url', 'text_link'] for e in entities)
        has_markdown = bool(self.markdown_pattern.search(content))
        
        return has_entities or has_markdown
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """过滤链接 - entities优先，markdown回退"""
        start_time = time.time()
        
        if not content:
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0,
                reason="空内容"
            )
        
        try:
            # 1. 优先使用entities
            entities_filtered, entities_count = self._filter_by_entities(content, context)
            if entities_count > 0:
                self.stats['entities_processed'] += entities_count
                self.stats['total_links_removed'] += entities_count
                
                # 清理多余空行
                result_content = re.sub(r'\n{3,}', '\n\n', entities_filtered).strip()
                
                processing_time = (time.time() - start_time) * 1000
                
                logger.info(f"entities过滤: 移除{entities_count}个链接")
                
                return FilterResult(
                    filtered_content=result_content,
                    passed=True,
                    processing_time_ms=processing_time,
                    reason=f"通过entities移除{entities_count}个链接",
                    confidence=1.0,
                    details={'method': 'entities', 'links_removed': entities_count}
                )
            
            # 2. 回退到markdown格式处理
            markdown_filtered, markdown_count = self._filter_by_markdown(content)
            if markdown_count > 0:
                self.stats['markdown_processed'] += markdown_count
                self.stats['total_links_removed'] += markdown_count
                
                # 清理多余空行
                result_content = re.sub(r'\n{3,}', '\n\n', markdown_filtered).strip()
                
                processing_time = (time.time() - start_time) * 1000
                
                logger.info(f"markdown过滤: 删除{markdown_count}个链接")
                
                return FilterResult(
                    filtered_content=result_content,
                    passed=True,
                    processing_time_ms=processing_time,
                    reason=f"删除{markdown_count}个markdown链接",
                    confidence=0.8,
                    details={'method': 'markdown', 'links_removed': markdown_count}
                )
            
            # 3. 没有链接需要处理
            processing_time = (time.time() - start_time) * 1000
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=processing_time,
                reason="无链接需要处理"
            )
            
        except Exception as e:
            logger.error(f"markdown过滤失败: {e}")
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=(time.time() - start_time) * 1000,
                reason=f"处理异常: {str(e)}"
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取简化的统计信息"""
        base_stats = super().get_stats()
        base_stats.update(self.stats)
        return base_stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        super().reset_stats()
        self.stats = {
            'entities_processed': 0,
            'markdown_processed': 0,
            'total_links_removed': 0
        }