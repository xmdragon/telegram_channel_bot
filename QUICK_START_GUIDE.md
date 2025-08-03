# Telegram 消息审核系统 - 快速启动指南

## 🚀 系统概述

这是一个功能完整的 Telegram 消息采集、过滤和审核系统，支持从多个频道采集消息，通过人工审核后自动转发到目标频道。现在系统已具备完整的管理员功能。

## ✨ 最新功能

### ✅ 完整的管理员功能
- **频道管理**: 添加、编辑、删除、启用/禁用频道
- **规则管理**: 添加、编辑、删除过滤规则
- **系统操作**: 重启、备份、清理缓存、导出日志
- **配置管理**: 智能的配置缓存管理

### ✅ 现代化的 Web 界面
- **响应式设计**: 适配各种设备
- **实时反馈**: 操作结果即时显示
- **用户友好**: 直观的操作流程

## 🛠️ 快速部署

### 方式一：Docker 部署（推荐）

```bash
# 克隆项目
git clone <repository-url>
cd telegram_channel_bot

# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f app

# 访问系统
# 状态检查: http://localhost:8000/status
# 登录页面: http://localhost:8000/auth
# 管理界面: http://localhost:8000/admin
```

### 方式二：本地部署

```bash
# 克隆项目
git clone <repository-url>
cd telegram_channel_bot

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python init_db.py

# 启动系统
python main.py
```

## 📱 系统配置

### 1. Telegram 配置

访问 http://localhost:8000/auth 完成 Telegram 登录：

1. **获取 API 凭据**:
   - 访问 https://my.telegram.org
   - 登录您的 Telegram 账号
   - 创建应用并获取 API ID 和 API Hash

2. **Web 界面登录**:
   - 输入 API ID、API Hash 和手机号码
   - 输入验证码
   - 完成登录

### 2. 频道配置

访问 http://localhost:8000/config 配置频道：

1. **源频道**: 添加要监听的频道
2. **审核群**: 设置审核群 ID
3. **目标频道**: 设置转发目标频道

### 3. 过滤配置

在配置界面设置过滤规则：

1. **文中过滤**: 包含关键词的消息会被过滤
2. **行中过滤**: 包含关键词的行会被过滤
3. **自定义规则**: 添加自定义过滤规则

## 🎯 使用指南

### 主界面操作

访问 http://localhost:8000 进入主界面：

1. **消息审核**: 查看待审核消息
2. **批量操作**: 批量批准或拒绝消息
3. **统计信息**: 查看处理统计

### 管理界面操作

访问 http://localhost:8000/admin 进入管理界面：

#### 频道管理
- **查看频道**: 显示所有频道列表
- **添加频道**: 添加新的监听频道
- **编辑频道**: 修改频道信息
- **删除频道**: 删除不需要的频道
- **启用/禁用**: 控制频道状态

#### 规则管理
- **查看规则**: 显示所有过滤规则
- **添加规则**: 添加新的过滤规则
- **编辑规则**: 修改规则信息
- **删除规则**: 删除不需要的规则

#### 系统操作
- **系统重启**: 重启系统服务
- **数据备份**: 备份系统数据
- **清理缓存**: 清理配置缓存
- **导出日志**: 导出系统日志

### 配置界面操作

访问 http://localhost:8000/config 进入配置界面：

#### Telegram 配置
- **API 凭据**: 设置 API ID、API Hash、手机号
- **配置验证**: 验证配置的有效性

#### 频道配置
- **源频道**: 管理监听的频道列表
- **审核群**: 设置审核群 ID
- **目标频道**: 设置转发目标

#### 过滤配置
- **文中关键词**: 设置整条消息过滤关键词
- **行中关键词**: 设置行过滤关键词
- **过滤开关**: 启用/禁用过滤功能

#### 账号配置
- **采集开关**: 启用/禁用账号采集
- **白名单**: 设置采集白名单
- **黑名单**: 设置采集黑名单

## 🔧 高级功能

### 命令行管理

```bash
# 查看系统统计
python scripts/manage.py stats

# 添加源频道
python scripts/manage.py add-channel @new_channel "新频道"

# 列出所有频道
python scripts/manage.py list-channels

# 添加过滤规则
python scripts/manage.py add-rule keyword "广告词"

# 清理旧消息
python scripts/manage.py cleanup --days 30
```

### API 接口

#### 管理员 API
```bash
# 获取频道列表
curl http://localhost:8000/api/admin/channels

# 添加频道
curl -X POST http://localhost:8000/api/admin/channels \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "test", "channel_name": "测试", "channel_type": "source"}'

# 清理缓存
curl -X POST http://localhost:8000/api/admin/clear-cache

# 健康检查
curl http://localhost:8000/api/admin/health
```

#### 配置 API
```bash
# 获取配置
curl http://localhost:8000/api/config

# 设置配置
curl -X POST http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"key": "test.config", "value": "test_value"}'
```

## 📊 监控和维护

### 系统状态

访问 http://localhost:8000/status 查看系统状态：

- **服务状态**: 各项服务运行状态
- **数据库连接**: 数据库连接状态
- **配置状态**: 配置加载状态

### 日志查看

```bash
# 查看应用日志
docker-compose logs app

# 实时日志
docker-compose logs -f app

# 导出日志
curl -X POST http://localhost:8000/api/admin/export-logs
```

### 数据备份

```bash
# 自动备份
curl -X POST http://localhost:8000/api/admin/backup

# 手动备份
docker-compose exec app tar -czf backup.tar.gz sessions/ data/
```

## 🐛 故障排除

### 常见问题

#### 1. Telegram 登录失败
- 检查 API ID 和 API Hash 是否正确
- 确认手机号码格式（+8613800138000）
- 检查网络连接

#### 2. 无法接收频道消息
- 确认账号已加入源频道
- 检查频道 ID 是否正确
- 验证频道权限

#### 3. 系统启动失败
- 检查端口是否被占用
- 确认数据库文件权限
- 查看错误日志

#### 4. 配置不生效
- 清理配置缓存
- 重新加载配置
- 检查配置格式

### 调试模式

```bash
# 启用调试日志
export LOG_LEVEL=DEBUG
python main.py
```

## 📈 性能优化

### 1. 系统优化
- **缓存机制**: 合理使用配置缓存
- **数据库优化**: 定期清理旧数据
- **内存管理**: 监控内存使用情况

### 2. 网络优化
- **连接池**: 使用连接池管理连接
- **超时设置**: 合理设置超时时间
- **重试机制**: 实现自动重试

### 3. 存储优化
- **数据压缩**: 压缩历史数据
- **定期清理**: 清理过期数据
- **备份策略**: 定期备份重要数据

## 🎯 下一步

### 1. 功能增强
- **批量操作**: 支持批量频道和规则操作
- **导入导出**: 支持配置的导入导出
- **模板管理**: 支持预设配置模板

### 2. 界面优化
- **编辑弹窗**: 实现频道和规则的编辑弹窗
- **拖拽排序**: 支持拖拽排序功能
- **搜索过滤**: 支持列表搜索和过滤

### 3. 监控增强
- **性能监控**: 添加系统性能监控
- **告警机制**: 实现系统告警功能
- **统计报表**: 添加详细的统计报表

## 📞 支持

如有问题，请：

1. **查看日志**: 检查系统日志获取错误信息
2. **查阅文档**: 参考项目文档和指南
3. **提交 Issue**: 在项目仓库提交 Issue
4. **联系维护者**: 直接联系项目维护者

---

**系统版本**: 1.0.0  
**最后更新**: 2024年12月  
**技术栈**: Python 3.11 + FastAPI + Vue.js 3 + Element Plus 