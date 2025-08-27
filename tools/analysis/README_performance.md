# 消息采集性能分析工具

本目录包含用于分析和监控消息采集系统性能的工具。

## 工具列表

### 1. 性能分析器 (performance_analyzer.py)
分析历史性能数据，生成详细报告。

#### 基本用法
```bash
# 分析所有性能数据
python3 tools/analysis/performance_analyzer.py

# 分析最近1小时的数据
python3 tools/analysis/performance_analyzer.py --last-hours 1

# 只分析特定频道
python3 tools/analysis/performance_analyzer.py --channel-filter "-1002557968812"

# 生成JSON格式报告
python3 tools/analysis/performance_analyzer.py --report-format json
```

#### 报告内容
- 性能瓶颈摘要
- 最慢操作Top 10
- 过滤器性能分析
- 频道性能统计
- 媒体处理性能
- 优化建议

### 2. 实时性能监控 (performance_monitor_realtime.py)
实时监控性能日志，显示慢操作警报。

#### 基本用法
```bash
# 默认监控 (显示>5秒的操作)
python3 tools/analysis/performance_monitor_realtime.py

# 设置3秒阈值
python3 tools/analysis/performance_monitor_realtime.py --threshold 3000

# 显示所有操作
python3 tools/analysis/performance_monitor_realtime.py --show-all
```

## 快速开始

1. **启动系统并等待消息处理**
2. **开始实时监控**:
   ```bash
   python3 tools/analysis/performance_monitor_realtime.py
   ```
3. **分析历史数据**:
   ```bash
   python3 tools/analysis/performance_analyzer.py --last-hours 1
   ```

## 性能日志说明

系统自动记录每条消息的详细处理时间，包括：
- 各个处理阶段耗时
- 每个过滤器的执行时间  
- 媒体下载和处理时间
- OCR识别时间
- Redis存储时间

日志文件位置：`logs/performance.log`