"""
优化的内容过滤器
精准识别并删除推广内容，不依赖位置判断
"""
import re
import logging
import asyncio
import json
from typing import Tuple, List, Set, Any
from app.services.ai_filter import ai_filter
from app.services.config_manager import config_manager
from app.services.message_structure_analyzer import message_structure_analyzer

logger = logging.getLogger(__name__)

class ContentFilter:
    """内容过滤器"""
    
    def __init__(self):
        """初始化过滤器"""
        # AI过滤器实例
        self.ai_filter = ai_filter
        self._compiled_patterns = {}  # 缓存编译后的正则表达式
        self._compiled_protectors = []  # 缓存保护器正则
        
        # 推广内容特征模式
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
            
            # === 带括号的链接（常见推广格式） ===
            (r'\([^\)]*https?://[^\)]+\)', 10),  # (链接)
            
            # === 表情符号密集+文字+链接的组合 ===
            (r'^[😊😀☕️🧩🎰🎮🎳🎯♟⚡️😘🎁😍❤💰🔥]{2,}.*https?://', 8),  # 多个表情开头+链接 - 降低权重
            (r'^[😊😀☕️🧩🎰🎮🎳🎯♟⚡️😘🎁😍❤💰🔥]{3,}[^\n]{0,50}$', 5),  # 纯表情推广行 - 降低权重
            
            # === Telegram用户名和频道（更智能的判断） ===
            # t.me链接需要在推广上下文中才算推广
            (r'^[📢📣🔔💬❤️🔗🔍✉️📮😍👌].{0,10}t\.me/[a-zA-Z][a-zA-Z0-9_]{4,31}', 9),  # 表情+t.me链接
            (r'(?:订阅|关注|加入|失联|备用).{0,10}t\.me/', 9),  # 推广词+t.me链接
            
            # 单独的@用户名不过滤，除非在明显的推广上下文中
            # 暂时不过滤单独的@用户名，避免误判
            
            # === 推广关键词组合（必须带链接或@） ===
            # 订阅、投稿、商务等推广词+@用户名（需要更精确的匹配）
            (r'^[📢📣🔔💬❤️🔗☎️😍✉️📮📬📭📧🇲🇲🔥✅👌].{0,10}(?:订阅|訂閱|投稿|爆料|商务|商務|联系|聯系|失联|导航|對接|对接|园区|吹水|交友)[^\n]{0,20}@[a-zA-Z]', 10),  # 表情+推广词+@
            (r'^[📢📣🔔💬❤️🔗☎️😍✉️📮📬📭📧].{0,5}(?:关注|關注)[^\n]{0,30}(?:中心|平台|频道|頻道)', 10),  # 表情+关注+中心/平台等
            (r'(?:欢迎|歡迎)(?:投稿|爆料|加入|关注)[^\n]{0,5}@', 9),  # 欢迎投稿+@
            (r'(?:失联|失聯)(?:导航|導航)[^\n]{0,5}@', 10),  # 失联导航
            (r'^.{0,5}(?:关注|關注)[^\n]{0,30}(?:悬赏|懸賞|吃瓜|曝光|爆料)', 10),  # 关注+悬赏/吃瓜等
            (r'(?:商务|商務)(?:对接|對接|合作)[^\n]{0,5}@', 10),  # 商务对接
            
            # === 特殊格式：👌开头的推广内容（例：👌订阅频道：@xxx）===
            (r'^👌(?:订阅|投稿|爆料|海外交友|商务|联系)', 10),  # 👌+推广词
            (r'^👌.{0,10}[:：；].{0,5}@', 10),  # 👌xxx：@用户名
            
            # === 频道推广固定格式 ===
            # 更精确的匹配：需要多个推广特征组合
            (r'^[📢📣🔔💬❤️🔗🔍✉️📮😍🇲🇲🔥✅👌].{0,5}(?:订阅|投稿|商务|联系|失联|导航|吹水站|园区|交友).{0,5}(?:频道|channel|@)', 10),  # 表情+推广词+频道/@
            (r'^[📢📣🔔💬❤️🔗🔍✉️📮😍🇲🇲🔥✅👌].{0,5}(?:订阅|投稿|商务|联系|失联|导航|交友)[^\n]{0,10}[@]', 10),  # 表情+推广词+@符号
            
            # === "本频道推荐"等明显推广开头 ===
            (r'本频道(?:推荐|推薦)', 10),  # "本频道推荐"（不限位置）
            (r'(?:频道|頻道)(?:推荐|推薦|合作)', 10),  # "频道推荐"等
            (r'^[😊😀😉🙂😄😃💯🔥❤️💰*]+本频道', 10),  # 表情+本频道
            
            # === 纯表情分隔线 ===
            (r'^[😊😀😉🙂😄😃💯🔥❤️💰]{5,}$', 2),  # 5个以上表情 - 降低权重
            (r'^[-=_—➖▪▫◆◇■□●○•～~]{10,}$', 1),  # 符号分隔线 - 最低权重
            
            # === Markdown链接格式 ===
            # 注意：新闻/曝光类链接会被content_protectors保护，不会被过滤
            (r'\[[^\]]+\]\(https?://[^\)]+\)', 7),  # [文字](链接) - 降低分数，防止误判新闻链接
            (r'\[[订阅訂閱加入关注關注&][^\]]*\]\([^\)]*t\.me[^\)]+\)', 10),  # [订阅xxx](t.me/xxx) - 明确的推广
            (r'[🔍🔔🔗📢]\[[^\]]*\]\(.*t\.me.*\)', 9),  # 推广表情[文字](t.me链接) - 降低分数
            # 新闻类链接特征（不算推广）
            (r'\[[🎥📰📸🎬]\s*(?:曝光|爆料|新闻|头条|热点|视频|图片)[^\]]*\]\(', -5),  # 新闻链接，负分保护
            
            # === 赌博/娱乐推广关键词（带数字或链接更可信） ===
            (r'(?:首充|返水|优惠|注册就送|日出千万)[^\n]*(?:\d+%|\d+U|https?://)', 10),
            (r'(?:体育|娱乐|赌场|博彩)[^\n]*(?:综合|平台|官网)[^\n]*(?:@|https?://)', 10),
            (r'(?:实力U盘|放心赢|大额无忧|巨款无忧)[^\n]*(?:\(|https?://)', 10),
            (r'(?:全网|独家|首发)[^\n]*(?:最高|返水|优惠)[^\n]*\d+', 9),
            (r'USDT[^\n]*(?:千万|巨款|无忧)', 9),
        ]
        
        # 正文内容保护模式（这些内容不应被删除）
        self.content_protectors = [
            # 个人情感表达
            r'妈的|草|恶心|难受|他妈|卑|妈逼|狗日|我操|卧槽',
            r'气死|郁闷|烦死|心疼|可怜',
            
            # 个人叙述
            r'我想|我觉得|我认为|我以为|我就',
            r'这次|上次|下次|结果',
            
            # 俗语成语
            r'常在河边走|哪有不湿鞋',
            
            # 新闻内容
            r'据报道|消息称|记者表示|记者获悉',
            r'警方称|政府表示|官方回应|调查显示',
            r'发生了|发生在|突发事件',  # 更精确的事件匹配
            
            # 曝光/爆料类内容（重要保护）
            r'曝光|爆料|揭露|举报|投诉|检举',
            r'骗子|骗吃骗喝|诈骗|黑店|黑心|无良|垃圾',
            r'此人|这人|该人|这个人|这家伙',
            r'#网友曝光|#曝光|#爆料|#举报|#投诉',
            r'🎥曝光|📰爆料|📸曝光|🎬视频'
            
            # 寻人启事（特殊保护）
            r'失踪|寻找|寻人|联系家人|报警',
            r'身高\d+|体重\d+|年龄\d+|失联',
            
            # 用户投稿标记（重要保护）
            r'^#网友投稿|^#群友投稿|^#读者投稿|^#粉丝投稿',
            r'^#用户分享|^#真实经历|^#亲身经历',
        ]
        
        # 初始化并编译所有正则表达式
        self._compile_patterns()
    
    def _compile_patterns(self):
        """编译所有正则表达式以提高性能"""
        # 编译推广模式
        for pattern, score in self.promo_patterns:
            try:
                self._compiled_patterns[pattern] = (re.compile(pattern, re.MULTILINE | re.IGNORECASE), score)
            except Exception as e:
                logger.error(f"编译正则表达式失败: {pattern[:50]}... - {e}")
        
        # 编译保护器模式
        for pattern in self.content_protectors:
            try:
                self._compiled_protectors.append(re.compile(pattern, re.MULTILINE | re.IGNORECASE))
            except Exception as e:
                logger.error(f"编译保护器正则失败: {pattern[:50]}... - {e}")
    
    def is_promo_line(self, line: str) -> Tuple[bool, int]:
        """
        判断单行是否为推广内容
        
        Returns:
            (是否推广, 置信度分数)
        """
        if not line.strip():
            return False, 0
            
        line_lower = line.lower()
        max_score = 0
        
        # 先检查是否是用户投稿等受保护内容
        # 如果以#网友投稿等开头，直接返回非推广
        if re.match(r'^#(网友|群友|读者|粉丝|用户)投稿', line, re.IGNORECASE):
            return False, 0
        if re.match(r'^#(真实经历|亲身经历|用户分享)', line, re.IGNORECASE):
            return False, 0
            
        # 使用编译后的正则表达式检查推广特征
        for pattern_str, (compiled_pattern, score) in self._compiled_patterns.items():
            if compiled_pattern.search(line):
                max_score = max(max_score, score)
        
        # 使用编译后的保护器检查保护内容
        has_protected_content = False
        for protector_pattern in self._compiled_protectors:
            if protector_pattern.search(line):
                has_protected_content = True
                # 如果包含保护内容，大幅降低推广分数
                if max_score >= 9:
                    # 高分推广内容如果包含保护词，可能是误判
                    max_score = max(0, max_score - 6)  # 降6分
                else:
                    max_score = max(0, max_score - 5)  # 降5分
                break
        
        # 特殊处理：如果包含曝光/爆料等强保护词，即使有链接也不算推广
        strong_protection_words = r'(曝光|爆料|揭露|举报|骗子|黑店|诈骗)'
        if re.search(strong_protection_words, line, re.IGNORECASE):
            # 除非是明确的推广链接（如"订阅频道"）
            if not re.search(r'(订阅|关注|加入).*(频道|channel|@|t\.me)', line, re.IGNORECASE):
                return False, 0  # 强保护，不算推广
                
        return max_score >= 8, max_score  # 提高阈值从7到8，减少误判
    
    def _smart_rule_filter(self, content: str) -> str:
        """
        智能规则过滤，寻找明确的推广边界
        
        Args:
            content: 原始内容
            
        Returns:
            过滤后的内容
        """
        lines = content.split('\n')
        if len(lines) < 3:
            return content
        
        # 明确的分隔标志
        strong_separators = [
            r'^[-=_—➖]{10,}$',  # 长分隔线
            r'^[📢📣🔔💬❤️🔗]{2,}.*$',  # 多个推广表情
            r'^[-=\*]{3,}\s*$',  # 短分隔线
        ]
        
        # 推广内容的强特征
        strong_promo = [
            r'\[.*\]\(https?://.*\)',  # Markdown链接格式
            r'(?:订阅|關注|投稿|商务|联系).*(?:@|t\.me/)',  # 推广词+链接
            r'https?://(?!(?:t\.me|telegram\.me))',  # 非Telegram链接
            r'^\s*(?:频道|頻道|channel).*(?:@|t\.me/)',  # 频道推广
        ]
        
        # 从后向前查找最明确的分隔点
        best_separator_index = -1
        
        for i in range(len(lines) - 1, max(0, len(lines) - 20), -1):
            line = lines[i].strip()
            
            # 检查是否是强分隔符
            is_strong_separator = any(re.match(p, line) for p in strong_separators)
            
            if is_strong_separator:
                # 验证分隔符后面确实有推广内容
                has_strong_promo = False
                promo_lines = 0
                
                for j in range(i + 1, min(i + 10, len(lines))):
                    if any(re.search(p, lines[j], re.IGNORECASE) for p in strong_promo):
                        has_strong_promo = True
                        promo_lines += 1
                
                # 如果后面有至少2行推广内容，这是一个有效的分隔点
                if has_strong_promo and promo_lines >= 2:
                    best_separator_index = i
                    break
        
        # 如果找到了明确的分隔点，过滤掉分隔符及之后的内容
        if best_separator_index != -1:
            result = '\n'.join(lines[:best_separator_index])
            # 清理尾部空行
            while result.endswith('\n\n'):
                result = result[:-1]
            return result.strip()
        
        return content
    
    def filter_promotional_content(self, content: str, channel_id: str = None) -> str:
        """
        智能过滤推广内容 - 优化版本
        优先使用规则，保护正文内容
        
        Args:
            content: 消息内容
            channel_id: 频道ID（用于AI尾部过滤）
        """
        if not content:
            return content
        
        # 保存原始内容
        original_content = content
        
        # 1. 首先使用智能规则过滤
        rule_filtered = self._smart_rule_filter(content)
        if rule_filtered != content:
            logger.info(f"规则过滤了尾部内容: {len(content)} -> {len(rule_filtered)}")
            content = rule_filtered
        
        # 2. 如果规则没有找到明确的尾部，才使用AI过滤（如果可用）
        if content == original_content and channel_id and self.ai_filter and self.ai_filter.initialized:
            ai_filtered = self.ai_filter.filter_channel_tail(channel_id, content)
            if ai_filtered != content:
                # 保护机制：验证AI过滤的合理性
                if not ai_filtered or len(ai_filtered) < 50:
                    logger.warning(f"AI过滤后内容过短（{len(ai_filtered) if ai_filtered else 0}字符），跳过AI过滤")
                    content = original_content
                elif len(ai_filtered) < len(content) * 0.3:
                    logger.warning(f"AI过滤删除了超过70%的内容，可能误判，跳过AI过滤")
                    content = original_content
                else:
                    logger.info(f"AI过滤了频道 {channel_id} 的尾部内容: {len(content)} -> {len(ai_filtered)}")
                    content = ai_filtered
            
        lines = content.split('\n')
        total_lines = len(lines)
        filtered_lines = []
        
        # 检查最后15行中的推广内容（扩大范围）
        tail_start = max(0, total_lines - 15)
        tail_promo_count = 0
        first_promo_index = total_lines
        
        # 扫描尾部，找到第一个推广行的位置
        for i in range(tail_start, total_lines):
            is_promo, score = self.is_promo_line(lines[i])
            # 特别检查"本频道推荐"等明显的推广开始标志
            if "本频道" in lines[i] and ("推荐" in lines[i] or "推薦" in lines[i]):
                # 找到"本频道推荐"，这是明确的推广开始
                first_promo_index = min(first_promo_index, i)
                tail_promo_count = 10  # 直接设为高值，确保过滤
                break
            elif is_promo and score >= 8:  # 提高阈值到8分
                tail_promo_count += 1
                if first_promo_index == total_lines:
                    first_promo_index = i
                    # 如果推广行前面有分隔符，也包括分隔符
                    if i > 0 and re.match(r'^[-=_—➖▪▫◆◇■□●○•]{3,}$', lines[i-1].strip()):
                        first_promo_index = i - 1
        
        # 如果尾部有2行或以上推广内容，从第一个推广行开始全部过滤（降低阈值）
        if tail_promo_count >= 2:
            # 只保留推广内容之前的部分
            for i in range(first_promo_index):
                filtered_lines.append(lines[i])
            
            # 清理尾部空行
            while filtered_lines and not filtered_lines[-1].strip():
                filtered_lines.pop()
                
            result = '\n'.join(filtered_lines)
            logger.info(f"过滤尾部推广内容: {len(content)} -> {len(result)} 字符, 删除了 {total_lines - len(filtered_lines)} 行")
            return result
        
        # 如果尾部推广内容不足2行，进行逐行精细过滤
        for i, line in enumerate(lines):
            is_promo, score = self.is_promo_line(line)
            
            # 尾部区域（最后20%）更严格
            if i >= total_lines * 0.8:
                if is_promo and score >= 8:  # 提高到8分
                    logger.info(f"过滤推广行(位置:{i+1}/{total_lines}, 分数:{score}): {line[:50]}...")
                    continue
                if re.match(r'^[-=_—➖▪▫◆◇■□●○•]{5,}$', line.strip()):
                    # 检查分隔符后是否有推广内容
                    has_promo_after = False
                    for j in range(i+1, min(i+3, total_lines)):
                        next_promo, next_score = self.is_promo_line(lines[j])
                        if next_promo and next_score >= 8:  # 提高到8分
                            has_promo_after = True
                            break
                    if has_promo_after:
                        logger.info(f"过滤分隔符(后有推广): {line[:50]}...")
                        continue
            # 正文部分（前80%）只过滤高置信度
            else:
                # 正文部分要求更高的置信度（10分）才过滤
                # 这样可以避免误删包含链接的新闻内容
                if is_promo and score >= 10:
                    logger.info(f"过滤正文推广行(分数:{score}): {line[:50]}...")
                    continue
            
            filtered_lines.append(line)
        
        # 清理尾部空行
        while filtered_lines and not filtered_lines[-1].strip():
            filtered_lines.pop()
            
        result = '\n'.join(filtered_lines)
        
        if len(result) < len(content):
            logger.info(f"内容过滤: {len(content)} -> {len(result)} 字符")
            
        return result
    
    
    def is_commercial_ad(self, content: str) -> bool:
        """检测是否为商业广告"""
        if not content:
            return False
            
        lines = content.split('\n')
        commercial_indicators = 0
        
        # 关键商业指标
        commercial_patterns = [
            r'(营业时间|營業時間|营业中|營業中)',
            r'(店铺地址|店鋪地址|门店地址|門店地址)',
            r'(经营项目|經營項目|主营|主營)',
            r'(优惠|優惠|折扣|打折|特价|特價)',
            r'(微信[:：]|WeChat[:：])',
            r'(电话[:：]|電話[:：]|手机[:：]|手機[:：])',
            r'(接单|接單|下单|下單|订购|訂購)',
            r'(价格|價格|收费|收費|费用|費用)',
        ]
        
        for line in lines:
            for pattern in commercial_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    commercial_indicators += 1
                    break
        
        # 如果有4个或以上商业指标，判定为商业广告（从3提高到4，减少误判）
        return commercial_indicators >= 4
    
    def is_high_risk_ad(self, content: str) -> bool:
        """
        检测是否为高风险广告（赌博、色情、诈骗等）
        
        Args:
            content: 消息内容
            
        Returns:
            是否为高风险广告
        """
        if not content:
            return False
        
        # 高风险广告关键词模式
        HIGH_RISK_PATTERNS = [
            # 赌博相关
            r'[Yy]3.*(?:娱乐|娛樂|国际|國際|YLC|ylc)',
            r'(?:USDT|泰达币|泰達幣|虚拟币|虛擬幣).*(?:娱乐城|娛樂城|平台)',
            r'(?:博彩|赌场|賭場|棋牌|体育|體育).*(?:平台|官网|官網)',
            r'(?:首充|首存|首冲).*(?:返水|优惠|優惠)',
            r'(?:日出|日入|日赚|日賺).*[0-9]+.*[uU万萬千]',
            r'(?:实力|實力).*(?:U盘|U盤|USDT)',
            r'(?:千万|千萬|巨款).*(?:无忧|無憂)',
            r'(?:PG|pg).*(?:幸运|幸運|注单|注單)',
            r'(?:百家乐|百家樂|轮盘|輪盤|转运金|轉運金)',
            r'全网福利.*业界龙头',
            r'电子.*(?:专损金|專損金|亏损|虧損).*最高',
            
            # 色情相关
            r'(?:上线|上線).*(?:福利|八大)',
            r'(?:永久|免费|免費).*(?:送|领取|領取)',
            r'(?:幸运|幸運).*(?:单|單).*(?:奖|獎)',
            r'(?:上门|上門).*(?:服务|服務).*(?:颜值|顏值|身材)',
            
            # 诈骗相关
            r'(?:一个月|一個月).*(?:奔驰|奔馳|宝马|寶馬|提奔驰|提寶馬)',
            r'(?:三个月|三個月).*(?:套房|房子|一套房)',
            r'(?:汽车|汽車).*(?:违停|違停).*(?:拍照|一张|一張).*[0-9]+',
            r'(?:想功成名就|胆子大|膽子大).*(?:灰色|看我|煮叶|煮葉)',
            r'(?:空闲|空閒).*(?:哥们|哥們).*(?:干点事|幹點事).*(?:宝马|寶馬)',
            
            # 其他高风险词汇
            r'匿名秒登|日出亿U|官方直营|官方直營',
            r'Y3YLC|y3ylc',  # 特定赌博网站
        ]
        
        # 检查是否包含高风险模式
        for pattern in HIGH_RISK_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                logger.info(f"检测到高风险广告关键词: {pattern[:30]}...")
                return True
                
        return False
    
    
    async def filter_message(self, content: str, channel_id: str = None, message_obj: Any = None, media_files: List[str] = None) -> Tuple[bool, str, str, dict]:
        """
        过滤消息内容 - 增强版检测流程（支持OCR图片文字提取）
        
        Args:
            content: 消息内容
            channel_id: 频道ID（用于AI过滤）
            message_obj: Telegram消息对象（用于结构化检测）
            media_files: 媒体文件路径列表（用于OCR处理）
        
        Returns:
            (是否广告, 过滤后内容, 过滤原因, OCR结果)
        """
        if not content:
            content = ""
        
        # 记录初始内容长度
        original_len = len(content)
        filtered_content = content
        is_ad = False
        reasons = []
        ocr_result = {}
        
        # 1. OCR图片文字提取和广告检测（优先级最高）
        if media_files:
            try:
                from app.services.ocr_service import ocr_service
                
                # 处理图片类型的媒体文件
                image_files = []
                for media_file in media_files:
                    if media_file and any(media_file.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                        image_files.append(media_file)
                
                if image_files:
                    logger.info(f"开始OCR处理 {len(image_files)} 个图片文件")
                    
                    # 批量处理图片
                    ocr_results = await ocr_service.batch_extract_content(image_files)
                    
                    # 合并所有OCR提取的文字
                    all_ocr_texts = []
                    all_qr_codes = []
                    total_ad_score = 0
                    ocr_ad_indicators = []
                    
                    for file_path, result in ocr_results.items():
                        if result.get('error'):
                            logger.warning(f"OCR处理失败: {file_path} - {result['error']}")
                            continue
                            
                        texts = result.get('texts', [])
                        qr_codes = result.get('qr_codes', [])
                        ad_score = result.get('ad_score', 0)
                        ad_indicators = result.get('ad_indicators', [])
                        
                        all_ocr_texts.extend(texts)
                        all_qr_codes.extend(qr_codes)
                        total_ad_score = max(total_ad_score, ad_score)  # 取最高分数
                        ocr_ad_indicators.extend(ad_indicators)
                    
                    # 将OCR文字合并到原始内容中进行综合检测
                    if all_ocr_texts:
                        ocr_text = ' '.join(all_ocr_texts)
                        # 将OCR文字添加到原始内容后面，用换行符分隔
                        if filtered_content.strip():
                            filtered_content = f"{filtered_content}\n\n[图片文字内容]\n{ocr_text}"
                        else:
                            filtered_content = f"[图片文字内容]\n{ocr_text}"
                        
                        logger.info(f"OCR提取文字 {len(all_ocr_texts)} 条，合并到消息内容中")
                    
                    # OCR广告检测
                    if total_ad_score >= 30:  # 30分以上认为是广告
                        is_ad = True
                        reasons.append(f"图片广告内容(分数:{total_ad_score:.0f})")
                        logger.info(f"OCR检测到图片广告，分数: {total_ad_score}")
                    
                    # 保存OCR结果
                    ocr_result = {
                        'texts': all_ocr_texts,
                        'qr_codes': all_qr_codes,
                        'ad_score': total_ad_score,
                        'ad_indicators': ocr_ad_indicators,
                        'processed_files': len(image_files)
                    }
                    
            except Exception as e:
                logger.error(f"OCR处理失败: {e}")
        
        # 2. 智能尾部过滤（移除频道标识，不算广告）
        try:
            from app.services.smart_tail_filter import smart_tail_filter
            clean_content, has_tail_ad, ad_part = smart_tail_filter.filter_tail_ads(filtered_content)
            if has_tail_ad:
                filtered_content = clean_content
                # 注意：尾部过滤是移除原频道标识，不算广告，所以不设置 is_ad = True
                # is_ad = True  # 移除这行
                reasons.append("尾部过滤")  # 改为"尾部过滤"而不是"尾部广告"
                logger.info(f"过滤了尾部频道标识，移除 {len(ad_part)} 字符")
        except Exception as e:
            logger.error(f"尾部过滤失败: {e}")
        
        # 3. 消息结构分析（格式化推广检测）- 新增功能
        # 只对合并后的内容进行结构分析，避免重复检测
        if filtered_content and not is_ad:  # 只有还不是广告时才检测
            try:
                is_structural_promo, structure_scores = message_structure_analyzer.analyze(filtered_content)
                if is_structural_promo:
                    is_ad = True
                    # 详细的结构异常说明
                    structure_details = []
                    if structure_scores.get('emoji_density', 0) > 0.15:
                        structure_details.append(f"表情密度{structure_scores['emoji_density']:.1%}")
                    if structure_scores.get('link_density', 0) > 2.0:
                        structure_details.append(f"链接密度{structure_scores['link_density']:.1f}/100字")
                    if structure_scores.get('structure_abnormality', 0) > 0.6:
                        structure_details.append(f"结构异常{structure_scores['structure_abnormality']:.1%}")
                    
                    detail_str = ",".join(structure_details) if structure_details else f"综合得分{structure_scores.get('total_score', 0):.2f}"
                    reasons.append(f"格式化推广({detail_str})")
                    logger.info(f"检测到格式化推广消息: {detail_str}")
                    
                    # 如果检测到格式化推广，可以选择清空内容或进行推广过滤
                    if structure_scores.get('total_score', 0) > 0.8:  # 高置信度时清空
                        filtered_content = ""
                    else:  # 否则进行推广内容过滤
                        filtered_content = self.filter_promotional_content(filtered_content, channel_id)
            except Exception as e:
                logger.error(f"消息结构分析失败: {e}")
        
        # 4. 结构化广告检测（检测按钮和实体中的广告）- 保留原有功能
        if message_obj and not is_ad:  # 只有还不是广告时才检测
            try:
                from app.services.structural_ad_detector import structural_detector
                structural_result = await structural_detector.detect_structural_ads(message_obj)
                if structural_result['has_structural_ad']:
                    is_ad = True
                    reasons.append(f"结构化广告({structural_result['ad_type']})")
                    # 如果有需要清理的文本实体，更新内容
                    if structural_result.get('clean_text'):
                        filtered_content = structural_result['clean_text']
                    logger.info(f"检测到结构化广告: {structural_result['ad_type']}")
            except Exception as e:
                logger.error(f"结构化广告检测失败: {e}")
        
        # 5. AI广告检测（对合并后的内容进行检测）
        if self.ai_filter and self.ai_filter.initialized and filtered_content:
            is_ad_by_ai, ai_confidence = self.ai_filter.is_advertisement(filtered_content)
            if is_ad_by_ai and ai_confidence > 0.85:  # 提高阈值从0.8到0.85
                is_ad = True
                reasons.append(f"AI检测(置信度:{ai_confidence:.2f})")
                logger.info(f"AI检测到广告内容，置信度: {ai_confidence:.2f}")
                # 如果整条消息都是广告，清空内容
                if ai_confidence > 0.95:  # 提高阈值从0.9到0.95
                    filtered_content = ""
        
        # 6. 商业广告检测
        if filtered_content:
            is_commercial = self.is_commercial_ad(filtered_content)
            if is_commercial:
                is_ad = True
                reasons.append("商业广告")
                # 进行推广内容过滤
                filtered_content = self.filter_promotional_content(filtered_content, channel_id)
        
        # 7. 高风险广告检测（赌博、色情、诈骗等）
        if content:  # 检查原始内容而不是过滤后的内容
            is_high_risk = self.is_high_risk_ad(content)
            if is_high_risk:
                is_ad = True
                if "高风险广告" not in reasons:
                    reasons.append("高风险广告")
                # 高风险广告应该清空内容
                filtered_content = ""
                logger.warning(f"检测到高风险广告，内容已清空")
        
        # 8. 推广内容过滤（最后的保险）
        if filtered_content:
            final_filtered = self.filter_promotional_content(filtered_content, channel_id)
            if final_filtered != filtered_content:
                filtered_content = final_filtered
                if not is_ad:
                    is_ad = True
                    reasons.append("推广内容")
        
        # 9. 清理OCR添加的标记（如果不是广告，移除OCR标记）
        if not is_ad and "[图片文字内容]" in filtered_content:
            # 如果不是广告，恢复原始内容（移除OCR文字）
            filtered_content = content
        elif is_ad and "[图片文字内容]" in filtered_content:
            # 如果是广告，移除OCR标记但保留原始内容
            lines = filtered_content.split('\n')
            clean_lines = []
            skip_ocr = False
            for line in lines:
                if "[图片文字内容]" in line:
                    skip_ocr = True
                    continue
                if not skip_ocr:
                    clean_lines.append(line)
            filtered_content = '\n'.join(clean_lines)
        
        # 检查是否整条消息都被过滤了
        if not filtered_content.strip() and content.strip():
            is_ad = True
            if "整条消息都是广告" not in reasons:
                reasons.append("整条消息都是广告")
        
        # 生成过滤原因说明
        filter_reason = " | ".join(reasons) if reasons else ""
        
        # 记录过滤效果
        if original_len != len(filtered_content):
            logger.info(f"内容过滤: {original_len} -> {len(filtered_content)} 字符 (减少 {original_len - len(filtered_content)})")
        
        return is_ad, filtered_content, filter_reason, ocr_result
    
    def filter_message_sync(self, content: str, channel_id: str = None, message_obj: Any = None) -> Tuple[bool, str, str]:
        """
        同步版本的消息过滤方法（向后兼容）
        注意：这个方法不包含OCR功能，只做基本的文本过滤
        
        Args:
            content: 消息内容
            channel_id: 频道ID
            message_obj: Telegram消息对象
            
        Returns:
            (是否广告, 过滤后内容, 过滤原因)
        """
        if not content:
            return False, content, ""
        
        # 记录初始内容长度
        original_len = len(content)
        filtered_content = content
        is_ad = False
        reasons = []
        
        # 1. 推广内容过滤
        final_filtered = self.filter_promotional_content(filtered_content, channel_id)
        if final_filtered != filtered_content:
            filtered_content = final_filtered
            is_ad = True
            reasons.append("推广内容")
        
        # 2. 商业广告检测
        if filtered_content:
            is_commercial = self.is_commercial_ad(filtered_content)
            if is_commercial:
                is_ad = True
                reasons.append("商业广告")
                # 进行推广内容过滤
                filtered_content = self.filter_promotional_content(filtered_content, channel_id)
        
        # 3. 高风险广告检测（赌博、色情、诈骗等）
        if content:  # 检查原始内容
            is_high_risk = self.is_high_risk_ad(content)
            if is_high_risk:
                is_ad = True
                if "高风险广告" not in reasons:
                    reasons.append("高风险广告")
                # 高风险广告应该清空内容
                filtered_content = ""
                logger.warning(f"同步检测到高风险广告，内容已清空")
        
        # 检查是否整条消息都被过滤了
        if not filtered_content.strip() and content.strip():
            is_ad = True
            if "整条消息都是广告" not in reasons:
                reasons.append("整条消息都是广告")
        
        # 生成过滤原因说明
        filter_reason = " | ".join(reasons) if reasons else ""
        
        # 记录过滤效果
        if original_len != len(filtered_content):
            logger.info(f"同步内容过滤: {original_len} -> {len(filtered_content)} 字符 (减少 {original_len - len(filtered_content)})")
        
        return is_ad, filtered_content, filter_reason
    
    def check_ad_keywords(self, content: str) -> Tuple[bool, str]:
        """
        检查广告关键词（兼容旧接口）
        """
        # 简单检查一些明显的广告关键词
        ad_keywords = [
            '赌场', '赌博', '娱乐城', '真人', '百家乐',
            '返水', '首充', '优惠', '注册就送',
            '日出千万', '全网独家'
        ]
        
        if not content:
            return False, ""
            
        content_lower = content.lower()
        for keyword in ad_keywords:
            if keyword in content_lower:
                return True, f"包含广告关键词: {keyword}"
                
        return False, ""
    
    def smart_filter_tail_promo(self, content: str) -> str:
        """
        智能过滤尾部推广（兼容旧接口）
        """
        return self.filter_promotional_content(content)
    
    async def is_pure_advertisement_ai(self, content: str) -> bool:
        """
        使用AI判断是否为广告内容
        """
        if not content:
            return False
        
        try:
            # 尝试使用AI广告检测器
            from app.services.ad_detector import ad_detector
            
            if ad_detector.initialized and len(ad_detector.ad_embeddings) > 0:
                # 使用纯AI检测
                is_ad, confidence = ad_detector.is_advertisement_ai(content)
                if confidence > 0.8:  # 高置信度时直接返回结果
                    logger.debug(f"AI广告检测: {'是' if is_ad else '否'}, 置信度: {confidence:.2f}")
                    return is_ad
                elif is_ad and confidence > 0.7:  # 中等置信度的广告也认为是广告
                    return True
        except Exception as e:
            logger.error(f"AI广告检测失败: {e}")
        
        # AI检测失败或置信度不足，回退到规则检测
        return self.is_pure_advertisement(content)
    
    def is_pure_advertisement(self, content: str) -> bool:
        """
        判断是否纯广告内容（基于规则的传统方法）
        """
        if not content:
            return False
            
        # 过滤后如果几乎没有剩余内容，说明是纯广告
        filtered = self.filter_promotional_content(content)
        
        # 如果过滤后内容为空或者剩余内容太少
        if not filtered.strip():
            return True
            
        # 如果过滤掉了80%以上的内容，认为是广告
        if len(filtered) < len(content) * 0.2:
            return True
            
        return False
    
    def add_channel_signature(self, content: str, channel_name: str) -> str:
        """
        添加频道签名（兼容旧接口）
        """
        if not content:
            return content
            
        # 添加频道标识
        signature = f"\n\n【来源：{channel_name}】"
        return content + signature

# 创建全局实例
content_filter = ContentFilter()