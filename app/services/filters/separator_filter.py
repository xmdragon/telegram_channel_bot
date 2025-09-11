"""
分隔符过滤器 - 独立类
基于separator_patterns.json配置，以行为单位进行正则匹配过滤

Author: Claude
Created: 2025-09-11
"""

import re
import json
import logging
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class SeparatorFilter:
    """独立的分隔符过滤器
    
    功能：
    - 基于separator_patterns.json加载正则表达式
    - 逐行匹配，匹配即过滤
    - 返回过滤后的内容
    """
    
    def __init__(self):
        """初始化分隔符过滤器"""
        self.regex_patterns: List[re.Pattern] = []
        self.pattern_descriptions: List[str] = []
        self.initialized = False
        
        self._load_separator_patterns()
    
    def _load_separator_patterns(self):
        """从separator_patterns.json加载正则表达式"""
        try:
            separator_file = PathConfig.DATA_DIR / "training/tail/separator_patterns.json"
            
            if not separator_file.exists():
                logger.warning(f"分隔符配置文件不存在: {separator_file}")
                logger.warning("过滤器将保持未初始化状态，不进行分隔符过滤")
                return
            
            with open(separator_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            patterns = data.get('patterns', [])
            if not patterns:
                logger.warning("分隔符配置文件中没有模式数据")
                logger.warning("过滤器将保持未初始化状态，不进行分隔符过滤")
                return
            
            # 编译所有正则表达式
            compiled_patterns = []
            descriptions = []
            
            for pattern_data in patterns:
                regex = pattern_data.get('regex')
                description = pattern_data.get('description', '')
                
                if not regex:
                    continue
                
                try:
                    compiled_pattern = re.compile(regex, re.IGNORECASE)
                    compiled_patterns.append(compiled_pattern)
                    descriptions.append(description)
                except re.error as e:
                    logger.warning(f"正则表达式编译失败: {regex} - {e}")
            
            self.regex_patterns = compiled_patterns
            self.pattern_descriptions = descriptions
            self.initialized = True
            
            logger.info(f"✅ 分隔符过滤器初始化成功")
            logger.info(f"   加载了 {len(self.regex_patterns)} 个分隔符模式")
            
        except Exception as e:
            logger.error(f"加载分隔符配置失败: {e}")
            logger.warning("过滤器将保持未初始化状态，不进行分隔符过滤")
    
    def filter_content(self, content: str) -> Tuple[str, Dict[str, Any]]:
        """
        过滤内容中的分隔符行
        
        Args:
            content: 要过滤的内容
            
        Returns:
            (过滤后内容, 过滤统计信息)
        """
        if not content or not content.strip():
            return content, {
                "reason": "内容为空",
                "total_lines": 0,
                "removed_lines_count": 0,
                "filtered_lines_count": 0,
                "patterns_matched_count": 0,
                "removed_lines": [],
                "matched_patterns": []
            }
        
        if not self.initialized:
            return content, {
                "reason": "过滤器未初始化",
                "total_lines": len(content.split('\n')),
                "removed_lines_count": 0,
                "filtered_lines_count": len(content.split('\n')),
                "patterns_matched_count": 0,
                "removed_lines": [],
                "matched_patterns": []
            }
        
        # 按行分割内容
        lines = content.split('\n')
        filtered_lines = []
        removed_lines = []
        matched_patterns = []
        
        # 逐行检查和过滤
        for line_num, line in enumerate(lines):
            line_matched = False
            
            # 对每行应用所有正则模式
            for pattern_idx, pattern in enumerate(self.regex_patterns):
                if pattern.search(line):
                    # 匹配到分隔符，移除这一行
                    removed_lines.append({
                        'line_number': line_num + 1,
                        'content': line,
                        'matched_pattern': self.pattern_descriptions[pattern_idx],
                        'regex': pattern.pattern
                    })
                    matched_patterns.append(self.pattern_descriptions[pattern_idx])
                    line_matched = True
                    break
            
            # 未匹配的行保留
            if not line_matched:
                filtered_lines.append(line)
        
        # 重新组合过滤后的内容
        filtered_content = '\n'.join(filtered_lines)
        
        # 清理多余的空行
        filtered_content = re.sub(r'\n{3,}', '\n\n', filtered_content).strip()
        
        # 构建统计信息
        stats = {
            'total_lines': len(lines),
            'removed_lines_count': len(removed_lines),
            'filtered_lines_count': len(filtered_lines),
            'patterns_matched_count': len(set(matched_patterns)),
            'removed_lines': removed_lines,
            'matched_patterns': list(set(matched_patterns))
        }
        
        if removed_lines:
            logger.info(f"✅ 分隔符过滤完成: 移除了 {len(removed_lines)} 行分隔符")
            logger.info(f"   原始行数: {len(lines)}, 过滤后行数: {len(filtered_lines)}")
        
        return filtered_content, stats
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取过滤器统计信息"""
        return {
            'initialized': self.initialized,
            'pattern_count': len(self.regex_patterns),
            'patterns': [
                {
                    'regex': pattern.pattern,
                    'description': desc
                }
                for pattern, desc in zip(self.regex_patterns, self.pattern_descriptions)
            ] if self.initialized else []
        }


# 便捷函数
def filter_separators(content: str) -> Tuple[str, Dict[str, Any]]:
    """便捷函数：直接过滤分隔符"""
    separator_filter = SeparatorFilter()
    return separator_filter.filter_content(content)