"""
智能自学习系统
解决原始训练机制的问题，实现真正的智能化学习
"""
import re
import json
import logging
import hashlib
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from pathlib import Path
import numpy as np
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class Pattern:
    """推广内容模式"""
    id: str
    structure: List[str]  # 结构模式
    features: Dict[str, float]  # 特征向量
    confidence: float  # 置信度
    created_at: str
    usage_count: int = 0
    success_rate: float = 0.0
    last_used: Optional[str] = None


class FeatureExtractor:
    """
    特征提取器 - 从文本中提取多维度特征
    不记忆原始文本，只提取特征
    """
    
    def __init__(self):
        self.promo_keywords = {
            '订阅', '订閱', '关注', '關注', '加入', '投稿', '爆料',
            '商务', '商務', '联系', '聯繫', '频道', '頻道', '客服'
        }
        self.link_patterns = [
            r't\.me/[\w+]+',
            r'@[\w]+',
            r'https?://[\w\./]+',
        ]
    
    def extract_features(self, text: str, position_ratio: float = 1.0) -> Dict[str, float]:
        """
        提取文本特征
        
        Args:
            text: 待分析文本
            position_ratio: 文本在消息中的位置比例（0=开头, 1=结尾）
            
        Returns:
            特征字典
        """
        if not text:
            return {}
        
        lines = text.split('\n')
        text_length = len(text)
        
        features = {
            # 结构特征
            'line_count': len(lines),
            'avg_line_length': sum(len(line) for line in lines) / max(len(lines), 1),
            'empty_line_ratio': sum(1 for line in lines if not line.strip()) / max(len(lines), 1),
            
            # 链接特征
            'has_telegram_link': 1.0 if 't.me/' in text else 0.0,
            'has_username': 1.0 if '@' in text else 0.0,
            'link_count': len(re.findall(r'(?:t\.me/|@|https?://)', text)),
            'link_density': len(re.findall(r'(?:t\.me/|@|https?://)', text)) / max(text_length, 1) * 100,
            
            # 表情符号特征
            'emoji_count': len(re.findall(r'[😀-🙏🌀-🗿🚀-🛿🏀-🏿]', text)),
            'emoji_density': len(re.findall(r'[😀-🙏🌀-🗿🚀-🛿🏀-🏿]', text)) / max(text_length, 1),
            
            # 关键词特征
            'promo_keyword_count': sum(1 for kw in self.promo_keywords if kw in text),
            'promo_keyword_density': sum(1 for kw in self.promo_keywords if kw in text) / max(len(lines), 1),
            
            # 格式特征
            'has_separator': 1.0 if re.search(r'^[-=*#_~—]{3,}$', text, re.MULTILINE) else 0.0,
            'bold_text_ratio': text.count('**') / max(text_length, 1) * 100,
            
            # 位置特征
            'position_ratio': position_ratio,
            'is_at_end': 1.0 if position_ratio > 0.8 else 0.0,
            
            # 语义特征
            'has_call_to_action': 1.0 if any(word in text for word in ['订阅', '关注', '加入', '点击']) else 0.0,
            'has_contact_info': 1.0 if any(word in text for word in ['联系', '投稿', '客服', '商务']) else 0.0,
        }
        
        return features
    
    def extract_structure(self, text: str) -> List[str]:
        """
        提取文本结构模式
        将文本转换为抽象的结构表示
        """
        lines = text.split('\n')
        structure = []
        
        for line in lines:
            line = line.strip()
            
            if not line:
                structure.append('EMPTY')
            elif '@' in line and len(line) < 50:
                structure.append('USERNAME')
            elif 't.me/' in line:
                structure.append('TELEGRAM_LINK')
            elif re.match(r'^https?://', line):
                structure.append('URL')
            elif re.match(r'^[-=*#_~—]{3,}$', line):
                structure.append('SEPARATOR')
            elif re.match(r'^[😀-🙏🌀-🗿🚀-🛿🏀-🏿]{2,}', line):
                structure.append('EMOJI_LINE')
            elif any(kw in line for kw in ['订阅', '关注', '频道']):
                structure.append('SUBSCRIBE_TEXT')
            elif any(kw in line for kw in ['投稿', '爆料', '联系']):
                structure.append('CONTACT_TEXT')
            elif len(line) < 20:
                structure.append('SHORT_TEXT')
            else:
                structure.append('LONG_TEXT')
        
        return structure


