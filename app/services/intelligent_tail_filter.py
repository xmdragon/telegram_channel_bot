"""
智能尾部过滤器 - 纯数据驱动的机器学习模型
仅基于尾部内容本身进行学习，不依赖上下文或频道信息
"""
import re
import json
import logging
from typing import Tuple, List, Dict, Optional
import numpy as np
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)


class TailFeatureExtractor:
    """尾部内容特征提取器"""
    
    def __init__(self):
        self.learned_keywords = Counter()  # 从训练数据中学习的关键词
        
    def extract_features(self, text: str) -> Dict[str, float]:
        """
        提取文本特征
        
        Returns:
            特征字典，包含各种特征的数值
        """
        if not text:
            return {}
            
        features = {}
        lines = text.split('\n')
        text_length = len(text)
        
        # 1. 链接特征
        links = re.findall(r'https?://[^\s]+|t\.me/[^\s]+', text)
        features['link_count'] = len(links)
        features['link_density'] = len(''.join(links)) / text_length if text_length > 0 else 0
        
        # 2. @用户名特征
        usernames = re.findall(r'@\w+', text)
        features['username_count'] = len(usernames)
        features['username_density'] = len(usernames) / len(lines) if lines else 0
        
        # 3. Emoji特征
        emojis = re.findall(r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF]', text)
        features['emoji_count'] = len(emojis)
        features['emoji_density'] = len(emojis) / text_length if text_length > 0 else 0
        
        # 4. 结构特征
        features['line_count'] = len(lines)
        features['avg_line_length'] = sum(len(line) for line in lines) / len(lines) if lines else 0
        features['has_separator'] = 1.0 if re.search(r'^[-=*#_~]{3,}$', text, re.MULTILINE) else 0.0
        
        # 5. 推广关键词特征（动态学习的）
        promo_score = 0
        for keyword, weight in self.learned_keywords.most_common(20):
            if keyword in text:
                promo_score += weight
        features['promo_keyword_score'] = promo_score
        
        # 6. 格式特征
        features['has_pipe_separator'] = 1.0 if '|' in text else 0.0
        features['has_arrow'] = 1.0 if '↓' in text or '→' in text or '▼' in text or '👇' in text else 0.0
        features['has_brackets'] = 1.0 if re.search(r'\[.*\]|\(.*\)', text) else 0.0
        
        # 7. 常见尾部标识符
        features['has_channel_indicator'] = 1.0 if re.search(r'频道|頻道|channel|群组|群組|group', text, re.IGNORECASE) else 0.0
        features['has_follow_indicator'] = 1.0 if re.search(r'关注|關注|订阅|訂閱|follow|subscribe', text, re.IGNORECASE) else 0.0
        features['has_contact_info'] = 1.0 if re.search(r'微信|wechat|qq|电话|電話|tel|联系|聯繫|contact', text, re.IGNORECASE) else 0.0
        
        return features
    
    def learn_keywords(self, tail_samples: List[str]):
        """从尾部样本中学习关键词"""
        # 提取所有中文词组和英文单词
        for sample in tail_samples:
            # 中文词组（2-4个字）
            chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,4}', sample)
            for word in chinese_words:
                self.learned_keywords[word] += 1
            
            # 英文单词
            english_words = re.findall(r'\b[A-Za-z]{3,}\b', sample.lower())
            for word in english_words:
                self.learned_keywords[word] += 1
        
        logger.info(f"学习了 {len(self.learned_keywords)} 个关键词")


