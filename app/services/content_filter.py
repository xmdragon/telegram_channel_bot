"""
内容过滤服务
"""
import re
from typing import Tuple, List
from app.core.config import db_settings

class ContentFilter:
    """内容过滤器"""
    
    def __init__(self):
        self.ad_keywords = []
        self.replacements = {}
        self._config_loaded = False
    
    async def _load_config(self):
        """加载配置"""
        if not self._config_loaded:
            self.ad_keywords = await db_settings.get_ad_keywords()
            self.replacements = await db_settings.get_channel_replacements()
            self._config_loaded = True
    
    async def filter_message(self, content: str) -> Tuple[bool, str]:
        """
        过滤消息内容
        返回: (是否为广告, 过滤后的内容)
        """
        if not content:
            return False, ""
        
        # 加载配置
        await self._load_config()
        
        # 检测广告
        is_ad = await self.detect_advertisement(content)
        
        # 内容替换
        filtered_content = await self.replace_content(content)
        
        return is_ad, filtered_content
    
    async def detect_advertisement(self, content: str) -> bool:
        """检测是否为广告"""
        content_lower = content.lower()
        
        # 关键词检测
        for keyword in self.ad_keywords:
            if keyword.lower() in content_lower:
                return True
        
        # 正则表达式检测
        ad_patterns = [
            r'微信[：:]\s*\w+',  # 微信号
            r'QQ[：:]\s*\d+',    # QQ号
            r'联系.*\d{11}',     # 手机号
            r'加.*群.*\d+',      # 加群信息
            r'优惠.*\d+.*元',    # 优惠信息
            r'限时.*\d+.*小时',  # 限时信息
        ]
        
        for pattern in ad_patterns:
            if re.search(pattern, content):
                return True
        
        return False
    
    async def replace_content(self, content: str) -> str:
        """替换内容中的频道相关信息"""
        filtered_content = content
        
        # 执行配置的替换规则
        for old_text, new_text in self.replacements.items():
            filtered_content = filtered_content.replace(old_text, new_text)
        
        # 移除底部频道信息
        filtered_content = self.remove_channel_footer(filtered_content)
        
        return filtered_content
    
    def remove_channel_footer(self, content: str) -> str:
        """移除消息底部的频道相关内容"""
        lines = content.split('\n')
        filtered_lines = []
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # 跳过包含频道信息的行
            if any(keyword in line_lower for keyword in [
                '@', 'channel', '频道', 'group', '群组', 
                'subscribe', '订阅', 'join', '加入'
            ]):
                continue
            
            # 跳过链接行
            if line_lower.startswith(('http', 'www', 't.me')):
                continue
                
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines).strip()
    
    def add_custom_filter(self, pattern: str, filter_type: str = "keyword"):
        """添加自定义过滤规则"""
        if filter_type == "keyword":
            self.ad_keywords.append(pattern)
        # 可以扩展其他类型的过滤规则
    
    def get_content_score(self, content: str) -> float:
        """
        计算内容质量分数
        返回0-1之间的分数，1表示高质量内容
        """
        if not content:
            return 0.0
        
        score = 1.0
        
        # 广告内容扣分
        if self.detect_advertisement(content):
            score -= 0.5
        
        # 内容长度评分
        if len(content) < 10:
            score -= 0.2
        elif len(content) > 1000:
            score -= 0.1
        
        # 特殊字符过多扣分
        special_chars = len(re.findall(r'[!@#$%^&*()_+=\[\]{}|;:,.<>?]', content))
        if special_chars > len(content) * 0.1:
            score -= 0.2
        
        return max(0.0, score)