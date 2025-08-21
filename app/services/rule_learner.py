"""
自动规则学习机制
从被检测为广告的消息中学习新的过滤规则
"""
import re
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import Counter

from app.services.rule_manager import rule_manager

logger = logging.getLogger(__name__)


class RuleLearner:
    """自动规则学习器"""
    
    def __init__(self):
        self.learning_enabled = True
        self.min_pattern_length = 3
        self.max_pattern_length = 50
        self.min_occurrence_count = 3  # 最少出现次数才考虑学习
        self.confidence_threshold = 0.8
        self.pattern_cache = {}  # 临时模式缓存
        self.learning_stats = {
            'total_analyzed': 0,
            'patterns_extracted': 0,
            'patterns_learned': 0,
            'last_learning': None
        }
    
    async def analyze_ad_message(self, content: str, confidence: float, 
                               detection_method: str = 'unknown', 
                               category: str = 'unknown') -> Dict[str, Any]:
        """
        分析广告消息并提取潜在的学习模式
        
        Args:
            content: 消息内容
            confidence: 检测置信度
            detection_method: 检测方法
            category: 广告类别
        
        Returns:
            分析结果和建议的学习模式
        """
        if not self.learning_enabled or confidence < self.confidence_threshold:
            return {'learned': False, 'reason': '学习已禁用或置信度不足'}
        
        try:
            self.learning_stats['total_analyzed'] += 1
            
            # 提取各种类型的模式
            extracted_patterns = []
            
            # 1. 提取关键词组合模式
            keyword_patterns = self._extract_keyword_patterns(content)
            extracted_patterns.extend(keyword_patterns)
            
            # 2. 提取URL模式
            url_patterns = self._extract_url_patterns(content)
            extracted_patterns.extend(url_patterns)
            
            # 3. 提取表情符号模式
            emoji_patterns = self._extract_emoji_patterns(content)
            extracted_patterns.extend(emoji_patterns)
            
            # 4. 提取数字金钱模式
            money_patterns = self._extract_money_patterns(content)
            extracted_patterns.extend(money_patterns)
            
            # 5. 提取联系方式模式
            contact_patterns = self._extract_contact_patterns(content)
            extracted_patterns.extend(contact_patterns)
            
            self.learning_stats['patterns_extracted'] += len(extracted_patterns)
            
            # 缓存模式用于频次统计
            for pattern_info in extracted_patterns:
                pattern = pattern_info['pattern']
                self.pattern_cache[pattern] = self.pattern_cache.get(pattern, 0) + 1
            
            # 检查是否有模式达到学习阈值
            learned_patterns = []
            for pattern_info in extracted_patterns:
                pattern = pattern_info['pattern']
                if self.pattern_cache[pattern] >= self.min_occurrence_count:
                    # 尝试学习这个模式
                    if await self._learn_pattern(pattern_info, confidence, category):
                        learned_patterns.append(pattern_info)
                        # 从缓存中移除已学习的模式
                        self.pattern_cache.pop(pattern, None)
            
            if learned_patterns:
                self.learning_stats['patterns_learned'] += len(learned_patterns)
                self.learning_stats['last_learning'] = datetime.now().isoformat()
                
                logger.info(f"学习了 {len(learned_patterns)} 个新模式，来源: {detection_method}")
            
            return {
                'learned': len(learned_patterns) > 0,
                'patterns_extracted': len(extracted_patterns),
                'patterns_learned': len(learned_patterns),
                'learned_patterns': learned_patterns,
                'confidence': confidence,
                'category': category
            }
            
        except Exception as e:
            logger.error(f"分析广告消息失败: {e}")
            return {'learned': False, 'reason': f'分析失败: {e}'}
    
    def _extract_keyword_patterns(self, content: str) -> List[Dict[str, Any]]:
        """提取关键词组合模式"""
        patterns = []
        
        # 高频广告关键词组合
        ad_keywords = [
            '博彩', '娱乐城', '平台', '充值', '提款', '出款', 'USDT', 
            '投注', '下注', '赌场', '棋牌', '老虎机', '返水',
            '首充', '优惠', '赠送', '免费', '注册送'
        ]
        
        # 寻找关键词附近的特征词汇
        for keyword in ad_keywords:
            if keyword in content:
                # 提取包含关键词的短语模式
                pattern_match = re.search(f'.{{0,10}}{re.escape(keyword)}.{{0,10}}', content)
                if pattern_match:
                    phrase = pattern_match.group().strip()
                    if len(phrase) >= self.min_pattern_length:
                        patterns.append({
                            'pattern': re.escape(phrase),
                            'type': 'keyword_combination',
                            'weight': 8,
                            'description': f'关键词组合: {phrase[:20]}...',
                            'source_keyword': keyword
                        })
        
        return patterns
    
    def _extract_url_patterns(self, content: str) -> List[Dict[str, Any]]:
        """提取URL模式"""
        patterns = []
        
        # 非Telegram链接
        url_pattern = r'https?://(?!(?:t\.me|telegram\.me|telegra\.ph))[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=]+'
        urls = re.findall(url_pattern, content)
        
        for url in urls:
            # 提取域名部分作为模式
            domain_match = re.search(r'https?://([^/]+)', url)
            if domain_match:
                domain = domain_match.group(1)
                patterns.append({
                    'pattern': re.escape(domain),
                    'type': 'external_domain',
                    'weight': 10,
                    'description': f'外部域名: {domain}',
                    'source_url': url
                })
        
        return patterns
    
    def _extract_emoji_patterns(self, content: str) -> List[Dict[str, Any]]:
        """提取表情符号模式"""
        patterns = []
        
        # 识别表情符号密集的模式
        emoji_pattern = r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002600-\U000027BF\U0001F900-\U0001F9FF]+'
        emoji_sequences = re.findall(emoji_pattern, content)
        
        for seq in emoji_sequences:
            if len(seq) >= 3:  # 3个或以上连续表情符号
                patterns.append({
                    'pattern': re.escape(seq),
                    'type': 'emoji_sequence',
                    'weight': 6,
                    'description': f'表情符号序列: {seq[:10]}...',
                    'emoji_count': len(seq)
                })
        
        return patterns
    
    def _extract_money_patterns(self, content: str) -> List[Dict[str, Any]]:
        """提取金钱数字模式"""
        patterns = []
        
        # 金钱相关模式
        money_patterns = [
            r'[0-9]+万.*(?:投入|资金|奖金|返水)',
            r'(?:日赚|月入|年入)[0-9]+[万元]',
            r'[0-9]+(?:倍|%)\s*(?:返水|优惠|赠送)',
            r'(?:首充|首存)[0-9]+.*(?:送|赠)',
        ]
        
        for pattern in money_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if len(match.strip()) >= self.min_pattern_length:
                    patterns.append({
                        'pattern': pattern,
                        'type': 'money_pattern',
                        'weight': 9,
                        'description': f'金钱模式: {match[:20]}...',
                        'matched_text': match
                    })
        
        return patterns
    
    def _extract_contact_patterns(self, content: str) -> List[Dict[str, Any]]:
        """提取联系方式模式"""
        patterns = []
        
        # 联系方式模式
        contact_patterns = [
            r'(?:微信|WeChat|wechat)[：:]\s*[a-zA-Z0-9_]+',
            r'(?:QQ|qq)[：:]\s*[0-9]+',
            r'(?:客服|官方|联系)[：:].{0,20}[0-9]+',
            r'@[a-zA-Z][a-zA-Z0-9_]{3,}(?:\s|$)',  # Telegram用户名
        ]
        
        for pattern in contact_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if len(match.strip()) >= self.min_pattern_length:
                    patterns.append({
                        'pattern': pattern,
                        'type': 'contact_pattern',
                        'weight': 7,
                        'description': f'联系方式: {match[:20]}...',
                        'matched_text': match
                    })
        
        return patterns
    
    async def _learn_pattern(self, pattern_info: Dict[str, Any], 
                           confidence: float, category: str) -> bool:
        """学习单个模式"""
        try:
            pattern = pattern_info['pattern']
            weight = pattern_info.get('weight', 5)
            description = pattern_info.get('description', '自动学习模式')
            pattern_type = pattern_info.get('type', 'unknown')
            
            # 验证模式有效性
            if not self._validate_pattern(pattern):
                logger.debug(f"模式验证失败: {pattern}")
                return False
            
            # 检查是否与现有规则重复
            if await self._is_duplicate_pattern(pattern):
                logger.debug(f"模式重复，跳过: {pattern}")
                return False
            
            # 添加到学习规则
            success = await rule_manager.add_learned_pattern(
                pattern=pattern,
                weight=weight,
                category=category,
                description=f"{description} (类型: {pattern_type})",
                confidence=confidence
            )
            
            if success:
                logger.info(f"成功学习新模式: {pattern} (权重: {weight}, 类别: {category})")
                return True
            else:
                logger.debug(f"模式学习失败: {pattern}")
                return False
                
        except Exception as e:
            logger.error(f"学习模式失败: {e}")
            return False
    
    def _validate_pattern(self, pattern: str) -> bool:
        """验证模式有效性"""
        try:
            # 检查长度
            if len(pattern) < self.min_pattern_length or len(pattern) > self.max_pattern_length:
                return False
            
            # 检查是否可以编译为正则表达式
            re.compile(pattern)
            
            # 避免过于宽泛的模式
            if pattern in ['.', '.*', '.+', '\\d+', '\\w+']:
                return False
            
            # 避免纯数字或纯标点
            if re.match(r'^[0-9\s\-_]+$', pattern) or re.match(r'^[^\w\s]+$', pattern):
                return False
            
            return True
            
        except re.error:
            return False
    
    async def _is_duplicate_pattern(self, pattern: str) -> bool:
        """检查是否与现有规则重复"""
        try:
            # 获取所有现有模式
            all_patterns = rule_manager.get_all_patterns()
            
            for category_patterns in all_patterns.values():
                for pattern_info in category_patterns:
                    existing_pattern = pattern_info.get('pattern_str', '')
                    if existing_pattern == pattern:
                        return True
                    
                    # 检查是否为子集或超集
                    if pattern in existing_pattern or existing_pattern in pattern:
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查重复模式失败: {e}")
            return True  # 出错时保守处理，认为重复
    
    async def cleanup_ineffective_patterns(self, days_threshold: int = 30, 
                                         usage_threshold: int = 1):
        """清理无效的学习模式"""
        try:
            logger.info("开始清理无效的学习模式")
            
            # 获取学习模式
            learned_patterns = rule_manager.get_patterns_by_category('learned_patterns')
            
            patterns_to_remove = []
            cutoff_date = datetime.now() - timedelta(days=days_threshold)
            
            for pattern_info in learned_patterns:
                created_at_str = pattern_info.get('created_at')
                usage_count = pattern_info.get('usage_count', 0)
                
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                        # 如果模式创建时间超过阈值且使用次数低于阈值
                        if created_at < cutoff_date and usage_count < usage_threshold:
                            patterns_to_remove.append(pattern_info.get('pattern'))
                    except ValueError:
                        # 日期格式错误的模式也清理掉
                        patterns_to_remove.append(pattern_info.get('pattern'))
            
            # 移除无效模式
            for pattern in patterns_to_remove:
                await rule_manager.remove_pattern('learned_patterns', pattern)
            
            logger.info(f"清理了 {len(patterns_to_remove)} 个无效的学习模式")
            
        except Exception as e:
            logger.error(f"清理无效模式失败: {e}")
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """获取学习统计信息"""
        stats = self.learning_stats.copy()
        stats['pattern_cache_size'] = len(self.pattern_cache)
        stats['learning_enabled'] = self.learning_enabled
        return stats
    
    def enable_learning(self, enabled: bool = True):
        """启用或禁用学习功能"""
        self.learning_enabled = enabled
        logger.info(f"自动学习功能{'启用' if enabled else '禁用'}")


# 全局单例实例
rule_learner = RuleLearner()