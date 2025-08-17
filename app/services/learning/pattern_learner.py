"""
模式学习器模块
负责学习推广内容的模式，而不是记忆文本
"""
import re
import json
import logging
import hashlib
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

from .feature_extractor import FeatureExtractor

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