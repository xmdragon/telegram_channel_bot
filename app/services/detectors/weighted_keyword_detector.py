"""
权重关键词广告检测器 - Linus式极简设计
基于关键词权重累计的广告检测方案

"好品味"原则：消除复杂性，只做一件事

Author: Claude
Created: 2025-09-12
"""

import logging
import json
import time
from typing import Dict, List, Tuple, Optional, Union
from pathlib import Path

from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class WeightedKeywordDetector:
    """权重关键词检测器 - 极简高效"""
    
    def __init__(self):
        self.name = "WeightedKeywordDetector"
        self.keywords_file = PathConfig.AD_KEYWORDS_FILE
        self.keywords: Dict[str, float] = {}
        self.threshold: float = 3.0
        self._file_mtime: float = 0
        
        # 初始加载
        self.load_keywords()
        
        # 统计信息
        self.stats = {
            'total_detections': 0,
            'ad_detected': 0,
            'avg_detection_time_ms': 0
        }
    
    def load_keywords(self) -> None:
        """加载关键词配置"""
        try:
            if not self.keywords_file.exists():
                logger.warning(f"关键词配置文件不存在: {self.keywords_file}")
                self._create_default_config()
                return
            
            with open(self.keywords_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 支持向后兼容：整数权重自动转为浮点数
                keywords_data = data.get('keywords', {})
                self.keywords = {k: float(v) for k, v in keywords_data.items()}
                self.threshold = float(data.get('threshold', 3.0))
                self._file_mtime = self.keywords_file.stat().st_mtime
                
            logger.info(f"加载关键词配置: {len(self.keywords)}个关键词, 阈值={self.threshold}")
            
        except Exception as e:
            logger.error(f"加载关键词配置失败: {e}")
            self.keywords = {}
            self.threshold = 3.0
    
    def _create_default_config(self) -> None:
        """创建默认配置文件"""
        default_data = {
            "keywords": {
                "娱乐城": 5.0,
                "USDT": 3.0,
                "充值": 1.0,
                "会员": 1.0
            },
            "threshold": 3.0,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "version": "1.0.0"
        }
        
        try:
            self.keywords_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.keywords_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
            
            self.keywords = {k: float(v) for k, v in default_data['keywords'].items()}
            self.threshold = float(default_data['threshold'])
            logger.info("已创建默认关键词配置")
            
        except Exception as e:
            logger.error(f"创建默认配置失败: {e}")
    
    def reload_if_needed(self) -> None:
        """检查并重新加载配置（如果文件已更新）"""
        try:
            if self.keywords_file.exists():
                current_mtime = self.keywords_file.stat().st_mtime
                if current_mtime != self._file_mtime:
                    logger.info("检测到关键词配置更新，重新加载...")
                    self.load_keywords()
        except Exception as e:
            logger.warning(f"检查配置更新失败: {e}")
    
    def detect(self, content: str) -> Tuple[bool, float, List[Dict[str, Union[str, float]]]]:
        """
        检测内容是否为广告
        
        Args:
            content: 要检测的内容
            
        Returns:
            (是否广告, 总权重, 匹配的关键词详情列表)
            关键词详情格式: [{"keyword": "xxx", "weight": 1.0}, ...]
        """
        start_time = time.time()
        
        # 检查是否需要重新加载
        self.reload_if_needed()
        
        # 更新统计
        self.stats['total_detections'] += 1
        
        if not content or not self.keywords:
            return False, 0, []
        
        total_weight = 0.0
        matched_keywords = []
        
        # 简单的关键词匹配
        for keyword, weight in self.keywords.items():
            if keyword in content:
                total_weight += weight
                matched_keywords.append({
                    "keyword": keyword,
                    "weight": weight
                })
        
        # 判定是否为广告
        is_ad = total_weight >= self.threshold
        
        if is_ad:
            self.stats['ad_detected'] += 1
            # 只记录前5个关键词用于日志
            keywords_for_log = [item['keyword'] for item in matched_keywords[:5]]
            logger.debug(f"检测到广告: 权重={total_weight}, 关键词={keywords_for_log}")
        
        # 更新平均检测时间
        detection_time = (time.time() - start_time) * 1000
        self._update_avg_time(detection_time)
        
        return is_ad, total_weight, matched_keywords
    
    def _update_avg_time(self, time_ms: float) -> None:
        """更新平均检测时间"""
        total = self.stats['total_detections']
        current_avg = self.stats['avg_detection_time_ms']
        self.stats['avg_detection_time_ms'] = (current_avg * (total - 1) + time_ms) / total
    
    def add_keyword(self, keyword: str, weight: Union[int, float] = 1.0) -> bool:
        """添加关键词"""
        try:
            # 加载最新配置
            self.reload_if_needed()
            
            # 添加关键词，确保是浮点数
            self.keywords[keyword] = float(weight)
            
            # 保存到文件
            return self._save_keywords()
            
        except Exception as e:
            logger.error(f"添加关键词失败: {e}")
            return False
    
    def update_keyword(self, keyword: str, weight: Union[int, float]) -> bool:
        """更新关键词权重"""
        try:
            # 加载最新配置
            self.reload_if_needed()
            
            if keyword not in self.keywords:
                logger.warning(f"关键词不存在: {keyword}")
                return False
            
            # 更新权重，确保是浮点数
            self.keywords[keyword] = float(weight)
            
            # 保存到文件
            return self._save_keywords()
            
        except Exception as e:
            logger.error(f"更新关键词失败: {e}")
            return False
    
    def delete_keyword(self, keyword: str) -> bool:
        """删除关键词"""
        try:
            # 加载最新配置
            self.reload_if_needed()
            
            if keyword not in self.keywords:
                logger.warning(f"关键词不存在: {keyword}")
                return False
            
            # 删除关键词
            del self.keywords[keyword]
            
            # 保存到文件
            return self._save_keywords()
            
        except Exception as e:
            logger.error(f"删除关键词失败: {e}")
            return False
    
    def _save_keywords(self) -> bool:
        """保存关键词配置到文件"""
        try:
            data = {
                "keywords": self.keywords,
                "threshold": self.threshold,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f"),
                "version": "1.0.0"
            }
            
            with open(self.keywords_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self._file_mtime = self.keywords_file.stat().st_mtime
            logger.info(f"关键词配置已保存: {len(self.keywords)}个关键词")
            return True
            
        except Exception as e:
            logger.error(f"保存关键词配置失败: {e}")
            return False
    
    def get_keywords(self) -> Dict[str, float]:
        """获取所有关键词及权重"""
        self.reload_if_needed()
        return self.keywords.copy()
    
    def set_threshold(self, threshold: Union[int, float]) -> bool:
        """设置检测阈值"""
        try:
            self.threshold = float(threshold)
            return self._save_keywords()
        except Exception as e:
            logger.error(f"设置阈值失败: {e}")
            return False
    
    def decrease_keyword_weight(self, keyword: str) -> bool:
        """降低关键词权重（用于纠正误判）"""
        try:
            # 加载最新配置
            self.reload_if_needed()
            
            if keyword not in self.keywords:
                logger.warning(f"关键词不存在: {keyword}")
                return False
            
            current_weight = self.keywords[keyword]
            
            # 降权逻辑
            if current_weight > 1.0:
                # 降低0.5或降到1.0，取较大值
                new_weight = max(current_weight - 0.5, 1.0)
                self.keywords[keyword] = new_weight
                logger.info(f"降低关键词权重: {keyword} {current_weight} -> {new_weight}")
            else:
                # 权重为1.0时，删除关键词
                del self.keywords[keyword]
                logger.info(f"删除低权重关键词: {keyword}")
            
            # 保存到文件
            return self._save_keywords()
            
        except Exception as e:
            logger.error(f"降低关键词权重失败: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            'keywords_count': len(self.keywords),
            'threshold': self.threshold
        }
    
    def extract_keywords_from_text(self, text: str, existing_only: bool = False) -> List[Tuple[str, float]]:
        """
        从文本中提取关键词
        
        Args:
            text: 要提取的文本
            existing_only: 是否只返回已存在的关键词
            
        Returns:
            [(关键词, 权重), ...]
        """
        self.reload_if_needed()
        
        found_keywords = []
        for keyword, weight in self.keywords.items():
            if keyword in text:
                found_keywords.append((keyword, weight))
        
        # 按权重排序
        found_keywords.sort(key=lambda x: x[1], reverse=True)
        
        return found_keywords


# 全局实例
_detector_instance: Optional[WeightedKeywordDetector] = None


def get_weighted_keyword_detector() -> WeightedKeywordDetector:
    """获取权重关键词检测器实例（单例）"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = WeightedKeywordDetector()
    return _detector_instance