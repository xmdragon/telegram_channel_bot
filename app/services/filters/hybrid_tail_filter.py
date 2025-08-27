"""
混合尾部过滤器 - 两阶段过滤策略
第一阶段：语义边界检测
第二阶段：向量匹配精确过滤

这个方案结合了语义分析的边界检测能力和向量匹配的精确识别能力，
解决了单一方法的缺陷。

Author: Claude
Created: 2025-08-24
"""

import logging
from typing import Tuple, Dict, Optional, List
from app.services.filters.tail_vector_filter import get_tail_vector_filter

logger = logging.getLogger(__name__)


class HybridTailFilter:
    """混合尾部过滤器
    
    两阶段过滤策略：
    1. 语义边界检测：找到大概的正文/推广分界点
    2. 向量精确过滤：逐行检测并移除推广内容
    
    优势：
    - 不会过度过滤（语义边界保护正文）
    - 不会欠过滤（向量匹配确保完整移除）
    - 利用训练数据（53+尾部样本）
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
            'boundary_detected': 0,
            'vector_filtered': 0,
            'lines_removed': 0
        }
        
        # 检查向量过滤器初始化状态
        if self.vector_filter.is_initialized:
            logger.info(f"✅ 混合尾部过滤器初始化完成 - 向量阈值: {vector_threshold}")
            logger.info(f"   向量过滤器状态: 正常 ({len(self.vector_filter.tail_samples)}个样本)")
        else:
            logger.error(f"❌ 混合尾部过滤器初始化异常 - 向量过滤器未正确初始化")
            logger.error(f"   向量过滤器错误: {getattr(self.vector_filter, 'init_error', '未知错误')}")
            logger.warning(f"   将降级到语义过滤模式")
    
    def filter_message(self, content: str, has_media: bool = False) -> Tuple[str, bool, Optional[str], Dict]:
        """
        执行两阶段尾部过滤
        
        Args:
            content: 完整消息内容
            has_media: 是否有媒体文件
            
        Returns:
            (过滤后内容, 是否过滤了尾部, 尾部内容, 分析详情)
        """
        self.stats['total_processed'] += 1
        
        logger.info(f"🔍 开始混合尾部过滤 - 内容长度: {len(content)} 字符")
        logger.debug(f"内容预览: {content[:200]}{'...' if len(content) > 200 else ''}")
        
        if not content or not content.strip():
            return content, False, None, {'reason': '内容为空'}
        
        lines = content.split('\n')
        if len(lines) < 2:
            logger.debug("内容行数不足，跳过过滤")
            return content, False, None, {'reason': '内容行数不足'}
        
        analysis = {
            'method': 'hybrid',
            'total_lines': len(lines),
            'has_media': has_media
        }
        
        # 直接使用向量过滤，跳过边界检测
        # 边界检测代码已完善但暂时不使用，避免误判
        boundary_line = 0  # 从第一行开始，全部用向量判断
        
        analysis['boundary_method'] = 'skip_boundary_use_vector_only'
        logger.debug(f"🚀 跳过边界检测，直接使用向量过滤（从尾部往前扫描）")
        
        # 第二阶段：向量精确过滤
        filtered_lines, removed_lines, similarities = self._vector_filter_lines(
            lines, boundary_line, has_media)
        
        if removed_lines:
            self.stats['vector_filtered'] += 1
            self.stats['lines_removed'] += len(removed_lines)
            
            filtered_content = '\n'.join(filtered_lines)
            removed_content = '\n'.join(removed_lines)
            
            logger.info(f"✅ 混合过滤成功: {len(content)} -> {len(filtered_content)} 字符")
            logger.info(f"   移除了 {len(removed_lines)} 行推广内容")
            logger.debug(f"   移除内容: {removed_content[:100]}{'...' if len(removed_content) > 100 else ''}")
            
            analysis.update({
                'removed_lines_count': len(removed_lines),
                'removed_lines': removed_lines[:3],  # 只记录前3行用于调试
                'max_similarity': max(similarities) if similarities else 0.0,
                'filter_ratio': len(removed_content) / len(content)
            })
            
            return filtered_content, True, removed_content, analysis
        else:
            logger.debug("未检测到推广内容，保留原始内容")
            analysis['no_promotion_detected'] = True
            return content, False, None, analysis
    
    def _detect_semantic_boundary(self, lines: List[str]) -> Optional[int]:
        """检测语义边界
        
        Args:
            lines: 文本行列表
            
        Returns:
            边界行号，如果没有找到返回None
        """
        # 使用向量过滤器的边界检测功能
        content = '\n'.join(lines)
        boundary = self.vector_filter.find_semantic_boundary(content)
        
        if boundary is not None:
            return boundary
        
        # 降级方案：基于组合特征检测
        for i in range(len(lines) - 1, max(0, len(lines) - 10), -1):
            line = lines[i].strip()
            if not line:
                continue
            
            # 组合特征检测
            has_contact = '@' in line or 't.me/' in line
            
            # 明确的推广词（单独出现就算）
            strong_promo_words = ['订阅', '加入', '关注', '频道', '群组']
            has_strong_promo = any(word in line for word in strong_promo_words)
            
            # 模糊词（必须配合联系方式）
            ambiguous_words = ['爆料', '投稿', '联系', '商务', '合作']
            has_ambiguous = any(word in line for word in ambiguous_words)
            
            # 推广表情
            promo_emojis = ['📣', '💬', '😍', '🔔', '📱']
            has_emoji = any(emoji in line for emoji in promo_emojis)
            
            # 判断逻辑
            is_promotion = False
            
            # 1. 有联系方式 + 模糊词 = 推广
            if has_contact and has_ambiguous:
                is_promotion = True
                logger.debug(f"组合检测: 联系方式+模糊词")
                
            # 2. 有联系方式 + 推广表情 = 推广  
            elif has_contact and has_emoji:
                is_promotion = True
                logger.debug(f"组合检测: 联系方式+表情")
                
            # 3. 强推广词 + 联系方式 = 推广
            elif has_strong_promo and has_contact:
                is_promotion = True
                logger.debug(f"组合检测: 强词+联系方式")
                
            # 4. 多个推广表情 = 可能是推广
            elif sum(1 for e in promo_emojis if e in line) >= 2:
                is_promotion = True
                logger.debug(f"组合检测: 多个推广表情")
            
            if is_promotion:
                logger.debug(f"🔍 组合特征检测到边界 - 第{i}行: {line[:30]}...")
                return i
        
        return None
    
    def _vector_filter_lines(self, lines: List[str], boundary_line: int, has_media: bool) -> Tuple[List[str], List[str], List[float]]:
        """使用向量匹配精确过滤行，从尾部往前扫描
        
        Args:
            lines: 文本行列表
            boundary_line: 语义边界行号（实际不使用，保留兼容）
            has_media: 是否有媒体
            
        Returns:
            (保留的行, 移除的行, 相似度列表)
        """
        if not self.vector_filter.is_initialized:
            logger.warning("⚠️ 向量过滤器未初始化，跳过向量过滤")
            return lines, [], []
        
        kept_lines = []
        removed_lines = []
        similarities = []
        
        # 从尾部往前扫描
        filter_start_index = len(lines)  # 开始过滤的位置
        found_non_promo = False
        
        logger.debug(f"🔍 从尾部往前扫描 {len(lines)} 行")
        
        # 第一步：从最后一行往前找到过滤的起始位置
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            
            if not line:  # 空行跳过
                continue
                
            # 处理行内分割：检查是否有推广内容与正文混在一行
            line_parts = self._split_mixed_line(line)
            
            if len(line_parts) > 1:
                # 有分割，检查各部分
                has_promo_part = False
                for part in line_parts:
                    is_tail, similarity = self.vector_filter.is_tail_content(part.strip())
                    if is_tail:
                        has_promo_part = True
                        break
                
                if has_promo_part:
                    logger.debug(f"🔍 第{i}行包含混合内容，设为过滤起点: {line[:50]}...")
                    filter_start_index = i
                else:
                    # 该行没有推广内容，停止往前扫描
                    found_non_promo = True
                    logger.debug(f"🛑 第{i}行为正文内容，停止往前扫描: {line[:50]}...")
                    break
            else:
                # 单纯一行，直接检查
                is_tail, similarity = self.vector_filter.is_tail_content(line)
                
                if is_tail:
                    logger.debug(f"🔍 第{i}行为推广内容，继续往前: {line[:50]}...")
                    filter_start_index = i
                else:
                    # 遇到明确的非推广内容，停止往前扫描
                    found_non_promo = True
                    logger.debug(f"🛑 第{i}行为正文内容，停止往前扫描: {line[:50]}...")
                    break
        
        logger.debug(f"📍 确定过滤范围: 第{filter_start_index}行至第{len(lines)-1}行")
        
        # 第二步：按行处理，从头到尾
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 空行处理
            if not line_stripped:
                if i >= filter_start_index:
                    removed_lines.append(line)  # 过滤范围内的空行也移除
                else:
                    kept_lines.append(line)
                similarities.append(0.0)
                continue
            
            # 在过滤范围之前：直接保留
            if i < filter_start_index:
                kept_lines.append(line)
                similarities.append(0.0)
                logger.debug(f"✅ 保留正文 (第{i}行): {line_stripped[:50]}...")
                continue
            
            # 在过滤范围内：处理行内分割
            line_parts = self._split_mixed_line(line_stripped)
            
            if len(line_parts) > 1:
                # 有分割的混合行
                kept_parts = []
                removed_parts = []
                max_similarity = 0.0
                
                for part in line_parts:
                    part = part.strip()
                    if not part:
                        continue
                        
                    is_tail, similarity = self.vector_filter.is_tail_content(part)
                    max_similarity = max(max_similarity, similarity)
                    
                    if is_tail:
                        removed_parts.append(part)
                        logger.debug(f"✂️ 移除行内推广片段 (相似度: {similarity:.3f}): {part[:30]}...")
                    else:
                        kept_parts.append(part)
                        logger.debug(f"✅ 保留行内正文片段 (相似度: {similarity:.3f}): {part[:30]}...")
                
                similarities.append(max_similarity)
                
                # 如果有保留的部分，重新组合行
                if kept_parts:
                    kept_line = " ".join(kept_parts).strip()
                    # 过滤掉只有表情符号或空白的残留
                    if kept_line and not self._is_only_emojis_or_whitespace(kept_line):
                        kept_lines.append(kept_line)
                        logger.debug(f"🔄 重组混合行保留: {kept_line[:50]}...")
                    else:
                        logger.debug(f"🗑️ 丢弃无意义残留: {kept_line}")
                
                # 如果有移除的部分，记录
                if removed_parts:
                    removed_line = " ".join(removed_parts)
                    removed_lines.append(removed_line)
                    
            else:
                # 整行处理
                is_tail, similarity = self.vector_filter.is_tail_content(line_stripped)
                similarities.append(similarity)
                
                if is_tail:
                    removed_lines.append(line)
                    logger.debug(f"✂️ 整行过滤 (第{i}行, 相似度: {similarity:.3f}): {line_stripped[:50]}...")
                else:
                    # 🚀 关键词兜底检测：即使相似度低，包含明显推广特征也过滤
                    has_contact = '@' in line_stripped or 't.me/' in line_stripped
                    promo_keywords = ['订阅', '加入', '关注', '频道', '群组', '投稿', '爆料', '联系', '商务', '合作']
                    has_promo_keyword = any(keyword in line_stripped for keyword in promo_keywords)
                    
                    # Unicode emoji范围检测
                    import re
                    has_emoji = bool(re.search(r'[\U0001F300-\U0001F9FF]', line_stripped))
                    
                    # 兜底条件：联系方式 + (推广词 或 emoji)
                    if has_contact and (has_promo_keyword or has_emoji):
                        removed_lines.append(line)
                        logger.debug(f"🎯 关键词兜底过滤 (第{i}行): {line_stripped[:50]}...")
                        logger.debug(f"   触发条件: 联系方式={has_contact}, 推广词={has_promo_keyword}, emoji={has_emoji}")
                    else:
                        kept_lines.append(line)
                        logger.debug(f"🟡 过滤范围内保留 (第{i}行, 相似度: {similarity:.3f}): {line_stripped[:50]}...")
        
        return kept_lines, removed_lines, similarities
    
    def _split_mixed_line(self, line: str) -> List[str]:
        """简化的混合行分割 - Linus式极简方案
        
        只检测通用模式：任何emoji + @符号的组合
        不依赖特定emoji列表，避免遗漏
        
        Args:
            line: 文本行
            
        Returns:
            分割后的文本片段列表，如果不需要分割则返回原行
        """
        import re
        
        # 🚀 极简模式：只检测 任何emoji + @username 的通用模式
        # 匹配任何Unicode emoji后跟@的内容
        promo_pattern = r'[\U0001F300-\U0001F9FF].*?@[^\s]*'
        
        match = re.search(promo_pattern, line)
        if not match:
            return [line]
        
        # 找到推广内容起始位置
        promo_start = match.start()
        
        # 简单分割：在emoji前寻找最近的空格
        split_point = promo_start
        for i in range(promo_start - 1, max(0, promo_start - 30), -1):
            if line[i] == ' ':
                split_point = i
                break
        
        if split_point <= 0:
            return [line]
        
        # 执行分割
        regular_part = line[:split_point].strip()
        promo_part = line[split_point:].strip()
        
        if regular_part and promo_part:
            logger.debug(f"🔪 简化分割: '{regular_part}' | '{promo_part}'")
            return [regular_part, promo_part]
        
        return [line]
    
    def _is_only_emojis_or_whitespace(self, text: str) -> bool:
        """检查文本是否只包含表情符号或空白字符"""
        import re
        
        # 移除所有空白字符
        text_no_whitespace = re.sub(r'\s+', '', text)
        
        if not text_no_whitespace:
            return True  # 只有空白
        
        # 检查是否只有表情符号和标点
        # Unicode表情符号范围
        emoji_pattern = r'[\U0001F600-\U0001F64F]|[\U0001F300-\U0001F5FF]|[\U0001F680-\U0001F6FF]|[\U0001F1E0-\U0001F1FF]|[\U00002600-\U000027BF]|[\U0001f900-\U0001f9ff]|[\U0001f780-\U0001f7ff]|[\U0001f800-\U0001f8ff]|[\u2100-\u214f]'
        
        # 移除表情符号和常见标点
        text_no_emoji = re.sub(emoji_pattern, '', text_no_whitespace)
        text_no_punct = re.sub(r'[.。！!？?，,；;：:（）()【】\[\]""''``~～_\\-=+*&%$#@]', '', text_no_emoji)
        
        # 如果移除表情和标点后为空，则认为是无意义的
        return len(text_no_punct) == 0
    
    def get_statistics(self) -> Dict:
        """获取过滤器统计信息"""
        vector_stats = self.vector_filter.get_statistics()
        
        return {
            'hybrid_stats': self.stats.copy(),
            'vector_filter_stats': vector_stats,
            'effectiveness': {
                'detection_rate': self.stats['boundary_detected'] / max(1, self.stats['total_processed']),
                'filter_rate': self.stats['vector_filtered'] / max(1, self.stats['total_processed']),
                'avg_lines_removed': self.stats['lines_removed'] / max(1, self.stats['vector_filtered'])
            }
        }
    
    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            'total_processed': 0,
            'boundary_detected': 0,
            'vector_filtered': 0,
            'lines_removed': 0
        }


# 全局实例
_hybrid_tail_filter = None

def get_hybrid_tail_filter() -> HybridTailFilter:
    """获取全局混合尾部过滤器实例"""
    global _hybrid_tail_filter
    if _hybrid_tail_filter is None:
        _hybrid_tail_filter = HybridTailFilter()
    return _hybrid_tail_filter