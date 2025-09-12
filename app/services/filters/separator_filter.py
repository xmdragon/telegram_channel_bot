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
        self._patterns_file = PathConfig.DATA_DIR / "training/tail/separator_patterns.json"
        
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
        过滤内容中的分隔符包裹的内容块
        
        Args:
            content: 要过滤的内容
            
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
        
        # 对每个正则模式进行整体匹配和替换
        for pattern_idx, pattern in enumerate(self.regex_patterns):
            # 查找所有匹配的内容块
            matches = pattern.findall(filtered_content)
            
            if matches:
                # 记录匹配信息
                for match in matches:
                    # 限制记录的内容长度，避免日志过大
                    preview = match[:100] + '...' if len(match) > 100 else match
                    removed_blocks.append({
                        'content_preview': preview,
                        'content_length': len(match),
                        'matched_pattern': self.pattern_descriptions[pattern_idx],
                        'regex': pattern.pattern
                    })
                    matched_patterns.append(self.pattern_descriptions[pattern_idx])
                
                # 使用 re.sub 移除所有匹配的内容块
                filtered_content = pattern.sub('', filtered_content)
                
                logger.debug(f"模式 '{self.pattern_descriptions[pattern_idx]}' 移除了 {len(matches)} 个内容块")
        
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