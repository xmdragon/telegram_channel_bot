"""
按钮分析器
检测Telegram消息中的可疑按钮
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class ButtonAnalyzer:
    """按钮分析器"""
    
    def __init__(self):
        pass
    
    def analyze_buttons(self, text: str, buttons: List[Dict]) -> Dict:
        """分析按钮是否为广告"""
        result = {
            'has_ad': False,
            'confidence': 0.0,
            'suspicious_buttons': []
        }
        
        if not buttons:
            return result
        
        suspicious_buttons = []
        
        for button in buttons:
            button_text = button.get('text', '')
            button_url = button.get('url', '')
            
            # 检查是否为可疑按钮
            if self._is_suspicious_button(button_text, button_url):
                suspicious_buttons.append(button)
        
        if suspicious_buttons:
            result['has_ad'] = True
            result['confidence'] = min(0.9, len(suspicious_buttons) * 0.3)
            result['suspicious_buttons'] = suspicious_buttons
        
        return result
    
    def _is_suspicious_button(self, text: str, url: str) -> bool:
        """检查按钮是否可疑"""
        if not text and not url:
            return False
        
        # 可疑按钮文本
        suspicious_texts = [
            '点击查看', '立即查看', '加入群组', '联系我们',
            '订阅频道', '投稿爆料', '商务合作', '更多详情'
        ]
        
        for suspicious in suspicious_texts:
            if suspicious in text:
                return True
        
        # 检查URL
        if url and self._is_suspicious_url(url):
            return True
        
        return False
    
    def _is_suspicious_url(self, url: str) -> bool:
        """检查URL是否可疑"""
        if not url:
            return False
        
        # Telegram邀请链接
        if 't.me/+' in url or 't.me/joinchat/' in url:
            return True
        
        # 非Telegram域名的HTTP链接
        import re
        if re.match(r'https?://(?!(?:t\.me|telegram\.me|telegra\.ph))', url.lower()):
            return True
            
        return False
    
    def extract_button_data(self, message) -> List[Dict]:
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