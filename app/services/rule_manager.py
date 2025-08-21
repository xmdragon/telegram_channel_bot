"""
统一过滤规则管理器
负责加载、管理和动态更新所有过滤规则
"""
import json
import re
import logging
import asyncio
import fcntl
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional, Pattern
from pathlib import Path

from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class RuleManager:
    """统一过滤规则管理器"""
    
    def __init__(self):
        self.config_path = Path(PathConfig.DATA_DIR) / "config" / "filter_rules.json"
        self.rules_data = {}
        self.compiled_patterns = {}
        self._lock = asyncio.Lock()
        self._file_lock = None
        self._last_modified = None
        
    async def initialize(self):
        """初始化规则管理器"""
        try:
            await self.load_rules()
            await self._compile_patterns()
            logger.info(f"规则管理器初始化完成，加载了 {self.get_total_pattern_count()} 个规则")
        except Exception as e:
            logger.error(f"规则管理器初始化失败: {e}")
            await self._create_default_config()
    
    async def load_rules(self):
        """加载规则配置文件"""
        async with self._lock:
            try:
                if not self.config_path.exists():
                    logger.warning(f"规则配置文件不存在: {self.config_path}")
                    await self._create_default_config()
                    return
                
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    # 使用文件锁保护读取
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    try:
                        self.rules_data = json.load(f)
                        self._last_modified = self.config_path.stat().st_mtime
                        logger.debug(f"成功加载规则配置，版本: {self.rules_data.get('version', 'unknown')}")
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        
            except Exception as e:
                logger.error(f"加载规则配置失败: {e}")
                await self._create_default_config()
    
    async def save_rules(self):
        """保存规则配置到文件"""
        async with self._lock:
            try:
                # 更新时间戳
                self.rules_data['last_updated'] = datetime.now().isoformat()
                
                # 确保目录存在
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 写入临时文件后原子性替换
                temp_path = self.config_path.with_suffix('.tmp')
                with open(temp_path, 'w', encoding='utf-8') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        json.dump(self.rules_data, f, ensure_ascii=False, indent=2)
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
                # 原子性替换
                temp_path.replace(self.config_path)
                self._last_modified = self.config_path.stat().st_mtime
                
                logger.debug("规则配置保存成功")
                
            except Exception as e:
                logger.error(f"保存规则配置失败: {e}")
                raise
    
    async def _create_default_config(self):
        """创建默认规则配置"""
        self.rules_data = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "description": "统一过滤规则配置 - 支持动态学习和规则管理",
            "rule_categories": {
                "high_risk_keywords": {
                    "description": "高危广告关键词",
                    "default_weight": 10,
                    "enabled": True,
                    "patterns": []
                },
                "promo_patterns": {
                    "description": "推广内容特征模式",
                    "enabled": True,
                    "patterns": []
                },
                "learned_patterns": {
                    "description": "自动学习的广告模式",
                    "enabled": True,
                    "patterns": []
                }
            },
            "learning_config": {
                "enabled": True,
                "confidence_threshold": 0.8,
                "max_learned_patterns": 1000,
                "learning_weight_start": 5,
                "learning_weight_increment": 1,
                "auto_cleanup_threshold": 30
            },
            "learning_stats": {
                "total_learned": 0,
                "last_learning": None,
                "patterns_by_category": {},
                "patterns_removed": 0,
                "last_cleanup": None
            }
        }
        await self.save_rules()
    
    async def _compile_patterns(self):
        """编译所有正则表达式模式"""
        self.compiled_patterns = {}
        
        for category_name, category_data in self.rules_data.get('rule_categories', {}).items():
            if not category_data.get('enabled', True):
                continue
                
            compiled_category = []
            patterns = category_data.get('patterns', [])
            
            for pattern_data in patterns:
                try:
                    if isinstance(pattern_data, dict):
                        pattern_str = pattern_data.get('pattern', '')
                        weight = pattern_data.get('weight', category_data.get('default_weight', 5))
                        description = pattern_data.get('description', '')
                        category = pattern_data.get('category', 'unknown')
                    else:
                        # 兼容旧格式 (pattern, weight)
                        pattern_str = pattern_data[0] if isinstance(pattern_data, (list, tuple)) else str(pattern_data)
                        weight = pattern_data[1] if isinstance(pattern_data, (list, tuple)) and len(pattern_data) > 1 else 5
                        description = ''
                        category = 'unknown'
                    
                    if pattern_str:
                        compiled_pattern = re.compile(pattern_str, re.IGNORECASE)
                        compiled_category.append({
                            'pattern': compiled_pattern,
                            'pattern_str': pattern_str,
                            'weight': weight,
                            'description': description,
                            'category': category
                        })
                        
                except re.error as e:
                    logger.warning(f"无效的正则表达式 '{pattern_str}': {e}")
                except Exception as e:
                    logger.warning(f"编译模式失败 '{pattern_data}': {e}")
            
            self.compiled_patterns[category_name] = compiled_category
            logger.debug(f"编译了 {len(compiled_category)} 个 {category_name} 规则")
    
    async def check_and_reload(self):
        """检查文件是否修改，如果是则重新加载"""
        try:
            if not self.config_path.exists():
                return
                
            current_mtime = self.config_path.stat().st_mtime
            if self._last_modified is None or current_mtime > self._last_modified:
                logger.info("检测到规则配置文件更新，重新加载")
                await self.load_rules()
                await self._compile_patterns()
        except Exception as e:
            logger.error(f"检查规则文件更新失败: {e}")
    
    def get_patterns_by_category(self, category: str) -> List[Dict[str, Any]]:
        """获取指定类别的编译模式"""
        return self.compiled_patterns.get(category, [])
    
    def get_all_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有编译模式"""
        return self.compiled_patterns.copy()
    
    def get_high_risk_keywords(self) -> List[Tuple[Pattern, int]]:
        """获取高危关键词模式（兼容现有代码）"""
        patterns = self.get_patterns_by_category('high_risk_keywords')
        return [(p['pattern'], p['weight']) for p in patterns]
    
    def get_promo_patterns(self) -> List[Tuple[Pattern, int]]:
        """获取推广模式（兼容现有代码）"""
        patterns = self.get_patterns_by_category('promo_patterns')
        return [(p['pattern'], p['weight']) for p in patterns]
    
    async def add_learned_pattern(self, pattern: str, weight: int, category: str = 'other', 
                                description: str = '', confidence: float = 1.0):
        """添加自动学习的模式"""
        async with self._lock:
            try:
                # 检查学习配置
                learning_config = self.rules_data.get('learning_config', {})
                if not learning_config.get('enabled', True):
                    logger.debug("自动学习功能已禁用")
                    return False
                
                # 检查置信度阈值
                confidence_threshold = learning_config.get('confidence_threshold', 0.8)
                if confidence < confidence_threshold:
                    logger.debug(f"置信度 {confidence} 低于阈值 {confidence_threshold}，跳过学习")
                    return False
                
                # 检查是否已存在
                learned_patterns = self.rules_data['rule_categories']['learned_patterns']['patterns']
                for existing in learned_patterns:
                    if existing.get('pattern') == pattern:
                        logger.debug(f"模式已存在，跳过: {pattern}")
                        return False
                
                # 检查最大数量限制
                max_patterns = learning_config.get('max_learned_patterns', 1000)
                if len(learned_patterns) >= max_patterns:
                    logger.warning(f"学习模式数量已达上限 {max_patterns}，跳过新模式")
                    return False
                
                # 添加新模式
                new_pattern = {
                    'pattern': pattern,
                    'weight': weight,
                    'description': description or f'自动学习模式 - {category}',
                    'category': category,
                    'auto_learned': True,
                    'confidence': confidence,
                    'created_at': datetime.now().isoformat(),
                    'usage_count': 0
                }
                
                learned_patterns.append(new_pattern)
                
                # 更新统计
                stats = self.rules_data.get('learning_stats', {})
                stats['total_learned'] = stats.get('total_learned', 0) + 1
                stats['last_learning'] = datetime.now().isoformat()
                
                category_stats = stats.get('patterns_by_category', {})
                category_stats[category] = category_stats.get(category, 0) + 1
                
                # 保存配置
                await self.save_rules()
                
                # 重新编译模式
                await self._compile_patterns()
                
                logger.info(f"成功学习新模式: {pattern} (权重: {weight}, 类别: {category})")
                return True
                
            except Exception as e:
                logger.error(f"添加学习模式失败: {e}")
                return False
    
    async def remove_pattern(self, category: str, pattern: str):
        """移除指定模式"""
        async with self._lock:
            try:
                category_data = self.rules_data['rule_categories'].get(category)
                if not category_data:
                    logger.warning(f"未找到类别: {category}")
                    return False
                
                patterns = category_data.get('patterns', [])
                original_count = len(patterns)
                
                # 移除匹配的模式
                patterns[:] = [p for p in patterns if p.get('pattern') != pattern]
                
                if len(patterns) < original_count:
                    await self.save_rules()
                    await self._compile_patterns()
                    logger.info(f"成功移除模式: {pattern} (类别: {category})")
                    return True
                else:
                    logger.warning(f"未找到要移除的模式: {pattern}")
                    return False
                    
            except Exception as e:
                logger.error(f"移除模式失败: {e}")
                return False
    
    def get_total_pattern_count(self) -> int:
        """获取总模式数量"""
        total = 0
        for category_patterns in self.compiled_patterns.values():
            total += len(category_patterns)
        return total
    
    def get_category_stats(self) -> Dict[str, int]:
        """获取各类别的模式统计"""
        stats = {}
        for category, patterns in self.compiled_patterns.items():
            stats[category] = len(patterns)
        return stats
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """获取学习统计信息"""
        return self.rules_data.get('learning_stats', {}).copy()


# 全局单例实例
rule_manager = RuleManager()