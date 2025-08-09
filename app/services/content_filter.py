"""
优化的内容过滤器
精准识别并删除推广内容，不依赖位置判断
"""
import re
import logging
import asyncio
from typing import Tuple, List, Set
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, AdKeyword

logger = logging.getLogger(__name__)

class ContentFilter:
    """内容过滤器"""
    
    def __init__(self):
        """初始化过滤器"""
        # 数据库关键词缓存
        self.db_keywords_text: Set[str] = set()  # 文中关键词
        self.db_keywords_line: Set[str] = set()  # 行过滤关键词
        self.keywords_loaded = False
        
        # 推广内容特征模式
        self.promo_patterns = [
            # === 非Telegram的HTTP链接（赌博网站等） ===
            (r'\bhttps?://(?!(?:t\.me|telegram\.me|telegra\.ph))[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=]+', 10),
            
            # === 带括号的链接（常见推广格式） ===
            (r'\([^\)]*https?://[^\)]+\)', 10),  # (链接)
            
            # === 表情符号密集+文字+链接的组合 ===
            (r'^[😊😀☕️🧩🎰🎮🎳🎯♟⚡️😘🎁😍❤💰🔥]{2,}.*https?://', 10),  # 多个表情开头+链接
            (r'^[😊😀☕️🧩🎰🎮🎳🎯♟⚡️😘🎁😍❤💰🔥]{3,}[^\n]{0,50}$', 8),  # 纯表情推广行
            
            # === Telegram用户名和频道（更智能的判断） ===
            # t.me链接总是推广
            (r'(?:^|\s)t\.me/[a-zA-Z][a-zA-Z0-9_]{4,31}(?:\s|$|/)', 9),  # t.me链接
            (r'(?:^|\s)https?://t\.me/[a-zA-Z][a-zA-Z0-9_]{4,31}', 9),  # 完整t.me链接
            
            # 单独的@用户名不过滤，除非在明显的推广上下文中
            # 暂时不过滤单独的@用户名，避免误判
            
            # === 推广关键词组合（必须带链接或@） ===
            # 订阅、投稿、商务等推广词+@用户名（需要更精确的匹配）
            (r'^[📢📣🔔💬❤️🔗☎️😍].{0,5}(?:订阅|訂閱|投稿|爆料|商务|商務|联系|聯系)[^\n]{0,5}@[a-zA-Z]', 10),  # 表情+推广词+@
            (r'(?:欢迎|歡迎)(?:投稿|爆料|加入)[^\n]{0,5}@', 9),  # 欢迎投稿+@
            
            # === 频道推广固定格式 ===
            (r'^[📢📣🔔💬❤️🔗🔍].{0,5}(?:订阅|投稿|商务|联系)', 8),  # 表情+推广词
            (r'(?:^|\n)[📢📣🔔💬❤️🔗👇🔍].{0,3}(?:@|t\.me|https?://)', 9),  # 表情+链接
            (r'(?:订阅|訂閱).*(?:t\.me/|@)', 9),  # 订阅+链接
            
            # === 纯表情分隔线 ===
            (r'^[😊😀😉🙂😄😃💯🔥❤️💰]{5,}$', 4),  # 5个以上表情
            (r'^[-=_—➖▪▫◆◇■□●○•～~]{10,}$', 3),  # 符号分隔线
            
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
        
        # 如果是高分推广内容（>=8分），不再检查保护内容
        # 因为订阅链接等明显推广内容不应被保护
        if max_score >= 8:
            return True, max_score
                
        # 中低分数才检查保护内容
        for protector in self.content_protectors:
            if re.search(protector, line, re.IGNORECASE):
                # 如果包含保护内容，降低推广分数
                max_score = max(0, max_score - 5)
                break
                
        return max_score >= 6, max_score
    
    def filter_promotional_content(self, content: str) -> str:
        """
        精准过滤推广内容
        逐行分析，只删除确定是推广的行
        """
        if not content:
            return content
            
        lines = content.split('\n')
        filtered_lines = []
        
        # 逐行分析
        for i, line in enumerate(lines):
            is_promo, score = self.is_promo_line(line)
            
            if is_promo:
                # 高置信度直接过滤
                if score >= 8:
                    logger.info(f"过滤推广行(分数:{score}): {line[:50]}...")
                    continue
                    
                # 中等置信度需要额外判断
                elif score >= 6:
                    # 检查是否是分隔符
                    if re.match(r'^[-=_—➖▪▫◆◇■□●○•]{5,}$', line.strip()):
                        # 分隔符后面是否有推广内容
                        has_promo_after = False
                        for j in range(i+1, min(i+3, len(lines))):
                            next_is_promo, next_score = self.is_promo_line(lines[j])
                            if next_is_promo and next_score >= 7:
                                has_promo_after = True
                                break
                        if has_promo_after:
                            logger.info(f"过滤分隔符: {line[:50]}...")
                            continue
                    else:
                        logger.info(f"过滤推广行(分数:{score}): {line[:50]}...")
                        continue
            
            # 保留非推广内容
            filtered_lines.append(line)
        
        # 清理尾部空行
        while filtered_lines and not filtered_lines[-1].strip():
            filtered_lines.pop()
            
        result = '\n'.join(filtered_lines)
        
        if len(result) < len(content):
            logger.info(f"内容过滤: {len(content)} -> {len(result)} 字符")
            
        return result
    
    async def load_keywords_from_db(self):
        """从数据库加载广告关键词"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(AdKeyword).where(AdKeyword.is_active == True)
                )
                keywords = result.scalars().all()
                
                # 清空缓存
                self.db_keywords_text.clear()
                self.db_keywords_line.clear()
                
                # 分类存储关键词
                for kw in keywords:
                    if kw.keyword_type == 'text':
                        self.db_keywords_text.add(kw.keyword.lower())
                    elif kw.keyword_type == 'line':
                        self.db_keywords_line.add(kw.keyword.lower())
                
                self.keywords_loaded = True
                logger.info(f"已加载广告关键词: {len(self.db_keywords_text)}个文中关键词, {len(self.db_keywords_line)}个行过滤关键词")
                
        except Exception as e:
            logger.error(f"加载广告关键词失败: {e}")
    
    def check_db_keywords(self, content: str) -> Tuple[bool, str]:
        """检查数据库中的广告关键词"""
        if not content:
            return False, ""
        
        content_lower = content.lower()
        lines = content_lower.split('\n')
        
        # 检查文中关键词
        for keyword in self.db_keywords_text:
            if keyword in content_lower:
                return True, f"包含广告关键词: {keyword}"
        
        # 检查行过滤关键词
        for line in lines:
            line = line.strip()
            if not line:
                continue
            for keyword in self.db_keywords_line:
                if keyword in line:
                    return True, f"行中包含过滤关键词: {keyword}"
        
        return False, ""
    
    def filter_message(self, content: str) -> Tuple[bool, str, str]:
        """
        过滤消息内容
        
        Returns:
            (是否广告, 过滤后内容, 过滤原因)
        """
        if not content:
            return False, content, ""
        
        # 确保关键词已加载（同步检查）
        if not self.keywords_loaded:
            # 在同步函数中运行异步加载
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果事件循环正在运行，创建任务
                    task = asyncio.create_task(self.load_keywords_from_db())
                    # 这里不能等待，因为是同步函数
                    logger.warning("关键词未加载，将在后台加载")
                else:
                    # 如果没有运行的事件循环，创建新的
                    asyncio.run(self.load_keywords_from_db())
            except Exception as e:
                logger.error(f"加载关键词失败: {e}")
        
        # 先检查数据库关键词
        is_ad_by_keyword, keyword_reason = self.check_db_keywords(content)
        if is_ad_by_keyword:
            # 如果检测到广告关键词，进行内容过滤
            filtered = self.filter_promotional_content(content)
            if not filtered.strip():
                return True, "", keyword_reason
            return True, filtered, keyword_reason
        
        # 进行推广内容过滤
        filtered = self.filter_promotional_content(content)
        
        # 检查是否整条消息都是广告
        if not filtered.strip():
            return True, "", "整条消息都是推广内容"
        
        # 再次检查过滤后的内容是否包含广告关键词
        is_ad_after_filter, keyword_reason_after = self.check_db_keywords(filtered)
        if is_ad_after_filter:
            return True, filtered, keyword_reason_after
        
        return False, filtered, ""
    
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
    
    def is_pure_advertisement(self, content: str) -> bool:
        """
        判断是否纯广告内容（兼容旧接口）
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