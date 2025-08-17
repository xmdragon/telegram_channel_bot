"""
广告内容分析模块
基于文字和二维码内容识别广告特征
"""
import logging
import re
from typing import List, Dict, Tuple, Any

logger = logging.getLogger(__name__)


class AdAnalyzer:
    """广告内容分析器"""
    
    def __init__(self):
        # 广告相关的模式匹配
        self.ad_patterns = [
            # 联系方式模式
            r'(?:微信|WeChat|wechat|WX|wx)[\s:：]*[A-Za-z0-9_-]+',
            r'(?:QQ|qq)[\s:：]*[0-9]{5,}',
            r'(?:电话|手机|Tel|tel|电話|手機)[\s:：]*[0-9\-\+\(\)\s]{7,}',
            r'[0-9]{3,4}[-\s][0-9]{7,8}',  # 电话号码格式
            r'1[3-9][0-9]{9}',  # 中国手机号
            
            # URL模式（非Telegram）
            r'(?:http[s]?://|www\.)[^\s]+',
            r'[a-zA-Z0-9.-]+\.(?:com|cn|net|org|info|biz|co|me|io|tv)[^\s]*',
            
            # 商业模式
            r'(?:营业时间|營業時間|营业中|營業中)',
            r'(?:店铺|店鋪|门店|門店|商店|店面)[\s]*(?:地址|位置)',
            r'(?:优惠|優惠|折扣|打折|特价|特價|促销|促銷)',
            r'(?:接单|接單|下单|下單|订购|訂購|咨询|諮詢)',
            
            # 赌博相关
            r'(?:博彩|体育|足球|篮球|彩票|棋牌|娱乐城|赌场|casino)',
            r'(?:USDT|usdt|泰达币|虚拟币|充值|提款|出款)',
            r'(?:返水|首充|注册就送|日出千万)',
            
            # 金融投资
            r'(?:投资|投資|理财|理財|炒股|股票|基金)',
            r'(?:贷款|貸款|借钱|借錢|放贷|放貸)',
            r'(?:利率|年化|收益|盈利|赚钱|賺錢)',
        ]
        
        # 赌博视觉特征指标
        self.gambling_visual_indicators = [
            "检测到密集文字区域",
            "包含醒目红色文字", 
            "包含醒目黄色文字",
            "包含大量绿色元素",
            "检测到多个圆形元素",
            "高风险广告图像特征组合"
        ]
    
    def analyze_ad_content(self, texts: List[str], qr_codes: List[Dict], 
                          combined_text: str) -> Tuple[bool, float, List[str]]:
        """
        分析图片内容中的广告特征
        
        Args:
            texts: 提取的文字列表
            qr_codes: 二维码信息列表
            combined_text: 合并的文字内容
            
        Returns:
            (是否包含广告, 广告分数, 广告指标列表)
        """
        ad_score = 0.0
        ad_indicators = []
        
        # 1. 检查文字中的广告模式
        text_score, text_indicators = self._analyze_text_patterns(combined_text)
        ad_score += text_score
        ad_indicators.extend(text_indicators)
        
        # 2. 检查视觉特征指标
        visual_score, visual_indicators = self._analyze_visual_features(texts)
        ad_score += visual_score
        ad_indicators.extend(visual_indicators)
        
        # 3. 检查二维码内容
        qr_score, qr_indicators = self._analyze_qr_content(qr_codes)
        ad_score += qr_score
        ad_indicators.extend(qr_indicators)
        
        # 4. 应用特殊权重规则
        ad_score, final_indicators = self._apply_weighting_rules(
            ad_score, ad_indicators, combined_text
        )
        
        # 标准化分数到0-100并判定是否为广告
        ad_score = min(ad_score, 100)
        has_ad = ad_score >= 30  # 30分以上认为是广告
        
        return has_ad, ad_score, final_indicators
    
    def _analyze_text_patterns(self, combined_text: str) -> Tuple[float, List[str]]:
        """分析文字中的广告模式"""
        score = 0.0
        indicators = []
        
        for pattern in self.ad_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            if matches:
                score += len(matches) * 10  # 每个匹配加10分
                indicators.extend([f"文字广告模式: {match[:20]}" for match in matches[:3]])
        
        return score, indicators
    
    def _analyze_visual_features(self, texts: List[str]) -> Tuple[float, List[str]]:
        """分析视觉特征指标"""
        score = 0.0
        indicators = []
        
        for text in texts:
            if text in self.gambling_visual_indicators:
                if "高风险" in text:
                    score += 25
                elif "密集文字" in text or "圆形元素" in text:
                    score += 15
                elif "醒目" in text or "大量" in text:
                    score += 10
        
        if score > 0:
            indicators.append(f"赌博视觉特征检测: {score}分")
        
        return score, indicators
    
    def _analyze_qr_content(self, qr_codes: List[Dict]) -> Tuple[float, List[str]]:
        """分析二维码内容"""
        score = 0.0
        indicators = []
        
        for qr in qr_codes:
            qr_data = qr.get('data', '')
            
            # 检查二维码中的URL
            if re.match(r'https?://', qr_data, re.IGNORECASE):
                # 排除Telegram链接
                if not re.search(r'(?:t\.me|telegram\.me|telegra\.ph)', qr_data, re.IGNORECASE):
                    score += 25  # 非Telegram链接加25分
                    indicators.append(f"外部链接二维码: {qr_data[:30]}")
                else:
                    score += 5  # Telegram链接加5分
                    indicators.append(f"Telegram二维码: {qr_data[:30]}")
            
            # 检查二维码中的联系信息
            for pattern in self.ad_patterns[:5]:  # 只检查联系方式相关模式
                if re.search(pattern, qr_data, re.IGNORECASE):
                    score += 15
                    indicators.append(f"联系信息二维码: {qr_data[:30]}")
                    break
        
        return score, indicators
    
    def _apply_weighting_rules(self, score: float, indicators: List[str], 
                             combined_text: str) -> Tuple[float, List[str]]:
        """应用特殊权重规则"""
        final_indicators = indicators.copy()
        
        # 1. 多种广告特征组合权重
        unique_indicator_types = len(set(indicator.split(':')[0] for indicator in indicators))
        if unique_indicator_types >= 2:
            score *= 1.2  # 提高20%
            final_indicators.append("多种广告特征组合")
        
        # 2. 简短文字+广告信息权重
        if len(combined_text) < 50 and score > 10:
            score *= 1.5  # 提高50%
            final_indicators.append("简短文字包含广告信息")
        
        return score, final_indicators
    
    def analyze_for_ads(self, texts: List[str], qr_codes: List[Dict]) -> Dict[str, Any]:
        """
        专门用于广告检测的图片内容分析
        
        Args:
            texts: 文字列表
            qr_codes: 二维码列表
            
        Returns:
            广告分析结果
        """
        combined_text = ' '.join(texts + [qr.get('data', '') for qr in qr_codes])
        has_ad, ad_score, ad_indicators = self.analyze_ad_content(texts, qr_codes, combined_text)
        
        return {
            'is_ad': has_ad,
            'confidence': ad_score / 100.0,
            'score': ad_score,
            'indicators': ad_indicators,
            'text_count': len(texts),
            'qr_count': len(qr_codes),
            'combined_text_length': len(combined_text)
        }
    
    def get_pattern_count(self) -> int:
        """获取广告模式数量"""
        return len(self.ad_patterns)