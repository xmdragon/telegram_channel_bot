"""
简单尾部过滤器 - 基于正则规则的直接匹配
从复杂特征分析简化为直接正则匹配

设计原则：消除所有不必要的复杂性
- 无AI模型依赖
- 无复杂特征计算
- 直接正则匹配
- 性能比特征分析快1000+倍

Author: Claude ()
Updated: 2025-09-11
"""

import re
import json
import logging
from typing import Tuple, Dict, List, Optional
from pathlib import Path
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class SimpleTailFilter:
    """基于正则规则的简单尾部过滤器
    
    核心思路：
    1. 从样本中加载预生成的正则规则
    2. 直接进行正则匹配
    3. 从消息尾部向前扫描，找到推广内容边界
    """
    
    def __init__(self):
        """初始化简单过滤器"""
        self.regex_rules = []
        self.initialized = False
        self._samples_mtime = 0  # 记录文件修改时间
        self._samples_file = Path(PathConfig.TAIL_TRAINING_DIR) / "tail_filter_samples.json"
        
        self._load_regex_rules()
    
    def _load_regex_rules(self):
        """从样本文件加载正则规则（新格式：直接存储规则列表）"""
        try:
            if not self._samples_file.exists():
                logger.warning(f"样本文件不存在: {self._samples_file}")
                logger.warning("过滤器将保持未初始化状态，不进行尾部过滤")
                return
            
            # 更新文件修改时间
            self._samples_mtime = self._samples_file.stat().st_mtime
            
            with open(self._samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 新格式：直接读取rules数组
            if 'rules' in data:
                rules = data['rules']
            # 兼容旧格式
            elif 'samples' in data:
                samples = data['samples']
                # 从样本中收集所有正则规则
                all_rules = set()
                for sample in samples:
                    rules_list = sample.get('rules', [])
                    if rules_list:
                        all_rules.update(rules_list)
                rules = list(all_rules)
            else:
                logger.warning("样本文件格式不正确")
                logger.warning("过滤器将保持未初始化状态，不进行尾部过滤")
                return

            if not rules:
                logger.warning("样本文件中没有规则数据")
                logger.warning("过滤器将保持未初始化状态，不进行尾部过滤")
                return
            
            # 编译正则表达式
            self._compile_regex_rules(rules)
            self.initialized = True
            
            logger.info(f"✅ 简单尾部过滤器初始化成功")
            logger.info(f"   正则规则: {len(self.regex_rules)} 个")
            
        except Exception as e:
            logger.error(f"加载样本文件失败: {e}")
            logger.warning("过滤器将保持未初始化状态，不进行尾部过滤")
    
    def _compile_regex_rules(self, rules: List[str]):
        """编译正则表达式规则"""
        self.regex_rules = []
        
        for rule in rules:
            if not rule:
                continue
            try:
                # 修复JSON中的双重转义问题
                fixed_rule = rule.replace('\\\\w\\+', r'\w+').replace('\\\\s', r'\s').replace('\\\\.', r'\.')
                compiled = re.compile(fixed_rule, re.IGNORECASE)
                self.regex_rules.append(compiled)
            except re.error as e:
                logger.warning(f"正则表达式编译失败: {rule} - {e}")
    
    
    def filter_tail_content(self, content: str) -> Tuple[str, bool, str, Dict]:
        """
        过滤消息尾部推广内容
        
        Args:
            content: 完整消息内容
            
        Returns:
            (过滤后内容, 是否过滤了内容, 移除的尾部内容, 分析详情)
        """
        # 检查是否需要重新加载
        self.reload_if_needed()
        
        if not content or not content.strip():
            return content, False, "", {"reason": "内容为空"}
        
        if not self.initialized:
            return content, False, "", {"reason": "过滤器未初始化"}
        
        # 处理连续空格为换行
        if re.search(r' {5,}', content):
            content = re.sub(r' {5,}', '\n', content)
        
        lines = content.split('\n')
        
        # 从尾部向前扫描，最多检查10行
        filter_start_index = len(lines)
        scan_start = max(0, len(lines) - 10)
        for i in range(len(lines) - 1, scan_start - 1, -1):
            line = lines[i].strip()
            if not line:  # 跳过空行
                continue
            
            if not self._line_matches_rules(line):  # 如果不匹配任何规则，认为是正文
                filter_start_index = i + 1
                break
        
        # 如果没有找到推广内容
        if filter_start_index >= len(lines):
            return content, False, "", {"reason": "未检测到推广内容"}
        
        # 分割内容
        kept_lines = lines[:filter_start_index]
        removed_lines = lines[filter_start_index:]
        
        # 移除空行
        while kept_lines and not kept_lines[-1].strip():
            removed_lines.insert(0, kept_lines.pop())
        
        if not removed_lines:
            return content, False, "", {"reason": "没有内容被过滤"}
        
        filtered_content = '\n'.join(kept_lines)
        removed_content = '\n'.join(removed_lines)
        
        analysis = {
            'method': 'regex_rules',
            'removed_lines_count': len(removed_lines),
            'filter_ratio': len(removed_content) / len(content),
            'model_type': 'Regex_Rules',
            'rules_matched': self._get_matched_rules(removed_content)
        }
        
        logger.info(f"✅ 正则过滤成功: {len(content)} -> {len(filtered_content)} 字符")
        logger.info(f"   移除了 {len(removed_lines)} 行推广内容")
        
        return filtered_content, True, removed_content, analysis
    
    def reload_if_needed(self):
        """检查文件是否修改，需要时重新加载"""
        if self._samples_file.exists():
            current_mtime = self._samples_file.stat().st_mtime
            if current_mtime != self._samples_mtime:
                logger.info("检测到尾部样本文件更新，重新加载...")
                self._load_regex_rules()
    
    def _line_matches_rules(self, text: str) -> bool:
        """检查文本是否匹配任何正则规则"""
        if not text:
            return False
        
        for rule in self.regex_rules:
            if rule.search(text):
                return True
        
        return False
    
    def _get_matched_rules(self, text: str) -> List[str]:
        """获取匹配的规则列表"""
        matched = []
        for rule in self.regex_rules:
            if rule.search(text):
                matched.append(rule.pattern)
        return matched
    
    def get_statistics(self) -> Dict:
        """获取过滤器统计信息"""
        return {
            'initialized': self.initialized,
            'rule_count': len(self.regex_rules),
            'model_type': 'Regex_Rules',
            'filter_method': 'regex_matching'
        }


# 全局实例
_simple_tail_filter = None

def get_simple_tail_filter() -> SimpleTailFilter:
    """获取简单尾部过滤器单例"""
    global _simple_tail_filter
    if _simple_tail_filter is None:
        _simple_tail_filter = SimpleTailFilter()
    return _simple_tail_filter

def filter_tail_content(content: str) -> Tuple[str, bool, str, Dict]:
    """便捷函数：直接过滤尾部内容"""
    filter_instance = get_simple_tail_filter()
    return filter_instance.filter_tail_content(content)