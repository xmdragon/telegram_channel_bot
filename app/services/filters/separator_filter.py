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
        self._patterns_mtime = 0  # 记录文件修改时间
        self._patterns_file = PathConfig.SEPARATOR_PATTERNS_FILE
        
        self._load_separator_patterns()
    
    def _load_separator_patterns(self):
        """从separator_patterns.json加载正则表达式"""
        try:
            if not self._patterns_file.exists():
                logger.warning(f"分隔符配置文件不存在: {self._patterns_file}")
                logger.warning("过滤器将保持未初始化状态，不进行分隔符过滤")
                return
            
            # 更新文件修改时间
            self._patterns_mtime = self._patterns_file.stat().st_mtime
            
            with open(self._patterns_file, 'r', encoding='utf-8') as f:
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
                    compiled_pattern = re.compile(regex, re.IGNORECASE | re.MULTILINE | re.DOTALL)
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
    
    def filter_content(self, content: str, return_matched_rules: bool = False) -> Tuple[str, Dict[str, Any]]:
        """
        过滤内容中的分隔符包裹的内容块

        Args:
            content: 要过滤的内容
            return_matched_rules: 是否返回匹配的规则详情

        Returns:
            (过滤后内容, 过滤统计信息)
        """
        # 检查是否需要重新加载
        self.reload_if_needed()

        if not content or not content.strip():
            return content, {
                "reason": "内容为空",
                "original_length": 0,
                "filtered_length": 0,
                "removed_blocks_count": 0,
                "patterns_matched_count": 0,
                "removed_blocks": [],
                "matched_patterns": []
            }

        if not self.initialized:
            return content, {
                "reason": "过滤器未初始化",
                "original_length": len(content),
                "filtered_length": len(content),
                "removed_blocks_count": 0,
                "patterns_matched_count": 0,
                "removed_blocks": [],
                "matched_patterns": []
            }

        # 记录原始内容长度
        original_length = len(content)
        filtered_content = content
        removed_blocks = []
        matched_patterns = []
        matched_rules_detail = [] if return_matched_rules else None

        # 对每个正则模式进行处理 - 简化：直接应用规则
        for pattern_idx, pattern in enumerate(self.regex_patterns):
            pattern_str = pattern.pattern

            # 简单判断：如果规则包含[\s\S]*，说明要删除匹配点之后的所有内容
            if r'[\s\S]*' in pattern_str:
                # 查找匹配
                match = pattern.search(filtered_content)
                if match:
                    # 删除匹配位置及之后的所有内容
                    removed_content = filtered_content[match.start():]
                    filtered_content = filtered_content[:match.start()]

                    # 记录删除信息
                    preview = removed_content[:100] + '...' if len(removed_content) > 100 else removed_content
                    block_info = {
                        'content_preview': preview,
                        'content_length': len(removed_content),
                        'matched_pattern': self.pattern_descriptions[pattern_idx],
                        'regex': pattern.pattern
                    }
                    removed_blocks.append(block_info)
                    matched_patterns.append(self.pattern_descriptions[pattern_idx])

                    # 记录详细的匹配规则信息
                    if return_matched_rules:
                        # 计算匹配位置的行号
                        lines_before = content[:match.start()].count('\n') + 1
                        matched_rules_detail.append({
                            'rule_index': pattern_idx,
                            'rule_pattern': pattern.pattern,
                            'rule_description': self.pattern_descriptions[pattern_idx],
                            'match_start_position': match.start(),
                            'match_line_number': lines_before,
                            'matched_text': match.group(0)[:100] + '...' if len(match.group(0)) > 100 else match.group(0),
                            'removed_chars': len(removed_content),
                            'match_type': 'delete_after'
                        })

                    logger.debug(f"模式 '{self.pattern_descriptions[pattern_idx]}' 删除了 {len(removed_content)} 字符")

                    # 找到一个匹配就跳出，避免重复处理
                    break
            else:
                # 普通规则：按行删除匹配的行
                lines = filtered_content.split('\n')
                filtered_lines = []
                removed_lines = []
                removed_line_numbers = []

                for line_num, line in enumerate(lines, 1):
                    if pattern.search(line):
                        # 记录被删除的行
                        preview = line[:100] + '...' if len(line) > 100 else line
                        removed_lines.append(line)
                        removed_line_numbers.append(line_num)
                        removed_blocks.append({
                            'content_preview': preview,
                            'content_length': len(line),
                            'matched_pattern': self.pattern_descriptions[pattern_idx],
                            'regex': pattern.pattern
                        })
                    else:
                        filtered_lines.append(line)

                if removed_lines:
                    filtered_content = '\n'.join(filtered_lines)
                    matched_patterns.append(self.pattern_descriptions[pattern_idx])
                    logger.debug(f"模式 '{self.pattern_descriptions[pattern_idx]}' 删除了 {len(removed_lines)} 行")

                    # 记录详细的匹配规则信息
                    if return_matched_rules:
                        for i, (line, line_num) in enumerate(zip(removed_lines, removed_line_numbers)):
                            matched_rules_detail.append({
                                'rule_index': pattern_idx,
                                'rule_pattern': pattern.pattern,
                                'rule_description': self.pattern_descriptions[pattern_idx],
                                'matched_line': line[:100] + '...' if len(line) > 100 else line,
                                'match_line_number': line_num,
                                'removed_chars': len(line),
                                'match_type': 'line_by_line'
                            })

        # 清理多余的空行（连续3个或更多换行符替换为2个）
        filtered_content = re.sub(r'\n{3,}', '\n\n', filtered_content).strip()
        
        # 构建统计信息
        stats = {
            'original_length': original_length,
            'filtered_length': len(filtered_content),
            'removed_blocks_count': len(removed_blocks),
            'patterns_matched_count': len(set(matched_patterns)),
            'removed_blocks': removed_blocks,
            'matched_patterns': list(set(matched_patterns))
        }

        # 添加详细的规则匹配信息
        if return_matched_rules and matched_rules_detail:
            stats['matched_rules_detail'] = matched_rules_detail
        
        if removed_blocks:
            removed_chars = original_length - len(filtered_content)
            logger.info(f"✅ 分隔符过滤完成: 移除了 {len(removed_blocks)} 个内容块")
            logger.info(f"   原始长度: {original_length} 字符, 过滤后: {len(filtered_content)} 字符")
            logger.info(f"   共移除: {removed_chars} 字符")
        
        return filtered_content, stats
    
    def reload_if_needed(self):
        """检查文件是否修改，需要时重新加载"""
        if self._patterns_file.exists():
            current_mtime = self._patterns_file.stat().st_mtime
            if current_mtime != self._patterns_mtime:
                logger.info("检测到分隔符配置文件更新，重新加载...")
                self._load_separator_patterns()
    
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