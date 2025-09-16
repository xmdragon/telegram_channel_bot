#!/usr/bin/env python3
"""
过滤器规则调试工具
用于检查指定消息被哪些过滤规则匹配

Usage:
    python3 check_filter_rules.py -1002203397527:24355
    python3 check_filter_rules.py -1002203397527:24355 --verbose

Author: Claude
Created: 2025-09-16
"""

import sys
import os
import json
import argparse
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis
from app.core.path_config import PathConfig
from app.services.filters.tail_filter import TailFilter
from app.services.filters.separator_filter import SeparatorFilter
from app.services.filters.markdown_filter import MarkdownFilter
from app.services.filters.ad_detector import AdDetector


@dataclass
class FilterDebugResult:
    """过滤器调试结果"""
    filter_name: str
    is_matched: bool
    matched_rules: Optional[List[Dict[str, Any]]] = None
    removed_content: Optional[str] = None
    filter_stats: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class FilterRulesChecker:
    """过滤器规则检查器"""

    def __init__(self):
        """初始化检查器"""
        # 初始化Redis连接
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True,
            encoding='utf-8'
        )

        # 初始化各个过滤器
        self.tail_filter = TailFilter()
        self.separator_filter = SeparatorFilter()
        self.markdown_filter = MarkdownFilter()
        self.ad_detector = AdDetector()

    def get_message_from_redis(self, message_id: str) -> Optional[Dict[str, Any]]:
        """从Redis获取消息内容"""
        try:
            # 解析消息ID
            if ':' not in message_id:
                print(f"❌ 无效的消息ID格式: {message_id}")
                print("正确格式: channel_id:message_id (如 -1002203397527:24355)")
                return None

            channel_id, msg_id = message_id.split(':', 1)

            # 构建Redis键
            redis_key = f"telegram:messages:{channel_id}:{msg_id}"

            # 获取消息数据
            message_data = self.redis_client.get(redis_key)
            if not message_data:
                print(f"❌ 在Redis中未找到消息: {redis_key}")
                return None

            # 解析JSON
            message = json.loads(message_data)
            return message

        except Exception as e:
            print(f"❌ 从Redis获取消息失败: {e}")
            return None

    def check_tail_filter(self, content: str, verbose: bool = False) -> FilterDebugResult:
        """检查尾部过滤规则"""
        result = FilterDebugResult(filter_name="尾部过滤器", is_matched=False)

        try:
            # 运行尾部过滤，获取匹配的规则
            filtered_content, is_filtered, removed_content, matched_rules = self.tail_filter.filter(
                content, return_matched_rules=True
            )

            result.is_matched = is_filtered
            result.matched_rules = matched_rules
            result.removed_content = removed_content if is_filtered else None

            # 输出结果
            print("\n" + "="*60)
            print("📋 尾部过滤器检查结果")
            print("="*60)

            if is_filtered and matched_rules:
                print(f"✅ 匹配到尾部过滤规则")
                for rule in matched_rules:
                    print(f"\n🎯 匹配的规则:")
                    print(f"   - 规则模式: {rule['rule_pattern']}")
                    print(f"   - 规则索引: {rule['rule_index']}")
                    print(f"   - 匹配行号: 第{rule['matched_line_number']}行")
                    print(f"   - 匹配内容: {rule['matched_line'][:100]}...")
                    print(f"   - 删除字符: {rule['removed_chars']}字符")
                    print(f"   - 删除行数: {rule['removed_lines']}行")

                    if verbose and rule['removed_content']:
                        print(f"\n   📝 删除的完整内容:")
                        print("   " + "-"*40)
                        for line in rule['removed_content'].split('\n')[:10]:
                            print(f"   {line}")
                        if len(rule['removed_content'].split('\n')) > 10:
                            print(f"   ... (还有{len(rule['removed_content'].split('\n'))-10}行)")
            else:
                print("❌ 未匹配到尾部过滤规则")

        except Exception as e:
            result.error = str(e)
            print(f"⚠️ 尾部过滤器检查失败: {e}")

        return result

    def check_separator_filter(self, content: str, verbose: bool = False) -> FilterDebugResult:
        """检查分隔符过滤规则"""
        result = FilterDebugResult(filter_name="分隔符过滤器", is_matched=False)

        try:
            # 运行分隔符过滤，获取匹配的规则
            filtered_content, stats = self.separator_filter.filter_content(
                content, return_matched_rules=True
            )

            result.is_matched = stats.get('removed_blocks_count', 0) > 0
            result.matched_rules = stats.get('matched_rules_detail', [])
            result.filter_stats = stats

            # 输出结果
            print("\n" + "="*60)
            print("📋 分隔符过滤器检查结果")
            print("="*60)

            if result.is_matched and result.matched_rules:
                print(f"✅ 匹配到{len(result.matched_rules)}个分隔符过滤规则")

                # 按规则分组
                rules_by_index = {}
                for rule in result.matched_rules:
                    idx = rule['rule_index']
                    if idx not in rules_by_index:
                        rules_by_index[idx] = []
                    rules_by_index[idx].append(rule)

                for idx, rules in rules_by_index.items():
                    first_rule = rules[0]
                    print(f"\n🎯 规则 #{idx}: {first_rule['rule_description']}")
                    print(f"   - 正则模式: {first_rule['rule_pattern']}")
                    print(f"   - 匹配类型: {first_rule['match_type']}")
                    print(f"   - 匹配次数: {len(rules)}次")

                    if first_rule['match_type'] == 'delete_after':
                        print(f"   - 匹配位置: 第{first_rule['match_line_number']}行，字符位置{first_rule['match_start_position']}")
                        print(f"   - 删除字符: {first_rule['removed_chars']}字符")
                    else:
                        print(f"   - 匹配行号: {', '.join(str(r['match_line_number']) for r in rules[:5])}")
                        if len(rules) > 5:
                            print(f"                ... (还有{len(rules)-5}行)")
                        total_chars = sum(r['removed_chars'] for r in rules)
                        print(f"   - 总删除字符: {total_chars}字符")

                    if verbose:
                        print(f"\n   📝 匹配的内容示例:")
                        for i, rule in enumerate(rules[:3]):
                            if 'matched_line' in rule:
                                print(f"   [{i+1}] 第{rule['match_line_number']}行: {rule['matched_line']}")
                            elif 'matched_text' in rule:
                                print(f"   [{i+1}] {rule['matched_text']}")
                        if len(rules) > 3:
                            print(f"   ... (还有{len(rules)-3}个匹配)")
            else:
                print("❌ 未匹配到分隔符过滤规则")

            # 输出统计信息
            if verbose:
                print(f"\n📊 统计信息:")
                print(f"   - 原始长度: {stats['original_length']}字符")
                print(f"   - 过滤后长度: {stats['filtered_length']}字符")
                print(f"   - 删除块数: {stats['removed_blocks_count']}")
                print(f"   - 匹配模式数: {stats['patterns_matched_count']}")

        except Exception as e:
            result.error = str(e)
            print(f"⚠️ 分隔符过滤器检查失败: {e}")

        return result

    def check_markdown_filter(self, content: str, entities: List = None) -> FilterDebugResult:
        """检查Markdown过滤规则"""
        result = FilterDebugResult(filter_name="Markdown过滤器", is_matched=False)

        try:
            # 运行Markdown过滤
            filtered_content, links_removed = self.markdown_filter.filter(content, entities or [])

            result.is_matched = links_removed > 0

            # 输出结果
            print("\n" + "="*60)
            print("📋 Markdown过滤器检查结果")
            print("="*60)

            if result.is_matched:
                print(f"✅ 删除了{links_removed}个Markdown链接")
            else:
                print("❌ 未发现需要过滤的Markdown链接")

        except Exception as e:
            result.error = str(e)
            print(f"⚠️ Markdown过滤器检查失败: {e}")

        return result

    def check_ad_detector(self, content: str, verbose: bool = False) -> FilterDebugResult:
        """检查广告检测规则"""
        result = FilterDebugResult(filter_name="广告检测器", is_matched=False)

        try:
            # 运行广告检测
            is_ad, total_weight, matched_keywords = self.ad_detector.detect(content)

            result.is_matched = is_ad
            result.matched_rules = matched_keywords

            # 输出结果
            print("\n" + "="*60)
            print("📋 广告检测器检查结果")
            print("="*60)

            if is_ad:
                print(f"✅ 检测为广告内容")
                print(f"   - 总权重: {total_weight:.2f}")
                print(f"   - 命中关键词数: {len(matched_keywords)}")
                print(f"\n🎯 命中的关键词:")

                for i, kw in enumerate(matched_keywords[:10], 1):
                    print(f"   [{i}] {kw['keyword']} (权重: {kw['weight']})")
                    if verbose and 'context' in kw:
                        print(f"       上下文: ...{kw['context']}...")

                if len(matched_keywords) > 10:
                    print(f"   ... (还有{len(matched_keywords)-10}个关键词)")
            else:
                print("❌ 未检测为广告内容")
                if matched_keywords:
                    print(f"   - 总权重: {total_weight:.2f} (低于阈值)")
                    print(f"   - 命中关键词数: {len(matched_keywords)}")
                    if verbose:
                        print(f"\n   弱匹配关键词:")
                        for kw in matched_keywords[:5]:
                            print(f"   - {kw['keyword']} (权重: {kw['weight']})")

        except Exception as e:
            result.error = str(e)
            print(f"⚠️ 广告检测器检查失败: {e}")

        return result

    def run(self, message_id: str, verbose: bool = False):
        """运行完整的过滤器检查"""
        print(f"\n🔍 开始检查消息: {message_id}")
        print("="*60)

        # 获取消息
        message = self.get_message_from_redis(message_id)
        if not message:
            return

        # 获取消息内容
        content = message.get('content', '')
        entities = message.get('entities', [])

        print(f"\n📄 消息信息:")
        print(f"   - 频道ID: {message.get('channel_id', 'N/A')}")
        print(f"   - 消息ID: {message.get('message_id', 'N/A')}")
        print(f"   - 内容长度: {len(content)}字符")
        print(f"   - 行数: {len(content.split(chr(10)))}行")
        print(f"   - 实体数: {len(entities)}")

        if verbose:
            print(f"\n📝 消息内容预览:")
            print("-"*40)
            lines = content.split('\n')
            for i, line in enumerate(lines[:10], 1):
                print(f"{i:3}: {line[:100]}{'...' if len(line) > 100 else ''}")
            if len(lines) > 10:
                print(f"... (还有{len(lines)-10}行)")

        # 检查各个过滤器
        results = []

        # 1. 尾部过滤
        tail_result = self.check_tail_filter(content, verbose)
        results.append(tail_result)

        # 2. 分隔符过滤
        separator_result = self.check_separator_filter(content, verbose)
        results.append(separator_result)

        # 3. Markdown过滤
        markdown_result = self.check_markdown_filter(content, entities)
        results.append(markdown_result)

        # 4. 广告检测
        ad_result = self.check_ad_detector(content, verbose)
        results.append(ad_result)

        # 总结
        print("\n" + "="*60)
        print("📊 检查总结")
        print("="*60)

        matched_filters = [r.filter_name for r in results if r.is_matched]
        if matched_filters:
            print(f"✅ 匹配的过滤器: {', '.join(matched_filters)}")
        else:
            print("❌ 未匹配任何过滤器")

        # 错误统计
        errors = [(r.filter_name, r.error) for r in results if r.error]
        if errors:
            print(f"\n⚠️ 发生错误的过滤器:")
            for name, error in errors:
                print(f"   - {name}: {error}")

        print("\n✨ 检查完成!")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='检查消息被哪些过滤规则匹配',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python3 check_filter_rules.py -1002203397527:24355
  python3 check_filter_rules.py -1002203397527:24355 --verbose
  python3 check_filter_rules.py -1002203397527:24355 -v
        '''
    )

    parser.add_argument(
        'message_id',
        help='消息ID，格式: channel_id:message_id (如 -1002203397527:24355)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细信息'
    )

    args = parser.parse_args()

    # 创建检查器并运行
    checker = FilterRulesChecker()
    checker.run(args.message_id, args.verbose)


if __name__ == '__main__':
    main()