"""
特征提取器模块
负责从文本中提取多维度特征和结构模式
"""
import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """
    特征提取器 - 从文本中提取多维度特征
    不记忆原始文本，只提取特征
    """
    
    def __init__(self):
        self.promo_keywords = {
            '订阅', '订閱', '关注', '關注', '加入', '投稿', '爆料',
            '商务', '商務', '联系', '聯繫', '频道', '頻道', '客服'
        }
        self.link_patterns = [
            r't\.me/[\w+]+',
            r'@[\w]+',
            r'https?://[\w\./]+',
        ]
    
    def extract_features(self, text: str, position_ratio: float = 1.0) -> Dict[str, float]:
        """
        提取文本特征
        
        Args:
            text: 待分析文本
            position_ratio: 文本在消息中的位置比例（0=开头, 1=结尾）
            
        Returns:
            特征字典
        """
        if not text:
            return {}
        
        lines = text.split('\n')
        text_length = len(text)
        
        features = {
            # 结构特征
            'line_count': len(lines),
            'avg_line_length': sum(len(line) for line in lines) / max(len(lines), 1),
            'empty_line_ratio': sum(1 for line in lines if not line.strip()) / max(len(lines), 1),
            
            # 链接特征
            'has_telegram_link': 1.0 if 't.me/' in text else 0.0,
            'has_username': 1.0 if '@' in text else 0.0,
            'link_count': len(re.findall(r'(?:t\.me/|@|https?://)', text)),
            'link_density': len(re.findall(r'(?:t\.me/|@|https?://)', text)) / max(text_length, 1) * 100,
            
            # 表情符号特征
            'emoji_count': len(re.findall(r'[😀-🙏🌀-🗿🚀-🛿🏀-🏿]', text)),
            'emoji_density': len(re.findall(r'[😀-🙏🌀-🗿🚀-🛿🏀-🏿]', text)) / max(text_length, 1),
            
            # 关键词特征
            'promo_keyword_count': sum(1 for kw in self.promo_keywords if kw in text),
            'promo_keyword_density': sum(1 for kw in self.promo_keywords if kw in text) / max(len(lines), 1),
            
            # 格式特征
            'has_separator': 1.0 if re.search(r'^[-=*#_~—]{3,}$', text, re.MULTILINE) else 0.0,
            'bold_text_ratio': text.count('**') / max(text_length, 1) * 100,
            
            # 位置特征
            'position_ratio': position_ratio,
            'is_at_end': 1.0 if position_ratio > 0.8 else 0.0,
            
            # 语义特征
            'has_call_to_action': 1.0 if any(word in text for word in ['订阅', '关注', '加入', '点击']) else 0.0,
            'has_contact_info': 1.0 if any(word in text for word in ['联系', '投稿', '客服', '商务']) else 0.0,
        }
        
        return features
    
    def extract_structure(self, text: str) -> List[str]:
        """
        提取文本结构模式
        将文本转换为抽象的结构表示
        """
        lines = text.split('\n')
        structure = []
        
        for line in lines:
            line = line.strip()
            
            if not line:
                structure.append('EMPTY')
            elif '@' in line and len(line) < 50:
                structure.append('USERNAME')
            elif 't.me/' in line:
                structure.append('TELEGRAM_LINK')
            elif re.match(r'^https?://', line):
                structure.append('URL')
            elif re.match(r'^[-=*#_~—]{3,}$', line):
                structure.append('SEPARATOR')
            elif re.match(r'^[😀-🙏🌀-🗿🚀-🛿🏀-🏿]{2,}', line):
                structure.append('EMOJI_LINE')
            elif any(kw in line for kw in ['订阅', '关注', '频道']):
                structure.append('SUBSCRIBE_TEXT')
            elif any(kw in line for kw in ['投稿', '爆料', '联系']):
                structure.append('CONTACT_TEXT')
            elif len(line) < 20:
                structure.append('SHORT_TEXT')
            else:
                structure.append('LONG_TEXT')
        
        return structure