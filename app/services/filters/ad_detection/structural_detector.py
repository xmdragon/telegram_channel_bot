"""
结构化广告检测器
分析按钮、实体和URL结构来检测广告
"""
import logging
import re
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class StructuralAdDetector:
    """结构化广告检测器"""
    
    def __init__(self, coherence_threshold: float = 0.35, url_threshold: float = 0.8):
        self.coherence_threshold = coherence_threshold
        self.url_threshold = url_threshold
    
    async def detect(self, content: str, buttons: List[Dict], entities: List[Dict], 
                    message: Any = None, ai_detector=None) -> Dict[str, Any]:
        """结构化广告检测（按钮和实体分析）"""
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'suspicious_buttons': [],
            'suspicious_entities': [],
            'method': '结构化检测'
        }
        
        confidence_scores = []
        
        # 检查按钮
        if buttons and content and ai_detector:
            button_analysis = self._analyze_buttons_semantics(content, buttons, ai_detector)
            if button_analysis['suspicious']:
                result['suspicious_buttons'] = button_analysis['buttons']
                confidence_scores.append(button_analysis['confidence'])
                
        # 检查实体链接
        if entities and content and ai_detector:
            entity_analysis = self._analyze_entities_semantics(content, entities, ai_detector)
            if entity_analysis['suspicious']:
                result['suspicious_entities'] = entity_analysis['entities']
                confidence_scores.append(entity_analysis['confidence'])
        
        # 检查URL模式
        url_analysis = self._analyze_suspicious_urls(buttons, entities)
        if url_analysis['suspicious']:
            confidence_scores.append(url_analysis['confidence'])
            result['suspicious_urls'] = url_analysis['urls']
        
        if confidence_scores:
            result['is_ad'] = True
            result['confidence'] = max(confidence_scores)
            
        return result
    
    def _analyze_buttons_semantics(self, content: str, buttons: List[Dict], ai_detector) -> Dict[str, Any]:
        """分析按钮语义相关性"""
        if not ai_detector or not ai_detector.is_available() or not content or not buttons:
            return {'suspicious': False, 'confidence': 0.0, 'buttons': []}
        
        try:
            # 提取按钮文本
            button_texts = [btn.get('text', '') for btn in buttons if btn.get('text')]
            if not button_texts:
                return {'suspicious': False, 'confidence': 0.0, 'buttons': []}
            
            # 检查语义相关性
            coherence = ai_detector.check_semantic_coherence(content, button_texts)
            
            # 低相关性表示可能是广告
            if coherence < self.coherence_threshold:
                return {
                    'suspicious': True,
                    'confidence': 1.0 - coherence,
                    'buttons': buttons,
                    'coherence_score': coherence
                }
            
        except Exception as e:
            logger.debug(f"分析按钮语义时出错: {e}")
        
        return {'suspicious': False, 'confidence': 0.0, 'buttons': []}
    
    def _analyze_entities_semantics(self, content: str, entities: List[Dict], ai_detector) -> Dict[str, Any]:
        """分析实体语义相关性"""
        if not ai_detector or not ai_detector.is_available() or not content or not entities:
            return {'suspicious': False, 'confidence': 0.0, 'entities': []}
        
        suspicious_entities = []
        max_confidence = 0.0
        
        try:
            for entity in entities:
                if entity.get('url') and entity.get('text'):
                    entity_text = entity['text']
                    # 检查链接文本与正文的相关性
                    coherence = ai_detector.check_semantic_coherence(content, [entity_text])
                    
                    if coherence < 0.4:  # 更严格的阈值
                        suspicious_entities.append({
                            **entity,
                            'coherence_score': coherence
                        })
                        max_confidence = max(max_confidence, 1.0 - coherence)
                        
        except Exception as e:
            logger.debug(f"分析实体语义时出错: {e}")
        
        return {
            'suspicious': len(suspicious_entities) > 0,
            'confidence': max_confidence,
            'entities': suspicious_entities
        }
    
    def _analyze_suspicious_urls(self, buttons: List[Dict], entities: List[Dict]) -> Dict[str, Any]:
        """分析可疑URL"""
        suspicious_urls = []
        
        # 检查按钮URL
        for button in buttons:
            url = button.get('url', '')
            if url and self._is_suspicious_url(url):
                suspicious_urls.append({'source': 'button', 'url': url, 'button': button})
        
        # 检查实体URL  
        for entity in entities:
            url = entity.get('url', '')
            if url and self._is_suspicious_url(url):
                suspicious_urls.append({'source': 'entity', 'url': url, 'entity': entity})
        
        return {
            'suspicious': len(suspicious_urls) > 0,
            'confidence': self.url_threshold if suspicious_urls else 0.0,
            'urls': suspicious_urls
        }
    
    def _is_suspicious_url(self, url: str) -> bool:
        """检查URL是否可疑"""
        if not url:
            return False
        
        url_lower = url.lower()
        
        # 短链接服务
        short_url_patterns = [
            r'bit\.ly', r'tinyurl\.com', r'goo\.gl', r'ow\.ly',
            r't\.co', r'short\.link', r'tiny\.cc'
        ]
        
        for pattern in short_url_patterns:
            if re.search(pattern, url_lower):
                return True
        
        # Telegram邀请链接
        if 't.me/+' in url or 't.me/joinchat/' in url:
            return True
        
        # 非Telegram域名的HTTP链接
        if re.match(r'https?://(?!(?:t\.me|telegram\.me|telegra\.ph))', url_lower):
            return True
            
        return False