"""
结构化广告检测器 - 重构版本
检测Telegram消息结构中的隐藏广告（按钮、实体链接等）

重构于2025-08-18：模块化架构，遵循500行限制
"""
import logging
import re
from typing import List, Dict, Tuple, Optional, Any

logger = logging.getLogger(__name__)


class StructuralAdDetector:
    """结构化广告检测器 - 重构版本"""
    
    def __init__(self):
        # 延迟导入避免循环依赖
        self.ad_detector = None
        
    def _get_ad_detector(self):
        """获取广告检测器实例"""
        if self.ad_detector is None:
            from app.services.ad_detector import ad_detector
            self.ad_detector = ad_detector
        return self.ad_detector
        
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
        
        # 1. 推广实体模式检测（优先级最高）
        entity_pattern_result = self._detect_promotional_entity_patterns(message, components)
        if entity_pattern_result['has_ad']:
            result.update({
                'has_structural_ad': True,
                'confidence': max(result['confidence'], entity_pattern_result['confidence']),
                'ad_type': entity_pattern_result['ad_type'],
                'clean_text': entity_pattern_result['clean_text']
            })
            result['suspicious_entities'].extend(entity_pattern_result['suspicious_entities'])
            result['removed_elements'].extend(entity_pattern_result['removed_elements'])
            logger.info(f"检测到推广实体模式: {entity_pattern_result['ad_type']}")
        
        # 2. 分析按钮广告
        if components['buttons']:
            button_analysis = self._analyze_buttons(message.text, components['buttons'])
            if button_analysis['has_ad']:
                result.update({
                    'has_structural_ad': True,
                    'confidence': max(result['confidence'], button_analysis['confidence']),
                    'suspicious_buttons': button_analysis['suspicious_buttons']
                })
                result['removed_elements'].extend([
                    {'type': 'button', 'content': btn} 
                    for btn in button_analysis['suspicious_buttons']
                ])
                if not result['ad_type']:
                    result['ad_type'] = 'button_ads'
        
        # 3. 分析隐藏链接
        if components['entities'] and not entity_pattern_result['has_ad']:
            entity_analysis = self._analyze_entities(message.text, components['entities'])
            if entity_analysis['has_ad']:
                result.update({
                    'has_structural_ad': True,
                    'confidence': max(result['confidence'], entity_analysis['confidence']),
                    'suspicious_entities': entity_analysis['suspicious_entities']
                })
                result['removed_elements'].extend([
                    {'type': 'entity', 'content': ent}
                    for ent in entity_analysis['suspicious_entities']
                ])
                if not result['ad_type']:
                    result['ad_type'] = 'hidden_links'
        
        # 4. 生成清理后的文本
        if result['has_structural_ad'] and not entity_pattern_result['has_ad']:
            result['clean_text'] = self._clean_text_from_ads(
                message.text, result['suspicious_entities']
            )
        
        return result
    
    def _extract_message_components(self, message: Any) -> Dict:
        """提取消息的结构化组件"""
        components = {
            'buttons': [],
            'entities': [],
            'media': []
        }
        
        # 提取按钮
        components['buttons'] = self.extract_button_data(message)
        
        # 提取实体
        components['entities'] = self.extract_entity_data(message)
        
        return components
    
    def _detect_promotional_entity_patterns(self, message: Any, components: Dict) -> Dict:
        """检测推广实体模式"""
        result = {
            'has_ad': False,
            'confidence': 0.0,
            'ad_type': None,
            'suspicious_entities': [],
            'removed_elements': [],
            'clean_text': message.text or ''
        }
        
        text = message.text or ''
        entities = components.get('entities', [])
        
        if not text or not entities:
            return result
        
        # 检测"本频道推荐"标记
        channel_promo = self._detect_channel_promotion_marker(text)
        if channel_promo['detected']:
            result.update({
                'has_ad': True,
                'confidence': 0.95,
                'ad_type': 'channel_promotion',
                'clean_text': channel_promo['clean_text']
            })
            result['removed_elements'].append({
                'type': 'promotion_marker',
                'content': '本频道推荐标记'
            })
        
        # 检测实体密度异常
        density_analysis = self._analyze_entity_density_and_distribution(text, entities)
        if density_analysis['is_suspicious']:
            result.update({
                'has_ad': True,
                'confidence': max(result['confidence'], density_analysis['confidence']),
                'ad_type': result['ad_type'] or 'entity_density'
            })
        
        # 检测代码块推广
        code_block_promo = self._detect_promotional_code_blocks(text, entities)
        if code_block_promo['detected']:
            result.update({
                'has_ad': True,
                'confidence': max(result['confidence'], code_block_promo['confidence']),
                'ad_type': result['ad_type'] or 'code_block_promotion'
            })
            result['suspicious_entities'].extend(code_block_promo['entities'])
        
        return result
    
    def _detect_channel_promotion_marker(self, text: str) -> Dict:
        """检测"本频道推荐"标记"""
        result = {'detected': False, 'clean_text': text}
        
        channel_promo_patterns = [
            r'[😆🎉🔥⭐✨]*\s*本频道推荐\s*[😆🎉🔥⭐✨]*',
            r'[🐾🎯💰🏆⚡]*\s*本频道推荐\s*[🐾🎯💰🏆⚡]*',
            r'\*+\s*本频道推荐\s*\*+',
            r'#+\s*本频道推荐\s*#+',
        ]
        
        for pattern in channel_promo_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                result['detected'] = True
                result['clean_text'] = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
                break
        
        return result
    
    def _analyze_entity_density_and_distribution(self, text: str, entities: List[Dict]) -> Dict:
        """分析实体密度和分布"""
        result = {'is_suspicious': False, 'confidence': 0.0}
        
        if len(text) < 50 or len(entities) < 3:
            return result
        
        # 计算实体密度
        entity_density = len(entities) / len(text) * 100
        
        # 统计格式化实体
        formatting_entities = sum(1 for e in entities 
                                 if e.get('type') in ['MessageEntityBold', 'MessageEntityItalic'])
        
        formatting_ratio = formatting_entities / len(entities) if entities else 0
        
        # 判断是否可疑
        if entity_density > 8.0 or (formatting_ratio > 0.6 and len(entities) > 5):
            result['is_suspicious'] = True
            result['confidence'] = min(0.8, entity_density / 15.0 + formatting_ratio * 0.5)
        
        return result
    
    def _detect_promotional_code_blocks(self, text: str, entities: List[Dict]) -> Dict:
        """检测代码块推广内容"""
        result = {'detected': False, 'confidence': 0.0, 'entities': []}
        
        # 查找代码块实体
        code_block_entities = [e for e in entities if e.get('type') == 'MessageEntityPre']
        
        if not code_block_entities:
            return result
        
        promotional_keywords = [
            '华硕科技', '币盘', 'EX', '交易所', '包网',
            '银河国际', '专属回馈', '现已上线',
            '订阅频道', '投稿爆料', '联系', '@yefan11'
        ]
        
        for entity in code_block_entities:
            offset = entity.get('offset', 0)
            length = entity.get('length', 0)
            
            if offset + length <= len(text):
                code_content = text[offset:offset + length]
                promo_count = sum(1 for kw in promotional_keywords if kw in code_content)
                
                if promo_count >= 2:
                    result.update({
                        'detected': True,
                        'confidence': min(0.9, promo_count * 0.3)
                    })
                    result['entities'].append(entity)
        
        return result
    
    def _analyze_buttons(self, text: str, buttons: List[Dict]) -> Dict:
        """分析按钮是否为广告"""
        result = {'has_ad': False, 'confidence': 0.0, 'suspicious_buttons': []}
        
        if not buttons:
            return result
        
        suspicious_buttons = []
        
        for button in buttons:
            button_text = button.get('text', '')
            button_url = button.get('url', '')
            
            # 检查可疑按钮文本
            suspicious_texts = ['点击查看', '立即查看', '加入群组', '联系我们', '订阅频道']
            
            is_suspicious = any(st in button_text for st in suspicious_texts)
            is_suspicious = is_suspicious or self._is_suspicious_url(button_url)
            
            if is_suspicious:
                suspicious_buttons.append(button)
        
        if suspicious_buttons:
            result.update({
                'has_ad': True,
                'confidence': min(0.9, len(suspicious_buttons) * 0.3),
                'suspicious_buttons': suspicious_buttons
            })
        
        return result
    
    def _analyze_entities(self, text: str, entities: List[Dict]) -> Dict:
        """分析实体是否为广告"""
        result = {'has_ad': False, 'confidence': 0.0, 'suspicious_entities': []}
        
        if not entities:
            return result
        
        suspicious_entities = []
        
        for entity in entities:
            if entity.get('url') and self._is_suspicious_url(entity['url']):
                suspicious_entities.append(entity)
        
        if suspicious_entities:
            result.update({
                'has_ad': True,
                'confidence': min(0.8, len(suspicious_entities) * 0.4),
                'suspicious_entities': suspicious_entities
            })
        
        return result
    
    def _is_suspicious_url(self, url: str) -> bool:
        """检查URL是否可疑"""
        if not url:
            return False
        
        url_lower = url.lower()
        
        # Telegram邀请链接
        if 't.me/+' in url or 't.me/joinchat/' in url:
            return True
        
        # 非Telegram域名的HTTP链接
        if re.match(r'https?://(?!(?:t\.me|telegram\.me|telegra\.ph))', url_lower):
            return True
            
        return False
    
    def _clean_text_from_ads(self, text: str, suspicious_entities: List[Dict]) -> str:
        """从文本中清理广告内容"""
        if not text or not suspicious_entities:
            return text
        
        clean_text = text
        
        # 按偏移量倒序处理，避免位置错位
        entities_sorted = sorted(suspicious_entities, key=lambda x: x.get('offset', 0), reverse=True)
        
        for entity in entities_sorted:
            offset = entity.get('offset', 0)
            length = entity.get('length', 0)
            
            if offset + length <= len(clean_text):
                clean_text = clean_text[:offset] + clean_text[offset + length:]
        
        return clean_text.strip()
    
    def extract_button_data(self, message: Any) -> List[Dict]:
        """从消息中提取按钮数据"""
        buttons = []
        
        try:
            if hasattr(message, 'reply_markup') and message.reply_markup:
                if hasattr(message.reply_markup, 'rows'):
                    for row in message.reply_markup.rows:
                        for button in row.buttons:
                            button_data = {
                                'text': getattr(button, 'text', ''),
                                'url': getattr(button, 'url', ''),
                                'type': type(button).__name__
                            }
                            buttons.append(button_data)
        except Exception as e:
            logger.debug(f"提取按钮数据失败: {e}")
        
        return buttons
    
    def extract_entity_data(self, message: Any) -> List[Dict]:
        """从消息中提取实体数据"""
        entities = []
        
        try:
            if hasattr(message, 'entities') and message.entities:
                for entity in message.entities:
                    entity_data = {
                        'type': type(entity).__name__,
                        'offset': getattr(entity, 'offset', 0),
                        'length': getattr(entity, 'length', 0),
                        'url': getattr(entity, 'url', ''),
                        'user_id': getattr(entity, 'user_id', None)
                    }
                    entities.append(entity_data)
        except Exception as e:
            logger.debug(f"提取实体数据失败: {e}")
        
        return entities
    
    def remove_hidden_links(self, message: Any) -> tuple:
        """移除隐藏链接（向后兼容API）"""
        try:
            result = await self.detect_structural_ads(message)
            if result['has_structural_ad']:
                return result['clean_text'], result['removed_elements']
            else:
                return message.text or '', []
        except Exception as e:
            logger.error(f"移除隐藏链接失败: {e}")
            return message.text or '', []


# 创建全局实例
# 懒加载全局实例
_structural_ad_detector_instance = None

def get_structural_ad_detector():
    """获取结构化广告检测器实例（懒加载）"""
    global _structural_ad_detector_instance
    if _structural_ad_detector_instance is None:
        _structural_ad_detector_instance = StructuralAdDetector()
    return _structural_ad_detector_instance

# 兼容性：保持structural_ad_detector属性访问
class StructuralAdDetectorProxy:
    """结构化广告检测器代理，实现懒加载"""
    def __getattr__(self, name):
        return getattr(get_structural_ad_detector(), name)
    
    def __setattr__(self, name, value):
        setattr(get_structural_ad_detector(), name, value)

structural_ad_detector = StructuralAdDetectorProxy()