class SampleValidator:
    """
    样本验证器 - 确保训练样本的质量
    """
    
    def __init__(self):
        self.news_keywords = {
            '政府', '国家', '总统', '部长', '警方', '法院',
            '亿', '万', '美元', '人民币', '股票', '经济',
            '公司', '企业', '集团', '发布', '宣布', '表示'
        }
        self.min_sample_length = 20
        self.max_sample_length = 500
    
    def validate(self, sample: str, original_message: str, message_id: int = None) -> Dict[str, Any]:
        """
        验证训练样本的合理性
        
        Args:
            sample: 训练样本
            original_message: 原始消息
            message_id: 消息ID（用于防止自引用）
            
        Returns:
            验证结果
        """
        results = {
            'is_valid': False,
            'confidence': 0.0,
            'checks': {},
            'errors': []
        }
        
        # 1. 基础检查
        if not sample or not original_message:
            results['errors'].append("样本或原始消息为空")
            return results
        
        # 2. 长度检查
        results['checks']['length_valid'] = self.min_sample_length <= len(sample) <= self.max_sample_length
        if not results['checks']['length_valid']:
            results['errors'].append(f"样本长度不合理: {len(sample)}")
        
        # 3. 推广内容检查
        results['checks']['is_promotional'] = self._check_promotional_content(sample)
        if not results['checks']['is_promotional']:
            results['errors'].append("样本不包含推广特征")
        
        # 4. 非正文内容检查
        results['checks']['not_news_content'] = self._check_not_news_content(sample)
        if not results['checks']['not_news_content']:
            results['errors'].append("样本包含新闻正文内容")
        
        # 5. 位置合理性检查
        results['checks']['position_valid'] = self._check_position_validity(sample, original_message)
        if not results['checks']['position_valid']:
            results['errors'].append("样本不在消息尾部")
        
        # 6. 自引用检查
        if message_id:
            results['checks']['no_self_reference'] = self._check_no_self_reference(sample, message_id)
            if not results['checks']['no_self_reference']:
                results['errors'].append("不能用消息自己的内容作为训练样本")
        
        # 计算置信度
        passed_checks = sum(1 for v in results['checks'].values() if v)
        total_checks = len(results['checks'])
        results['confidence'] = passed_checks / max(total_checks, 1)
        
        # 判断是否有效
        results['is_valid'] = (
            results['confidence'] >= 0.7 and
            results['checks'].get('is_promotional', False) and
            results['checks'].get('position_valid', False)
        )
        
        return results
    
    def _check_promotional_content(self, sample: str) -> bool:
        """检查是否包含推广特征"""
        promo_indicators = [
            '@',  # Telegram用户名
            't.me/',  # Telegram链接
            '订阅', '訂閱', '关注', '關注',
            '频道', '頻道', '投稿', '爆料',
            '联系', '聯繫', '商务', '商務'
        ]
        
        # 至少包含2个推广特征
        indicator_count = sum(1 for indicator in promo_indicators if indicator in sample)
        return indicator_count >= 2
    
    def _check_not_news_content(self, sample: str) -> bool:
        """检查是否不包含新闻正文"""
        # 检查是否包含过多新闻关键词
        news_word_count = sum(1 for keyword in self.news_keywords if keyword in sample)
        
        # 如果包含超过3个新闻关键词，可能是正文
        if news_word_count > 3:
            return False
        
        # 检查是否包含日期、金额等
        if re.search(r'\d{4}年\d{1,2}月\d{1,2}日', sample):
            return False
        if re.search(r'\d+[亿万]', sample):
            return False
        
        return True
    
    def _check_position_validity(self, sample: str, original: str) -> bool:
        """检查位置合理性"""
        if sample not in original:
            return False
        
        # 找到样本在原文中的位置
        position = original.rfind(sample)
        if position == -1:
            return False
        
        # 检查是否在消息末尾附近
        after_content = original[position + len(sample):].strip()
        
        # 后面的内容不应该太多
        return len(after_content) < 100
    
    def _check_no_self_reference(self, sample: str, message_id: int) -> bool:
        """检查是否自引用"""
        # 这里需要查询数据库，检查样本是否来自同一条消息
        # 暂时返回True，实际实现时需要查询数据库
        return True


