"""
结构化广告检测器
检测Telegram消息结构中的隐藏广告（按钮、实体链接等）
"""
import logging
import re
from typing import List, Dict, Tuple, Optional, Any
from app.services.ad_detector import ad_detector

logger = logging.getLogger(__name__)


class StructuralAdDetector:
    """结构化广告检测器"""
    
    def __init__(self):
        self.ad_detector = ad_detector
        
    async def detect_structural_ads(self, message: Any) -> Dict:
        """
        检测消息结构中的广告
        
        Args:
            message: Telegram消息对象
            
        Returns:
            检测结果字典
        """
        result = {
            'has_structural_ad': False,
            'confidence': 0.0,
            'ad_type': None,
            'suspicious_buttons': [],
            'suspicious_entities': [],
            'clean_text': message.text or '',
            'removed_elements': []
        }
        
        # 提取消息组件
        components = self._extract_message_components(message)
        
        # 1. 新增：推广实体模式检测（优先级最高）
        entity_pattern_result = self._detect_promotional_entity_patterns(message, components)
        if entity_pattern_result['has_ad']:
            result['has_structural_ad'] = True
            result['confidence'] = max(result['confidence'], entity_pattern_result['confidence'])
            result['ad_type'] = entity_pattern_result['ad_type']
            result['suspicious_entities'].extend(entity_pattern_result['suspicious_entities'])
            result['removed_elements'].extend(entity_pattern_result['removed_elements'])
            result['clean_text'] = entity_pattern_result['clean_text']
            logger.info(f"检测到推广实体模式: {entity_pattern_result['ad_type']}")
        
        # 2. 分析按钮广告
        if components['buttons']:
            button_analysis = self._analyze_buttons(
                message.text,
                components['buttons']
            )
            if button_analysis['has_ad']:
                result['has_structural_ad'] = True
                result['confidence'] = max(result['confidence'], button_analysis['confidence'])
                result['suspicious_buttons'] = button_analysis['suspicious_buttons']
                result['removed_elements'].extend([
                    {'type': 'button', 'content': btn} 
                    for btn in button_analysis['suspicious_buttons']
                ])
                if not result['ad_type']:
                    result['ad_type'] = 'button_ads'
        
        # 3. 分析隐藏链接（如果推广模式检测没有完全处理）
        if components['entities'] and not entity_pattern_result['has_ad']:
            entity_analysis = self._analyze_entities(
                message.text,
                components['entities']
            )
            if entity_analysis['has_ad']:
                result['has_structural_ad'] = True
                result['confidence'] = max(result['confidence'], entity_analysis['confidence'])
                result['suspicious_entities'] = entity_analysis['suspicious_entities']
                result['removed_elements'].extend([
                    {'type': 'entity', 'content': ent}
                    for ent in entity_analysis['suspicious_entities']
                ])
                if not result['ad_type']:
                    result['ad_type'] = 'hidden_links'
        
        # 4. 生成清理后的文本（如果还没有被推广模式检测处理）
        if result['has_structural_ad'] and not entity_pattern_result['has_ad']:
            result['clean_text'] = self._clean_text_from_ads(
                message.text,
                result['suspicious_entities']
            )
        
        return result
    
    def _extract_message_components(self, message: Any) -> Dict:
        """提取消息的结构化组件"""
        components = {
            'buttons': [],
            'entities': [],
            'media': None
        }
        
        try:
            # 提取按钮
            if hasattr(message, 'reply_markup') and message.reply_markup:
                if hasattr(message.reply_markup, 'rows'):
                    for row in message.reply_markup.rows:
                        for button in row.buttons:
                            button_info = {
                                'text': getattr(button, 'text', ''),
                                'url': getattr(button, 'url', None),
                                'data': getattr(button, 'data', None)
                            }
                            components['buttons'].append(button_info)
            
            # 提取实体（隐藏链接等）
            if hasattr(message, 'entities') and message.entities:
                for entity in message.entities:
                    entity_info = {
                        'type': entity.__class__.__name__,
                        'offset': getattr(entity, 'offset', 0),
                        'length': getattr(entity, 'length', 0),
                        'url': getattr(entity, 'url', None)
                    }
                    
                    # 提取实体对应的文本
                    if message.text and entity_info['offset'] is not None and entity_info['length']:
                        start = entity_info['offset']
                        end = start + entity_info['length']
                        entity_info['text'] = message.text[start:end]
                    
                    components['entities'].append(entity_info)
            
            # 提取媒体信息
            if hasattr(message, 'media') and message.media:
                components['media'] = {
                    'type': message.media.__class__.__name__,
                    'has_webpage': hasattr(message.media, 'webpage')
                }
        
        except Exception as e:
            logger.error(f"提取消息组件失败: {e}")
        
        return components
    
    def _detect_promotional_entity_patterns(self, message: Any, components: Dict) -> Dict:
        """
        检测推广实体模式 - 基于Telegram消息实体结构
        
        Args:
            message: Telegram消息对象
            components: 提取的消息组件
            
        Returns:
            检测结果字典
        """
        result = {
            'has_ad': False,
            'confidence': 0.0,
            'ad_type': None,
            'suspicious_entities': [],
            'removed_elements': [],
            'clean_text': message.text or ''
        }
        
        if not message.text or not components['entities']:
            return result
        
        text = message.text
        entities = components['entities']
        
        # 1. 检测"本频道推荐"标记
        channel_promo_detected = self._detect_channel_promotion_marker(text)
        
        # 2. 分析实体密度和分布
        entity_analysis = self._analyze_entity_density_and_distribution(text, entities)
        
        # 3. 检测代码块中的推广内容
        code_block_analysis = self._detect_promotional_code_blocks(text, entities)
        
        # 4. 检测实体组合模式
        pattern_analysis = self._detect_entity_combination_patterns(text, entities)
        
        # 综合判定
        confidence_scores = []
        ad_types = []
        
        if channel_promo_detected['detected']:
            confidence_scores.append(0.9)  # 高置信度
            ad_types.append('channel_promotion')
            result['suspicious_entities'].extend(channel_promo_detected.get('entities', []))
        
        if code_block_analysis['has_promotional_content']:
            confidence_scores.append(code_block_analysis['confidence'])
            ad_types.append('code_block_promotion')
            result['suspicious_entities'].extend(code_block_analysis['suspicious_entities'])
        
        if entity_analysis['is_promotional']:
            confidence_scores.append(entity_analysis['confidence'])
            ad_types.append('entity_density_anomaly')
        
        if pattern_analysis['has_promotional_pattern']:
            confidence_scores.append(pattern_analysis['confidence'])
            ad_types.append('promotional_entity_pattern')
            result['suspicious_entities'].extend(pattern_analysis['suspicious_entities'])
        
        # 综合判定结果
        if confidence_scores:
            result['has_ad'] = True
            result['confidence'] = max(confidence_scores)
            result['ad_type'] = ad_types[confidence_scores.index(max(confidence_scores))]
            
            # 基于实体的内容分区和清理
            result['clean_text'] = self._partition_and_clean_content(
                text, entities, result['suspicious_entities'], channel_promo_detected
            )
            
            logger.info(f"推广实体模式检测: {result['ad_type']}, 置信度: {result['confidence']:.2f}")
        
        return result
    
    def _detect_channel_promotion_marker(self, text: str) -> Dict:
        """检测"本频道推荐"标记"""
        result = {'detected': False, 'position': -1, 'entities': []}
        
        # 检测"本频道推荐"模式（支持表情符号包围）
        channel_promo_patterns = [
            r'[😆🎉🔥⭐✨]*\s*本频道推荐\s*[😆🎉🔥⭐✨]*',
            r'[🐾🎯💰🏆⚡]*\s*本频道推荐\s*[🐾🎯💰🏆⚡]*',
            r'\*+\s*本频道推荐\s*\*+',
            r'#+\s*本频道推荐\s*#+',
        ]
        
        for pattern in channel_promo_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['detected'] = True
                result['position'] = match.start()
                logger.debug(f"检测到频道推荐标记: {match.group()}")
                break
        
        return result
    
    def _analyze_entity_density_and_distribution(self, text: str, entities: List[Dict]) -> Dict:
        """分析实体密度和分布"""
        result = {
            'is_promotional': False,
            'confidence': 0.0,
            'entity_density': 0.0,
            'formatting_ratio': 0.0
        }
        
        if not entities or not text:
            return result
        
        text_length = len(text)
        total_entities = len(entities)
        
        # 计算实体密度（每100字符的实体数）
        entity_density = (total_entities * 100) / text_length
        result['entity_density'] = entity_density
        
        # 统计格式化实体（Bold, Italic, Code等）
        formatting_entities = 0
        for entity in entities:
            entity_type = entity.get('type', '')
            if entity_type in ['MessageEntityBold', 'MessageEntityItalic', 
                              'MessageEntityCode', 'MessageEntityPre',
                              'MessageEntityStrikethrough', 'MessageEntityUnderline']:
                formatting_entities += 1
        
        formatting_ratio = formatting_entities / total_entities if total_entities > 0 else 0
        result['formatting_ratio'] = formatting_ratio
        
        # 推广判定逻辑
        # 1. 实体密度过高（每100字符超过8个实体）
        if entity_density > 8.0:
            result['is_promotional'] = True
            result['confidence'] = min(0.8, entity_density / 15.0)
        
        # 2. 格式化实体比例过高（超过60%）
        elif formatting_ratio > 0.6 and total_entities > 5:
            result['is_promotional'] = True
            result['confidence'] = min(0.7, formatting_ratio)
        
        # 3. 中等密度但分布异常（实体集中在后半部分，典型的推广模式）
        elif entity_density > 4.0 and self._is_entity_distribution_suspicious(text, entities):
            result['is_promotional'] = True
            result['confidence'] = 0.6
        
        return result
    
    def _detect_promotional_code_blocks(self, text: str, entities: List[Dict]) -> Dict:
        """检测代码块实体中的推广内容"""
        result = {
            'has_promotional_content': False,
            'confidence': 0.0,
            'suspicious_entities': []
        }
        
        # 查找代码块实体
        code_block_entities = [
            entity for entity in entities 
            if entity.get('type') == 'MessageEntityPre'
        ]
        
        if not code_block_entities:
            return result
        
        # 检查每个代码块的内容
        for entity in code_block_entities:
            offset = entity.get('offset', 0)
            length = entity.get('length', 0)
            
            if offset + length <= len(text):
                code_content = text[offset:offset + length]
                
                # 检测代码块中的推广关键词
                promotional_keywords = [
                    '华硕科技', '币盘', 'EX', '交易所', '包网',
                    '银河国际', '专属回馈', '现已上线',
                    '订阅频道', '投稿爆料', '联系', '@yefan11',
                    '坚若磐石', '全天在线', '迎咨询'
                ]
                
                promo_keyword_count = 0
                for keyword in promotional_keywords:
                    if keyword in code_content:
                        promo_keyword_count += 1
                
                # 如果代码块包含多个推广关键词，判定为推广内容
                if promo_keyword_count >= 2:
                    result['has_promotional_content'] = True
                    result['confidence'] = min(0.9, 0.5 + (promo_keyword_count * 0.1))
                    result['suspicious_entities'].append(entity)
                    logger.info(f"代码块推广内容: 包含{promo_keyword_count}个关键词")
        
        return result
    
    def _detect_entity_combination_patterns(self, text: str, entities: List[Dict]) -> Dict:
        """检测实体组合模式"""
        result = {
            'has_promotional_pattern': False,
            'confidence': 0.0,
            'suspicious_entities': []
        }
        
        if len(entities) < 3:
            return result
        
        # 按偏移量排序实体
        sorted_entities = sorted(entities, key=lambda x: x.get('offset', 0))
        
        # 检测推广模式：Bold + Code/Pre + URL/Mention 的组合
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
            result['has_promotional_pattern'] = True
            result['confidence'] = min(0.8, 0.5 + (max_consecutive_bold * 0.1))
            result['suspicious_entities'] = [
                entity for entity in sorted_entities 
                if entity.get('type') == 'MessageEntityBold'
            ]
        
        # 模式2：Pre + 多个URL的组合
        has_pre = 'MessageEntityPre' in entity_types
        url_count = entity_types.count('MessageEntityUrl') + entity_types.count('MessageEntityTextUrl')
        
        if has_pre and url_count >= 2:
            result['has_promotional_pattern'] = True
            result['confidence'] = max(result['confidence'], 0.75)
            for entity in sorted_entities:
                if entity.get('type') in ['MessageEntityPre', 'MessageEntityUrl', 'MessageEntityTextUrl']:
                    result['suspicious_entities'].append(entity)
        
        # 模式3：实体类型多样性异常（推广消息通常包含多种格式化）
        unique_types = set(entity_types)
        if len(unique_types) >= 5 and len(entities) <= 15:  # 类型多但总数不多，典型推广特征
            result['has_promotional_pattern'] = True
            result['confidence'] = max(result['confidence'], 0.65)
        
        return result
    
    def _is_entity_distribution_suspicious(self, text: str, entities: List[Dict]) -> bool:
        """检测实体分布是否可疑（集中在后半部分）"""
        if len(entities) < 5:
            return False
        
        text_length = len(text)
        second_half_start = text_length // 2
        
        entities_in_second_half = sum(
            1 for entity in entities 
            if entity.get('offset', 0) >= second_half_start
        )
        
        # 如果超过70%的实体在后半部分，认为分布可疑
        return (entities_in_second_half / len(entities)) > 0.7
    
    def _partition_and_clean_content(self, text: str, entities: List[Dict], 
                                   suspicious_entities: List[Dict], 
                                   channel_promo_info: Dict) -> str:
        """基于实体的内容分区和清理"""
        if not text:
            return text
        
        # 如果检测到"本频道推荐"，从该位置开始删除后续内容
        if channel_promo_info['detected']:
            promo_position = channel_promo_info['position']
            # 保留推荐标记之前的内容
            clean_text = text[:promo_position].strip()
            logger.info(f"基于频道推荐标记分区，保留前 {promo_position} 个字符")
            return clean_text
        
        # 否则，移除可疑实体对应的内容
        if suspicious_entities:
            clean_text = text
            # 按偏移量倒序排序，从后往前删除
            sorted_entities = sorted(
                suspicious_entities,
                key=lambda x: x.get('offset', 0),
                reverse=True
            )
            
            for entity in sorted_entities:
                offset = entity.get('offset')
                length = entity.get('length')
                if offset is not None and length and offset + length <= len(clean_text):
                    clean_text = clean_text[:offset] + clean_text[offset + length:]
            
            # 清理多余空白
            clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()
            return clean_text
        
        return text
    
    def _analyze_buttons(self, text: str, buttons: List[Dict]) -> Dict:
        """分析按钮是否为广告"""
        result = {
            'has_ad': False,
            'confidence': 0.0,
            'suspicious_buttons': []
        }
        
        if not buttons:
            return result
        
        # 提取按钮文本
        button_texts = [btn.get('text', '') for btn in buttons if btn.get('text')]
        
        if not button_texts or not text:
            return result
        
        # 使用语义检测器检查相关性
        coherence = self.ad_detector.check_semantic_coherence(text, button_texts)
        
        # 低相关性表示可能是广告
        if coherence < 0.35:  # 阈值可调
            result['has_ad'] = True
            result['confidence'] = 1.0 - coherence
            result['suspicious_buttons'] = buttons
            logger.info(f"检测到可疑广告按钮，语义相关性: {coherence:.3f}")
        
        # 额外检查：URL模式分析
        for button in buttons:
            url = button.get('url', '')
            if url:
                # 检查短链接（常用于追踪）
                if self._is_suspicious_url(url):
                    if button not in result['suspicious_buttons']:
                        result['suspicious_buttons'].append(button)
                        result['has_ad'] = True
                        result['confidence'] = max(result['confidence'], 0.8)
        
        return result
    
    def _analyze_entities(self, text: str, entities: List[Dict]) -> Dict:
        """分析实体链接是否为广告"""
        result = {
            'has_ad': False,
            'confidence': 0.0,
            'suspicious_entities': []
        }
        
        if not entities or not text:
            return result
        
        for entity in entities:
            if entity.get('url'):
                entity_text = entity.get('text', '')
                
                # 检查链接文本与正文的相关性
                if entity_text:
                    coherence = self.ad_detector.check_semantic_coherence(text, [entity_text])
                    
                    if coherence < 0.4:  # 阈值可调
                        result['suspicious_entities'].append(entity)
                        result['has_ad'] = True
                        result['confidence'] = max(result['confidence'], 1.0 - coherence)
                        logger.info(f"检测到可疑隐藏链接: {entity_text[:50]}")
                
                # 检查URL本身
                if self._is_suspicious_url(entity['url']):
                    if entity not in result['suspicious_entities']:
                        result['suspicious_entities'].append(entity)
                        result['has_ad'] = True
                        result['confidence'] = max(result['confidence'], 0.75)
        
        return result
    
    def _is_suspicious_url(self, url: str) -> bool:
        """检查URL是否可疑（使用智能模式匹配而非硬编码）"""
        if not url:
            return False
        
        url_lower = url.lower()
        
        # 短链接服务（常用于追踪和隐藏真实URL）
        short_url_patterns = [
            r'bit\.ly', r'tinyurl\.com', r'goo\.gl', r'ow\.ly',
            r't\.co', r'short\.link', r'tiny\.cc'
        ]
        
        for pattern in short_url_patterns:
            if re.search(pattern, url_lower):
                logger.debug(f"检测到短链接: {url}")
                return True
        
        # Telegram邀请链接（常用于推广群组）
        if 't.me/+' in url or 't.me/joinchat/' in url:
            logger.debug(f"检测到Telegram邀请链接: {url}")
            return True
        
        return False
    
    def _clean_text_from_ads(self, text: str, suspicious_entities: List[Dict]) -> str:
        """从文本中清理广告实体"""
        if not text or not suspicious_entities:
            return text
        
        clean_text = text
        
        # 按偏移量降序排序，从后往前删除，避免偏移量变化
        sorted_entities = sorted(
            suspicious_entities,
            key=lambda x: x.get('offset', 0),
            reverse=True
        )
        
        for entity in sorted_entities:
            offset = entity.get('offset')
            length = entity.get('length')
            
            if offset is not None and length:
                # 删除实体文本
                start = offset
                end = start + length
                
                if 0 <= start < len(clean_text) and end <= len(clean_text):
                    clean_text = clean_text[:start] + clean_text[end:]
        
        # 清理多余的空白
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        return clean_text
    
    def extract_button_data(self, message: Any) -> List[Dict]:
        """提取消息中的按钮数据用于存储"""
        buttons = []
        
        try:
            if hasattr(message, 'reply_markup') and message.reply_markup:
                if hasattr(message.reply_markup, 'rows'):
                    for row_idx, row in enumerate(message.reply_markup.rows):
                        for col_idx, button in enumerate(row.buttons):
                            button_data = {
                                'row': row_idx,
                                'col': col_idx,
                                'text': getattr(button, 'text', ''),
                                'url': getattr(button, 'url', None),
                                'callback_data': getattr(button, 'data', None)
                            }
                            buttons.append(button_data)
        except Exception as e:
            logger.error(f"提取按钮数据失败: {e}")
        
        return buttons
    
    def extract_entity_data(self, message: Any) -> List[Dict]:
        """提取消息中的实体数据用于存储"""
        entities = []
        
        try:
            if hasattr(message, 'entities') and message.entities:
                for entity in message.entities:
                    entity_data = {
                        'type': entity.__class__.__name__,
                        'offset': getattr(entity, 'offset', 0),
                        'length': getattr(entity, 'length', 0),
                        'url': getattr(entity, 'url', None)
                    }
                    
                    # 提取实体文本
                    if message.text and entity_data['offset'] is not None and entity_data['length']:
                        start = entity_data['offset']
                        end = start + entity_data['length']
                        if 0 <= start < len(message.text) and end <= len(message.text):
                            entity_data['text'] = message.text[start:end]
                    
                    # 标记隐藏链接
                    if entity_data['type'] == 'MessageEntityTextUrl' and entity_data['url']:
                        entity_data['is_hidden_link'] = True
                    else:
                        entity_data['is_hidden_link'] = False
                    
                    entities.append(entity_data)
        except Exception as e:
            logger.error(f"提取实体数据失败: {e}")
        
        return entities
    
    def remove_hidden_links(self, message: Any) -> tuple:
        """
        移除消息中的隐藏链接（MessageEntityTextUrl）
        
        Args:
            message: Telegram消息对象
            
        Returns:
            tuple: (处理后的实体列表, 被移除的隐藏链接列表)
        """
        clean_entities = []
        removed_links = []
        
        try:
            if hasattr(message, 'entities') and message.entities:
                for entity in message.entities:
                    # 检查是否为隐藏链接
                    if entity.__class__.__name__ == 'MessageEntityTextUrl':
                        # 记录被移除的链接
                        removed_link_info = {
                            'text': '',
                            'url': getattr(entity, 'url', ''),
                            'offset': getattr(entity, 'offset', 0),
                            'length': getattr(entity, 'length', 0)
                        }
                        
                        # 提取链接文本
                        if message.text and removed_link_info['offset'] is not None and removed_link_info['length']:
                            start = removed_link_info['offset']
                            end = start + removed_link_info['length']
                            if 0 <= start < len(message.text) and end <= len(message.text):
                                removed_link_info['text'] = message.text[start:end]
                        
                        removed_links.append(removed_link_info)
                        logger.info(f"移除隐藏链接: {removed_link_info['text']} -> {removed_link_info['url']}")
                    else:
                        # 保留其他类型的实体（如粗体、斜体等）
                        clean_entities.append(entity)
            
            if removed_links:
                logger.info(f"共移除 {len(removed_links)} 个隐藏链接")
        
        except Exception as e:
            logger.error(f"移除隐藏链接失败: {e}")
            # 出错时返回原始实体
            return (message.entities if hasattr(message, 'entities') else [], [])
        
        return clean_entities, removed_links


# 全局实例
structural_detector = StructuralAdDetector()