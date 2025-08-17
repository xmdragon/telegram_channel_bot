"""
推广实体检测器
基于消息实体分析检测推广内容
"""
import logging
import re
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class PromotionalEntityDetector:
    """推广实体检测器"""
    
    def __init__(self):
        pass
    
    async def detect(self, content: str, entities: List[Dict]) -> Dict[str, Any]:
        """推广实体模式检测（基于实体分析）"""
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'entity_density': 0.0,
            'formatting_ratio': 0.0,
            'promotional_patterns': [],
            'method': '推广实体检测'
        }
        
        if not entities or not content:
            return result
        
        text_length = len(content)
        total_entities = len(entities)
        
        # 1. 计算实体密度
        entity_density = (total_entities * 100) / text_length
        result['entity_density'] = entity_density
        
        # 2. 统计格式化实体
        formatting_entities = 0
        for entity in entities:
            entity_type = entity.get('type', '')
            if entity_type in ['MessageEntityBold', 'MessageEntityItalic', 
                              'MessageEntityCode', 'MessageEntityPre',
                              'MessageEntityStrikethrough', 'MessageEntityUnderline']:
                formatting_entities += 1
        
        formatting_ratio = formatting_entities / total_entities if total_entities > 0 else 0
        result['formatting_ratio'] = formatting_ratio
        
        # 3. 检测"本频道推荐"标记
        channel_promo_detected = self._detect_channel_promotion_marker(content)
        if channel_promo_detected:
            result['promotional_patterns'].append('channel_promotion_marker')
        
        # 4. 检测代码块推广内容
        code_block_promo = self._detect_promotional_code_blocks(content, entities)
        if code_block_promo:
            result['promotional_patterns'].append('code_block_promotion')
        
        # 5. 检测实体组合模式
        entity_patterns = self._detect_entity_combination_patterns(entities)
        if entity_patterns:
            result['promotional_patterns'].extend(entity_patterns)
        
        # 综合判定
        confidence_scores = []
        
        # 实体密度过高
        if entity_density > 8.0:
            confidence_scores.append(min(0.8, entity_density / 15.0))
        
        # 格式化实体比例过高
        if formatting_ratio > 0.6 and total_entities > 5:
            confidence_scores.append(min(0.7, formatting_ratio))
        
        # 检测到推广模式
        if result['promotional_patterns']:
            confidence_scores.append(0.85)
        
        if confidence_scores:
            result['is_ad'] = True
            result['confidence'] = max(confidence_scores)
            
        return result
    
    def _detect_channel_promotion_marker(self, text: str) -> bool:
        """检测"本频道推荐"标记"""
        channel_promo_patterns = [
            r'[😆🎉🔥⭐✨]*\s*本频道推荐\s*[😆🎉🔥⭐✨]*',
            r'[🐾🎯💰🏆⚡]*\s*本频道推荐\s*[🐾🎯💰🏆⚡]*',
            r'\*+\s*本频道推荐\s*\*+',
            r'#+\s*本频道推荐\s*#+',
        ]
        
        for pattern in channel_promo_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _detect_promotional_code_blocks(self, text: str, entities: List[Dict]) -> bool:
        """检测代码块实体中的推广内容"""
        # 查找代码块实体
        code_block_entities = [
            entity for entity in entities 
            if entity.get('type') == 'MessageEntityPre'
        ]
        
        if not code_block_entities:
            return False
        
        # 推广关键词
        promotional_keywords = [
            '华硕科技', '币盘', 'EX', '交易所', '包网',
            '银河国际', '专属回馈', '现已上线',
            '订阅频道', '投稿爆料', '联系', '@yefan11',
            '坚若磐石', '全天在线', '迎咨询'
        ]
        
        # 检查每个代码块的内容
        for entity in code_block_entities:
            offset = entity.get('offset', 0)
            length = entity.get('length', 0)
            
            if offset + length <= len(text):
                code_content = text[offset:offset + length]
                
                promo_keyword_count = sum(1 for keyword in promotional_keywords if keyword in code_content)
                
                # 如果代码块包含多个推广关键词，判定为推广内容
                if promo_keyword_count >= 2:
                    return True
        
        return False
    
    def _detect_entity_combination_patterns(self, entities: List[Dict]) -> List[str]:
        """检测实体组合模式"""
        patterns = []
        
        if len(entities) < 3:
            return patterns
        
        # 按偏移量排序实体
        sorted_entities = sorted(entities, key=lambda x: x.get('offset', 0))
        entity_types = [entity.get('type', '') for entity in sorted_entities]
        
        # 模式1：连续的Bold实体（装饰性格式化）
        consecutive_bold_count = 0
        max_consecutive_bold = 0
        for entity_type in entity_types:
            if entity_type == 'MessageEntityBold':
                consecutive_bold_count += 1
                max_consecutive_bold = max(max_consecutive_bold, consecutive_bold_count)
            else:
                consecutive_bold_count = 0
        
        if max_consecutive_bold >= 3:
            patterns.append('consecutive_bold_formatting')
        
        # 模式2：Pre + 多个URL的组合
        has_pre = 'MessageEntityPre' in entity_types
        url_count = entity_types.count('MessageEntityUrl') + entity_types.count('MessageEntityTextUrl')
        
        if has_pre and url_count >= 2:
            patterns.append('code_block_with_multiple_urls')
        
        # 模式3：实体类型多样性异常
        unique_types = set(entity_types)
        if len(unique_types) >= 5 and len(entities) <= 15:
            patterns.append('diverse_entity_types')
        
        return patterns