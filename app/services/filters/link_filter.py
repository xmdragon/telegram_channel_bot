"""
Markdown链接过滤器
专门处理各种Markdown格式链接的识别和移除
"""
import re
import logging
from typing import str

logger = logging.getLogger(__name__)

class LinkFilter:
    """
    Markdown链接过滤器
    职责：专门处理Markdown格式链接的识别、分析和移除
    """
    
    def __init__(self):
        """初始化链接过滤器"""
        # 推广关键词模式
        self.promo_keywords = [
            '订阅', '订閱', '关注', '關注', '加入', 
            '投稿', '商务', '商務', '联系', '聯繫',
            '频道', '頻道', 'channel', 'group', '失联', 
            '导航', '備用', '官方'
        ]
        
        # 引导性文字模式
        self.guide_words = [
            '查看详情', '订阅频道', '订阅我们', '关注我们', '更多信息', 
            '查看更多', '点击查看', '了解更多', '商务合作', '投稿爆料'
        ]
        
        # Markdown链接正则
        self.markdown_pattern = r'\[([^\]]*)\]\(([^\)]+)\)'
    
    def remove_markdown_links(self, content: str, channel_id: str = None) -> str:
        """
        移除Markdown格式链接
        
        Args:
            content: 消息内容
            channel_id: 频道ID（用于判断频道相关标签）
            
        Returns:
            过滤后的内容
        """
        if not content:
            return content
        
        # 获取频道名称（用于判断标签相关性）
        channel_name = self._extract_channel_name(channel_id)
        
        lines = content.split('\n')
        filtered_lines = []
        
        for line in lines:
            processed_line = self._process_line(line, channel_name)
            if processed_line is not None:
                filtered_lines.append(processed_line)
        
        # 组合结果并清理多余空行
        result = '\n'.join(filtered_lines)
        result = re.sub(r'\n{3,}', '\n\n', result).strip()
        
        if len(result) < len(content):
            logger.info(f"移除Markdown链接: {len(content)} -> {len(result)} 字符")
        
        return result
    
    def _extract_channel_name(self, channel_id: str) -> str:
        """提取频道名称"""
        if not channel_id:
            return None
        
        if isinstance(channel_id, str):
            if channel_id.startswith('@'):
                return channel_id[1:].lower()
            elif channel_id.startswith('-100'):
                # 已知频道映射
                known_channels = {
                    '-1001153220419': 'dny185',
                    '-1001875033283': 'dubai0',
                }
                return known_channels.get(channel_id, '').lower()
            else:
                return channel_id.lower()
        
        return None
    
    def _process_line(self, line: str, channel_name: str) -> str:
        """处理单行内容"""
        if not re.search(self.markdown_pattern, line):
            return line
        
        original_line = line
        processed_line = re.sub(self.markdown_pattern, 
                               lambda m: self._replace_link(m, channel_name), 
                               line)
        
        # 清理多余空格和标点
        processed_line = self._clean_line(processed_line)
        
        # 检查是否应该删除整行
        if self._should_remove_line(processed_line, original_line):
            return None
        
        # 记录处理效果
        if processed_line != original_line.strip():
            logger.info(f"处理Markdown链接: '{original_line[:50]}...' -> '{processed_line[:50] if processed_line else '(已删除)'}'")
        
        return processed_line if processed_line else None
    
    def _replace_link(self, match, channel_name: str) -> str:
        """替换单个链接"""
        link_text = match.group(1)  # [文字]部分
        link_url = match.group(2)   # (链接)部分
        
        # 判断是否应该完全移除
        if self._should_remove_link(link_text, link_url, channel_name):
            return ''
        
        # 对于非Telegram链接，保留文字部分
        return link_text.strip() if link_text else ''
    
    def _should_remove_link(self, link_text: str, link_url: str, channel_name: str) -> bool:
        """判断是否应该移除链接"""
        # 1. 检查频道相关标签
        if channel_name and link_text and channel_name in link_text.lower():
            logger.debug(f"检测到频道相关标签: {link_text}")
            return True
        
        # 2. 检查推广关键词
        if link_text:
            for keyword in self.promo_keywords:
                if keyword in link_text.lower():
                    logger.debug(f"检测到推广关键词 '{keyword}': {link_text}")
                    return True
        
        # 3. 检查纯符号链接
        if link_text and re.match(r'^[^\w\u4e00-\u9fa5]+$', link_text):
            logger.debug(f"检测到纯符号链接: {link_text}")
            return True
        
        # 4. 检查Telegram链接
        if 't.me' in link_url.lower() or 'telegram' in link_url.lower():
            logger.debug(f"检测到Telegram链接: {link_url[:30]}")
            return True
        
        return False
    
    def _clean_line(self, line: str) -> str:
        """清理行内容"""
        # 清理多余空格、标点和分隔符
        line = re.sub(r'\s+', ' ', line).strip()
        line = re.sub(r'^[:：]\s*', '', line)  # 移除行首冒号
        line = re.sub(r'^\|\s*|\s*\|$', '', line)  # 移除行首行尾的 |
        line = re.sub(r'\|\s*\|', '|', line)  # 合并多个 |
        
        return line
    
    def _should_remove_line(self, processed_line: str, original_line: str) -> bool:
        """判断是否应该删除整行"""
        # 如果行为空或只包含分隔符
        if not processed_line or processed_line in ['|', '||', ''] or len(processed_line.strip('| ')) < 3:
            logger.info(f"删除只含分隔符的行: '{original_line[:50]}...'")
            return True
        
        # 如果行首是emoji+文字+冒号但后面没有实质内容
        if re.match(r'^[^a-zA-Z]*[^:：]*[:：]\s*$', processed_line) and len(processed_line) < 30:
            logger.info(f"删除只含标题的行: '{original_line[:50]}...'")
            return True
        
        # 如果是引导性文字+冒号但后面没有内容
        for word in self.guide_words:
            if processed_line.startswith(word) and re.match(f'^{re.escape(word)}[:：]?\\s*$', processed_line):
                logger.info(f"删除只含引导词的行: '{original_line[:50]}...'")
                return True
        
        return False

# 创建全局实例
link_filter = LinkFilter()