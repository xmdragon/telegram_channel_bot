#!/usr/bin/env python3
"""
性能分析工具
分析performance.log中的性能数据，识别瓶颈并生成报告

使用方法:
    python3 tools/analysis/performance_analyzer.py
    python3 tools/analysis/performance_analyzer.py --last-hours 1
    python3 tools/analysis/performance_analyzer.py --channel-filter "-1002557968812"
    python3 tools/analysis/performance_analyzer.py --report-format json
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, Counter
import statistics

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.path_config import PathConfig


class PerformanceAnalyzer:
    """性能分析器"""
    
    def __init__(self, log_file_path: Optional[str] = None):
        self.log_file = Path(log_file_path) if log_file_path else (PathConfig.LOGS_DIR / "performance.log")
        self.data: List[Dict[str, Any]] = []
        self.filter_data: List[Dict[str, Any]] = []
        
    def load_data(self, last_hours: Optional[int] = None, channel_filter: Optional[str] = None) -> int:
        """加载性能数据"""
        if not self.log_file.exists():
            print(f"❌ 性能日志文件不存在: {self.log_file}")
            return 0
        
        # 计算时间过滤器
        time_filter = None
        if last_hours:
            time_filter = datetime.now() - timedelta(hours=last_hours)
        
        loaded_count = 0
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # 时间过滤
                    if time_filter:
                        timestamp_str = data.get('timestamp')
                        if timestamp_str:
                            try:
                                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                if timestamp < time_filter:
                                    continue
                            except ValueError:
                                pass
                    
                    # 频道过滤
                    if channel_filter and data.get('channel_id') != channel_filter:
                        continue
                    
                    self.data.append(data)
                    loaded_count += 1
                    
                except json.JSONDecodeError as e:
                    print(f"⚠️ 第{line_num}行JSON解析错误: {e}")
                    continue
        
        print(f"✅ 加载了 {loaded_count} 条性能记录")
        return loaded_count
    
    def analyze_bottlenecks(self) -> Dict[str, Any]:
        """分析性能瓶颈"""
        analysis = {
            'total_records': len(self.data),
            'time_range': self._get_time_range(),
            'slow_operations': [],
            'filter_performance': {},
            'channel_performance': {},
            'media_performance': {},
            'bottleneck_summary': []
        }
        
        # 1. 找出最慢的操作
        slow_operations = [d for d in self.data if d.get('total_time_ms', 0) > 3000]  # 超过3秒
        slow_operations.sort(key=lambda x: x.get('total_time_ms', 0), reverse=True)
        analysis['slow_operations'] = slow_operations[:20]  # Top 20
        
        # 2. 过滤器性能分析
        filter_times = defaultdict(list)
        for record in self.data:
            stages = record.get('stages', {})
            # 从过滤管道提取过滤器时间
            filter_stage = stages.get('pipeline_execution', {})
            if isinstance(filter_stage, dict) and 'children' in filter_stage:
                for filter_name, filter_data in filter_stage['children'].items():
                    if isinstance(filter_data, dict):
                        time_ms = filter_data.get('time_ms', 0)
                        filter_times[filter_name].append(time_ms)
        
        # 计算过滤器统计
        for filter_name, times in filter_times.items():
            if times:
                analysis['filter_performance'][filter_name] = {
                    'count': len(times),
                    'avg_time_ms': statistics.mean(times),
                    'max_time_ms': max(times),
                    'median_time_ms': statistics.median(times),
                    'total_time_ms': sum(times)
                }
        
        # 3. 按频道分析
        channel_times = defaultdict(list)
        for record in self.data:
            channel_id = record.get('channel_id')
            if channel_id:
                total_time = record.get('total_time_ms', 0)
                channel_times[channel_id].append({
                    'time_ms': total_time,
                    'channel_name': record.get('channel_name', 'Unknown'),
                    'message_type': record.get('message_type', 'unknown')
                })
        
        # 频道性能统计
        for channel_id, records in channel_times.items():
            times = [r['time_ms'] for r in records]
            if times:
                analysis['channel_performance'][channel_id] = {
                    'channel_name': records[0]['channel_name'],
                    'message_count': len(times),
                    'avg_time_ms': statistics.mean(times),
                    'max_time_ms': max(times),
                    'total_time_ms': sum(times),
                    'slow_messages_count': sum(1 for t in times if t > 5000)  # 超过5秒的消息
                }
        
        # 4. 媒体处理性能
        media_records = [r for r in self.data if r.get('message_type') != 'text']
        if media_records:
            media_times = [r['total_time_ms'] for r in media_records if r.get('total_time_ms', 0) > 0]
            if media_times:
                analysis['media_performance'] = {
                    'count': len(media_times),
                    'avg_time_ms': statistics.mean(media_times),
                    'max_time_ms': max(media_times),
                    'median_time_ms': statistics.median(media_times)
                }
        
        # 5. 生成瓶颈摘要
        bottlenecks = []
        
        # 最慢的过滤器
        if analysis['filter_performance']:
            slowest_filter = max(analysis['filter_performance'].items(), 
                               key=lambda x: x[1]['avg_time_ms'])
            bottlenecks.append({
                'type': 'filter',
                'name': slowest_filter[0],
                'avg_time_ms': slowest_filter[1]['avg_time_ms'],
                'description': f"过滤器 {slowest_filter[0]} 平均耗时 {slowest_filter[1]['avg_time_ms']:.1f}ms"
            })
        
        # 最慢的频道
        if analysis['channel_performance']:
            slowest_channel = max(analysis['channel_performance'].items(),
                                key=lambda x: x[1]['avg_time_ms'])
            bottlenecks.append({
                'type': 'channel',
                'name': slowest_channel[1]['channel_name'],
                'channel_id': slowest_channel[0],
                'avg_time_ms': slowest_channel[1]['avg_time_ms'],
                'description': f"频道 {slowest_channel[1]['channel_name']} 平均耗时 {slowest_channel[1]['avg_time_ms']:.1f}ms"
            })
        
        # 媒体处理瓶颈
        if analysis['media_performance'] and analysis['media_performance']['avg_time_ms'] > 2000:
            bottlenecks.append({
                'type': 'media',
                'avg_time_ms': analysis['media_performance']['avg_time_ms'],
                'description': f"媒体处理平均耗时 {analysis['media_performance']['avg_time_ms']:.1f}ms"
            })
        
        analysis['bottleneck_summary'] = bottlenecks
        
        return analysis
    
    def _get_time_range(self) -> Dict[str, str]:
        """获取数据时间范围"""
        if not self.data:
            return {'start': 'N/A', 'end': 'N/A', 'duration': 'N/A'}
        
        timestamps = []
        for record in self.data:
            timestamp_str = record.get('timestamp')
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    timestamps.append(timestamp)
                except ValueError:
                    continue
        
        if not timestamps:
            return {'start': 'N/A', 'end': 'N/A', 'duration': 'N/A'}
        
        start_time = min(timestamps)
        end_time = max(timestamps)
        duration = end_time - start_time
        
        return {
            'start': start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'end': end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'duration': str(duration)
        }
    
    def generate_report(self, format_type: str = 'text') -> str:
        """生成分析报告"""
        if not self.data:
            return "❌ 没有可分析的数据"
        
        analysis = self.analyze_bottlenecks()
        
        if format_type == 'json':
            return json.dumps(analysis, ensure_ascii=False, indent=2)
        
        # 文本报告
        report = []
        report.append("🔍 消息采集性能分析报告")
        report.append("=" * 50)
        report.append(f"分析时间范围: {analysis['time_range']['start']} ~ {analysis['time_range']['end']}")
        report.append(f"数据持续时间: {analysis['time_range']['duration']}")
        report.append(f"总记录数: {analysis['total_records']}")
        report.append("")
        
        # 瓶颈摘要
        report.append("🚨 性能瓶颈摘要")
        report.append("-" * 30)
        if analysis['bottleneck_summary']:
            for i, bottleneck in enumerate(analysis['bottleneck_summary'], 1):
                report.append(f"{i}. {bottleneck['description']}")
        else:
            report.append("✅ 未发现明显的性能瓶颈")
        report.append("")
        
        # 最慢操作
        if analysis['slow_operations']:
            report.append("⚠️ 最慢的操作 (Top 10)")
            report.append("-" * 30)
            for i, op in enumerate(analysis['slow_operations'][:10], 1):
                channel_name = op.get('channel_name', 'Unknown')[:15]
                time_ms = op.get('total_time_ms', 0)
                msg_id = op.get('message_id', 'N/A')
                report.append(f"{i:2d}. {time_ms:7.1f}ms | {channel_name:15s} | 消息#{msg_id}")
            report.append("")
        
        # 过滤器性能
        if analysis['filter_performance']:
            report.append("🔧 过滤器性能分析")
            report.append("-" * 30)
            # 按平均时间排序
            sorted_filters = sorted(analysis['filter_performance'].items(),
                                  key=lambda x: x[1]['avg_time_ms'], reverse=True)
            for filter_name, stats in sorted_filters:
                report.append(f"{filter_name:20s} | 平均: {stats['avg_time_ms']:6.1f}ms | "
                            f"最大: {stats['max_time_ms']:6.1f}ms | 次数: {stats['count']:4d}")
            report.append("")
        
        # 频道性能
        if analysis['channel_performance']:
            report.append("📺 频道性能分析 (Top 10)")
            report.append("-" * 30)
            # 按平均时间排序
            sorted_channels = sorted(analysis['channel_performance'].items(),
                                   key=lambda x: x[1]['avg_time_ms'], reverse=True)
            for channel_id, stats in sorted_channels[:10]:
                channel_name = stats['channel_name'][:20]
                avg_time = stats['avg_time_ms']
                msg_count = stats['message_count']
                slow_count = stats['slow_messages_count']
                report.append(f"{channel_name:20s} | 平均: {avg_time:6.1f}ms | "
                            f"消息: {msg_count:3d} | 慢消息: {slow_count:2d}")
            report.append("")
        
        # 媒体处理性能
        if analysis['media_performance']:
            mp = analysis['media_performance']
            report.append("🖼️ 媒体处理性能")
            report.append("-" * 30)
            report.append(f"媒体消息数量: {mp['count']}")
            report.append(f"平均处理时间: {mp['avg_time_ms']:.1f}ms")
            report.append(f"最长处理时间: {mp['max_time_ms']:.1f}ms")
            report.append(f"中位数时间: {mp['median_time_ms']:.1f}ms")
            report.append("")
        
        # 优化建议
        report.append("💡 优化建议")
        report.append("-" * 30)
        suggestions = self._generate_suggestions(analysis)
        for i, suggestion in enumerate(suggestions, 1):
            report.append(f"{i}. {suggestion}")
        
        return "\n".join(report)
    
    def _generate_suggestions(self, analysis: Dict[str, Any]) -> List[str]:
        """生成优化建议"""
        suggestions = []
        
        # 过滤器优化建议
        if analysis['filter_performance']:
            slowest_filters = sorted(analysis['filter_performance'].items(),
                                   key=lambda x: x[1]['avg_time_ms'], reverse=True)[:3]
            for filter_name, stats in slowest_filters:
                if stats['avg_time_ms'] > 500:
                    suggestions.append(f"优化 {filter_name} 过滤器 (当前平均 {stats['avg_time_ms']:.1f}ms)")
        
        # 媒体处理优化
        if analysis['media_performance'] and analysis['media_performance']['avg_time_ms'] > 3000:
            suggestions.append("考虑并行处理媒体文件或增加下载超时优化")
        
        # 频道特定优化
        if analysis['channel_performance']:
            problematic_channels = [
                (cid, stats) for cid, stats in analysis['channel_performance'].items()
                if stats['avg_time_ms'] > 5000 or stats['slow_messages_count'] > stats['message_count'] * 0.3
            ]
            if problematic_channels:
                suggestions.append("检查特定频道的消息特征，考虑针对性优化")
        
        # 通用建议
        slow_ops_count = len(analysis.get('slow_operations', []))
        total_records = analysis.get('total_records', 0)
        if total_records > 0 and slow_ops_count / total_records > 0.1:
            suggestions.append("考虑增加处理器并发度或优化数据库查询")
        
        if not suggestions:
            suggestions.append("系统性能良好，继续保持监控")
        
        return suggestions


def main():
    parser = argparse.ArgumentParser(description='分析消息采集性能数据')
    parser.add_argument('--log-file', help='指定性能日志文件路径')
    parser.add_argument('--last-hours', type=int, help='只分析最近N小时的数据')
    parser.add_argument('--channel-filter', help='只分析指定频道的数据')
    parser.add_argument('--report-format', choices=['text', 'json'], default='text',
                       help='报告格式 (默认: text)')
    
    args = parser.parse_args()
    
    analyzer = PerformanceAnalyzer(args.log_file)
    
    # 加载数据
    record_count = analyzer.load_data(args.last_hours, args.channel_filter)
    if record_count == 0:
        print("❌ 没有找到符合条件的性能数据")
        sys.exit(1)
    
    # 生成报告
    try:
        report = analyzer.generate_report(args.report_format)
        print(report)
    except Exception as e:
        print(f"❌ 生成报告时出错: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()