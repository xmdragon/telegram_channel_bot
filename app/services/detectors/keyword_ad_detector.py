"""
关键词广告检测器 - Linus式简洁设计
基于正则表达式和关键词匹配的广告检测方案

"复杂性是万恶之源" - 移除ONNX，回归简单的规则匹配

Author: Claude
Created: 2025-09-09
"""

import logging
import time
import re
from typing import Dict, List, Optional, Any, Tuple
import json
from pathlib import Path

from app.services.filters.base import BaseFilter, FilterContext, FilterResult
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class KeywordAdDetector(BaseFilter):
    """关键词广告检测器 - 基于正则表达式的广告检测"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("keyword_ad_detector", config)
        
        # 加载过滤规则
        self.filter_rules = self._load_filter_rules()
        
        # 配置参数
        self.auto_reject_ads = self.config.get('auto_reject_ads', True)
        self.enable_learning = self.config.get('enable_learning', True)
        
        # 统计信息
        self.detection_stats = {
            'total_processed': 0,
            'keyword_detections': 0,
            'high_risk_matches': 0,
            'promo_matches': 0,
            'avg_processing_time': 0.0
        }
        
        logger.info(f"关键词广告检测器初始化完成 - 规则数量: {self._get_rules_count()}")
    
    def _load_filter_rules(self) -> Dict[str, Any]:
        """加载过滤规则配置"""
        try:
            filter_rules_file = PathConfig.DATA_DIR / "config" / "filter_rules.json"
            
            if filter_rules_file.exists():
                with open(filter_rules_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"过滤规则文件不存在: {filter_rules_file}")
                return self._get_default_rules()
                
        except Exception as e:
            logger.error(f"加载过滤规则失败: {e}")
            return self._get_default_rules()
    
    def _get_default_rules(self) -> Dict[str, Any]:
        """获取默认规则"""
        return {
            "rule_categories": {
                "high_risk_keywords": {
                    "enabled": True,
                    "patterns": []
                },
                "promo_patterns": {
                    "enabled": True,
                    "patterns": []
                }
            }
        }
    
    def _get_rules_count(self) -> int:
        """获取规则总数"""
        count = 0
        for category in self.filter_rules.get("rule_categories", {}).values():
            if category.get("enabled", False):
                count += len(category.get("patterns", []))
        return count
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """关键词广告检测主方法"""
        start_time = time.time()
        
        # 初始化结果
        result = FilterResult(
            filtered_content=content,
            passed=True,
            confidence=0.0,
            details={}
        )
        
        try:
            # 更新统计
            self.detection_stats['total_processed'] += 1
            
            # 获取要检测的内容
            original_content = context.get_metadata('original_content', content)
            
            logger.debug(f"🔍 关键词检测开始 - 内容长度: {len(content)}")
            
            # 执行关键词检测
            is_ad, confidence, match_details = await self._detect_keywords(original_content, context)
            
            result.confidence = confidence
            result.details = match_details
            
            if is_ad:
                # 检测到广告
                self.detection_stats['keyword_detections'] += 1
                
                if self.auto_reject_ads:
                    # 自动拒绝模式
                    result.passed = False
                    result.should_early_stop = True
                    result.reason = f"关键词检测到广告: {match_details.get('reason', 'unknown')}"
                    
                    logger.info(f"🚫 关键词检测拒绝广告 - {result.reason}")
                else:
                    # 仅标记模式
                    result.passed = True
                    result.should_early_stop = False
                    result.reason = f"关键词检测到疑似广告: {match_details.get('reason', 'unknown')}"
                    
                    logger.debug(f"🔍 关键词检测标记 - {result.reason}")
            else:
                # 未检测到广告
                result.reason = "关键词检测正常"
                logger.debug(f"✅ 关键词检测正常")
            
            # 在context中记录检测结果
            context.add_metadata('keyword_ad_detection', {
                'is_ad': not result.passed,
                'confidence': result.confidence,
                'method': 'keyword',
                'match_details': match_details,
                'reason': result.reason
            })
            
        except Exception as e:
            logger.error(f"关键词广告检测异常: {e}", exc_info=True)
            # 异常时默认通过
            result.reason = f"检测异常: {str(e)}"
            result.details['error'] = str(e)
        
        # 记录处理时间
        processing_time = (time.time() - start_time) * 1000
        result.processing_time_ms = processing_time
        
        # 更新平均处理时间
        self._update_processing_time_stats(processing_time)
        
        return result
    
    async def _detect_keywords(self, content: str, context: FilterContext) -> Tuple[bool, float, Dict[str, Any]]:
        """
        关键词检测核心逻辑
        
        Returns:
            (是否广告, 置信度, 匹配详情)
        """
        try:
            if not content or not content.strip():
                return False, 0.0, {"reason": "空内容"}
            
            # 清理内容
            clean_content = self._clean_content(content)
            
            matched_patterns = []
            total_weight = 0
            category_matches = {}
            
            # 检查高危关键词
            high_risk_matches = self._check_high_risk_keywords(clean_content)
            if high_risk_matches:
                matched_patterns.extend(high_risk_matches)
                total_weight += sum(m['weight'] for m in high_risk_matches)
                category_matches['high_risk'] = high_risk_matches
                self.detection_stats['high_risk_matches'] += 1
            
            # 检查推广模式
            promo_matches = self._check_promo_patterns(clean_content)
            if promo_matches:
                matched_patterns.extend(promo_matches)
                total_weight += sum(m['weight'] for m in promo_matches)
                category_matches['promo'] = promo_matches
                self.detection_stats['promo_matches'] += 1
            
            # 判断是否为广告
            is_ad = total_weight >= 10  # 权重阈值
            confidence = min(total_weight / 10.0, 1.0)  # 置信度标准化
            
            match_details = {
                'total_weight': total_weight,
                'matched_patterns_count': len(matched_patterns),
                'category_matches': category_matches,
                'threshold': 10
            }
            
            if is_ad and matched_patterns:
                # 构建匹配原因
                reasons = []
                for pattern in matched_patterns[:3]:  # 只显示前3个匹配
                    reasons.append(f"{pattern['description']}(权重:{pattern['weight']})")
                match_details['reason'] = f"匹配广告模式: {'; '.join(reasons)}"
            else:
                match_details['reason'] = "未匹配广告模式"
            
            return is_ad, confidence, match_details
            
        except Exception as e:
            return False, 0.0, {"reason": f"检测异常: {str(e)}"}
    
    def _clean_content(self, content: str) -> str:
        """清理内容，去除多余空白字符"""
        # 去除多余换行和空白
        content = re.sub(r'\n+', ' ', content)
        content = re.sub(r'\s+', ' ', content)
        return content.strip()
    
    def _check_high_risk_keywords(self, content: str) -> List[Dict[str, Any]]:
        """检查高危关键词"""
        matches = []
        
        high_risk_category = self.filter_rules.get("rule_categories", {}).get("high_risk_keywords", {})
        if not high_risk_category.get("enabled", False):
            return matches
        
        patterns = high_risk_category.get("patterns", [])
        
        for pattern_config in patterns:
            pattern = pattern_config.get("pattern", "")
            if not pattern:
                continue
            
            try:
                if re.search(pattern, content, re.IGNORECASE):
                    matches.append({
                        'pattern': pattern,
                        'weight': pattern_config.get("weight", 10),
                        'description': pattern_config.get("description", "高危关键词"),
                        'category': pattern_config.get("category", "high_risk")
                    })
            except re.error as e:
                logger.warning(f"正则表达式错误: {pattern} - {e}")
        
        return matches
    
    def _check_promo_patterns(self, content: str) -> List[Dict[str, Any]]:
        """检查推广模式"""
        matches = []
        
        promo_category = self.filter_rules.get("rule_categories", {}).get("promo_patterns", {})
        if not promo_category.get("enabled", False):
            return matches
        
        patterns = promo_category.get("patterns", [])
        
        for pattern_config in patterns:
            pattern = pattern_config.get("pattern", "")
            if not pattern:
                continue
            
            try:
                if re.search(pattern, content, re.IGNORECASE):
                    matches.append({
                        'pattern': pattern,
                        'weight': pattern_config.get("weight", 8),
                        'description': pattern_config.get("description", "推广模式"),
                        'category': pattern_config.get("category", "promotion")
                    })
            except re.error as e:
                logger.warning(f"正则表达式错误: {pattern} - {e}")
        
        return matches
    
    def _update_processing_time_stats(self, processing_time_ms: float):
        """更新处理时间统计"""
        current_avg = self.detection_stats['avg_processing_time']
        total_processed = self.detection_stats['total_processed']
        
        # 增量计算平均值
        self.detection_stats['avg_processing_time'] = (
            (current_avg * (total_processed - 1) + processing_time_ms) / total_processed
        )
    
    def manual_learn_ad(self, content: str, context: Optional[FilterContext] = None) -> bool:
        """手动标记广告样本进行学习（暂时保留接口兼容性）"""
        try:
            logger.info(f"记录广告样本学习请求: {content[:50]}...")
            # 这里可以实现自动生成规则的逻辑
            return True
        except Exception as e:
            logger.error(f"手动学习失败: {e}")
            return False
    
    def get_detection_stats(self) -> Dict[str, Any]:
        """获取检测统计信息"""
        return {
            'detector_stats': self.detection_stats.copy(),
            'rules_info': {
                'total_rules': self._get_rules_count(),
                'high_risk_patterns': len(self.filter_rules.get("rule_categories", {}).get("high_risk_keywords", {}).get("patterns", [])),
                'promo_patterns': len(self.filter_rules.get("rule_categories", {}).get("promo_patterns", {}).get("patterns", [])),
            },
            'config': {
                'auto_reject_ads': self.auto_reject_ads,
                'enable_learning': self.enable_learning
            }
        }


# 全局关键词广告检测器实例
_keyword_ad_detector = None

def get_keyword_ad_detector() -> KeywordAdDetector:
    """获取关键词广告检测器实例（单例）"""
    global _keyword_ad_detector
    if _keyword_ad_detector is None:
        _keyword_ad_detector = KeywordAdDetector()
    return _keyword_ad_detector