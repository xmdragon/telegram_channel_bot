"""
模式匹配广告检测器
使用正则表达式模式匹配检测广告内容
"""
import logging
import re
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class PatternAdDetector:
    """模式匹配广告检测器"""
    
    def __init__(self, pattern_weights: Dict[str, Any] = None):
        self.pattern_weights = pattern_weights or {}
        self._load_pattern_rules()
    
    def _load_pattern_rules(self):
        """加载模式检测规则"""
        # 推广内容特征模式（从content_filter.py整合）
        self.promo_patterns = [
            # === 明确的广告/赞助商标识（最高优先级） ===
            (r'(频道|頻道).*(广告|廣告|赞助|贊助|推广|推廣)', 10),
            (r'(广告|廣告|赞助|贊助|推广|推廣).*(频道|頻道)', 10),
            (r'赞助商|贊助商|sponsor|Sponsor|SPONSOR', 10),
            
            # === 商业信息标识（最高优先级） ===
            (r'(营业时间|營業時間|营业中|營業中|营业状态|營業狀態)', 10),
            (r'(店铺地址|店鋪地址|门店地址|門店地址|地址：)', 10),
            (r'(经营项目|經營項目|主营|主營|业务范围|業務範圍)', 10),
            (r'(优惠|優惠|折扣|打折|特价|特價|促销|促銷)', 9),
            (r'(接单|接單|下单|下單|订购|訂購|咨询|諮詢)', 9),
            (r'(微信[:：]|WeChat[:：])', 9),
            (r'(电话[:：]|電話[:：]|手机[:：]|手機[:：]|联系[:：]|聯繫[:：])', 9),
            
            # === 博彩/赌博相关（最高优先级） ===
            (r'(博彩|体育|足球|篮球|彩票|棋牌|娱乐城|赌场|casino|Casino)', 10),
            (r'(U存U提|USDT|泰达币|虚拟币|提款|出款|充值|下注|投注)', 10),
            (r'(线上|線上).*(博彩|平台|娱乐|娛樂)', 10),
            (r'(无需实名|無需實名|不限.*ip|不限.*IP|绑定.*银行|綁定.*銀行)', 10),
            (r'(大额|大額).*(出款|提款)', 10),
            
            # === 非Telegram的HTTP链接（赌博网站等） ===
            (r'\bhttps?://(?!(?:t\.me|telegram\.me|telegra\.ph))[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=]+', 10),
            
            # === 推广关键词组合 ===
            (r'^[📢📣🔔💬❤️🔗☎️😍✉️📮📬📭📧🇲🇲🔥✅👌].{0,10}(?:订阅|訂閱|投稿|爆料|商务|商務|联系|聯系|失联|导航|對接|对接|园区|吹水|交友)[^\n]{0,20}@[a-zA-Z]', 10),
            (r'^👌(?:订阅|投稿|爆料|海外交友|商务|联系)', 10),
            (r'本频道(?:推荐|推薦)', 10),
            (r'(?:频道|頻道)(?:推荐|推薦|合作)', 10),
            
            # === 表情符号密集+文字+链接的组合 ===
            (r'^[😊😀☕️🧩🎰🎮🎳🎯♟⚡️😘🎁😍❤💰🔥]{2,}.*https?://', 8),
            (r'^[😊😀☕️🧩🎰🎮🎳🎯♟⚡️😘🎁😍❤💰🔥]{3,}[^\n]{0,50}$', 5),
        ]
        
        # 编译正则表达式
        self.compiled_patterns = [(re.compile(pattern, re.IGNORECASE), weight) for pattern, weight in self.promo_patterns]
    
    async def detect(self, content: str) -> Dict[str, Any]:
        """模式匹配广告检测"""
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'matched_patterns': [],
            'total_weight': 0,
            'method': '模式匹配检测'
        }
        
        total_weight = 0
        matched_patterns = []
        
        # 检查所有预定义模式
        for pattern, weight in self.compiled_patterns:
            matches = pattern.findall(content)
            if matches:
                matched_patterns.append({
                    'pattern': pattern.pattern,
                    'weight': weight,
                    'matches': matches
                })
                total_weight += weight
        
        result['matched_patterns'] = matched_patterns
        result['total_weight'] = total_weight
        
        # 根据权重判断
        if total_weight >= 10:  # 高权重模式
            result['is_ad'] = True
            result['confidence'] = min(1.0, total_weight / 15.0)
        elif total_weight >= 5:  # 中等权重
            result['is_ad'] = True
            result['confidence'] = min(0.8, total_weight / 10.0)
            
        return result
    
    def get_pattern_count(self) -> int:
        """获取模式数量"""
        return len(self.compiled_patterns)