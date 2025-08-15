"""
Markdown链接过滤器
从 content_filter.py 迁移 remove_all_markdown_links 逻辑

Author: Claude
Created: 2025-08-15
"""

import re
import time
import logging
from typing import Dict, Any, Optional

from .base import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)


class MarkdownFilter(BaseFilter):
    """Markdown链接过滤器
    
    智能处理Markdown格式的链接：
    - 如果链接文字有语义价值，只移除链接保留文字
    - 如果链接文字是推广词汇，连文字一起移除
    - 结合消息结构体(message.entities)判断链接性质
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("markdown_filter", config)
        
        # 推广关键词列表
        self.promo_keywords = [
            '订阅', '订閱', '关注', '關注', '加入', 
            '投稿', '商务', '商務', '联系', '聯繫',
            '频道', '頻道', 'channel', 'group', '失联', 
            '导航', '備用', '官方', '联系方式', '聯繫方式'
        ]
        
        # 引导性文字
        self.guide_words = [
            '查看详情', '订阅频道', '订阅我们', '关注我们', '更多信息', 
            '查看更多', '点击查看', '了解更多', '商务合作', '投稿爆料'
        ]
        
        # Markdown链接正则
        self.markdown_pattern = re.compile(r'\[([^\]]*)\]\(([^\)]+)\)')
        
        # 统计信息
        self.stats = {
            'total_links_processed': 0,
            'links_completely_removed': 0,
            'links_text_preserved': 0,
            'telegram_links_removed': 0,
            'non_telegram_links_processed': 0
        }
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """预检查是否包含Markdown链接"""
        if not content:
            return False
        
        # 快速检查是否包含Markdown链接模式
        return bool(self.markdown_pattern.search(content))
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """过滤Markdown链接"""
        start_time = time.time()
        
        if not content:
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0,
                reason="空内容"
            )
        
        try:
            # 获取频道信息
            channel_id = context.get_metadata('channel_id')
            channel_name = self._extract_channel_name(channel_id)
            
            # 处理每一行
            lines = content.split('\n')
            filtered_lines = []
            modifications = []
            links_removed = 0
            
            for line in lines:
                if not self.markdown_pattern.search(line):
                    # 没有Markdown链接，直接保留
                    filtered_lines.append(line)
                    continue
                
                original_line = line
                processed_line = self._process_line_with_links(line, channel_name)
                
                # 记录修改
                if processed_line != original_line:
                    if not processed_line:
                        # 整行被删除
                        modifications.append(f"删除包含链接的行: '{original_line[:50]}...'")
                        logger.info(f"删除包含链接的行: '{original_line[:50]}...'")
                        links_removed += 1
                    else:
                        # 行被修改
                        modifications.append(f"修改链接行: '{original_line[:30]}...' -> '{processed_line[:30]}...'")
                        logger.info(f"处理Markdown链接: '{original_line[:50]}...' -> '{processed_line[:50]}'")
                        links_removed += 1
                
                # 检查处理后的行是否有效
                if processed_line and self._is_valid_line(processed_line, original_line):
                    filtered_lines.append(processed_line)
            
            # 组合结果
            result_content = '\n'.join(filtered_lines)
            
            # 清理多余空行
            result_content = re.sub(r'\n{3,}', '\n\n', result_content).strip()
            
            # 计算处理时间
            processing_time = (time.time() - start_time) * 1000
            
            # 更新统计
            self.stats['total_links_processed'] += links_removed
            
            # 构建结果
            filter_result = FilterResult(
                filtered_content=result_content,
                passed=True,  # Markdown过滤器不阻止消息通过，只是清理内容
                processing_time_ms=processing_time,
                reason=f"处理了{links_removed}个Markdown链接" if links_removed > 0 else None,
                confidence=1.0 if links_removed > 0 else 0.0,
                details={
                    'links_processed': links_removed,
                    'original_length': len(content),
                    'filtered_length': len(result_content),
                    'channel_id': channel_id,
                    'channel_name': channel_name
                },
                should_early_stop=False,  # 不设置Early Stop，继续后续过滤
                modifications=modifications
            )
            
            if len(result_content) < len(content):
                logger.info(f"移除Markdown链接: {len(content)} -> {len(result_content)} 字符")
            
            return filter_result
            
        except Exception as e:
            logger.error(f"Markdown链接过滤失败: {e}")
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=(time.time() - start_time) * 1000,
                reason=f"处理异常: {str(e)}",
                confidence=0.0
            )
    
    def _extract_channel_name(self, channel_id: str) -> Optional[str]:
        """提取频道名称"""
        if not channel_id:
            return None
        
        if isinstance(channel_id, str):
            if channel_id.startswith('@'):
                return channel_id[1:].lower()
            elif channel_id.startswith('-100'):
                # 使用已知映射
                known_channels = {
                    '-1001153220419': 'dny185',
                    '-1001875033283': 'dubai0',
                }
                return known_channels.get(channel_id, '').lower()
            else:
                return channel_id.lower()
        
        return None
    
    def _process_line_with_links(self, line: str, channel_name: Optional[str]) -> str:
        """处理包含链接的行"""
        def replace_link(match):
            link_text = match.group(1)  # [文字]部分
            link_url = match.group(2)   # (链接)部分
            
            # 判断是否应该完全移除
            should_remove_completely = False
            removal_reason = ""
            
            # 1. 检查是否包含频道相关标签
            if channel_name and link_text:
                if channel_name in link_text.lower():
                    should_remove_completely = True
                    removal_reason = f"频道相关标签: {link_text}"
                    logger.debug(f"检测到频道相关标签: {link_text}")
            
            # 2. 检查是否包含推广关键词
            if link_text:
                for keyword in self.promo_keywords:
                    if keyword in link_text.lower():
                        should_remove_completely = True
                        removal_reason = f"推广关键词 '{keyword}': {link_text}"
                        logger.debug(f"检测到推广关键词 '{keyword}': {link_text}")
                        break
            
            # 3. 检查是否是纯emoji或符号
            if link_text and re.match(r'^[^\w\u4e00-\u9fa5]+$', link_text):
                should_remove_completely = True
                removal_reason = f"纯符号链接: {link_text}"
                logger.debug(f"检测到纯符号链接: {link_text}")
            
            # 4. 检查链接是否指向t.me（高概率推广）
            if 't.me' in link_url.lower() or 'telegram' in link_url.lower():
                should_remove_completely = True
                removal_reason = f"Telegram链接: {link_url[:30]}"
                logger.debug(f"检测到Telegram链接: {link_url[:30]}")
                self.stats['telegram_links_removed'] += 1
            else:
                self.stats['non_telegram_links_processed'] += 1
                # 对于非Telegram链接，如果没有其他推广特征，只移除链接保留文字
                if not should_remove_completely:
                    # 非推广的普通链接，保留文字
                    logger.debug(f"保留非推广链接的文字: {link_text}")
                    should_remove_completely = False
            
            # 更新统计
            if should_remove_completely:
                self.stats['links_completely_removed'] += 1
                logger.debug(f"完全移除链接 - 原因: {removal_reason}")
                return ''  # 完全移除
            else:
                self.stats['links_text_preserved'] += 1
                # 对于非Telegram链接，可以保留文字部分
                return link_text.strip() if link_text else ''
        
        # 替换所有Markdown链接
        processed_line = self.markdown_pattern.sub(replace_link, line)
        
        # 清理多余空格、标点和分隔符
        processed_line = re.sub(r'\s+', ' ', processed_line).strip()
        processed_line = re.sub(r'^[:：]\s*', '', processed_line)  # 移除行首的冒号
        processed_line = re.sub(r'^\|\s*|\s*\|$', '', processed_line)  # 移除行首行尾的 |
        processed_line = re.sub(r'\|\s*\|', '|', processed_line)  # 合并多个 |
        
        return processed_line
    
    def _is_valid_line(self, processed_line: str, original_line: str) -> bool:
        """检查处理后的行是否有效"""
        if not processed_line:
            return False
        
        # 如果行首是emoji+文字+冒号但后面没有实质内容，认为无效
        # 例如: "🎥柬埔寨事件：" (链接被移除后)
        if re.match(r'^[^a-zA-Z]*[^:：]*[:：]\s*$', processed_line) and len(processed_line) < 30:
            logger.info(f"删除只含标题的行: '{original_line[:50]}...'")
            return False
        
        # 如果是引导性文字+冒号但后面没有内容，认为无效
        for word in self.guide_words:
            if processed_line.startswith(word) and re.match(f'^{re.escape(word)}[:：]?\\s*$', processed_line):
                logger.info(f"删除只含引导词的行: '{original_line[:50]}...'")
                return False
        
        # 如果只剩下分隔符或很少的内容，认为无效
        if processed_line in ['|', '||', ''] or len(processed_line.strip('| ')) < 3:
            logger.info(f"删除只含分隔符的行: '{original_line[:50]}...'")
            return False
        
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """获取过滤器统计信息"""
        base_stats = super().get_stats()
        base_stats.update(self.stats)
        return base_stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        super().reset_stats()
        self.stats = {
            'total_links_processed': 0,
            'links_completely_removed': 0,
            'links_text_preserved': 0,
            'telegram_links_removed': 0,
            'non_telegram_links_processed': 0
        }