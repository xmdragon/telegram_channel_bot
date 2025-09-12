# 服务分离架构使用指南

## 概述

为了解决本地开发时主进程停止导致采集和页面都无法访问的问题，我们将系统重构为服务分离架构。现在系统由三个独立的服务组成：

- **Web服务器** (`web_server.py`) - 提供Web界面和API服务
- **Telegram采集服务** (`message_collector.py`) - 处理Telegram消息采集
- **消息调度服务** (`message_scheduler.py`) - 处理自动转发和数据清理

## 使用方法

### 启动所有服务
```bash
./dev.sh
# 或
./dev.sh all
```

### 启动特定服务
```bash
./dev.sh web                    # 仅启动Web服务
./dev.sh collector              # 仅启动采集服务
./dev.sh scheduler              # 仅启动调度服务
./dev.sh web collector          # 启动Web和采集服务
```

### 查看服务状态
```bash
./dev.sh --status
```

### 使用传统模式（单进程）
```bash
./dev.sh --legacy
```

### 获取帮助
```bash
./dev.sh --help
```

## 服务详情

### Web服务器 (web_server.py)
- **端口**: 8000
- **功能**: 
  - 提供Web界面 (http://localhost:8000)
  - API接口服务
  - 静态文件服务
  - 健康检查端点
- **日志**: `./logs/app.log`

### Telegram采集服务 (message_collector.py)
- **功能**:
  - Telegram消息采集
  - 消息过滤和处理
  - 媒体文件下载
- **日志**: `./logs/telegram_collector.log`
- **依赖**: 需要Telegram认证

### 消息调度服务 (message_scheduler.py)
- **功能**:
  - 自动转发定时任务
  - 数据清理任务
  - 媒体文件清理
- **日志**: `./logs/message_scheduler.log`

## 开发优势

### ✅ 解决的问题
- Web服务和采集服务独立运行，互不影响
- 修改Web代码不会中断消息采集
- 可以单独重启某个服务进行调试
- 支持选择性启动服务

### ✅ 新增功能
- 进程管理器自动监控服务状态
- 服务异常时自动重启
- 健康状态监控和上报
- 实时服务状态查看

## 健康监控

### API端点
- `GET /api/health` - 获取系统整体健康状态
- `GET /api/health/{service_name}` - 获取指定服务健康状态

### 监控数据
每个服务会定期上报以下信息：
- 服务状态 (healthy/unhealthy/starting/stopping)
- 运行时间
- 最后心跳时间
- 服务特定的元数据
- 错误信息（如有）

### 状态存储
- 健康状态存储在Redis中
- 30分钟自动过期防止僵尸记录
- 超过2分钟无心跳视为异常

## 日志管理

### 日志文件分布
```
logs/
├── app.log                    # Web服务日志
├── telegram_collector.log    # 采集服务日志
├── message_scheduler.log     # 调度服务日志
├── error.log                 # 所有错误日志汇总
└── supervisor_status.json    # 进程管理器状态
```

### 日志轮转
- 按小时轮转日志文件
- 保留7天的历史日志
- 错误日志单独记录

## 进程管理

### 进程管理器特性
- 自动重启崩溃的服务
- 5秒延迟重启避免频繁重启
- 优雅关闭所有子进程
- 实时状态监控和汇报

### 信号处理
- 支持 SIGINT (Ctrl+C) 和 SIGTERM
- 优雅关闭所有服务
- 等待服务完成当前任务

## 开发工作流

### 典型使用场景

#### 1. 全栈开发
```bash
./dev.sh                    # 启动所有服务
# 修改前端代码 -> Web服务自动重载
# 修改采集逻辑 -> 重启采集服务
# 查看状态
./dev.sh --status
```

#### 2. 前端开发
```bash
./dev.sh web               # 仅启动Web服务
# 快速测试前端修改，不受采集服务影响
```

#### 3. 后端调试
```bash
./dev.sh collector         # 仅启动采集服务
# 专注调试Telegram采集逻辑
```

#### 4. 性能测试
```bash
./dev.sh web scheduler     # 启动Web和调度，不启动采集
# 测试Web界面和调度性能
```

## 故障排除

### 常见问题

#### 1. 服务启动失败
```bash
./dev.sh --status          # 查看错误信息
# 检查对应服务的日志文件
tail -f logs/telegram_collector.log
```

#### 2. 端口被占用
```bash
lsof -ti:8000 | xargs kill -9    # 清理占用的端口
./dev.sh web                     # 重新启动
```

#### 3. Redis连接失败
```bash
docker compose ps redis     # 检查Redis状态
docker compose up -d redis  # 启动Redis
```

### 调试技巧

#### 1. 单服务调试
```bash
# 直接运行单个服务进行调试
python3 web_server.py
python3 message_collector.py
python3 message_scheduler.py
```

#### 2. 查看详细日志
```bash
tail -f logs/*.log          # 查看所有日志
grep ERROR logs/*.log       # 查找错误信息
```

#### 3. 健康状态检查
```bash
curl http://localhost:8000/api/health | jq .
# 查看所有服务的健康状态
```

## 兼容性

### 向后兼容
- 可通过 `--legacy` 参数使用传统模式
- 所有API接口保持不变
- Web界面功能完全一致

### 迁移指南
现有的开发流程无需修改，只需：
1. 使用新的 `./dev.sh` 命令启动
2. 根据需要选择启动的服务
3. 通过 `--status` 查看服务状态

## 总结

服务分离架构大幅提升了开发体验：
- ✅ 解决了服务耦合问题
- ✅ 支持独立调试和部署
- ✅ 提供了完善的监控机制
- ✅ 保持了向后兼容性

这个架构既解决了当前的开发痛点，又为未来的扩展奠定了基础。