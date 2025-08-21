"""
模式匹配广告检测器
使用正则表达式模式匹配检测广告内容
"""
import logging
import re
from typing import Dict, Any, List, Tuple

from app.services.rule_manager import rule_manager

logger = logging.getLogger(__name__)


class PatternAdDetector:
    """模式匹配广告检测器"""
    
    def __init__(self, pattern_weights: Dict[str, Any] = None):
        self.pattern_weights = pattern_weights or {}
        self.compiled_patterns = []
        self._rule_manager_initialized = False
    
    async def _ensure_rule_manager_initialized(self):
        """确保规则管理器已初始化"""
        if not self._rule_manager_initialized:
            try:
                await rule_manager.initialize()
                await self._load_pattern_rules()
                self._rule_manager_initialized = True
                logger.debug("规则管理器初始化完成，模式检测器规则已加载")
            except Exception as e:
                logger.error(f"规则管理器初始化失败: {e}")
                # 即使失败也标记为已尝试，避免重复初始化
                self._rule_manager_initialized = True
                # 加载空规则以避免错误
                self.compiled_patterns = []
    
    async def _load_pattern_rules(self):
        """从规则管理器加载模式检测规则"""
        try:
            # 获取推广模式
            promo_patterns = rule_manager.get_promo_patterns()
            
            # 获取高危关键词（也用于模式检测）
            high_risk_patterns = rule_manager.get_high_risk_keywords()
            
            # 合并所有模式
            self.compiled_patterns = promo_patterns + high_risk_patterns
            
            logger.debug(f"从规则管理器加载了 {len(self.compiled_patterns)} 个模式检测规则")
            
        except Exception as e:
            logger.error(f"从规则管理器加载模式失败: {e}")
            # 降级到空规则列表
            self.compiled_patterns = []
    
    async def detect(self, content: str) -> Dict[str, Any]:
        """模式匹配广告检测"""
        # 确保规则管理器已初始化
        await self._ensure_rule_manager_initialized()
        
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'matched_patterns': [],
            'total_weight': 0,
            'method': '模式匹配检测'
        }
        
        total_weight = 0
        matched_patterns = []
        
        # 检查所有预定义模式
        for pattern, weight in self.compiled_patterns:
            matches = pattern.findall(content)
            if matches:
                matched_patterns.append({
                    'pattern': pattern.pattern,
                    'weight': weight,
                    'matches': matches
                })
                total_weight += weight
        
        result['matched_patterns'] = matched_patterns
        result['total_weight'] = total_weight
        
        # 根据权重判断
        if total_weight >= 10:  # 高权重模式
            result['is_ad'] = True
            result['confidence'] = min(1.0, total_weight / 15.0)
        elif total_weight >= 5:  # 中等权重
            result['is_ad'] = True
            result['confidence'] = min(0.8, total_weight / 10.0)
            
        return result
    
    def get_pattern_count(self) -> int:
        """获取模式数量"""
        return len(self.compiled_patterns)