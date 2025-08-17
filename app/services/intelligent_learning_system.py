"""
智能自学习系统 - 重构版本
解决原始训练机制的问题，实现真正的智能化学习
"""
import logging
from typing import Dict, Tuple, Optional, Any

from .learning import (
    FeatureExtractor,
    SampleValidator, 
    PatternLearner,
    IntelligentFilterEngine
)

logger = logging.getLogger(__name__)


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
    
    def add_training_sample(self, tail_part: str = None, original_content: str = None, 
                          message_id: int = None, sample: str = None, 
                          original_message: str = None) -> Dict[str, Any]:
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