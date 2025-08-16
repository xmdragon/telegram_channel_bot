"""
聊天内容检测过滤器
检测并过滤聊天性质的消息，如短文本、@用户名互动、口语化对话等
检测到聊天内容时返回 should_early_stop=True

Author: Claude
Created: 2025-08-16
"""

import re
import time
import logging
from typing import Dict, Any, Optional, List, Set
from .base import BaseFilter, FilterContext, FilterResult

logger = logging.getLogger(__name__)


class ChatContentFilter(BaseFilter):
    """聊天内容检测过滤器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("chat_content_filter", config)
        
        # 配置阈值 (从统一阈值管理器获取)
        self._load_thresholds()
        self.chat_threshold = self.config.get('chat_threshold', self._get_threshold('chat_filter', 'detection'))
        
        # 长度阈值配置
        self.short_length_threshold = self.config.get('short_length_threshold', 50)
        self.medium_length_threshold = self.config.get('medium_length_threshold', 100)
        self.max_chat_length = self.config.get('max_chat_length', 150)
        
        # 特征权重配置 (优化权重分配)
        self.weights = self.config.get('weights', {
            'length': 0.35,           # 增加长度权重
            'mention': 0.25,          # 降低@提及权重 
            'casual_language': 0.30,  # 增加口语化权重
            'structure': 0.10         # 降低结构权重
        })
        
        # 加载检测规则
        self._load_chat_patterns()
        
        logger.info(f"✅ {self.name} 初始化完成，阈值: {self.chat_threshold} (来源: {'配置文件' if 'chat_threshold' in self.config else '阈值管理器'})")
    
    def _load_chat_patterns(self):
        """加载聊天内容检测规则"""
        
        # @用户名提及模式
        self.mention_patterns = [
            r'@\w{3,}',                    # 标准@用户名
            r'@[a-zA-Z0-9_]{3,}',         # 英数字用户名
            r'@[\u4e00-\u9fa5\w]{2,}',    # 中文用户名
        ]
        
        # 口语化关键词（按类别分组，便于调试）
        self.casual_keywords = {
            # 问候寒暄类 (高权重)
            'greetings': [
                '你好', '您好', '在吗', '在不', '在么', 
                '有空吗', '忙吗', '忙不忙', '干嘛呢',
                'hi', 'hello', '早', '晚上好'
            ],
            
            # 日常对话类 (高权重)
            'daily_chat': [
                '干嘛', '干啥', '咋样', '怎么样', '什么情况',
                '来干嘛', '去哪', '哪里', '做什么',
                '咋回事', '咋了', '怎么了', '咋整'
            ],
            
            # 状态表达类 (中权重)
            'status': [
                '上班', '下班', '上学', '放学', '睡了', '起床',
                '在忙', '在家', '出门', '回来', '到了',
                '累了', '饿了', '吃饭', '洗澡'
            ],
            
            # 回应确认类 (中权重)  
            'responses': [
                '哦', '嗯', '啊', '哈', '好的', '知道了',
                '收到', '明白', '懂了', '可以', '行',
                'ok', 'OK', '👌', '好滴', '好嘞'
            ],
            
            # 情感表达类 (中权重)
            'emotions': [
                '哈哈', '嘿嘿', '嘻嘻', '哎呀', '哇',
                '真的吗', '不会吧', '太好了', '完了',
                '烦死了', '好累', '开心', '难过'
            ]
        }
        
        # 扁平化关键词列表（用于快速检测）
        self.all_casual_keywords = []
        for category, keywords in self.casual_keywords.items():
            self.all_casual_keywords.extend(keywords)
            
        # 非信息性内容特征
        self.non_informative_patterns = [
            r'^[哦嗯啊哈]*$',              # 纯语气词
            r'^[👌😀-🙏🌀-🗿🚀-🛿🏀-🏿]+$', # 纯表情符号
            r'^[.,，。！!？?…]+$',         # 纯标点符号
        ]
        
        logger.debug(f"加载聊天检测规则完成，关键词总数: {len(self.all_casual_keywords)}")
    
    async def pre_filter(self, content: str, context: FilterContext) -> bool:
        """预检查：快速跳过明显不是聊天的内容"""
        content_length = len(content.strip())
        
        # 过长的消息通常不是聊天
        if content_length > self.max_chat_length:
            return False
            
        # 包含链接的通常不是聊天 
        if re.search(r'https?://|t\.me/', content):
            return False
            
        # 包含特殊标记的通常不是聊天
        if re.search(r'【|】|\[|\]|#\w+', content):
            return False
            
        return True
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """主要检测逻辑"""
        start_time = time.time()
        
        try:
            # 预处理内容
            cleaned_content = content.strip()
            content_length = len(cleaned_content)
            
            # 计算各维度得分
            length_score = self._calculate_length_score(content_length)
            mention_score = self._calculate_mention_score(cleaned_content)
            casual_score = self._calculate_casual_language_score(cleaned_content)
            structure_score = self._calculate_structure_score(cleaned_content)
            
            # 计算综合得分
            total_score = (
                length_score * self.weights['length'] +
                mention_score * self.weights['mention'] + 
                casual_score * self.weights['casual_language'] +
                structure_score * self.weights['structure']
            )
            
            # 判断是否为聊天内容
            is_chat = total_score >= self.chat_threshold
            
            # 构建检测详情
            details = {
                'content_length': content_length,
                'scores': {
                    'length': length_score,
                    'mention': mention_score, 
                    'casual_language': casual_score,
                    'structure': structure_score,
                    'total': total_score
                },
                'threshold': self.chat_threshold,
                'is_chat': is_chat
            }
            
            # 如果检测到聊天内容，添加具体特征信息
            if is_chat:
                details.update({
                    'detected_mentions': self._extract_mentions(cleaned_content),
                    'detected_casual_words': self._extract_casual_words(cleaned_content),
                    'line_count': len(cleaned_content.split('\n'))
                })
            
            processing_time = (time.time() - start_time) * 1000
            
            result = FilterResult(
                filtered_content=content,  # 聊天检测不修改内容
                passed=not is_chat,        # 检测到聊天内容则不通过
                processing_time_ms=processing_time,
                reason=f"检测到聊天内容 (得分: {total_score:.2f})" if is_chat else None,
                confidence=total_score if is_chat else 1.0 - total_score,
                details=details,
                should_early_stop=is_chat  # 检测到聊天内容时早停
            )
            
            if is_chat:
                logger.info(f"🚫 检测到聊天内容: {cleaned_content[:50]}... "
                           f"(得分: {total_score:.2f}, 长度: {content_length})")
            else:
                logger.debug(f"✅ 非聊天内容通过: 得分 {total_score:.2f}")
                
            return result
            
        except Exception as e:
            logger.error(f"聊天内容检测失败: {e}", exc_info=True)
            
            # 错误时默认通过
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=(time.time() - start_time) * 1000,
                reason=f"检测错误: {str(e)}",
                confidence=0.0,
                details={'error': str(e)}
            )
    
    def _calculate_length_score(self, length: int) -> float:
        """计算长度得分 (越短得分越高)"""
        if length <= 20:  # 极短消息
            return 1.0  # 极短的文本很可能是聊天
        elif length <= self.short_length_threshold:
            return 0.8  # 很短的文本很可能是聊天
        elif length <= self.medium_length_threshold:
            return 0.5  # 中等长度可能是聊天 (提高得分)
        elif length <= self.max_chat_length:
            return 0.2  # 较长的可能性较低 (提高得分)
        else:
            return 0.0  # 很长的基本不是聊天
    
    def _calculate_mention_score(self, content: str) -> float:
        """计算@提及得分"""
        mention_count = 0
        detected_mentions = []
        
        for pattern in self.mention_patterns:
            matches = re.findall(pattern, content)
            mention_count += len(matches)
            detected_mentions.extend(matches)
        
        # 根据提及数量计算得分
        if mention_count >= 2:
            return 1.0  # 多个@提及，很可能是聊天
        elif mention_count == 1:
            return 0.7  # 单个@提及，可能是聊天
        else:
            return 0.0  # 无@提及
    
    def _calculate_casual_language_score(self, content: str) -> float:
        """计算口语化语言得分 (增强检测)"""
        total_score = 0.0
        detected_words = []
        
        # 检查各类别的口语化词汇
        for category, keywords in self.casual_keywords.items():
            category_score = 0.0
            category_weight = {
                'greetings': 1.0,     # 问候类权重最高
                'daily_chat': 1.0,    # 日常对话权重最高  
                'status': 0.8,        # 状态类权重提高
                'responses': 0.8,     # 回应类权重提高
                'emotions': 0.6       # 情感类权重提高
            }.get(category, 0.5)
            
            for keyword in keywords:
                if keyword in content:
                    category_score = min(category_score + 0.4, 1.0)  # 提高单词权重
                    detected_words.append(f"{keyword}({category})")
            
            total_score += category_score * category_weight
        
        # 检查非信息性模式
        for pattern in self.non_informative_patterns:
            if re.search(pattern, content):
                total_score += 0.8  # 提高非信息性内容权重
                detected_words.append("非信息性内容")
                break
        
        # 检查简单问号/感叹号模式
        if re.search(r'^.{0,20}[？?!！]$', content.strip()):
            total_score += 0.5
            detected_words.append("简单疑问/感叹")
        
        # 标准化得分 (降低分母，提高敏感度)
        normalized_score = min(total_score / 1.5, 1.0)
        return normalized_score
    
    def _calculate_structure_score(self, content: str) -> float:
        """计算结构特征得分"""
        lines = content.split('\n')
        line_count = len(lines)
        non_empty_lines = len([line for line in lines if line.strip()])
        
        score = 0.0
        
        # 行数特征 (越少越像聊天)
        if non_empty_lines <= 1:
            score += 0.5  # 单行很可能是聊天
        elif non_empty_lines <= 3:
            score += 0.3  # 少量行可能是聊天
        else:
            score += 0.0  # 多行通常不是聊天
        
        # 复杂标点检查 (越少越像聊天)
        complex_punctuation = ['：', ':', '；', ';', '——', '…', '——']
        complex_count = sum(content.count(p) for p in complex_punctuation)
        if complex_count == 0:
            score += 0.3  # 无复杂标点
        elif complex_count <= 2:
            score += 0.1  # 少量复杂标点
        
        # 信息元素检查 (越少越像聊天)
        info_patterns = [
            r'\d{4}-\d{2}-\d{2}',    # 日期
            r'\d{1,2}:\d{2}',        # 时间
            r'[0-9]{3,}',            # 长数字
            r'[A-Z]{2,}',            # 全大写单词
        ]
        
        info_count = sum(len(re.findall(pattern, content)) for pattern in info_patterns)
        if info_count == 0:
            score += 0.2  # 无信息元素更像聊天
        
        return min(score, 1.0)
    
    def _load_thresholds(self):
        """加载阈值管理器"""
        if not hasattr(self, '_threshold_manager') or self._threshold_manager is None:
            try:
                from app.core.threshold_manager import ThresholdManager
                self._threshold_manager = ThresholdManager()
            except Exception as e:
                logger.warning(f"阈值管理器加载失败: {e}，使用默认值")
                self._threshold_manager = None
    
    def _get_threshold(self, filter_type: str, threshold_type: str) -> float:
        """从阈值管理器获取阈值"""
        if self._threshold_manager:
            try:
                return self._threshold_manager.get_threshold(filter_type, threshold_type)
            except Exception as e:
                logger.warning(f"获取阈值失败: {e}，使用默认值")
        return 0.5  # 默认阈值
    
    def _extract_mentions(self, content: str) -> List[str]:
        """提取@提及"""
        mentions = []
        for pattern in self.mention_patterns:
            mentions.extend(re.findall(pattern, content))
        return list(set(mentions))  # 去重
    
    def _extract_casual_words(self, content: str) -> List[str]:
        """提取检测到的口语化词汇"""
        detected = []
        for word in self.all_casual_keywords:
            if word in content:
                detected.append(word)
        return detected
    
    async def validate_config(self) -> bool:
        """验证过滤器配置"""
        try:
            # 检查阈值范围
            if not (0.0 <= self.chat_threshold <= 1.0):
                logger.error(f"聊天检测阈值超出范围: {self.chat_threshold}")
                return False
            
            # 检查权重配置
            total_weight = sum(self.weights.values())
            if abs(total_weight - 1.0) > 0.01:
                logger.warning(f"权重总和不为1.0: {total_weight}")
            
            logger.info(f"✅ {self.name} 配置验证通过，当前阈值: {self.chat_threshold}")
            return True
            
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False