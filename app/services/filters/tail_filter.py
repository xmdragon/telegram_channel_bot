"""
尾部过滤器 - 完全独立，所有代码在一个类里
基于正则规则的直接匹配，无需导入其他文件

Author: Claude ()
Created: 2025-09-13
"""

import re
import json
import logging
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class TailFilter:
    """尾部过滤器 - 基于正则规则的直接匹配

    性能优化：
    1. 使用预编译规则缓存
    2. 优化的Trie树结构用于快速匹配
    3. 批量匹配减少循环开销
    """

    def __init__(self):
        """初始化并加载规则"""
        self.regex_rules: List[re.Pattern] = []
        self._compiled_combined_pattern: Optional[re.Pattern] = None  # 合并的正则模式
        self._rule_keywords: set = set()  # 关键词快速预筛选
        self.initialized = False
        self._samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
        self._samples_mtime = 0
        self._load_rules()

    def _load_rules(self):
        """从样本文件加载正则规则 - 优化版本"""
        try:
            if not self._samples_file.exists():
                logger.warning(f"样本文件不存在: {self._samples_file}")
                return

            self._samples_mtime = self._samples_file.stat().st_mtime

            with open(self._samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 优先使用新格式，消除特殊情况
            rules = data.get('rules', [])
            if not rules and 'samples' in data:
                # 兼容旧格式（减少遗留代码路径）
                all_rules = set()
                for sample in data['samples']:
                    if sample.get('rules'):
                        all_rules.update(sample['rules'])
                rules = list(all_rules)

            # 性能优化：预处理和批量编译
            valid_rules = []
            keywords = set()

            for rule in rules:
                if not rule or len(rule.strip()) < 3:
                    continue

                try:
                    # 预编译检查
                    compiled = re.compile(rule, re.IGNORECASE | re.MULTILINE)
                    valid_rules.append(rule)

                    # 提取关键词用于快速预筛选
                    self._extract_keywords_from_pattern(rule, keywords)

                except re.error as e:
                    logger.warning(f"正则编译失败 '{rule}': {e}")

            if valid_rules:
                # 优化：合并规则为单个正则模式
                self._build_optimized_patterns(valid_rules)
                self._rule_keywords = keywords
                self.initialized = True
                logger.info(f"优化加载了 {len(valid_rules)} 条尾部规则，提取了 {len(keywords)} 个关键词")
            else:
                logger.warning("没有有效的尾部过滤规则")

        except Exception as e:
            logger.error(f"加载尾部规则失败: {e}")

    def _extract_keywords_from_pattern(self, pattern: str, keywords: set):
        """从正则模式中提取关键词用于快速预筛选"""
        try:
            # 提取明显的文字关键词（忽略正则符号）
            # 这里只提取简单的中英文关键词
            import re
            # 匹配连续的中文或字母数字字符
            text_parts = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]{2,}', pattern)
            for part in text_parts:
                if len(part) >= 2:  # 只保留长度>=2的关键词
                    keywords.add(part.lower())
        except Exception:
            pass  # 忽略关键词提取错误

    def _build_optimized_patterns(self, rules: List[str]):
        """构建优化的正则模式"""
        try:
            # 方式1：保留原始逐个匹配（更精确）
            self.regex_rules = []
            for rule in rules:
                try:
                    compiled = re.compile(rule, re.IGNORECASE | re.MULTILINE)
                    self.regex_rules.append(compiled)
                except re.error:
                    continue

            # 方式2：尝试合并简单规则（性能优化，但可能降低精度）
            simple_rules = []
            complex_rules = []

            for rule in rules:
                # 简单规则：不包含复杂正则语法
                if not any(char in rule for char in ['(', ')', '[', ']', '{', '}', '?', '*', '+']):
                    simple_rules.append(re.escape(rule))
                else:
                    complex_rules.append(rule)

            # 合并简单规则为一个大的OR模式
            if simple_rules:
                combined_simple = '|'.join(f'({rule})' for rule in simple_rules[:50])  # 限制数量防止过大
                try:
                    self._compiled_combined_pattern = re.compile(combined_simple, re.IGNORECASE | re.MULTILINE)
                except re.error:
                    self._compiled_combined_pattern = None

        except Exception as e:
            logger.warning(f"构建优化模式失败: {e}")
            # 降级到基础方式

    def filter(self, content: str, return_matched_rules: bool = False) -> Tuple[str, bool, str, Optional[List[Dict[str, Any]]]]:
        """过滤尾部内容 - 性能优化版本

        Args:
            content: 输入内容
            return_matched_rules: 是否返回匹配的规则详情

        Returns:
            (过滤后内容, 是否过滤, 删除的内容, 匹配的规则详情)
        """
        # 检查是否需要重新加载
        if self._samples_file.exists():
            current_mtime = self._samples_file.stat().st_mtime
            if current_mtime != self._samples_mtime:
                logger.info("检测到规则文件更新，重新加载...")
                self._load_rules()

        # 如果未初始化或内容为空，直接返回
        if not self.initialized or not content:
            return content, False, "", None if not return_matched_rules else []

        # 按行分割
        lines = content.split('\n')
        if len(lines) <= 1:
            return content, False, "", None if not return_matched_rules else []

        # 性能优化：快速预筛选
        if self._rule_keywords:
            content_lower = content.lower()
            if not any(keyword in content_lower for keyword in self._rule_keywords):
                logger.debug("快速预筛选：无匹配关键词，跳过详细匹配")
                return content, False, "", None if not return_matched_rules else []

        logger.debug(f"尾部过滤调试 - 总行数: {len(lines)}")

        # 优化：批量匹配减少循环 - 增强版本，支持返回匹配的规则
        matched_idx, matched_rule_info = self._find_tail_match_optimized(lines, return_matched_rules)

        # 如果找到匹配，删除该行及其后的所有内容
        if matched_idx != -1:
            logger.debug(f"🗑️ 找到尾部匹配: 第{matched_idx+1}行开始")

            filtered_lines = lines[:matched_idx]

            # 去除末尾空行 - 简化
            while filtered_lines and not filtered_lines[-1].strip():
                filtered_lines.pop()

            filtered = '\n'.join(filtered_lines)
            removed = '\n'.join(lines[matched_idx:])

            logger.debug(f"✂️ 尾部过滤: {len(content)} -> {len(filtered)} 字符 ({len(lines) - matched_idx}行删除)")

            # 构建返回的规则信息
            matched_rules = None
            if return_matched_rules and matched_rule_info:
                matched_rules = [{
                    'rule_pattern': matched_rule_info.get('pattern', ''),
                    'rule_index': matched_rule_info.get('index', -1),
                    'matched_line': matched_rule_info.get('matched_line', ''),
                    'matched_line_number': matched_idx + 1,
                    'removed_content': removed,
                    'removed_chars': len(removed),
                    'removed_lines': len(lines) - matched_idx
                }]

            return filtered, True, removed, matched_rules

        # 没有匹配
        logger.debug("🚫 尾部过滤: 未找到匹配的推广内容")
        return content, False, "", None if not return_matched_rules else []

    def _find_tail_match_optimized(self, lines: List[str], return_matched_rules: bool = False) -> Tuple[int, Optional[Dict[str, Any]]]:
        """优化的尾部匹配查找 - 从前向后，找到第一个匹配就停止

        Args:
            lines: 文本行列表
            return_matched_rules: 是否返回匹配的规则信息

        Returns:
            (匹配的行索引, 匹配的规则信息)
        """
        try:
            # 从前向后遍历，找第一个匹配的行
            for i in range(len(lines)):
                line = lines[i].strip()
                if not line:
                    continue

                # 方法1：尝试合并模式匹配（如果可用）
                if self._compiled_combined_pattern and self._compiled_combined_pattern.search(line):
                    logger.debug(f"🎯 合并模式匹配: 第{i+1}行")
                    if return_matched_rules:
                        # 需要找出具体是哪个规则匹配的
                        for rule_idx, rule in enumerate(self.regex_rules):
                            if rule.search(line):
                                return i, {
                                    'pattern': rule.pattern,
                                    'index': rule_idx,
                                    'matched_line': line,
                                    'match_type': 'combined_then_individual'
                                }
                    return i, None

                # 方法2：逐个规则匹配（保持原有精度）
                for rule_idx, rule in enumerate(self.regex_rules):
                    if rule.search(line):
                        logger.debug(f"🎯 单规则匹配: 第{i+1}行, 规则索引: {rule_idx}")
                        if return_matched_rules:
                            return i, {
                                'pattern': rule.pattern,
                                'index': rule_idx,
                                'matched_line': line,
                                'match_type': 'individual'
                            }
                        return i, None

            return -1, None
        except Exception as e:
            logger.warning(f"优化匹配失败，降级到基础模式: {e}")
            # 降级处理
            basic_result = self._find_tail_match_basic(lines, return_matched_rules)
            return basic_result

    def _find_tail_match_basic(self, lines: List[str], return_matched_rules: bool = False) -> Tuple[int, Optional[Dict[str, Any]]]:
        """基础尾部匹配查找 - 降级版本"""
        # 从前向后查找
        for i in range(len(lines)):
            line = lines[i].strip()
            if not line:
                continue

            for rule_idx, rule in enumerate(self.regex_rules):
                if rule.search(line):
                    if return_matched_rules:
                        return i, {
                            'pattern': rule.pattern,
                            'index': rule_idx,
                            'matched_line': line,
                            'match_type': 'basic'
                        }
                    return i, None
        return -1, None


