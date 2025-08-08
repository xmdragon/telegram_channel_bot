"""
内容过滤服务
"""
import re
import logging
from typing import Tuple, List
from sqlalchemy import select
from app.core.config import db_settings
from app.core.database import AdKeyword, AsyncSessionLocal

logger = logging.getLogger(__name__)

class ContentFilter:
    """内容过滤器"""
    
    def __init__(self):
        self.ad_keywords = []
        self.replacements = {}
        self._config_loaded = False
    
    async def _load_config(self):
        """加载配置"""
        if not self._config_loaded:
            # 从数据库加载关键词
            await self._load_keywords_from_db()
            
            # 从系统配置加载其他设置
            self.replacements = await db_settings.get_channel_replacements()
            self.enable_keyword_filter = await db_settings.get_enable_keyword_filter()  
            self.enable_line_filter = await db_settings.get_enable_line_filter()
            self._config_loaded = True
    
    async def _load_keywords_from_db(self):
        """从数据库加载关键词"""
        async with AsyncSessionLocal() as db:
            # 加载文中关键词（检测到则判定为广告）
            text_query = select(AdKeyword).where(
                AdKeyword.keyword_type == "text",
                AdKeyword.is_active == True
            )
            text_result = await db.execute(text_query)
            text_keywords = text_result.scalars().all()
            self.ad_keywords_text = [kw.keyword for kw in text_keywords]
            
            # 加载行过滤关键词（检测到则过滤该行）
            line_query = select(AdKeyword).where(
                AdKeyword.keyword_type == "line",
                AdKeyword.is_active == True
            )
            line_result = await db.execute(line_query)
            line_keywords = line_result.scalars().all()
            self.ad_keywords_line = [kw.keyword for kw in line_keywords]
    
    async def reload_keywords(self):
        """重新加载关键词配置"""
        self._config_loaded = False
        await self._load_config()
    
    async def filter_message(self, content: str) -> Tuple[bool, str, str]:
        """
        过滤消息内容
        返回: (是否为广告, 过滤后的内容, 过滤原因)
        
        过滤原因:
        - "tail_only": 文本完全是尾部推广
        - "ad_filtered": 广告内容被过滤
        - "normal": 正常过滤（只移除了部分尾部）
        - "": 没有过滤
        
        重要：区分尾部过滤和广告过滤
        - 尾部过滤：只是移除频道推广，不影响消息采集
        - 广告过滤：真正的广告内容，需要拒绝
        """
        if not content:
            return False, "", ""
        
        # 加载配置
        await self._load_config()
        
        # 第一步：先进行尾部过滤和内容替换
        filtered_content = await self.replace_content(content)
        
        # 记录是否因为尾部过滤导致内容为空
        is_empty_due_to_tail = (len(content) > 0 and len(filtered_content) == 0)
        
        if is_empty_due_to_tail:
            logger.info(f"📝 文本完全是尾部推广，已过滤（不是广告）")
            # 尾部过滤导致为空，这不是广告，返回False
            return False, filtered_content, "tail_only"
        elif len(filtered_content) < len(content):
            logger.info(f"📝 第一步：尾部过滤完成，原始长度: {len(content)}, 过滤后: {len(filtered_content)}")
            filter_reason = "normal"
        else:
            filter_reason = ""
        
        # 第二步：基于过滤后的内容判断是否为广告
        is_ad = False
        if filtered_content:
            # 对过滤后的内容进行广告检测
            is_ad = await self.detect_advertisement(filtered_content)
            if is_ad:
                logger.info(f"🚫 第二步：检测到广告内容")
                filter_reason = "ad_filtered"
        
        return is_ad, filtered_content, filter_reason
    
    def is_pure_advertisement(self, content: str) -> bool:
        """检测是否为纯广告（无新闻价值）"""
        if not content:
            return False
            
        content_lower = content.lower()
        lines = content.split('\n')
        
        # 纯广告特征计数
        ad_score = 0
        
        # 1. 检查是否包含大量联系方式
        contact_patterns = [
            r'@\w+',  # Telegram用户名
            r'微信[:：]\s*\w+',  # 微信号
            r'[Ww][Xx][:：]\s*\w+',  # WX号
            r'电话[:：]\s*[\d\-]+',  # 电话号码
            r'\d{11}',  # 手机号
            r'[Qq][Qq][:：]\s*\d+',  # QQ号
        ]
        contact_count = 0
        for pattern in contact_patterns:
            matches = re.findall(pattern, content)
            contact_count += len(matches)
        if contact_count >= 3:
            ad_score += 3
        elif contact_count >= 2:
            ad_score += 2
        
        # 2. 检查是否包含大量价格信息
        price_patterns = [
            r'\d+[元块]',  # 价格
            r'[¥￥]\d+',  # 货币符号
            r'\d+[%％]',  # 百分比
            r'[0-9]+折',  # 折扣
        ]
        price_count = sum(len(re.findall(pattern, content)) for pattern in price_patterns)
        if price_count >= 5:
            ad_score += 2
        
        # 3. 检查促销关键词密度
        promo_keywords = [
            '优惠', '特价', '折扣', '免费', '送', '赠送', '活动', '促销',
            '注册', '开户', '充值', '返利', '提现', '彩金', 'VIP', '会员',
            '首充', '首存', '爆', '赢', '奖', '中奖', '福利', '红包',
            '娱乐', '游戏', '平台', '官网', '代理', '佣金', '推广', '合作',
            'usdt', '存款', '取款', '投注', '下注', '博彩', '彩票'
        ]
        promo_count = sum(1 for kw in promo_keywords if kw in content_lower)
        if promo_count >= 5:
            ad_score += 3
        elif promo_count >= 3:
            ad_score += 2
        
        # 4. 检查是否包含营业信息
        business_patterns = [
            r'营业时间',
            r'营业中',
            r'[0-9]+[:：][0-9]+\s*[到至\-]\s*[0-9]+[:：][0-9]+',  # 时间范围
            r'周[一二三四五六日末]',
            r'地址[:：]',
            r'位于',
        ]
        business_count = sum(1 for pattern in business_patterns if re.search(pattern, content))
        if business_count >= 2:
            ad_score += 1
        
        # 5. 检查是否缺少新闻内容（短句子多，缺少完整段落）
        paragraphs = [p for p in content.split('\n\n') if len(p.strip()) > 50]
        if len(paragraphs) == 0:  # 没有超过50字的段落
            ad_score += 2
        
        # 6. 检查是否是菜单格式
        if '套餐' in content or '菜单' in content or '价目表' in content:
            ad_score += 2
        
        # 7. 检查是否包含网站链接
        url_patterns = [
            r'https?://[^\s]+',
            r'www\.[^\s]+',
            r'\w+\.com',
            r't\.me/[^\s]+',
        ]
        url_count = sum(len(re.findall(pattern, content)) for pattern in url_patterns)
        if url_count >= 2:
            ad_score += 2
        
        # 8. 检查特定赌博平台名称
        gambling_platforms = [
            'uu国际', 'no钱包', 'x6.com', '新葡京', '惠旺娱乐', 'u68国际',
            '澳门', '威尼斯', '金沙', '银河', '永利', '美高梅', '太阳城'
        ]
        if any(platform in content_lower for platform in gambling_platforms):
            ad_score += 3
        
        # 判定为纯广告的阈值
        is_pure_ad = ad_score >= 5
        
        if is_pure_ad:
            logger.info(f"🚫 检测到纯广告内容 (得分: {ad_score})")
            logger.info(f"   联系方式: {contact_count}个")
            logger.info(f"   促销关键词: {promo_count}个")
            logger.info(f"   价格信息: {price_count}个")
        
        return is_pure_ad
    
    async def detect_advertisement(self, content: str) -> bool:
        """检测是否为广告"""
        if not self.enable_keyword_filter:
            return False
            
        # 首先检查是否为纯广告
        if self.is_pure_advertisement(content):
            return True
            
        content_lower = content.lower()
        
        # 文中关键词检测（消息内容包含这些关键词时过滤）
        for keyword in self.ad_keywords_text:
            if keyword.lower() in content_lower:
                return True
        
        # 行中关键词检测（消息行包含这些关键词时过滤整行）
        if self.enable_line_filter:
            lines = content.split('\n')
            for line in lines:
                line_lower = line.lower().strip()
                for keyword in self.ad_keywords_line:
                    if keyword.lower() in line_lower:
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
        
        # 如果启用了行过滤，移除包含行中关键词的行
        if self.enable_line_filter:
            lines = filtered_content.split('\n')
            filtered_lines = []
            for line in lines:
                line_lower = line.lower().strip()
                should_keep = True
                
                # 检查是否包含行中关键词
                for keyword in self.ad_keywords_line:
                    if keyword.lower() in line_lower:
                        should_keep = False
                        break
                
                if should_keep:
                    filtered_lines.append(line)
            
            filtered_content = '\n'.join(filtered_lines).strip()
        
        # 不在这里添加频道落款，留到转发时添加
        return filtered_content
    
    def remove_channel_footer(self, content: str) -> str:
        """智能移除消息底部的频道推广内容
        
        处理原则：
        1. 只处理消息尾部，不影响正文内容
        2. 对于短消息（≤5行），检查是否整体都是推广内容
        3. 对于长消息，只检查最后10行
        """
        if not content:
            return content
            
        original_content = content
        lines = content.split('\n')
        
        # 从后往前找到第一个推广相关内容的位置
        promo_start_index = len(lines)
        
        # 定义推广关键词和模式（基于实际截图分析优化）
        promo_keywords = [
            # 核心推广词
            '投稿', '爆料', '订阅', '订閱', '联系', '聯系', '合作', '对接', '對接', '反馈', '反饋', '关注', '關注',
            '频道', '頻道', '群组', '群組', 'channel', 'group', 'subscribe', 'join',
            '客服', '欢迎', '歡迎', '添加', '认准', '認準', '置顶', '置頂', '推荐', '推薦', '转载', '轉載', '来源',
            '更多', '搜索', '私聊', '咨询', '諮詢', '进群', '進群', '转发', '轉發', '分享',
            'vip', 'vx', '微信', 'qq', 'tg', 'telegram', '内推', '內推',
            '独家', '獨家', '资源', '資源', '福利', '优惠', '優惠', '限时', '限時', '免费', '免費', '会员', '會員',
            # 广告赞助相关
            '广告', '廣告', '赞助商', '贊助商', '赞助', '贊助', '娱乐', '娛樂', '首充', '送', '充值', '返利',
            '注册', '註冊', '开户', '開戶', '体验', '體驗', '试玩', '試玩', '彩票', '博彩', '游戏', '遊戲', '平台',
            '代理', '推广', '推廣', '佣金', '奖金', '獎金', '活动', '活動', '优惠券', '優惠券', '红包', '紅包',
            # 群组和社区相关
            '互助群', '交流群', '讨论群', '討論群', '互助组', '互助組', '交流组', '交流組', '讨论组', '討論組',
            '华人群', '華人群', '华人组', '華人組', '同胞群', '老乡群', '老鄉群', '群聊', '群友',
            # 事件频道相关（基于截图新增）
            '事件频道', '事件頻道', '事件群', '新闻频道', '新聞頻道', '曝光频道', '曝光頻道', '爆料频道', '爆料頻道',
            '茶水间', '茶水間', '闯荡记', '闖蕩記', '大事件', '悬赏', '懸賞', '情报站', '情報站',
            # 服务类（基于截图新增）
            '商务曝光', '商務曝光', '商务对接', '商務對接', '投稿澄清', '投稿澄清爆料', '意见反馈', '意見反饋',
            '失联', '失聯', '寻前', '尋前', '查档', '查檔', '开户', '開戶', '海外交友', '全球线上', '全球線上'
        ]
        
        # 定义推广表情符号（基于截图扩充）
        promo_emojis = [
            # 常见推广表情
            '📢', '📣', '✅', '🔔', '⭐️', '👇', '🔥', '💰', '🎁', 
            '🍉', '🔋', '💬', '👆', '⬇️', '🔗', '💎', '🚀', '📎',
            '🎯', '💡', '🛒', '🎊', '🎉', '💯', '🔞', '📝', '📲',
            '💌', '🔴', '🟢', '🔵', '⚡', '🌟', '💫', '🎈', '🎪',
            # 新增（基于截图）
            '👌', '😍', '☎️', '📍', '🏳️', '🏁', '✝️', '🧐', '📡',
            '❤️', '💙', '🍒', '😉', '☺️', '😊', '🤝', '👍', '👏',
            '🔸', '🔹', '▪️', '▫️', '◆', '◇', '➖', '➡️', '⬅️',
            # 警告和提示类
            '⚠️', '🚨', '‼️', '❗', '❓', '❔', '💭', '💡', '🔍',
            # 国旗表情（常用于地区群组推广）
            '🇵🇭', '🇨🇳', '🇺🇸', '🇲🇾', '🇸🇬', '🇹🇭', '🇻🇳', '🇰🇭',
            '🇲🇲', '🇱🇦', '🇮🇩', '🇯🇵', '🇰🇷', '🇭🇰', '🇹🇼', '🇲🇴'
        ]
        
        # 从后往前扫描，找到推广内容开始的位置
        found_strong_promo = False  # 是否发现强推广信号
        
        # -1. 使用正则表达式检测推广模式（基于截图分析优化）
        promo_patterns = [
            # 包围符格式：一XXX一、【XXX】、▼XXX▼、➖XXX➖等（优先级最高）
            r'^[➖—－一▼▪️◆●〓=【]+.*[订訂][阅閱].*[频頻][道].*[➖—－一】▼▪️◆●〓=]+$',  # 特殊格式：➖订阅西港事件频道➖
            r'^[一【▼◆●—－➖〓=]+.*[一】▼◆●—－➖〓=]+$',  # 通用包围符格式
            
            # 订阅/关注类（各种变体）
            r'[订訂][阅閱阅][^。，！？]*[频頻][道]',  # 订阅XX频道
            r'[关關][注註注][^。，！？]*[频頻群][道组組]',  # 关注XX群组
            r'[📣🔔👌💬😍🔗].*[订訂][阅閱]',  # 表情+订阅
            r'[订訂][阅閱].*[新闻新聞|事件|曝光|爆料|茶水间茶水間|闯荡记闖蕩記]',  # 订阅+特定频道名
            
            # 投稿/爆料/商务类
            r'[投][稿搞].*[@:]',  # 投稿爆料
            r'[爆][料].*[@:]',
            r'[商][务務].*[合作|对接對接|曝光].*[@:]',
            r'[澄清|反馈反饋|意见意見].*[投稿|爆料].*[@:]',
            r'[免费免費].*[爆料|投稿].*[@:]',
            
            # Telegram链接和用户名（更全面）
            r'@[a-zA-Z][a-zA-Z0-9_]{2,}',  # @username（降低长度要求）
            r't\.me/[^\s]+',  # t.me链接
            r'https?://t\.me/[^\s]+',  # 完整t.me链接
            r'telegram\.me/[^\s]+',
            
            # 带表情的投稿/商务行（基于截图）
            r'^[📢📣☎️💬😍🔗👌✅🔔⭐️🔥].{0,3}[投稿|爆料|商务商務|对接對接|联系聯系]',
            r'[投稿|爆料|商务商務].*：.*@',
            
            # 服务类推广（基于截图新增）
            r'[查档查檔|开户開戶].*@',  # 查档开户服务
            r'[全球].*[线上線上|线下線下].*@',  # 全球线上线下服务
            r'[海外].*[交友|互助]',  # 海外交友/互助
            r'[失联失聯|寻前尋前].*@',  # 失联寻前
            
            # 频道列表推广（多个频道）
            r'⭐️\[.*\]\(.*t\.me.*\)',  # ⭐️[频道名](链接)
            r'[👍🔞💯📍].{0,5}https?://t\.me',  # 表情+链接
            r'便民服务.*中文包',  # 便民服务中文包
            
            # 分隔线和装饰符
            r'^[-=_—➖▪▫◆◇■□●○•]{3,}$',  # 符号分隔线
            r'^[😉☺️😊😄😃😀🙂]{5,}$',  # 表情分隔线
            r'^"""{3,}|^={5,}',  # 引号或等号分隔
            
            # 组合模式（基于截图常见组合）
            r'[订訂阅閱].*[频頻道].*\n.*[投稿|爆料].*@',  # 订阅+投稿组合
            r'[商务商務].*[合作|对接對接].*\n.*[投稿|爆料]',  # 商务+投稿组合
            
            # 推广/赞助标识（开头检测）
            r'^[🔥🎯💰🎁].*[推广推廣|赞助贊助|广告廣告|合作]',  # 表情开头的推广
            r'^推广推廣|^赞助贊助|^广告廣告|^AD|^ads|^PR',  # 明确的推广标识
            r'本频道推荐|本頻道推薦|点击加入|點擊加入',  # 推荐加入类
            r'利充慢充|首充加赠|首充加贈|充值优惠|充值優惠',  # 赌博推广
        ]
        
        # 特殊情况处理：如果消息很短（少于5行），可能整个文本都是推广内容
        is_short_message = len(lines) <= 5
        
        # 检查最后10行是否匹配推广模式（只在尾部搜索）
        # 对于短消息，检查所有行；对于长消息，只检查最后10行
        search_start = 0 if is_short_message else max(0, len(lines) - 10)
        
        for i in range(len(lines) - 1, search_start - 1, -1):
            line = lines[i].strip()
            if not line:
                continue
            
            # 使用正则表达式匹配
            for pattern in promo_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # 对于短消息，如果匹配到推广模式，可能整个消息都是推广
                    if is_short_message:
                        # 检查是否所有非空行都包含推广特征
                        non_empty_lines = [l for l in lines if l.strip()]
                        promo_line_count = 0
                        for check_line in non_empty_lines:
                            # 检查是否包含推广特征
                            if any(kw in check_line.lower() for kw in ['订阅', '投稿', '爆料', '商务', '@', 't.me']):
                                promo_line_count += 1
                        
                        # 如果超过80%的行都是推广内容，认为整个消息都是推广
                        if promo_line_count >= len(non_empty_lines) * 0.8:
                            promo_start_index = 0
                            found_strong_promo = True
                            logger.info(f"🎯 短消息检测：整个文本都是推广内容")
                            break
                    else:
                        # 长消息：正常处理，只标记尾部
                        promo_start_index = i
                        found_strong_promo = True
                        logger.info(f"🎯 正则匹配到推广内容: '{line[:50]}...' (第{i+1}行，模式: {pattern})")
                        break
            
            if found_strong_promo:
                break
        
        # 0. 检测连续的短行推广模式（只在消息尾部检测）
        # 只检查最后8行，避免误删正文内容
        if len(lines) >= 2:
            # 从后往前检查连续的短行（只在尾部）
            short_line_count = 0
            has_promo_content = False
            tail_start = max(0, len(lines) - 8)  # 只检查最后8行
            
            for i in range(len(lines) - 1, tail_start, -1):
                line = lines[i].strip()
                if not line:
                    continue
                    
                # 判断是否为短行（少于50个字符）
                if len(line) < 50:
                    short_line_count += 1
                    
                    # 检查是否包含推广特征
                    line_lower = line.lower()
                    if (any(kw in line_lower for kw in ['群', '组', 'ps', '大赛', '上分', '互助', '华人']) or
                        any(emoji in line for emoji in ['🇵🇭', '🏁', '**']) or
                        '##' in line or '****' in line):
                        has_promo_content = True
                else:
                    # 遇到长行，停止检查
                    break
            
            # 如果在尾部连续有2行以上的短行且包含推广内容
            if short_line_count >= 2 and has_promo_content:
                # 找到这些短行的起始位置（只在尾部范围内）
                for i in range(len(lines) - 1, tail_start, -1):
                    line = lines[i].strip()
                    if line and len(line) < 50:
                        line_lower = line.lower()
                        if any(kw in line_lower for kw in ['群', '组', 'ps', '大赛', '上分', '互助', '华人']):
                            promo_start_index = min(promo_start_index, i)
                            found_strong_promo = True
                
                if found_strong_promo:
                    logger.info(f"🎯 检测到尾部连续短行推广模式，从第{promo_start_index+1}行开始")
                
        # 1. 检测国旗+群组名称模式（只在尾部最后6行检测）
        if not found_strong_promo:
            tail_start = max(0, len(lines) - 6)  # 只检查最后6行
            for i in range(len(lines) - 1, tail_start, -1):
                line = lines[i].strip()
                # 检查是否包含国旗表情
                if any(flag in line for flag in ['🇵🇭', '🇨🇳', '🇺🇸', '🇲🇾', '🇸🇬', '🇹🇭', '🇻🇳', '🇰🇭', '🇲🇲', '🇱🇦', '🇮🇩']):
                    # 同时包含群组相关关键词
                    if any(kw in line for kw in ['群', '组', 'group', 'chat', '互助', '交流', '讨论']):
                        promo_start_index = i
                        found_strong_promo = True
                        logger.info(f"🎯 检测到尾部国旗+群组推广: '{line}' (第{i+1}行)")
                        break
        
        # 1. 检测典型的三行尾部模式（订阅+群组+投稿）
        if len(lines) >= 3 and not found_strong_promo:
            last_3_lines = '\n'.join(lines[-3:]).lower()
            # 检查是否包含典型的尾部关键词组合
            if ('订阅' in last_3_lines or 'subscribe' in last_3_lines) and \
               ('投稿' in last_3_lines or '爆料' in last_3_lines or '联系' in last_3_lines) and \
               ('@' in last_3_lines):
                # 向前查找起始位置（可能有空行分隔）
                for i in range(len(lines) - 1, max(0, len(lines) - 6), -1):
                    line = lines[i].strip()
                    if line and not any(char in line for char in ['@', '🇲🇲', '🔥', '✅', '🔔', '📣', '☎️', '😍', '✉️', '🔗', '订阅', '投稿']):
                        # 找到非推广内容，下一行开始是推广
                        promo_start_index = i + 1
                        found_strong_promo = True
                        logger.info(f"🎯 检测到典型三行尾部模式 (第{promo_start_index + 1}行开始)")
                        break
        
        # 2. 检查是否有单独的hashtag行作为频道标识（只在尾部检测）
        if not found_strong_promo:
            tail_start = max(0, len(lines) - 5)  # 只检查最后5行
            for i in range(len(lines) - 1, tail_start, -1):
                line = lines[i].strip()
                # 如果是单独的hashtag行（如 #国际爆料）
                if line.startswith('#') and len(line) < 50:
                    # 检查是否包含推广相关词汇
                    if any(kw in line.lower() for kw in ['爆料', '频道', '订阅', '关注', '资讯', '新闻', '独家', '投稿', '曝光', '事件']):
                        promo_start_index = i
                        found_strong_promo = True
                        logger.info(f"🎯 检测到尾部频道hashtag: '{line}' (第{i+1}行)")
                        break
                        
                # 检查特殊格式文本（##开头或包含****）
                if ('##' in line and len(line) < 50) or ('****' in line and len(line) < 50):
                    # 这种格式在尾部通常是推广内容
                    promo_start_index = min(promo_start_index, i)
                    found_strong_promo = True
                    logger.info(f"🎯 检测到尾部特殊格式推广: '{line}' (第{i+1}行)")
                    break
        
        # 检查是否有明显的广告分界线或广告内容（只在后半部分检测）
        ad_section_markers = [
            '频道广告赞助商', '广告赞助商', '赞助商', '频道广告', '广告位',
            '商业推广', '合作推广', '友情推广', '广告合作', '赞助内容'
        ]
        
        # 只检查消息的后半部分，避免误删正文
        mid_point = len(lines) // 2
        for i in range(mid_point, len(lines)):
            line_clean = lines[i].strip()
            
            # 检查是否包含广告分界线标识
            if any(marker in line_clean for marker in ad_section_markers):
                promo_start_index = i
                found_strong_promo = True
                logger.info(f"🎯 检测到广告分界线: '{line_clean}' (第{i+1}行)")
                break
            
            # 检查emoji+链接模式（这是最常见的广告特征）
            emoji_link_pattern = r'[😊😎☕🧩🎰🎮🎳🎯♟⚡😘🎁😍❤️💰🔥📢🎈💎💫🌟]+.*\[.*\]\(.*\)'
            if re.search(emoji_link_pattern, line_clean):
                promo_start_index = i
                found_strong_promo = True
                logger.info(f"🎯 检测到emoji+链接广告: '{line_clean[:50]}...' (第{i+1}行)")
                break
            
            # 检查多个emoji开头的行（广告特征）
            emoji_count = len(re.findall(r'[😊😎☕🧩🎰🎮🎳🎯♟⚡😘🎁😍💰🔥📢🎈💎💫🌟]', line_clean[:20]))
            if emoji_count >= 3 and ('http' in line_clean or '[' in line_clean):
                promo_start_index = i
                found_strong_promo = True
                logger.info(f"🎯 检测到emoji广告行: '{line_clean[:50]}...' (第{i+1}行)")
                break
            
            # 检查赌博平台关键词
            gambling_keywords = [
                'X9体育', '体育综合', '负盈利', '全网独家', '返水', 
                '实力U盘', '优惠多多', '大额无忧', '首发', '注册就送', '神秘彩金',
                '玩游戏上', 'UC', '首存', '赠送', '日出千万', 'USDT', '巨款无忧',
                '不限IP', 'UU国际', 'NO钱包', 'X6.com', '新葡京', '惠旺娱乐', 'U68国际',
                # PS游戏相关
                'PS大赛', 'PS 大赛', '持续上分', '上分', 'PS大赛子', '赛子'
            ]
            if any(kw in line_clean for kw in gambling_keywords):
                promo_start_index = i
                found_strong_promo = True
                logger.info(f"🎯 检测到赌博广告: '{line_clean[:50]}...' (第{i+1}行)")
                break
        
        # 主要推广内容扫描（只扫描尾部最后10行）
        tail_scan_start = max(0, len(lines) - 10)
        for i in range(len(lines) - 1, tail_scan_start, -1):
            line = lines[i].strip()
            if not line:  # 跳过空行
                continue
                
            line_lower = line.lower()
            is_promo = False
            confidence = 0
            
            # 检查各种推广模式（按置信度评分）
            # 1. 包含 @ 用户名或频道 (高置信度)
            if '@' in line and not line.startswith('#'):  # 排除hashtag
                is_promo = True
                confidence = 10
            
            # 2. 包含 t.me 链接 (高置信度)
            elif 't.me/' in line_lower or 'telegram.me/' in line_lower:
                is_promo = True
                confidence = 10
            
            # 3. 包含 http/https 链接 (中等置信度)
            elif 'http://' in line_lower or 'https://' in line_lower:
                is_promo = True
                confidence = 7
            
            # 4. Markdown链接格式 (高置信度)
            elif re.search(r'\[.*\]\(https?://.*\)', line):
                is_promo = True
                confidence = 9
            
            # 5. 包含"欢迎"+"投稿/爆料"组合 (高置信度)
            elif ('欢迎' in line_lower and any(kw in line_lower for kw in ['投稿', '爆料', '点击'])):
                is_promo = True
                confidence = 8
            
            # 6. 包含推广关键词 + 特殊符号 (中等置信度)
            elif any(kw in line_lower for kw in ['投稿', '订阅', '爆料', '联系', '关注', '频道']) and \
                 any(char in line for char in ['：', ':', '👉', '📢', '✅', '@', '▶', '▷', '►', '✈️', '🔔']):
                is_promo = True
                confidence = 7
            
            # 6. 包含多个推广关键词 (中等置信度)
            elif sum(1 for kw in promo_keywords if kw in line_lower) >= 2:
                is_promo = True
                confidence = 6
            
            # 如果发现高置信度推广内容
            if is_promo and confidence >= 7:
                found_strong_promo = True
                # 从这里开始向前回溯，找到推广区域的开始
                for j in range(i, -1, -1):  # 修正：应该向前查找，不是向后
                    back_line = lines[j].strip()
                    if not back_line:
                        continue
                    back_line_lower = back_line.lower()
                    
                    # 检查是否是推广相关内容
                    is_promo_related = False
                    
                    # 重复字符模式 (如 "=====", "-----") 
                    if re.search(r'(.)\1{4,}', back_line) and len(back_line.strip()) < 50:
                        is_promo_related = True
                    
                    # 包含推广emoji
                    elif any(emoji in back_line for emoji in promo_emojis):
                        is_promo_related = True
                    
                    # 包含推广关键词
                    elif any(kw in back_line_lower for kw in promo_keywords):
                        is_promo_related = True
                        
                    # 短行且在推广区域
                    elif len(back_line) < 30 and j > i:
                        is_promo_related = True
                    
                    
                    # 博彩娱乐内容
                    elif any(word in back_line_lower for word in ['娱乐', '首充', '注册', '开户', '返利', '送']) and \
                         ('**' in back_line or '%' in back_line):
                        is_promo_related = True
                    
                    # 下划线链接文本 (推广链接)
                    elif '_' in back_line and len(back_line.replace('_', '')) < len(back_line) * 0.7:
                        is_promo_related = True
                    
                    # 金币符号广告
                    elif '💰' in back_line and any(word in back_line_lower for word in ['娱乐', '彩票', '博彩', '游戏']):
                        is_promo_related = True
                    
                    # 连续横线分隔符
                    elif re.match(r'^[-─—_]{10,}$', back_line.strip()):
                        is_promo_related = True
                    
                    # 如果是推广相关内容，更新开始位置
                    if is_promo_related:
                        promo_start_index = min(promo_start_index, j)
                    elif j < i:  # 如果不是推广内容且在发现点之前，停止回溯
                        break
                        
                break  # 找到强推广信号后停止扫描
            
            elif is_promo and confidence >= 4:
                # 低置信度推广内容，只在尾部才考虑
                if i > len(lines) - 5:
                    promo_start_index = min(promo_start_index, i)
        
        # 如果没有发现强推广信号，但找到了分隔符（只在尾部检查）
        if not found_strong_promo:
            for i in range(len(lines) - 1, max(0, len(lines) - 6), -1):
                line = lines[i].strip()
                if re.search(r'(.)\1{4,}', line) and len(line.strip()) < 50:
                    # 检查分隔符后是否有推广内容
                    has_promo_after = False
                    for j in range(i + 1, len(lines)):
                        next_line = lines[j].strip()
                        if not next_line:
                            continue
                        next_line_lower = next_line.lower()
                        
                        if (any(emoji in next_line for emoji in promo_emojis) or
                            any(kw in next_line_lower for kw in promo_keywords) or
                            '@' in next_line or 't.me' in next_line_lower):
                            has_promo_after = True
                            break
                    
                    if has_promo_after:
                        promo_start_index = i
                        break
        
        # 保留非推广部分
        if promo_start_index < len(lines):
            # 确保不会删除太多内容
            lines_to_remove = len(lines) - promo_start_index
            
            # 只有满足以下条件之一时才过滤：
            # 1. 推广内容在最后10行内
            # 2. 推广内容少于总行数的40%
            # 3. 推广内容起始位置在总行数的60%之后
            if (lines_to_remove <= 10 or 
                lines_to_remove < len(lines) * 0.4 or 
                promo_start_index > len(lines) * 0.6):
                
                filtered_lines = lines[:promo_start_index]
                # 移除尾部空行和分隔符
                while filtered_lines:
                    last_line = filtered_lines[-1].strip()
                    if not last_line or re.match(r'^[-=_*~`]{3,}$', last_line):
                        filtered_lines.pop()
                    else:
                        break
            else:
                # 推广内容太多，可能是误判，不过滤
                logger.warning(f"⚠️ 检测到的推广内容过多（{lines_to_remove}行），可能是误判，不进行过滤")
                filtered_lines = lines
        else:
            filtered_lines = lines
        
        result = '\n'.join(filtered_lines).strip()
        
        # 记录调试信息
        if len(result) < len(original_content):
            removed_content = original_content[len(result):].strip()
            logger.info(f"🔍 智能去尾部检测:")
            logger.info(f"   原始长度: {len(original_content)} 字符")
            logger.info(f"   过滤后长度: {len(result)} 字符") 
            logger.info(f"   移除内容: {repr(removed_content[:200])}...")
            logger.info(f"   移除行数: {len(lines) - len(filtered_lines)}")
            logger.info(f"   检测位置: 第 {promo_start_index + 1} 行开始")
        else:
            logger.debug("🔍 智能去尾部: 未检测到推广内容")
        
        return result
    
    async def add_channel_signature(self, content: str) -> str:
        """在消息尾部添加频道落款（如果还没有的话）"""
        # 使用配置管理器获取签名
        from app.services.config_manager import config_manager
        signature = await config_manager.get_config("channels.signature", "")
        
        if not signature:
            return content
        
        # 处理换行符，支持 \n 转换为真实换行
        signature = signature.replace('\\n', '\n')
        
        # 检查内容是否已经包含落款
        # 去掉可能的尾部空白后检查
        content_stripped = content.rstrip()
        signature_stripped = signature.strip()
        
        if content_stripped.endswith(signature_stripped):
            # 已经有落款了，直接返回
            return content
        
        # 如果内容不为空且没有以换行结尾，则添加换行
        if content and not content.endswith('\n'):
            content += '\n'
        
        # 添加频道落款
        if signature:
            # 确保落款前有分隔空行
            if content.strip():
                content += '\n' + signature
            else:
                content = signature
        
        return content
    
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