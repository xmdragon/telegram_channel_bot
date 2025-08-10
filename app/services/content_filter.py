"""
优化的内容过滤器
精准识别并删除推广内容，不依赖位置判断
"""
import re
import logging
import asyncio
from typing import Tuple, List, Set, Any
from app.services.ai_filter import ai_filter
from app.services.config_manager import config_manager

logger = logging.getLogger(__name__)

class ContentFilter:
    """内容过滤器"""
    
    def __init__(self):
        """初始化过滤器"""
        # AI过滤器实例
        self.ai_filter = ai_filter
        
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
            
            # === 纯表情分隔线 ===
            (r'^[😊😀😉🙂😄😃💯🔥❤️💰]{5,}$', 2),  # 5个以上表情 - 降低权重
            (r'^[-=_—➖▪▫◆◇■□●○•～~]{10,}$', 1),  # 符号分隔线 - 最低权重
            
            # === Markdown链接格式 ===
            (r'\[[^\]]+\]\(https?://[^\)]+\)', 9),  # [文字](链接)
            (r'\[[订阅訂閱&][^\]]*\]\([^\)]*t\.me[^\)]+\)', 10),  # [订阅xxx](t.me/xxx)
            (r'[🔍🔔🔗]\[[^\]]*\]\(.*t\.me.*\)', 10),  # 表情[文字](t.me链接)
            
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
            
            # 寻人启事（特殊保护）
            r'失踪|寻找|寻人|联系家人|报警',
            r'身高\d+|体重\d+|年龄\d+|失联',
            
            # 用户投稿标记（重要保护）
            r'^#网友投稿|^#群友投稿|^#读者投稿|^#粉丝投稿',
            r'^#用户分享|^#真实经历|^#亲身经历',
        ]
    
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
            
        # 检查推广特征
        for pattern, score in self.promo_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                max_score = max(max_score, score)
        
        # 如果是高分推广内容（>=9分），不再检查保护内容
        # 因为订阅链接等明显推广内容不应被保护
        if max_score >= 9:
            return True, max_score
                
        # 中低分数才检查保护内容
        for protector in self.content_protectors:
            if re.search(protector, line, re.IGNORECASE):
                # 如果包含保护内容，降低推广分数
                max_score = max(0, max_score - 5)
                break
                
        return max_score >= 8, max_score  # 提高阈值从7到8，减少误判
    
    def filter_promotional_content(self, content: str, channel_id: str = None) -> str:
        """
        精准过滤推广内容 - 简化版
        重点过滤尾部推广内容
        
        Args:
            content: 消息内容
            channel_id: 频道ID（用于AI尾部过滤）
        """
        if not content:
            return content
        
        # 1. 首先尝试使用AI过滤频道尾部（如果可用）
        if channel_id and self.ai_filter and self.ai_filter.initialized:
            ai_filtered = self.ai_filter.filter_channel_tail(channel_id, content)
            if ai_filtered != content:
                logger.info(f"AI过滤了频道 {channel_id} 的尾部内容")
                content = ai_filtered
            
        lines = content.split('\n')
        total_lines = len(lines)
        filtered_lines = []
        
        # 检查最后10行中的推广内容
        tail_start = max(0, total_lines - 10)
        tail_promo_count = 0
        first_promo_index = total_lines
        
        # 扫描尾部，找到第一个推广行的位置
        for i in range(tail_start, total_lines):
            is_promo, score = self.is_promo_line(lines[i])
            if is_promo and score >= 8:  # 提高阈值到8分
                tail_promo_count += 1
                if first_promo_index == total_lines:
                    first_promo_index = i
                    # 如果推广行前面有分隔符，也包括分隔符
                    if i > 0 and re.match(r'^[-=_—➖▪▫◆◇■□●○•]{3,}$', lines[i-1].strip()):
                        first_promo_index = i - 1
        
        # 如果尾部有3行或以上推广内容，从第一个推广行开始全部过滤
        if tail_promo_count >= 3:
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
                if is_promo and score >= 9:
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
    
    
    def filter_message(self, content: str, channel_id: str = None, message_obj: Any = None) -> Tuple[bool, str, str]:
        """
        过滤消息内容 - 增强版检测流程
        
        Args:
            content: 消息内容
            channel_id: 频道ID（用于AI过滤）
            message_obj: Telegram消息对象（用于结构化检测）
        
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
        
        # 1. 智能尾部广告过滤（优先级最高）
        try:
            from app.services.smart_tail_filter import smart_tail_filter
            clean_content, has_tail_ad, ad_part = smart_tail_filter.filter_tail_ads(content)
            if has_tail_ad:
                filtered_content = clean_content
                is_ad = True
                reasons.append("尾部广告")
                logger.info(f"检测到尾部广告，过滤了 {len(ad_part)} 字符")
        except Exception as e:
            logger.error(f"尾部广告过滤失败: {e}")
        
        # 2. 结构化广告检测（检测按钮和实体中的广告）
        if message_obj:
            try:
                from app.services.structural_ad_detector import structural_detector
                structural_result = asyncio.run(structural_detector.detect_structural_ads(message_obj))
                if structural_result['has_structural_ad']:
                    is_ad = True
                    reasons.append(f"结构化广告({structural_result['ad_type']})")
                    # 如果有需要清理的文本实体，更新内容
                    if structural_result.get('clean_text'):
                        filtered_content = structural_result['clean_text']
                    logger.info(f"检测到结构化广告: {structural_result['ad_type']}")
            except Exception as e:
                logger.error(f"结构化广告检测失败: {e}")
        
        # 3. AI广告检测（对过滤后的内容进行检测）
        if self.ai_filter and self.ai_filter.initialized and filtered_content:
            is_ad_by_ai, ai_confidence = self.ai_filter.is_advertisement(filtered_content)
            if is_ad_by_ai and ai_confidence > 0.85:  # 提高阈值从0.8到0.85
                is_ad = True
                reasons.append(f"AI检测(置信度:{ai_confidence:.2f})")
                logger.info(f"AI检测到广告内容，置信度: {ai_confidence:.2f}")
                # 如果整条消息都是广告，清空内容
                if ai_confidence > 0.95:  # 提高阈值从0.9到0.95
                    filtered_content = ""
        
        # 4. 商业广告检测
        if filtered_content:
            is_commercial = self.is_commercial_ad(filtered_content)
            if is_commercial:
                is_ad = True
                reasons.append("商业广告")
                # 进行推广内容过滤
                filtered_content = self.filter_promotional_content(filtered_content, channel_id)
        
        # 5. 推广内容过滤（最后的保险）
        if filtered_content:
            final_filtered = self.filter_promotional_content(filtered_content, channel_id)
            if final_filtered != filtered_content:
                filtered_content = final_filtered
                if not is_ad:
                    is_ad = True
                    reasons.append("推广内容")
        
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