class PatternLearner:
    """
    模式学习器 - 学习推广内容的模式，而不是记忆文本
    """
    
    def __init__(self, storage_path: str = "data/learned_patterns.json"):
        self.storage_path = Path(storage_path)
        self.patterns: List[Pattern] = []
        self.feature_extractor = FeatureExtractor()
        self.load_patterns()
    
    def learn_from_sample(self, sample: str, confidence: float = 0.5) -> Optional[str]:
        """
        从样本中学习模式
        
        Args:
            sample: 训练样本
            confidence: 初始置信度
            
        Returns:
            模式ID
        """
        # 提取特征
        features = self.feature_extractor.extract_features(sample)
        structure = self.feature_extractor.extract_structure(sample)
        
        # 检查是否已存在相似模式
        if self._is_duplicate_pattern(structure, features):
            logger.info("模式已存在，跳过学习")
            return None
        
        # 创建新模式
        pattern = Pattern(
            id=self._generate_pattern_id(structure),
            structure=structure,
            features=features,
            confidence=confidence,
            created_at=datetime.now().isoformat(),
            usage_count=0,
            success_rate=0.0
        )
        
        self.patterns.append(pattern)
        self.save_patterns()
        
        logger.info(f"学习了新模式: {pattern.id}")
        return pattern.id
    
    def match_pattern(self, text: str, position_ratio: float = 1.0) -> Tuple[Optional[Pattern], float]:
        """
        匹配文本与已学习的模式
        
        Args:
            text: 待匹配文本
            position_ratio: 文本在消息中的位置
            
        Returns:
            (最佳匹配模式, 匹配得分)
        """
        if not text or not self.patterns:
            return None, 0.0
        
        # 提取文本特征
        text_features = self.feature_extractor.extract_features(text, position_ratio)
        text_structure = self.feature_extractor.extract_structure(text)
        
        best_pattern = None
        best_score = 0.0
        
        for pattern in self.patterns:
            # 计算结构相似度
            structure_score = self._calculate_structure_similarity(text_structure, pattern.structure)
            
            # 计算特征相似度
            feature_score = self._calculate_feature_similarity(text_features, pattern.features)
            
            # 综合得分
            total_score = (structure_score * 0.4 + feature_score * 0.6) * pattern.confidence
            
            if total_score > best_score:
                best_score = total_score
                best_pattern = pattern
        
        return best_pattern, best_score
    
    def update_pattern_performance(self, pattern_id: str, was_correct: bool):
        """更新模式的性能指标"""
        for pattern in self.patterns:
            if pattern.id == pattern_id:
                pattern.usage_count += 1
                pattern.last_used = datetime.now().isoformat()
                
                # 更新成功率
                if was_correct:
                    pattern.success_rate = (
                        (pattern.success_rate * (pattern.usage_count - 1) + 1) /
                        pattern.usage_count
                    )
                else:
                    pattern.success_rate = (
                        (pattern.success_rate * (pattern.usage_count - 1)) /
                        pattern.usage_count
                    )
                
                # 调整置信度
                if pattern.usage_count >= 10:
                    pattern.confidence = min(1.0, pattern.success_rate * 1.2)
                
                self.save_patterns()
                break
    
    def _is_duplicate_pattern(self, structure: List[str], features: Dict) -> bool:
        """检查是否存在重复模式"""
        for pattern in self.patterns:
            # 结构完全相同
            if pattern.structure == structure:
                # 特征相似度超过90%
                similarity = self._calculate_feature_similarity(features, pattern.features)
                if similarity > 0.9:
                    return True
        return False
    
    def _calculate_structure_similarity(self, struct1: List[str], struct2: List[str]) -> float:
        """计算结构相似度"""
        if not struct1 or not struct2:
            return 0.0
        
        # 使用最长公共子序列算法
        m, n = len(struct1), len(struct2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if struct1[i-1] == struct2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        
        lcs_length = dp[m][n]
        return lcs_length / max(m, n)
    
    def _calculate_feature_similarity(self, feat1: Dict, feat2: Dict) -> float:
        """计算特征相似度"""
        if not feat1 or not feat2:
            return 0.0
        
        # 获取共同特征
        common_keys = set(feat1.keys()) & set(feat2.keys())
        if not common_keys:
            return 0.0
        
        # 计算余弦相似度
        dot_product = sum(feat1[k] * feat2[k] for k in common_keys)
        norm1 = sum(feat1[k]**2 for k in common_keys) ** 0.5
        norm2 = sum(feat2[k]**2 for k in common_keys) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _generate_pattern_id(self, structure: List[str]) -> str:
        """生成模式ID"""
        structure_str = '-'.join(structure[:5])  # 使用前5个结构元素
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        hash_suffix = hashlib.md5(str(structure).encode()).hexdigest()[:6]
        return f"pattern_{timestamp}_{hash_suffix}"
    
    def save_patterns(self):
        """保存模式到文件"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            patterns_data = [asdict(p) for p in self.patterns]
            
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(patterns_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"保存了 {len(self.patterns)} 个模式")
        except Exception as e:
            logger.error(f"保存模式失败: {e}")
    
    def load_patterns(self):
        """从文件加载模式"""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    patterns_data = json.load(f)
                
                self.patterns = [Pattern(**p) for p in patterns_data]
                logger.info(f"加载了 {len(self.patterns)} 个模式")
        except Exception as e:
            logger.error(f"加载模式失败: {e}")
            self.patterns = []


class IntelligentFilterEngine:
    """
    智能过滤引擎 - 使用学习到的模式进行过滤
    """
    
    def __init__(self):
        self.pattern_learner = PatternLearner()
        self.feature_extractor = FeatureExtractor()
        self.min_confidence_threshold = 0.5  # 降低阈值提高敏感度
        self.max_filter_ratio = 0.45  # 最多过滤45%的内容，允许更大尾部
    
    def filter_message(self, message: str) -> Tuple[str, bool, Optional[str]]:
        """
        智能过滤消息
        
        Args:
            message: 原始消息
            
        Returns:
            (过滤后内容, 是否过滤了内容, 被过滤的部分)
        """
        if not message:
            return message, False, None
        
        lines = message.split('\n')
        best_split_point = -1
        best_score = 0.0
        best_tail = None
        exact_match_found = False
        
        # 从后向前扫描，寻找最佳分割点
        for i in range(len(lines) - 1, max(0, len(lines) - 20), -1):
            # 获取候选尾部
            tail_candidate = '\n'.join(lines[i:])
            
            # 0. 检查是否有完全匹配的训练样本（直接过滤，不受阈值限制）
            if self._has_exact_match(tail_candidate):
                logger.info(f"找到完全匹配的训练样本，直接过滤")
                if self._is_safe_to_filter(message, i, tail_candidate):
                    best_split_point = i
                    best_tail = tail_candidate
                    exact_match_found = True
                    best_score = 1.0  # 完全匹配给予最高分数
                    break  # 找到完全匹配就停止扫描
            
            # 计算位置比例
            position_ratio = i / len(lines)
            
            # 匹配模式（仅当没有完全匹配时才使用阈值）
            pattern, score = self.pattern_learner.match_pattern(tail_candidate, position_ratio)
            
            # 高相似度直接通过（不受阈值限制）
            if score > 0.9:  # 90%以上相似度
                if self._is_safe_to_filter(message, i, tail_candidate):
                    best_score = score
                    best_split_point = i
                    best_tail = tail_candidate
                    exact_match_found = True
                    break
            
            # 部分匹配情况使用阈值判断
            if score > self.min_confidence_threshold and score > best_score:
                # 安全检查
                if self._is_safe_to_filter(message, i, tail_candidate):
                    best_score = score
                    best_split_point = i
                    best_tail = tail_candidate
        
        # 应用过滤
        if best_split_point > 0 and best_tail:
            filtered = '\n'.join(lines[:best_split_point]).rstrip()
            
            # 完全匹配或高相似度情况跳过比例检查
            if not exact_match_found:
                # 最终安全检查（仅对部分匹配情况）
                filter_ratio = 1 - len(filtered) / len(message)
                if filter_ratio > self.max_filter_ratio:
                    logger.warning(f"过滤比例过大 ({filter_ratio:.1%})，取消过滤")
                    return message, False, None
            
            logger.info(f"成功过滤尾部，置信度: {best_score:.2f}，完全匹配: {exact_match_found}")
            return filtered, True, best_tail
        
        return message, False, None
    
    def _has_exact_match(self, text: str) -> bool:
        """
        检查是否有完全匹配的训练样本
        
        Args:
            text: 待检查的文本
            
        Returns:
            是否有完全匹配
        """
        if not text:
            return False
            
        text_stripped = text.strip()
        
        # 检查所有已学习的模式中是否有原始训练数据
        # 这里需要访问原始训练数据，暂时使用pattern learner的方式
        try:
            from app.core.path_config import PathConfig
            import json
            
            # 检查尾部过滤样本
            tail_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
            if tail_file.exists():
                with open(tail_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    samples = data.get('samples', data) if isinstance(data, dict) else data
                    
                    for sample in samples:
                        if isinstance(sample, dict) and sample.get('tail_part'):
                            sample_text = sample['tail_part'].strip()
                        elif isinstance(sample, str):
                            sample_text = sample.strip()
                        else:
                            continue
                            
                        # 完全匹配或高度重合
                        if text_stripped == sample_text:
                            return True
                        elif sample_text in text_stripped or text_stripped in sample_text:
                            # 计算重合度
                            shorter = min(len(text_stripped), len(sample_text))
                            longer = max(len(text_stripped), len(sample_text))
                            if shorter >= longer * 0.8:  # 80%以上重合
                                return True
                                
        except Exception as e:
            logger.warning(f"检查完全匹配时出错: {e}")
        
        return False
    
    def _is_safe_to_filter(self, message: str, split_point: int, tail: str) -> bool:
        """
        安全检查，确保不会破坏正文
        """
        lines = message.split('\n')
        
        # 检查剩余内容长度
        remaining = '\n'.join(lines[:split_point])
        if len(remaining) < 50:
            return False
        
        # 检查是否包含重要信息
        important_patterns = [
            r'\d{4}年\d{1,2}月\d{1,2}日',  # 日期
            r'\d+[亿万]',  # 金额
            r'[^，。！？]{50,}',  # 长句子（可能是正文）
        ]
        
        for pattern in important_patterns:
            if re.search(pattern, tail):
                # 尾部包含重要信息，可能不安全
                return False
        
        return True


class IntelligentLearningSystem:
    """
    智能学习系统主类 - 整合所有组件
    """
    
    def __init__(self):
        self.feature_extractor = FeatureExtractor()
        self.validator = SampleValidator()
        self.pattern_learner = PatternLearner()
        self.filter_engine = IntelligentFilterEngine()
        
        # 学习统计
        self.stats = {
            'samples_processed': 0,
            'samples_accepted': 0,
            'samples_rejected': 0,
            'patterns_learned': 0
        }
    
    def add_training_sample(self, tail_part: str = None, original_content: str = None, message_id: int = None, sample: str = None, original_message: str = None) -> Dict[str, Any]:
        """
        添加训练样本（支持新旧接口）
        
        Args:
            tail_part: 尾部内容（新接口）
            original_content: 原始消息内容（可选）
            message_id: 消息ID
            sample: 训练样本（旧接口兼容）
            original_message: 原始消息（旧接口兼容）
            
        Returns:
            处理结果
        """
        result = {
            'success': False,
            'message': '',
            'pattern_id': None,
            'validation': None
        }
        
        # 兼容旧接口
        if sample is not None:
            tail_part = sample
        if original_message is not None:
            original_content = original_message
        
        if not tail_part:
            result['message'] = "尾部内容不能为空"
            return result
        
        # 验证样本（原始内容可以为空）
        validation = self.validator.validate(tail_part, original_content, message_id)
        result['validation'] = validation
        
        self.stats['samples_processed'] += 1
        
        if not validation['is_valid']:
            self.stats['samples_rejected'] += 1
            result['message'] = f"样本验证失败: {', '.join(validation['errors'])}"
            logger.warning(result['message'])
            return result
        
        # 学习模式
        pattern_id = self.pattern_learner.learn_from_sample(tail_part, validation['confidence'])
        
        if pattern_id:
            self.stats['samples_accepted'] += 1
            self.stats['patterns_learned'] += 1
            result['success'] = True
            result['pattern_id'] = pattern_id
            result['message'] = f"成功学习新模式: {pattern_id}"
            logger.info(result['message'])
        else:
            result['message'] = "模式已存在，未学习新内容"
            
        return result
    
    def filter_message(self, message: str) -> Tuple[str, bool, Optional[str]]:
        """
        使用智能过滤引擎过滤消息
        """
        return self.filter_engine.filter_message(message)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        return {
            'learning_stats': self.stats,
            'pattern_count': len(self.pattern_learner.patterns),
            'patterns': [
                {
                    'id': p.id,
                    'confidence': p.confidence,
                    'usage_count': p.usage_count,
                    'success_rate': p.success_rate
                }
                for p in self.pattern_learner.patterns[:10]  # 只返回前10个
            ]
        }


# 创建全局实例
intelligent_learning_system = IntelligentLearningSystem()