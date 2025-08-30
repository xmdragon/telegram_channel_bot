"""
Markdown链接过滤器
从 content_filter.py 迁移 remove_all_markdown_links 逻辑

Author: Claude
Created: 2025-08-15
"""

import re
import time
import logging
import json
import os
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
        
        # 从配置文件加载关键词
        self._load_filter_rules()
        
        # Markdown链接正则
        self.markdown_pattern = re.compile(r'\[([^\]]*)\]\(([^\)]+)\)')
        
        # emoji+广告词+链接模式（动态构建）
        self._build_emoji_ad_pattern()
        
        # 统计信息
        self.stats = {
            'total_links_processed': 0,
            'links_completely_removed': 0,
            'links_text_preserved': 0,
            'telegram_links_removed': 0,
            'non_telegram_links_processed': 0
        }
    
    def _load_filter_rules(self):
        """从配置文件加载过滤规则"""
        config_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
            'data', 'config', 'markdown_filter_rules.json'
        )
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
                    self.promo_keywords = rules.get('promo_keywords', [])
                    self.gambling_keywords = rules.get('gambling_keywords', [])
                    self.guide_words = rules.get('guide_words', [])
                    logger.info(f"加载了{len(self.promo_keywords)}个推广关键词，{len(self.gambling_keywords)}个赌博关键词")
            else:
                logger.warning("配置文件不存在，使用空关键词列表")
                self.promo_keywords = []
                self.gambling_keywords = []
                self.guide_words = []
        except Exception as e:
            logger.error(f"加载过滤规则失败: {e}")
            self.promo_keywords = []
            self.gambling_keywords = []
            self.guide_words = []
    
    def _build_emoji_ad_pattern(self):
        """构建emoji+广告词+链接匹配模式"""
        if self.gambling_keywords:
            pattern = (
                r'[\U0001F300-\U0001F9FF\s]{2,}\s*\[([^\]]*(?:' + 
                '|'.join(re.escape(kw) for kw in self.gambling_keywords) + 
                r')[^\]]*)\]\([^\)]+\)'
            )
            self.emoji_ad_pattern = re.compile(pattern, re.IGNORECASE)
        else:
            # 如果没有关键词，创建一个永不匹配的模式
            self.emoji_ad_pattern = re.compile(r'(?!.*)', re.IGNORECASE)
    
    def _filter_by_entities(self, content: str, context: FilterContext) -> tuple[str, int]:
        """优先使用entities检测并过滤推广链接"""
        try:
            # 从context中获取message entities
            entities = context.get_metadata('entities')
            if not entities:
                return content, 0
            
            # 寻找url和text_link类型的实体
            promo_entities = []
            for entity in entities:
                entity_type = entity.get('type')
                if entity_type in ['url', 'text_link']:
                    # 提取实体文本
                    offset = entity.get('offset', 0) 
                    length = entity.get('length', 0)
                    entity_text = content[offset:offset + length] if offset + length <= len(content) else ''
                    entity_url = entity.get('url', '') if entity_type == 'text_link' else entity_text
                    
                    # 检查是否为推广链接
                    if self._is_promo_entity(entity_text, entity_url):
                        promo_entities.append({
                            'offset': offset,
                            'length': length,
                            'text': entity_text,
                            'url': entity_url,
                            'type': entity_type
                        })
            
            if not promo_entities:
                return content, 0
            
            # 按偏移量倒序排序，从后往前删除以避免位置偏移问题
            promo_entities.sort(key=lambda x: x['offset'], reverse=True)
            
            filtered_content = content
            for entity in promo_entities:
                # 删除推广链接实体
                start = entity['offset']
                end = start + entity['length']
                filtered_content = filtered_content[:start] + filtered_content[end:]
                logger.debug(f"删除推广链接实体: {entity['text'][:30]}... -> {entity['url'][:50]}...")
            
            # 清理多余空行
            filtered_content = re.sub(r'\n{3,}', '\n\n', filtered_content).strip()
            
            return filtered_content, len(promo_entities)
            
        except Exception as e:
            logger.error(f"entities过滤失败: {e}")
            return content, 0
    
    def _is_promo_entity(self, entity_text: str, entity_url: str) -> bool:
        """检查实体是否为推广内容"""
        # 1. 检查URL是否指向推广域名
        if entity_url:
            if any(domain in entity_url.lower() for domain in ['t.me', 'telegram']):
                return True
        
        # 2. 检查文本是否包含推广关键词
        if entity_text:
            text_lower = entity_text.lower()
            for keyword in self.promo_keywords:
                if keyword in text_lower:
                    return True
            for keyword in self.gambling_keywords:
                if keyword in text_lower:
                    return True
        
        return False
    
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
            # 优先使用entities检测推广链接
            entities_filtered_content, entities_removed = self._filter_by_entities(content, context)
            if entities_removed > 0:
                # 如果entities过滤有结果，使用entities过滤后的内容
                logger.info(f"通过entities检测过滤了{entities_removed}个推广链接")
                processing_time = (time.time() - start_time) * 1000
                return FilterResult(
                    filtered_content=entities_filtered_content,
                    passed=True,
                    processing_time_ms=processing_time,
                    reason=f"通过entities检测过滤了{entities_removed}个推广链接",
                    confidence=1.0,
                    details={'entities_filtered': entities_removed},
                    modifications=[f"通过entities移除{entities_removed}个推广链接"]
                )
            
            # 如果entities检测无结果，回退到markdown正则检测
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
                processed_line = self._process_line_with_links(line)
                
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
                    'filtered_length': len(result_content)
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
    
    
    def _process_line_with_links(self, line: str) -> str:
        """处理包含链接的行"""
        original_line = line
        
        # 1. 首先检查是否为emoji+广告词+链接模式，如果是则整行删除
        if self._is_emoji_gambling_pattern(line):
            logger.info(f"检测到emoji+赌博广告模式，删除整行: {line[:50]}...")
            return ''  # 整行删除
        
        def replace_link(match):
            link_text = match.group(1)  # [文字]部分
            link_url = match.group(2)   # (链接)部分
            
            # 判断是否应该完全移除
            should_remove_completely = False
            removal_reason = ""
            
            # 删除频道相关检查 - 过滤与来源频道无关
            
            # 2. 检查是否包含推广关键词
            if link_text:
                for keyword in self.promo_keywords:
                    if keyword in link_text.lower():
                        should_remove_completely = True
                        removal_reason = f"推广关键词 '{keyword}': {link_text}"
                        logger.debug(f"检测到推广关键词 '{keyword}': {link_text}")
                        break
            
            # 3. 检查是否包含赌博关键词
            if link_text:
                for keyword in self.gambling_keywords:
                    if keyword in link_text:
                        should_remove_completely = True
                        removal_reason = f"赌博关键词 '{keyword}': {link_text}"
                        logger.debug(f"检测到赌博关键词 '{keyword}': {link_text}")
                        break
            
            # 4. 检查是否是纯emoji或符号
            if link_text and re.match(r'^[^\w\u4e00-\u9fa5]+$', link_text):
                should_remove_completely = True
                removal_reason = f"纯符号链接: {link_text}"
                logger.debug(f"检测到纯符号链接: {link_text}")
            
            # 5. 检查链接是否指向t.me（高概率推广）
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
    
    def _is_emoji_gambling_pattern(self, line: str) -> bool:
        """检测是否为emoji+赌博广告模式"""
        # 检查是否匹配emoji+广告词+链接模式
        if self.emoji_ad_pattern.search(line):
            return True
        
        # 检查连续emoji开头 + 包含赌博关键词 + 包含链接
        emoji_start = re.match(r'^[\U0001F300-\U0001F9FF\s]{2,}', line)
        if emoji_start:
            has_gambling_keyword = any(keyword in line for keyword in self.gambling_keywords)
            has_markdown_link = self.markdown_pattern.search(line)
            
            if has_gambling_keyword and has_markdown_link:
                logger.debug(f"检测到emoji+赌博关键词+链接组合: {line[:50]}...")
                return True
        
        return False
    
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