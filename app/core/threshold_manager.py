"""
自适应阈值管理器
动态优化AI检测阈值，基于用户反馈持续学习
"""
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.optimize import minimize_scalar
import fcntl

from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class ThresholdManager:
    """自适应阈值管理器"""
    
    def __init__(self):
        self.config_file = PathConfig.CONFIG_DIR / "thresholds.json"
        self._lock = threading.RLock()
        self.thresholds = {}
        self.feedback_history = {}
        
        # 优化参数
        self.min_feedback_count = 10  # 最少反馈数量才开始优化
        self.window_size = 1000  # 滑动窗口大小
        self.optimization_interval = 50  # 每N个反馈触发一次优化
        
        # 默认阈值配置
        self.default_config = {
            "tail_filter": {
                "intelligent": {
                    "current": 0.6,
                    "min": 0.3,
                    "max": 0.9,
                    "history": [0.7, 0.65, 0.6],
                    "feedback_stats": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
                    "last_updated": None
                },
                "semantic": {
                    "current": 0.45,
                    "min": 0.2,
                    "max": 0.8,
                    "history": [0.5, 0.48, 0.45],
                    "feedback_stats": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
                    "last_updated": None
                }
            },
            "ad_detector": {
                "classifier": {
                    "current": 0.7,
                    "min": 0.4,
                    "max": 0.95,
                    "history": [0.7],
                    "feedback_stats": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
                    "last_updated": None
                },
                "keywords": {
                    "current": 0.8,
                    "min": 0.5,
                    "max": 1.0,
                    "history": [0.8],
                    "feedback_stats": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
                    "last_updated": None
                }
            },
            "promo_filter": {
                "score": {
                    "current": 0.65,
                    "min": 0.3,
                    "max": 0.9,
                    "history": [0.65],
                    "feedback_stats": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
                    "last_updated": None
                }
            },
            "chat_filter": {
                "detection": {
                    "current": 0.5,
                    "min": 0.3,
                    "max": 0.8,
                    "history": [0.5],
                    "feedback_stats": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
                    "last_updated": None
                }
            }
        }
        
        # 初始化
        self._load_config()
    
    def _load_config(self):
        """加载阈值配置"""
        with self._lock:
            try:
                if self.config_file.exists():
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                        try:
                            self.thresholds = json.load(f)
                        finally:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    
                    logger.info("✅ 加载阈值配置成功")
                else:
                    # 使用默认配置
                    self.thresholds = self.default_config.copy()
                    self._save_config()
                    logger.info("📝 创建默认阈值配置")
                
                # 确保所有默认配置项都存在
                self._ensure_default_keys()
                
            except Exception as e:
                logger.error(f"❌ 加载阈值配置失败: {e}")
                self.thresholds = self.default_config.copy()
    
    def _ensure_default_keys(self):
        """确保所有默认配置项存在"""
        updated = False
        
        for filter_name, metrics in self.default_config.items():
            if filter_name not in self.thresholds:
                self.thresholds[filter_name] = metrics.copy()
                updated = True
            else:
                for metric_name, config in metrics.items():
                    if metric_name not in self.thresholds[filter_name]:
                        self.thresholds[filter_name][metric_name] = config.copy()
                        updated = True
                    else:
                        # 确保所有必需的字段存在
                        for key, default_value in config.items():
                            if key not in self.thresholds[filter_name][metric_name]:
                                self.thresholds[filter_name][metric_name][key] = default_value
                                updated = True
        
        if updated:
            self._save_config()
            logger.info("🔄 更新默认配置项")
    
    def _save_config(self):
        """保存阈值配置"""
        try:
            # 确保目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存配置
            with open(self.config_file, 'w', encoding='utf-8') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(self.thresholds, f, ensure_ascii=False, indent=2)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            logger.debug("💾 保存阈值配置成功")
            
        except Exception as e:
            logger.error(f"❌ 保存阈值配置失败: {e}")
    
    def get_threshold(self, filter_name: str, metric_name: str) -> float:
        """
        获取当前阈值
        
        Args:
            filter_name: 过滤器名称
            metric_name: 指标名称
            
        Returns:
            当前阈值
        """
        with self._lock:
            try:
                return self.thresholds[filter_name][metric_name]["current"]
            except KeyError:
                logger.warning(f"⚠️ 未找到阈值 {filter_name}.{metric_name}，使用默认值")
                # 尝试从默认配置获取
                try:
                    default_value = self.default_config[filter_name][metric_name]["current"]
                    # 添加到配置中
                    if filter_name not in self.thresholds:
                        self.thresholds[filter_name] = {}
                    self.thresholds[filter_name][metric_name] = self.default_config[filter_name][metric_name].copy()
                    self._save_config()
                    return default_value
                except KeyError:
                    return 0.5  # 最后的默认值
    
    def get_threshold_config(self, filter_name: str, metric_name: str) -> Dict:
        """获取完整的阈值配置"""
        with self._lock:
            try:
                return self.thresholds[filter_name][metric_name].copy()
            except KeyError:
                logger.warning(f"⚠️ 未找到阈值配置 {filter_name}.{metric_name}")
                return {}
    
    def record_feedback(self, filter_name: str, metric_name: str, 
                       predicted_score: float, actual_result: str,
                       threshold_used: float = None):
        """
        记录反馈数据
        
        Args:
            filter_name: 过滤器名称
            metric_name: 指标名称
            predicted_score: 预测分数
            actual_result: 实际结果 ('positive', 'negative')
            threshold_used: 使用的阈值（可选）
        """
        with self._lock:
            try:
                config = self.thresholds[filter_name][metric_name]
                current_threshold = threshold_used or config["current"]
                
                # 基于阈值判断预测结果
                predicted_positive = predicted_score >= current_threshold
                actual_positive = actual_result == 'positive'
                
                # 更新统计
                stats = config["feedback_stats"]
                if predicted_positive and actual_positive:
                    stats["tp"] += 1  # True Positive
                elif predicted_positive and not actual_positive:
                    stats["fp"] += 1  # False Positive
                elif not predicted_positive and actual_positive:
                    stats["fn"] += 1  # False Negative
                else:
                    stats["tn"] += 1  # True Negative
                
                # 记录反馈历史
                feedback_key = f"{filter_name}.{metric_name}"
                if feedback_key not in self.feedback_history:
                    self.feedback_history[feedback_key] = []
                
                self.feedback_history[feedback_key].append({
                    "timestamp": datetime.now().isoformat(),
                    "predicted_score": predicted_score,
                    "actual_result": actual_result,
                    "threshold_used": current_threshold,
                    "predicted_positive": predicted_positive,
                    "actual_positive": actual_positive
                })
                
                # 限制历史记录长度
                if len(self.feedback_history[feedback_key]) > self.window_size:
                    self.feedback_history[feedback_key] = self.feedback_history[feedback_key][-self.window_size:]
                
                # 保存配置
                self._save_config()
                
                logger.debug(f"📝 记录反馈: {filter_name}.{metric_name} - 得分: {predicted_score:.3f}, 结果: {actual_result}")
                
                # 检查是否需要触发优化
                total_feedback = sum(stats.values())
                if total_feedback > 0 and total_feedback % self.optimization_interval == 0:
                    if total_feedback >= self.min_feedback_count:
                        self._optimize_threshold(filter_name, metric_name)
                
            except Exception as e:
                logger.error(f"❌ 记录反馈失败: {e}")
    
    def _optimize_threshold(self, filter_name: str, metric_name: str):
        """
        优化特定阈值
        
        Args:
            filter_name: 过滤器名称
            metric_name: 指标名称
        """
        try:
            config = self.thresholds[filter_name][metric_name]
            feedback_key = f"{filter_name}.{metric_name}"
            
            if feedback_key not in self.feedback_history:
                return
            
            history = self.feedback_history[feedback_key]
            if len(history) < self.min_feedback_count:
                return
            
            # 提取数据
            scores = [h["predicted_score"] for h in history[-self.window_size:]]
            actuals = [h["actual_positive"] for h in history[-self.window_size:]]
            
            if len(set(actuals)) < 2:  # 需要正负样本都有
                logger.debug(f"⚠️ {filter_name}.{metric_name} 样本不平衡，跳过优化")
                return
            
            # 定义目标函数（最大化F1分数）
            def objective(threshold):
                return -self._calculate_f1_score(scores, actuals, threshold)
            
            # 优化阈值
            min_val = config.get("min", 0.1)
            max_val = config.get("max", 0.9)
            
            result = minimize_scalar(objective, bounds=(min_val, max_val), method='bounded')
            
            if result.success:
                new_threshold = round(result.x, 3)
                old_threshold = config["current"]
                
                # 如果新阈值有显著改进，则更新
                improvement = -result.fun - self._calculate_f1_score(scores, actuals, old_threshold)
                
                if improvement > 0.02:  # 至少提升2%
                    # 更新阈值
                    config["current"] = new_threshold
                    config["history"].append(new_threshold)
                    config["last_updated"] = datetime.now().isoformat()
                    
                    # 限制历史长度
                    if len(config["history"]) > 10:
                        config["history"] = config["history"][-10:]
                    
                    self._save_config()
                    
                    logger.info(f"🎯 优化阈值: {filter_name}.{metric_name} {old_threshold:.3f} → {new_threshold:.3f} (F1提升: {improvement:.3f})")
                else:
                    logger.debug(f"📊 {filter_name}.{metric_name} 阈值无需调整 (改进: {improvement:.3f})")
            else:
                logger.warning(f"⚠️ {filter_name}.{metric_name} 阈值优化失败")
                
        except Exception as e:
            logger.error(f"❌ 优化阈值失败: {e}")
    
    def _calculate_f1_score(self, scores: List[float], actuals: List[bool], threshold: float) -> float:
        """计算F1分数"""
        try:
            predictions = [score >= threshold for score in scores]
            
            tp = sum(1 for p, a in zip(predictions, actuals) if p and a)
            fp = sum(1 for p, a in zip(predictions, actuals) if p and not a)
            fn = sum(1 for p, a in zip(predictions, actuals) if not p and a)
            
            if tp + fp == 0 or tp + fn == 0:
                return 0.0
            
            precision = tp / (tp + fp)
            recall = tp / (tp + fn)
            
            if precision + recall == 0:
                return 0.0
            
            return 2 * precision * recall / (precision + recall)
        
        except Exception:
            return 0.0
    
    def batch_optimize(self):
        """批量优化所有阈值"""
        logger.info("🚀 开始批量阈值优化")
        
        optimized_count = 0
        for filter_name in self.thresholds:
            for metric_name in self.thresholds[filter_name]:
                try:
                    old_threshold = self.thresholds[filter_name][metric_name]["current"]
                    self._optimize_threshold(filter_name, metric_name)
                    new_threshold = self.thresholds[filter_name][metric_name]["current"]
                    
                    if abs(old_threshold - new_threshold) > 0.001:
                        optimized_count += 1
                
                except Exception as e:
                    logger.error(f"❌ 优化 {filter_name}.{metric_name} 失败: {e}")
        
        logger.info(f"✅ 批量优化完成，调整了 {optimized_count} 个阈值")
    
    def get_all_stats(self) -> Dict:
        """获取所有阈值统计信息"""
        with self._lock:
            stats = {}
            
            for filter_name, metrics in self.thresholds.items():
                stats[filter_name] = {}
                
                for metric_name, config in metrics.items():
                    feedback_stats = config["feedback_stats"]
                    total = sum(feedback_stats.values())
                    
                    if total > 0:
                        precision = feedback_stats["tp"] / (feedback_stats["tp"] + feedback_stats["fp"]) if (feedback_stats["tp"] + feedback_stats["fp"]) > 0 else 0
                        recall = feedback_stats["tp"] / (feedback_stats["tp"] + feedback_stats["fn"]) if (feedback_stats["tp"] + feedback_stats["fn"]) > 0 else 0
                        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
                        accuracy = (feedback_stats["tp"] + feedback_stats["tn"]) / total
                    else:
                        precision = recall = f1 = accuracy = 0
                    
                    stats[filter_name][metric_name] = {
                        "current_threshold": config["current"],
                        "feedback_count": total,
                        "precision": round(precision, 3),
                        "recall": round(recall, 3),
                        "f1_score": round(f1, 3),
                        "accuracy": round(accuracy, 3),
                        "last_updated": config["last_updated"],
                        "history": config["history"][-5:],  # 最近5个值
                        "raw_stats": feedback_stats.copy()
                    }
            
            return stats
    
    def reset_threshold(self, filter_name: str, metric_name: str):
        """重置特定阈值到默认值"""
        with self._lock:
            try:
                default_config = self.default_config[filter_name][metric_name]
                self.thresholds[filter_name][metric_name] = default_config.copy()
                self._save_config()
                
                # 清理反馈历史
                feedback_key = f"{filter_name}.{metric_name}"
                if feedback_key in self.feedback_history:
                    del self.feedback_history[feedback_key]
                
                logger.info(f"🔄 重置阈值: {filter_name}.{metric_name} → {default_config['current']}")
                
            except KeyError:
                logger.error(f"❌ 重置失败：未找到 {filter_name}.{metric_name}")
    
    def reset_all_thresholds(self):
        """重置所有阈值到默认值"""
        with self._lock:
            self.thresholds = self.default_config.copy()
            self.feedback_history.clear()
            self._save_config()
            logger.info("🔄 重置所有阈值到默认值")
    
    def export_config(self) -> Dict:
        """导出阈值配置"""
        with self._lock:
            return {
                "thresholds": self.thresholds.copy(),
                "feedback_history_summary": {
                    key: len(history) for key, history in self.feedback_history.items()
                },
                "exported_at": datetime.now().isoformat()
            }


# 全局实例
threshold_manager = ThresholdManager()