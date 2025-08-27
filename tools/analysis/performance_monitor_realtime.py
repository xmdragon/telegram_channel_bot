#!/usr/bin/env python3
"""
实时性能监控工具
实时监控performance.log文件，显示性能警报

使用方法:
    python3 tools/analysis/performance_monitor_realtime.py
    python3 tools/analysis/performance_monitor_realtime.py --threshold 3000
    python3 tools/analysis/performance_monitor_realtime.py --show-all
"""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.path_config import PathConfig


class RealtimePerformanceMonitor:
    """实时性能监控器"""
    
    def __init__(self, threshold_ms: int = 5000, show_all: bool = False):
        self.log_file = PathConfig.LOGS_DIR / "performance.log"
        self.threshold_ms = threshold_ms
        self.show_all = show_all
        self.last_position = 0
        self.stats = {
            'total_processed': 0,
            'slow_operations': 0,
            'avg_time_ms': 0,
            'max_time_ms': 0
        }
        
    def start_monitoring(self):
        """开始实时监控"""
        print(f"🔍 开始实时监控消息采集性能...")
        print(f"📊 性能阈值: {self.threshold_ms}ms")
        print(f"📁 监控文件: {self.log_file}")
        print(f"显示模式: {'所有消息' if self.show_all else '仅慢消息'}")
        print("-" * 60)
        
        if not self.log_file.exists():
            print(f"⚠️ 性能日志文件不存在，等待创建...")
        
        try:
            while True:
                self._check_new_data()
                time.sleep(1)  # 每秒检查一次
        except KeyboardInterrupt:
            print("\n👋 监控已停止")
            self._print_summary()
    
    def _check_new_data(self):
        """检查新的日志数据"""
        if not self.log_file.exists():
            return
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                f.seek(self.last_position)
                new_lines = f.readlines()
                self.last_position = f.tell()
            
            for line in new_lines:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    self._process_record(data)
                except json.JSONDecodeError:
                    continue
                    
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"❌ 读取日志文件错误: {e}")
    
    def _process_record(self, record: Dict[str, Any]):
        """处理单条性能记录"""
        total_time = record.get('total_time_ms', 0)
        operation = record.get('operation', 'unknown')
        
        # 更新统计
        self.stats['total_processed'] += 1
        if total_time > self.threshold_ms:
            self.stats['slow_operations'] += 1
        
        # 更新平均时间和最大时间
        if self.stats['total_processed'] == 1:
            self.stats['avg_time_ms'] = total_time
        else:
            self.stats['avg_time_ms'] = (
                (self.stats['avg_time_ms'] * (self.stats['total_processed'] - 1) + total_time) / 
                self.stats['total_processed']
            )
        
        self.stats['max_time_ms'] = max(self.stats['max_time_ms'], total_time)
        
        # 决定是否显示
        should_show = self.show_all or total_time > self.threshold_ms
        
        if should_show:
            self._print_record(record, is_slow=total_time > self.threshold_ms)
    
    def _print_record(self, record: Dict[str, Any], is_slow: bool = False):
        """打印性能记录"""
        timestamp = record.get('timestamp', 'Unknown')
        operation = record.get('operation', 'unknown')
        total_time = record.get('total_time_ms', 0)
        channel_name = record.get('channel_name', 'Unknown')[:15]
        message_id = record.get('message_id', 'N/A')
        message_type = record.get('message_type', 'text')
        
        # 时间戳简化显示
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_str = dt.strftime('%H:%M:%S')
        except:
            time_str = timestamp[:8] if len(timestamp) >= 8 else timestamp
        
        # 性能标识
        if is_slow:
            if total_time > 10000:  # 超过10秒
                perf_icon = "🚨"
            elif total_time > 5000:  # 超过5秒
                perf_icon = "⚠️"
            else:
                perf_icon = "🐌"
        else:
            perf_icon = "✅"
        
        # 格式化输出
        print(f"{perf_icon} {time_str} | {total_time:7.1f}ms | {operation:20s} | "
              f"{channel_name:15s} | {message_type:5s} | #{message_id}")
        
        # 如果是严重慢的操作，显示详细分解
        if total_time > self.threshold_ms * 2:  # 超过阈值2倍
            self._print_breakdown(record)
    
    def _print_breakdown(self, record: Dict[str, Any]):
        """打印性能分解"""
        stages = record.get('stages', {})
        if not stages:
            return
        
        print("    📊 性能分解:")
        for stage_name, stage_data in stages.items():
            if isinstance(stage_data, dict):
                stage_time = stage_data.get('time_ms', 0)
                if stage_time > 100:  # 只显示超过100ms的阶段
                    print(f"      {stage_name:20s}: {stage_time:6.1f}ms")
                
                # 显示子阶段（过滤器等）
                children = stage_data.get('children', {})
                if children:
                    slow_children = [(name, child) for name, child in children.items() 
                                   if isinstance(child, dict) and child.get('time_ms', 0) > 100]
                    if slow_children:
                        for child_name, child_data in slow_children:
                            child_time = child_data.get('time_ms', 0)
                            print(f"        └─ {child_name:16s}: {child_time:6.1f}ms")
        print()
    
    def _print_summary(self):
        """打印监控摘要"""
        print("\n📊 监控摘要")
        print("-" * 40)
        print(f"总处理消息: {self.stats['total_processed']}")
        print(f"慢消息数量: {self.stats['slow_operations']}")
        print(f"慢消息比例: {self.stats['slow_operations']/max(self.stats['total_processed'], 1)*100:.1f}%")
        print(f"平均处理时间: {self.stats['avg_time_ms']:.1f}ms")
        print(f"最长处理时间: {self.stats['max_time_ms']:.1f}ms")
    
    def _get_bottleneck_alerts(self, record: Dict[str, Any]) -> List[str]:
        """获取瓶颈警报"""
        alerts = []
        total_time = record.get('total_time_ms', 0)
        
        if total_time > 10000:
            alerts.append("🚨 极慢操作 (>10s)")
        elif total_time > 5000:
            alerts.append("⚠️ 慢操作 (>5s)")
        
        # 检查特定瓶颈
        stages = record.get('stages', {})
        for stage_name, stage_data in stages.items():
            if isinstance(stage_data, dict):
                stage_time = stage_data.get('time_ms', 0)
                
                if stage_name == 'pipeline_execution' and stage_time > 3000:
                    alerts.append("🔧 过滤管道慢")
                elif stage_name == 'media_processing' and stage_time > 5000:
                    alerts.append("🖼️ 媒体处理慢")
        
        return alerts


def main():
    parser = argparse.ArgumentParser(description='实时监控消息采集性能')
    parser.add_argument('--threshold', type=int, default=5000,
                       help='慢操作阈值(毫秒，默认5000)')
    parser.add_argument('--show-all', action='store_true',
                       help='显示所有操作，不仅慢操作')
    
    args = parser.parse_args()
    
    monitor = RealtimePerformanceMonitor(
        threshold_ms=args.threshold,
        show_all=args.show_all
    )
    
    monitor.start_monitoring()


if __name__ == '__main__':
    main()