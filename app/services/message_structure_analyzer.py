"""
消息结构分析器
通过分析消息的结构特征（而非内容）来识别格式化推广消息
"""
import re
import logging
from typing import Dict, List, Tuple, Optional
import unicodedata

logger = logging.getLogger(__name__)


class MessageStructureAnalyzer:
    """消息结构分析器 - 基于格式特征识别推广消息"""
    
    def __init__(self):
        """初始化分析器"""
        # 配置阈值（可调整）
        self.thresholds = {
            'emoji_ratio': 0.15,           # 表情符号占比阈值
            'link_density': 2.0,            # 每100字符的链接数阈值
            'short_line_ratio': 0.6,        # 短行占比阈值
            'repeat_symbol_count': 3,       # 重复符号数量阈值
            'decoration_lines': 2,          # 装饰性分隔线数量阈值
            'min_structure_score': 0.7,     # 最小结构异常得分
        }
        
        # 装饰性分隔线模式
        self.separator_patterns = [
            r'^[-=_—➖▪▫◆◇■□●○•～~※※]{5,}$',  # 符号分隔线
            r'^[\.·。、]{5,}$',                   # 点号分隔线
            r'^[\*\+]{5,}$',                      # 星号/加号分隔线
        ]
        
        # 链接模式
        self.link_patterns = [
            r'(?:https?://[^\s]+)',              # HTTP/HTTPS链接
            r'(?:t\.me/[a-zA-Z0-9_]+)',         # Telegram链接
            r'(?:@[a-zA-Z][a-zA-Z0-9_]{4,31})', # Telegram用户名
            r'(?:tg://[^\s]+)',                  # Telegram协议链接
        ]
        
    def analyze(self, content: str) -> Tuple[bool, Dict[str, float]]:
        """
        分析消息结构，判断是否为格式化推广消息
        
        Args:
            content: 消息内容
            
        Returns:
            (是否为推广消息, 各项得分详情)
        """
        if not content or len(content) < 20:
            return False, {}
        
        # 计算各项指标
        scores = {
            'emoji_density': self._calculate_emoji_density(content),
            'link_density': self._calculate_link_density(content),
            'structure_abnormality': self._calculate_structure_abnormality(content),
            'decoration_score': self._calculate_decoration_score(content),
            'repetition_score': self._calculate_repetition_score(content),
        }
        
        # 综合判定
        is_promotional = self._judge_promotional(scores)
        
        # 计算总分
        scores['total_score'] = self._calculate_total_score(scores)
        
        if is_promotional:
            logger.info(f"检测到结构化推广消息，得分: {scores}")
        
        return is_promotional, scores
    
    def _calculate_emoji_density(self, content: str) -> float:
        """计算表情符号密度"""
        if not content:
            return 0.0
        
        emoji_count = 0
        total_chars = len(content)
        
        for char in content:
            # 检测表情符号（Unicode范围）
            if self._is_emoji(char):
                emoji_count += 1
        
        return emoji_count / total_chars if total_chars > 0 else 0.0
    
    def _is_emoji(self, char: str) -> bool:
        """判断字符是否为表情符号"""
        # 常见表情符号Unicode范围
        emoji_ranges = [
            (0x1F300, 0x1F9FF),  # 杂项符号和图形
            (0x2600, 0x26FF),    # 杂项符号
            (0x2700, 0x27BF),    # 装饰符号
            (0x1F680, 0x1F6FF),  # 交通和地图符号
            (0x1F900, 0x1F9FF),  # 补充符号和图形
        ]
        
        code_point = ord(char)
        for start, end in emoji_ranges:
            if start <= code_point <= end:
                return True
        
        # 检查特定的表情字符
        if char in '😀😃😄😁😆😅🤣😂🙂🙃😉😊😇🥰😍🤩😘😗☺😚😙😋😛😜🤪😝🤑🤗🤭🤫🤔🐾🦆🐸🦋🏦🏧💰💵💴💶💷🔥❤️✓✔️☑️🏅📧📢📣🔔💬🔗🔍✉️📮':
            return True
            
        return False
    
    def _calculate_link_density(self, content: str) -> float:
        """计算链接密度（每100字符的链接数）"""
        if not content or len(content) < 10:
            return 0.0
        
        link_count = 0
        for pattern in self.link_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            link_count += len(matches)
        
        # 计算每100字符的链接数
        char_count = len(content)
        link_density = (link_count * 100) / char_count
        
        return link_density
    
    def _calculate_structure_abnormality(self, content: str) -> float:
        """计算文本结构异常度"""
        lines = content.split('\n')
        if not lines:
            return 0.0
        
        total_lines = len(lines)
        short_lines = 0
        empty_lines = 0
        very_short_lines = 0  # 极短行（少于10字符）
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                empty_lines += 1
            elif len(line_stripped) < 10:
                very_short_lines += 1
                short_lines += 1
            elif len(line_stripped) < 20:
                short_lines += 1
        
        # 计算短行占比（排除空行）
        non_empty_lines = total_lines - empty_lines
        if non_empty_lines == 0:
            return 1.0
        
        # 如果非空行少于5行，不判定为结构异常（避免短消息误判）
        if non_empty_lines < 5:
            return 0.0
        
        short_line_ratio = short_lines / non_empty_lines
        very_short_ratio = very_short_lines / non_empty_lines
        
        # 计算行数与内容长度的比例异常度
        avg_line_length = len(content) / total_lines if total_lines > 0 else 0
        
        # 检查是否为正常的列表格式（如工作安排、编号列表等）
        list_pattern_count = 0
        for line in lines:
            line_stripped = line.strip()
            # 检查常见的列表格式
            if re.match(r'^[\d一二三四五六七八九十]+[\.、\)]\s', line_stripped):
                list_pattern_count += 1
            elif re.match(r'^[-\*•]\s', line_stripped):
                list_pattern_count += 1
        
        # 如果超过30%的行是列表格式，认为是正常列表
        if non_empty_lines > 0 and list_pattern_count / non_empty_lines > 0.3:
            return 0.0
        
        # 综合评分：
        # 1. 如果极短行占比超过60%（提高阈值），高度异常
        if very_short_ratio > 0.6:
            return 0.9
        # 2. 如果平均行长度小于12字符（更严格），且极短行占比超过40%
        elif avg_line_length < 12 and very_short_ratio > 0.4:
            return 0.8
        # 3. 如果短行占比超过85%（提高阈值）
        elif short_line_ratio > 0.85:
            return 0.7
        # 4. 正常情况，返回较低的异常度
        else:
            # 如果内容较长（超过200字符）且短行不多，认为正常
            if len(content) > 200 and short_line_ratio < 0.5:
                return 0.0
            return short_line_ratio * 0.3  # 进一步降低权重
    
    def _calculate_decoration_score(self, content: str) -> float:
        """计算装饰性元素得分"""
        lines = content.split('\n')
        decoration_lines = 0
        
        for line in lines:
            line_stripped = line.strip()
            # 检查是否为装饰性分隔线
            for pattern in self.separator_patterns:
                if re.match(pattern, line_stripped):
                    decoration_lines += 1
                    break
        
        # 计算装饰线占比
        decoration_ratio = decoration_lines / len(lines) if lines else 0.0
        
        return decoration_ratio
    
    def _calculate_repetition_score(self, content: str) -> float:
        """计算重复模式得分"""
        # 检查连续重复的表情或符号
        repetition_pattern = r'(.)\1{2,}'  # 同一字符连续3次或以上
        matches = re.findall(repetition_pattern, content)
        
        repetition_count = len(matches)
        
        # 检查表情符号的重复模式
        emoji_repetition = 0
        for match in matches:
            if self._is_emoji(match):
                emoji_repetition += 1
        
        # 综合得分
        total_chars = len(content)
        if total_chars == 0:
            return 0.0
        
        repetition_score = (repetition_count + emoji_repetition * 2) / total_chars * 10
        return min(repetition_score, 1.0)  # 限制最大值为1.0
    
    def _judge_promotional(self, scores: Dict[str, float]) -> bool:
        """
        综合判定是否为推广消息
        使用多维度评分，任一维度超过阈值即判定为推广
        """
        # 检查单项指标
        if scores.get('emoji_density', 0) > self.thresholds['emoji_ratio']:
            logger.debug(f"表情密度超标: {scores['emoji_density']:.2%}")
            return True
        
        if scores.get('link_density', 0) > self.thresholds['link_density']:
            logger.debug(f"链接密度超标: {scores['link_density']:.2f}/100字符")
            return True
        
        if scores.get('structure_abnormality', 0) > self.thresholds['short_line_ratio']:
            logger.debug(f"结构异常度超标: {scores['structure_abnormality']:.2%}")
            return True
        
        # 组合判定：多个中等得分指标同时存在
        suspicious_count = 0
        if scores.get('emoji_density', 0) > self.thresholds['emoji_ratio'] * 0.7:
            suspicious_count += 1
        if scores.get('link_density', 0) > self.thresholds['link_density'] * 0.7:
            suspicious_count += 1
        if scores.get('decoration_score', 0) > 0.1:
            suspicious_count += 1
        if scores.get('repetition_score', 0) > 0.3:
            suspicious_count += 1
        
        if suspicious_count >= 3:
            logger.debug(f"组合特征可疑: {suspicious_count}项指标异常")
            return True
        
        return False
    
    def _calculate_total_score(self, scores: Dict[str, float]) -> float:
        """计算综合得分"""
        weights = {
            'emoji_density': 2.0,
            'link_density': 0.5,  # link_density已经是按100字符计算的，所以权重较低
            'structure_abnormality': 1.5,
            'decoration_score': 1.0,
            'repetition_score': 1.0,
        }
        
        total_score = 0.0
        total_weight = 0.0
        
        for key, weight in weights.items():
            if key in scores:
                total_score += scores[key] * weight
                total_weight += weight
        
        return total_score / total_weight if total_weight > 0 else 0.0
    
    def get_analysis_report(self, content: str) -> str:
        """
        生成详细的分析报告（用于调试）
        """
        is_promotional, scores = self.analyze(content)
        
        report = []
        report.append("=" * 50)
        report.append("消息结构分析报告")
        report.append("=" * 50)
        report.append(f"判定结果: {'推广消息' if is_promotional else '正常消息'}")
        report.append(f"综合得分: {scores.get('total_score', 0):.2f}")
        report.append("-" * 30)
        report.append("详细指标:")
        report.append(f"  表情密度: {scores.get('emoji_density', 0):.2%} (阈值: {self.thresholds['emoji_ratio']:.2%})")
        report.append(f"  链接密度: {scores.get('link_density', 0):.2f}/100字符 (阈值: {self.thresholds['link_density']:.1f})")
        report.append(f"  结构异常: {scores.get('structure_abnormality', 0):.2%} (阈值: {self.thresholds['short_line_ratio']:.2%})")
        report.append(f"  装饰得分: {scores.get('decoration_score', 0):.2%}")
        report.append(f"  重复得分: {scores.get('repetition_score', 0):.2f}")
        report.append("=" * 50)
        
        return "\n".join(report)


# 创建全局实例
message_structure_analyzer = MessageStructureAnalyzer()