class IntelligentTailFilter:
    """智能尾部过滤器 - 基于纯尾部数据学习"""
    
    def __init__(self):
        self.feature_extractor = TailFeatureExtractor()
        self.tail_samples = []
        self.sample_features = []  # 缓存的特征向量
        self.feature_weights = None  # 特征权重
        self.threshold = 0.5  # 判定阈值（降低以提高敏感度）
        self._last_load_time = 0  # 上次加载时间
        self._reload_interval = 300  # 5分钟重载间隔
        
        # 加载训练数据
        self._load_training_data()
        
    def _load_training_data(self, force_reload=False):
        """加载训练数据（带缓存机制）"""
        import time
        current_time = time.time()
        
        # 如果不是强制重载，且在缓存时间内，跳过加载
        if not force_reload and self._last_load_time > 0:
            if current_time - self._last_load_time < self._reload_interval:
                return
        
        from app.core.path_config import PathConfig
        
        try:
            self._last_load_time = current_time
            tail_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
            if tail_file.exists():
                with open(tail_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    samples = data.get('samples', data) if isinstance(data, dict) else data
                    
                    # 只提取tail_part
                    self.tail_samples = []
                    for sample in samples:
                        if sample.get('tail_part'):
                            self.tail_samples.append(sample['tail_part'])
                    
                    logger.info(f"加载了 {len(self.tail_samples)} 个尾部样本")
                    
                    # 学习关键词
                    self.feature_extractor.learn_keywords(self.tail_samples)
                    
                    # 提取所有样本的特征
                    self._extract_sample_features()
                    
                    # 计算特征权重
                    self._calculate_feature_weights()
                    
        except Exception as e:
            logger.error(f"加载训练数据失败: {e}")
    
    def _extract_sample_features(self):
        """提取所有样本的特征向量"""
        self.sample_features = []
        for sample in self.tail_samples:
            features = self.feature_extractor.extract_features(sample)
            self.sample_features.append(features)
    
    def _calculate_feature_weights(self):
        """计算特征权重（基于特征的区分度和重要性）"""
        if not self.sample_features:
            return
        
        # 获取所有特征名
        all_features = set()
        for features in self.sample_features:
            all_features.update(features.keys())
        
        # 基础权重（根据特征重要性预设）
        base_weights = {
            'link_count': 0.25,  # 链接是强特征
            'username_count': 0.20,  # @用户名也是强特征
            'promo_keyword_score': 0.15,  # 推广关键词
            'emoji_density': 0.10,  # emoji密度
            'has_separator': 0.10,  # 分隔符
            'has_arrow': 0.08,  # 箭头符号
            'line_count': 0.05,  # 行数
            'has_pipe_separator': 0.04,  # 管道分隔符
            'has_brackets': 0.03  # 括号
        }
        
        # 计算每个特征的标准差（标准差大说明区分度高）
        feature_stds = {}
        for feature_name in all_features:
            values = [f.get(feature_name, 0) for f in self.sample_features]
            if values:
                feature_stds[feature_name] = np.std(values)
        
        # 结合基础权重和标准差
        self.feature_weights = {}
        for feature_name in all_features:
            base_w = base_weights.get(feature_name, 0.01)
            std_w = feature_stds.get(feature_name, 0)
            
            # 组合权重：基础权重70% + 标准差权重30%
            if sum(feature_stds.values()) > 0:
                std_normalized = std_w / sum(feature_stds.values())
            else:
                std_normalized = 1.0 / len(all_features)
            
            self.feature_weights[feature_name] = base_w * 0.7 + std_normalized * 0.3
        
        # 归一化权重
        total_weight = sum(self.feature_weights.values())
        if total_weight > 0:
            self.feature_weights = {
                name: weight / total_weight
                for name, weight in self.feature_weights.items()
            }
        
        logger.info(f"计算了 {len(self.feature_weights)} 个特征的权重")
    
    def calculate_similarity(self, text: str) -> float:
        """
        计算文本与训练样本的相似度
        
        Returns:
            相似度分数 (0-1)
        """
        if not self.tail_samples:
            return 0.0
        
        # 提取特征
        features = self.feature_extractor.extract_features(text)
        
        if not features or not self.sample_features:
            return 0.0
        
        # 计算与每个样本的相似度
        similarities = []
        for sample_feat in self.sample_features:
            similarity = self._compute_feature_similarity(features, sample_feat)
            similarities.append(similarity)
        
        # 返回最大相似度
        return max(similarities) if similarities else 0.0
    
    def _compute_feature_similarity(self, feat1: Dict, feat2: Dict) -> float:
        """计算两个特征向量的相似度"""
        if not self.feature_weights:
            return 0.0
        
        similarity = 0.0
        total_weight = 0.0
        
        for feature_name, weight in self.feature_weights.items():
            val1 = feat1.get(feature_name, 0)
            val2 = feat2.get(feature_name, 0)
            
            # 计算该特征的相似度（使用1-normalized_diff）
            max_val = max(abs(val1), abs(val2))
            if max_val > 0:
                feature_sim = 1 - abs(val1 - val2) / max_val
            else:
                feature_sim = 1.0 if val1 == val2 else 0.0
            
            similarity += feature_sim * weight
            total_weight += weight
        
        return similarity / total_weight if total_weight > 0 else 0.0
    
    def is_tail(self, text: str) -> bool:
        """
        判断文本是否为尾部推广
        
        Args:
            text: 要检测的文本
            
        Returns:
            是否为尾部
        """
        if not text or len(text) < 10:
            return False
        
        # 0. 完全匹配检查：如果与训练样本完全匹配，直接返回True
        text_stripped = text.strip()
        for sample in self.tail_samples:
            sample_stripped = sample.strip()
            # 完全匹配或包含匹配（训练样本包含在检测文本中）
            if text_stripped == sample_stripped or sample_stripped in text_stripped:
                logger.info(f"完全匹配训练样本，直接过滤")
                return True
            # 检测文本包含在训练样本中（检测文本是训练样本的子集）
            if text_stripped in sample_stripped and len(text_stripped) >= len(sample_stripped) * 0.8:
                logger.info(f"高度匹配训练样本（80%+重合），直接过滤")
                return True
        
        # 提取特征
        features = self.feature_extractor.extract_features(text)
        
        # 四层判断机制（仅用于部分匹配情况）
        
        # 1. 移除了过激的快速判断规则（之前误判正常内容）
        
        # 2. 特征得分判断：特征得分很高直接过滤
        feature_score = self._calculate_feature_score(features)
        if feature_score > 0.8:  # 提高阈值，减少误判
            return True
        
        # 3. 高相似度判断：与训练样本高度相似
        similarity = self.calculate_similarity(text)
        if similarity > 0.85:  # 85%以上相似度直接过滤
            logger.info(f"高相似度匹配 ({similarity:.2f})，直接过滤")
            return True
        
        # 4. 综合判断：特征+相似度综合评估（使用阈值）
        if feature_score > 0.25:  # 有一定特征才进行综合判断
            # 动态阈值：特征越明显，相似度要求越低
            dynamic_threshold = self.threshold - (feature_score * 0.2)
            
            # 综合得分
            final_score = similarity * 0.5 + feature_score * 0.5
            
            return final_score > dynamic_threshold
        
        return False
    
    def _calculate_feature_score(self, features: Dict) -> float:
        """计算特征得分（更精细的评分）"""
        score = 0.0
        
        # 链接特征（最强信号）
        link_count = features.get('link_count', 0)
        if link_count >= 2:
            score += 0.35
        elif link_count == 1:
            score += 0.25
        
        # 用户名特征
        username_count = features.get('username_count', 0)
        if username_count >= 2:
            score += 0.25
        elif username_count == 1:
            score += 0.15
        
        # Emoji密度（广告常用emoji）
        emoji_density = features.get('emoji_density', 0)
        if emoji_density > 0.15:
            score += 0.15
        elif emoji_density > 0.1:
            score += 0.10
        elif emoji_density > 0.05:
            score += 0.05
        
        # 分隔符（明显的结构特征）
        if features.get('has_separator', 0) > 0:
            score += 0.15
        
        # 推广关键词（从训练数据学习）
        keyword_score = features.get('promo_keyword_score', 0)
        if keyword_score > 10:
            score += 0.20
        elif keyword_score > 5:
            score += 0.15
        elif keyword_score > 0:
            score += 0.10
        
        # 箭头和管道符号
        if features.get('has_arrow', 0) > 0:
            score += 0.08
        if features.get('has_pipe_separator', 0) > 0:
            score += 0.07
        
        # 新增特征评分
        if features.get('has_channel_indicator', 0) > 0:
            score += 0.12  # 频道标识符权重较高
        if features.get('has_follow_indicator', 0) > 0:
            score += 0.10
        if features.get('has_contact_info', 0) > 0:
            score += 0.15  # 联系信息权重很高
        
        return min(score, 1.0)
    
    def filter_message(self, content: str) -> Tuple[str, bool, Optional[str]]:
        """
        过滤消息中的尾部（简化逻辑：只要匹配就过滤）
        
        Args:
            content: 完整消息内容
            
        Returns:
            (过滤后内容, 是否有尾部, 尾部内容)
        """
        import re
        
        if not content:
            return content, False, None
        
        lines = content.split('\n')
        
        # 策略1：快速检测明显的分隔符
        separator_patterns = [
            r'^[-=*#_~]{3,}$',  # 常见分隔符
            r'^[—]+$',  # 中文破折号
            r'^\s*[📣🔔😉👌]+\s*$'  # emoji分隔行
        ]
        
        separator_line = -1
        # 缩小扫描范围，从最后10行开始扫描
        scan_start = max(0, len(lines) - 10)
        for i in range(len(lines) - 1, scan_start, -1):
            for pattern in separator_patterns:
                if re.match(pattern, lines[i].strip()):
                    separator_line = i
                    break
            if separator_line != -1:
                break
        
        # 如果找到分隔符，从分隔符开始检查
        if separator_line != -1:
            potential_tail = '\n'.join(lines[separator_line:])
            if self.is_tail(potential_tail):
                clean_content = '\n'.join(lines[:separator_line]).rstrip()
                # 简化：只要有内容就返回，不管比例
                if clean_content:
                    return clean_content, True, potential_tail
        
        # 策略2：智能扫描（找到最大的尾部范围）
        best_split = -1
        best_tail = None
        
        # 从后往前扫描，找到最早的尾部起始位置
        # 缩小扫描范围，最多扫描10行
        scan_end = max(1, len(lines) - 10)
        for i in range(len(lines) - 1, scan_end - 1, -1):  # 从倒数第二行扫描
            potential_tail = '\n'.join(lines[i:])
            
            # 跳过太短的内容（降低最小长度）
            if len(potential_tail) < 10:
                continue
            
            # 检查是否为尾部
            if self.is_tail(potential_tail):
                # 记录这个位置（继续向前扫描，找更大的尾部）
                best_split = i
                best_tail = potential_tail
            else:
                # 如果不是尾部了，停止扫描
                if best_split != -1:
                    break
        
        # 如果找到尾部
        if best_split != -1 and best_tail:
            clean_content = '\n'.join(lines[:best_split]).rstrip()
            
            # 简化的判断逻辑
            # 1. 如果有正文内容（>5字符），直接返回
            if clean_content and len(clean_content) > 5:
                # 确保正文有基本内容
                has_content = bool(re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]+', clean_content))
                if has_content:
                    return clean_content, True, best_tail
            
            # 2. 如果没有正文或正文太短，可能整条都是推广
            if best_split <= 1:  # 只剩第一行或没有正文
                # 检查第一行是否也是推广
                if lines and self.is_tail(lines[0]):
                    return "", True, content  # 整条都是推广
                elif clean_content:  # 有短正文
                    return clean_content, True, best_tail
        
        return content, False, None
    
    def add_training_sample(self, tail_text: str):
        """
        添加新的训练样本
        
        Args:
            tail_text: 尾部文本
        """
        if tail_text and tail_text not in self.tail_samples:
            self.tail_samples.append(tail_text)
            
            # 更新关键词
            self.feature_extractor.learn_keywords([tail_text])
            
            # 重新提取特征
            self._extract_sample_features()
            
            # 重新计算权重
            self._calculate_feature_weights()
            
            # 强制重新加载以获取最新数据
            self._load_training_data(force_reload=True)
            
            logger.info(f"添加了新的训练样本，当前共 {len(self.tail_samples)} 个样本")
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            'total_samples': len(self.tail_samples),
            'learned_keywords': len(self.feature_extractor.learned_keywords),
            'top_keywords': self.feature_extractor.learned_keywords.most_common(10),
            'feature_count': len(self.feature_weights) if self.feature_weights else 0,
            'threshold': self.threshold
        }


# 全局实例
intelligent_tail_filter = IntelligentTailFilter()