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
        
        # 1. 分析按钮广告
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
        
        # 2. 分析隐藏链接
        if components['entities']:
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
        
        # 3. 生成清理后的文本
        if result['has_structural_ad']:
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
                    
                    entities.append(entity_data)
        except Exception as e:
            logger.error(f"提取实体数据失败: {e}")
        
        return entities


# 全局实例
structural_detector = StructuralAdDetector()