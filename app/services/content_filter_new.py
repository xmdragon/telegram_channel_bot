"""
优化的内容过滤器
精准识别并删除推广内容，不依赖位置判断
"""
import re
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)

class ContentFilter:
    """内容过滤器"""
    
    def __init__(self):
        """初始化过滤器"""
        # 推广内容特征模式
        self.promo_patterns = [
            # 核心推广特征：带链接的推广关键词
            (r'[订訂阅閱][^\n]{0,20}[@:：].*', 10),  # 订阅+链接
            (r'[投稿爆料][^\n]{0,20}[@:：].*', 10),  # 投稿/爆料+链接
            (r'[商务商務合作][^\n]{0,20}[@:：].*', 10),  # 商务合作+链接
            (r'[联系聯系联络聯絡][^\n]{0,20}[@:：].*', 10),  # 联系+链接
            
            # Telegram链接（高置信度）
            (r'@[a-zA-Z][a-zA-Z0-9_]{3,}', 9),  # @username
            (r't\.me/[^\s]+', 10),  # t.me链接
            (r'https?://t\.me/[^\s]+', 10),  # 完整t.me链接
            
            # 表情符号+推广词+链接（组合特征）
            (r'^[📢📣☎️💬😍🔗👌✅🔔⭐️🔥💰🎁].{0,5}[投稿爆料商务商務]', 8),
            (r'^[📢📣☎️💬😍🔗👌✅🔔⭐️🔥💰🎁].{0,5}@', 9),
            
            # Markdown链接格式
            (r'\[.*\]\(https?://.*\)', 7),  # [文字](链接)
            (r'\[.*\]\(.*t\.me.*\)', 9),  # [文字](t.me链接)
            
            # 分隔符（低置信度，需要上下文）
            (r'^[-=_—➖▪▫◆◇■□●○•]{5,}$', 3),
            (r'^[😉☺️😊😄😃😀🙂]{5,}$', 3),
            
            # 赌博/娱乐推广
            (r'首充|返水|优惠|注册就送|日出千万', 8),
            (r'体育.*综合|负盈利|全网独家', 8),
            
            # 群组推广
            (r'加入.*群|进群|入群', 6),
            (r'欢迎加入|点击加入|扫码加入', 7),
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
            r'据报道|消息称|记者|发生|事件',
            r'警方|政府|官方|调查',
            
            # 寻人启事（特殊保护）
            r'失踪|寻找|寻人|联系家人|报警',
            r'身高\d+|体重\d+|年龄\d+|失联',
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
        
        # 检查推广特征
        for pattern, score in self.promo_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                max_score = max(max_score, score)
                
        # 检查是否受保护内容
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
    
    def filter_message(self, content: str) -> Tuple[bool, str, str]:
        """
        过滤消息内容
        
        Returns:
            (是否广告, 过滤后内容, 过滤原因)
        """
        if not content:
            return False, content, ""
            
        # 先进行推广内容过滤
        filtered = self.filter_promotional_content(content)
        
        # 检查是否整条消息都是广告
        if not filtered.strip():
            return True, "", "整条消息都是推广内容"
            
        # 检查剩余内容是否包含广告关键词
        # 这里可以添加更多广告检测逻辑
        
        return False, filtered, ""

# 创建全局实例
content_filter = ContentFilter()