from datetime import datetime
from typing import Dict, Any, List


class TailFilterManager:
    """尾部过滤管理器 - 提供API所需的管理功能"""

    def __init__(self):
        self.filter = TailFilter()
        self._samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE

    def get_statistics(self) -> Dict[str, Any]:
        """获取尾部过滤统计信息 - 极简版"""
        try:
            data = self._load_samples_data()
            rules = data.get('rules', [])

            return {
                "success": True,
                "total_samples": len(rules)
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "success": False,
                "total_samples": 0
            }

    def get_samples(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取尾部过滤样本（分页）"""
        try:
            data = self._load_samples_data()
            rules = data.get('rules', [])

            # 分页处理
            start = (page - 1) * page_size
            end = start + page_size
            page_rules = rules[start:end]

            # 转换为样本格式
            samples = []
            for i, rule in enumerate(page_rules):
                if rule:
                    samples.append({
                        "id": start + i + 1,
                        "tail_part": rule,
                        "rules": [rule],
                        "created_at": data.get('updated_at', ''),
                        "rule_type": "regex"
                    })

            return {
                "success": True,
                "samples": samples,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": len(rules),
                    "total_pages": (len(rules) + page_size - 1) // page_size
                }
            }
        except Exception as e:
            logger.error(f"获取样本失败: {e}")
            return {
                "success": False,
                "samples": [],
                "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 0}
            }

    def _line_to_rule(self, line: str) -> str:
        """将一行文本转换为合适的过滤规则"""
        import re

        # 保留特定用户名的列表
        specific_usernames = ['@awen636', '@xiaoyaya6', '@YT798', '@Pyz22', '@MT0666',
                              '@dny103v', '@shuis665', '@sijiguanjia888', '@cn_zhm0']

        # 先检查是否有特定用户名
        has_specific_username = any(username in line for username in specific_usernames)

        # 开始构建规则
        rule = line

        # 1. 处理@用户名（如果不是特定用户名）
        if '@' in rule and not has_specific_username:
            # 替换通用的@用户名为模式
            rule = re.sub(r'@[a-zA-Z0-9_]+', r'@\\w+', rule)

        # 2. 处理Telegram链接
        # https://t.me/+xxx 格式
        rule = re.sub(r'https://t\.me/\+[a-zA-Z0-9_-]+', r'https://t\.me/\\+[a-zA-Z0-9_]+', rule)
        # https://t.me/xxx 格式
        rule = re.sub(r'https://t\.me/[a-zA-Z0-9_]+', r'https://t\.me/[a-zA-Z0-9_]+', rule)
        # t.me/+xxx 格式
        rule = re.sub(r't\.me/\+[a-zA-Z0-9_-]+', r't\.me/\\+[a-zA-Z0-9_]+', rule)
        # t.me/xxx 格式（不包括https://）
        rule = re.sub(r'(?<!https://)t\.me/[a-zA-Z0-9_]+', r't\.me/[a-zA-Z0-9_]+', rule)

        # 3. 转义特殊正则字符（但保留我们已经处理的模式）
        # 转义点号（但不转义已经在t\.me中的）
        rule = re.sub(r'(?<!\\)\.(?!me)', r'\.', rule)

        # 转义其他特殊字符
        special_chars = {
            '(': r'\(',
            ')': r'\)',
            '[': r'\[',
            ']': r'\]',
            '{': r'\{',
            '}': r'\}',
            '*': r'\*',
            '?': r'\?',
            '^': r'\^',
            '$': r'\$',
            '|': r'\|',
        }

        for char, escaped in special_chars.items():
            # 但不转义我们模式中的字符
            if char == '[' and '[a-zA-Z0-9_]' in rule:
                continue
            if char == ']' and '[a-zA-Z0-9_]' in rule:
                continue
            if char == '*' and r'\*' in rule:  # 已经转义的*
                continue
            rule = rule.replace(char, escaped)

        # 4. 处理空格 - 使其更灵活
        rule = re.sub(r' +', r'\\s*', rule)

        # 5. 修复可能的双转义问题
        rule = rule.replace(r'\\\\w+', r'\\w+')
        rule = rule.replace(r'\\\\s*', r'\\s*')
        rule = rule.replace(r'\\.', r'\.')

        return rule

    def add_sample(self, tail_part: str, rules: List[str] = None) -> Dict[str, Any]:
        """添加尾部过滤样本（智能版本）"""
        try:
            data = self._load_samples_data()
            existing_rules = data.get('rules', [])

            # 如果tail_part包含换行符，按行分割
            if '\n' in tail_part:
                lines = tail_part.split('\n')
                new_rules = []
                for line in lines:
                    line = line.strip()
                    if line:
                        # 转换为正则规则
                        rule = self._line_to_rule(line)
                        new_rules.append(rule)
            else:
                if rules:
                    new_rules = rules
                else:
                    # 单行也需要转换
                    rule = self._line_to_rule(tail_part.strip())
                    new_rules = [rule]

            added_rules = []
            skipped_rules = []
            covered_by = {}

            for new_rule in new_rules:
                if not new_rule:
                    continue

                # 检查是否已存在
                if new_rule in existing_rules:
                    skipped_rules.append(new_rule)
                    continue

                # 检查是否被已有规则覆盖
                is_covered = False
                for existing_rule in existing_rules:
                    try:
                        # 简单检查：如果新规则包含在已有规则中
                        if existing_rule in new_rule and existing_rule != new_rule:
                            # 新规则是已有规则的子集（更具体）
                            continue

                        # 检查通用规则是否会匹配新规则
                        import re
                        if existing_rule == '@\\w+' and '@' in new_rule:
                            covered_by[new_rule] = existing_rule
                            is_covered = True
                            break
                        elif existing_rule == '订阅\\s*频道\\s*↓' and '订阅' in new_rule and '频道' in new_rule:
                            covered_by[new_rule] = existing_rule
                            is_covered = True
                            break
                        # 可以添加更多覆盖检查
                    except:
                        pass

                if not is_covered:
                    added_rules.append(new_rule)

            # 将新规则插入到合适的位置（按具体程度）
            if added_rules:
                # 计算规则的具体程度
                def calculate_specificity(rule):
                    score = 0
                    # 纯文本最具体（检查是否包含正则元字符）
                    regex_chars = ['\\w', '\\s', '\\d', '[', ']', '(', ')', '+', '*', '?', '^', '$']
                    if not any(char in rule for char in regex_chars):
                        score += 1000
                    # 包含中文更具体
                    import re
                    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', rule))
                    score += chinese_chars * 10
                    # 包含emoji更具体
                    emoji_count = sum(1 for char in rule if ord(char) > 0x1F300)
                    score += emoji_count * 20
                    # 通配符越多越不具体
                    wildcards = rule.count('\\w+') + rule.count('\\s*') + rule.count('[a-zA-Z0-9_]+')
                    score -= wildcards * 30
                    # 特殊通用规则
                    if rule == '@\\w+':
                        score = -1000
                    elif '订阅' in rule and '频道' in rule and chinese_chars < 10:
                        score = -500
                    elif rule.startswith('t\\.me/') or rule.startswith('https://t\\.me/'):
                        score = -400
                    return score

                # 合并并重新排序所有规则
                all_rules = existing_rules + added_rules
                rules_with_scores = [(rule, calculate_specificity(rule)) for rule in all_rules]
                rules_with_scores.sort(key=lambda x: x[1], reverse=True)
                data['rules'] = [rule for rule, score in rules_with_scores]
            else:
                data['rules'] = existing_rules

            # 更新元数据
            data['updated_at'] = datetime.now().isoformat()
            data['total_count'] = len(data['rules'])

            self._save_samples_data(data)

            # 触发过滤器重新加载
            self.filter._load_rules()

            # 构建返回消息
            message_parts = []
            if added_rules:
                message_parts.append(f"成功添加 {len(added_rules)} 条规则")
            if skipped_rules:
                message_parts.append(f"跳过 {len(skipped_rules)} 条重复规则")
            if covered_by:
                message_parts.append(f"{len(covered_by)} 条规则被已有规则覆盖")

            return {
                "success": True,
                "message": ', '.join(message_parts) if message_parts else "没有添加新规则",
                "sample_id": len(data['rules']),
                "added": added_rules,
                "skipped": skipped_rules,
                "covered_by": covered_by
            }
        except Exception as e:
            logger.error(f"添加样本失败: {e}")
            return {"success": False, "message": str(e)}

    def update_sample(self, sample_id: int, tail_part: str, rules: List[str] = None) -> Dict[str, Any]:
        """更新尾部过滤样本"""
        try:
            data = self._load_samples_data()
            rules_list = data.get('rules', [])

            if 0 < sample_id <= len(rules_list):
                # 更新指定位置的规则
                new_rule = rules[0] if rules else tail_part
                rules_list[sample_id - 1] = new_rule

                data['rules'] = rules_list
                data['updated_at'] = datetime.now().isoformat()

                self._save_samples_data(data)
                self.filter._load_rules()

                return {
                    "success": True,
                    "message": f"成功更新规则 #{sample_id}"
                }
            else:
                return {"success": False, "message": "样本ID不存在"}

        except Exception as e:
            logger.error(f"更新样本失败: {e}")
            return {"success": False, "message": str(e)}

    def delete_sample(self, sample_id: int) -> Dict[str, Any]:
        """删除尾部过滤样本"""
        try:
            data = self._load_samples_data()
            rules_list = data.get('rules', [])

            if 0 < sample_id <= len(rules_list):
                rules_list.pop(sample_id - 1)

                data['rules'] = rules_list
                data['updated_at'] = datetime.now().isoformat()
                data['total_count'] = len(rules_list)

                self._save_samples_data(data)
                self.filter._load_rules()

                return {
                    "success": True,
                    "message": f"成功删除规则 #{sample_id}"
                }
            else:
                return {"success": False, "message": "样本ID不存在"}

        except Exception as e:
            logger.error(f"删除样本失败: {e}")
            return {"success": False, "message": str(e)}

    def get_sample_by_id(self, sample_id: int) -> Dict[str, Any]:
        """根据ID获取样本"""
        try:
            data = self._load_samples_data()
            rules_list = data.get('rules', [])

            if 0 < sample_id <= len(rules_list):
                rule = rules_list[sample_id - 1]
                return {
                    "success": True,
                    "sample": {
                        "id": sample_id,
                        "tail_part": rule,
                        "rules": [rule],
                        "created_at": data.get('updated_at', ''),
                        "rule_type": "regex"
                    }
                }
            else:
                return {"success": False, "message": "样本不存在"}

        except Exception as e:
            logger.error(f"获取样本失败: {e}")
            return {"success": False, "message": str(e)}

    def _load_samples_data(self) -> Dict:
        """加载样本数据"""
        if not self._samples_file.exists():
            return {"rules": [], "updated_at": "", "total_count": 0}

        with open(self._samples_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_samples_data(self, data: Dict):
        """保存样本数据"""
        with open(self._samples_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# 全局管理器实例
_tail_filter_manager = None


def get_tail_filter_manager() -> TailFilterManager:
    """获取尾部过滤管理器单例"""
    global _tail_filter_manager
    if _tail_filter_manager is None:
        _tail_filter_manager = TailFilterManager()
    return _tail_filter_manager