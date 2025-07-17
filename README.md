# Telegram消息采集审核系统

一个智能的Telegram消息采集、过滤和审核系统，支持从多个频道采集消息，通过人工审核后自动转发到目标频道。

## ✨ 功能特性

- 🔄 **多频道采集**: 同时监控多个Telegram频道
- 🛡️ **智能过滤**: 自动识别和过滤广告消息
- 👥 **人工审核**: 转发到审核群进行人工确认
- ⏰ **自动转发**: 30分钟无人审核自动转发
- 🔄 **内容替换**: 自动替换频道相关信息
- 🌐 **Web管理**: 现代化的Web界面管理
- 📊 **数据统计**: 详细的消息处理统计
- 🚀 **批量操作**: 支持批量审核和管理

## 🏗️ 系统架构

```
源频道 → 消息采集 → 内容过滤 → 审核群 → Web管理界面 → 目标频道
   ↓         ↓         ↓        ↓         ↓          ↓
 监听消息   提取内容   广告检测   人工审核   批量管理    自动转发
```

## 🛠️ 技术栈

- **后端**: Python 3.11 + FastAPI
- **数据库**: SQLite/PostgreSQL + SQLAlchemy
- **缓存**: Redis
- **前端**: Vue.js 3 + Element Plus
- **Telegram**: python-telegram-bot
- **部署**: Docker + Docker Compose

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd telegram-message-system

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置系统

系统现在使用**数据库存储配置**，不再依赖.env文件。所有配置都可以通过Web界面或命令行动态管理。

```bash
# 初始化数据库和默认配置
python init_db.py
```

**重要配置项**（必须通过Web界面或命令行设置）：
- `telegram.bot_token`: Telegram机器人Token
- `telegram.api_id`: Telegram API ID  
- `telegram.api_hash`: Telegram API Hash
- `channels.source_channels`: 源频道列表
- `channels.review_group_id`: 审核群ID
- `channels.target_channel_id`: 目标频道ID

### 3. 初始化数据库

```bash
python init_db.py
```

### 4. 启动系统

```bash
# 开发模式
python main.py

# 或使用Docker
docker-compose up -d
```

### 5. 配置系统参数

通过Web界面配置必要参数：

```bash
# 启动系统
python main.py

# 访问配置界面
http://localhost:8000/config
```

**必须配置的参数**：
1. 在Telegram分类中设置机器人Token和API信息
2. 在频道设置中配置源频道、审核群和目标频道
3. 根据需要调整审核和过滤设置

### 6. 访问管理界面

- **主界面**: http://localhost:8000 - 消息审核和统计
- **管理界面**: http://localhost:8000/admin - 频道和规则管理  
- **配置界面**: http://localhost:8000/config - 系统配置管理

## 📋 使用指南

### 机器人设置

1. 创建Telegram机器人:
   - 联系 @BotFather
   - 发送 `/newbot` 创建机器人
   - 获取机器人Token

2. 配置机器人权限:
   - 将机器人添加到审核群（需要管理员权限）
   - 将机器人添加到目标频道（需要发送消息权限）

3. 获取频道ID:
   ```bash
   # 使用管理脚本
   python scripts/manage.py list-channels
   ```

### Web界面操作

1. **消息审核**:
   - 查看待审核消息列表
   - 单个或批量批准/拒绝消息
   - 查看消息详情和过滤结果

2. **统计监控**:
   - 实时查看消息处理统计
   - 监控系统运行状态

3. **过滤管理**:
   - 添加自定义过滤规则
   - 管理广告关键词

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

## ⚙️ 高级配置

### 过滤规则配置

系统支持多种过滤规则：

1. **关键词过滤**:
   ```python
   AD_KEYWORDS = ["广告", "推广", "代理", "加微信"]
   ```

2. **正则表达式过滤**:
   - 微信号: `微信[：:]\s*\w+`
   - QQ号: `QQ[：:]\s*\d+`
   - 手机号: `联系.*\d{11}`

3. **内容替换**:
   ```python
   CHANNEL_REPLACEMENTS = {
       "@原频道": "@你的频道",
       "原频道链接": "你的频道链接"
   }
   ```

### 数据库配置

支持SQLite和PostgreSQL：

```env
# SQLite (默认)
DATABASE_URL=sqlite:///./telegram_system.db

# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/telegram_system
```

## 🐳 Docker部署

### 使用Docker Compose

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 单独构建

```bash
# 构建镜像
docker build -t telegram-system .

# 运行容器
docker run -d -p 8000:8000 --env-file .env telegram-system
```

## 📊 监控和维护

### 日志查看

```bash
# 查看应用日志
docker-compose logs app

# 实时日志
docker-compose logs -f app
```

### 数据备份

```bash
# 备份SQLite数据库
cp telegram_system.db backup_$(date +%Y%m%d).db

# 备份PostgreSQL
docker-compose exec db pg_dump -U postgres telegram_system > backup.sql
```

### 性能优化

1. **数据库优化**:
   - 定期清理旧消息
   - 添加适当的索引

2. **内存优化**:
   - 调整Redis配置
   - 限制消息缓存大小

## 🔧 故障排除

### 常见问题

1. **机器人无法接收消息**:
   - 检查Token是否正确
   - 确认机器人已添加到相应群组/频道

2. **数据库连接失败**:
   - 检查数据库URL配置
   - 确认数据库服务正在运行

3. **消息过滤不准确**:
   - 调整过滤关键词
   - 优化正则表达式规则

### 调试模式

```bash
# 启用调试日志
export LOG_LEVEL=DEBUG
python main.py
```

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 发起Pull Request

## 📄 许可证

MIT License

## 📞 支持

如有问题，请提交Issue或联系维护者。