# Telegram 消息采集审核系统

一个智能的 Telegram 消息采集、过滤和审核系统，支持从多个频道采集消息，通过人工审核后自动转发到目标频道。

## ✨ 功能特性

- 🔄 **多频道采集**: 同时监控多个 Telegram 频道
- 🛡️ **智能过滤**: 自动识别和过滤广告消息
- 👥 **人工审核**: 转发到审核群进行人工确认
- ⏰ **自动转发**: 30分钟无人审核自动转发
- 🔄 **内容替换**: 自动替换频道相关信息
- 🌐 **Web管理**: 现代化的 Web 界面管理
- 📊 **数据统计**: 详细的消息处理统计
- 🚀 **批量操作**: 支持批量审核和管理
- 🔐 **WebSocket认证**: 交互式 Telegram 登录
- 📱 **响应式设计**: 适配各种设备

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
- **Telegram**: Telethon (支持真人账号)
- **部署**: Docker + Docker Compose
- **通信**: WebSocket (实时认证)

## 🚀 快速开始

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
# 主界面: http://localhost:8000
# 配置界面: http://localhost:8000/config
```

### 方式二：本地部署

#### 1. 环境准备

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
```

#### 2. 初始化系统

```bash
# 初始化数据库和默认配置
python init_db.py

# 运行 Telethon 设置脚本（推荐）
python setup_telethon.py
```

#### 3. 启动系统

```bash
# 开发模式
python main.py

# 或使用Docker
docker-compose up -d
```

## 📱 系统配置

### 1. Telegram 认证

访问 http://localhost:8000/auth 完成 Telegram 登录：

**认证流程**：
1. 输入 API ID、API Hash 和 Session Name
2. 输入手机号码
3. 输入收到的验证码
4. 如果启用了两步验证，输入两步验证密码
5. 认证成功后自动跳转到主界面

**获取 API 凭据**：
- 访问 https://my.telegram.org
- 登录您的 Telegram 账号
- 点击 "API development tools"
- 创建一个新的应用
- 记录下 API ID 和 API Hash

### 2. 频道配置

访问 http://localhost:8000/config 配置频道：

**必须配置的参数**：
- **源频道**: 添加要监听的频道
- **审核群**: 设置审核群 ID
- **目标频道**: 设置转发目标频道

### 3. 过滤配置

在配置界面设置过滤规则：

- **关键词过滤**: 包含关键词的消息会被过滤
- **正则表达式**: 支持复杂的匹配规则
- **自定义规则**: 添加自定义过滤规则

## �� 使用指南

### Web 界面操作

#### 主界面 (http://localhost:8000)
- **消息审核**: 查看待审核消息列表，单个或批量批准/拒绝消息
- **统计监控**: 实时查看消息处理统计，监控系统运行状态
- **点击统计模块**: 可以筛选不同类型的消息

#### 配置界面 (http://localhost:8000/config)
- **频道管理**: 添加、编辑、删除、启用/禁用频道
- **规则管理**: 添加、编辑、删除过滤规则
- **系统设置**: 配置系统参数和缓存管理

#### 状态界面 (http://localhost:8000/status)
- **系统状态**: 查看系统运行状态和性能指标
- **服务监控**: 监控各个服务的运行状态

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

## 🐳 Docker 部署

### 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DATABASE_URL` | `sqlite:///./telegram_system.db` | 数据库连接URL |
| `REDIS_URL` | `redis://redis:6379` | Redis连接URL |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `TZ` | `Asia/Shanghai` | 时区设置 |

### 常用命令

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f app

# 停止服务
docker-compose down

# 开发环境（代码热重载）
docker-compose -f docker-compose.dev.yml up -d
```

### 数据持久化

项目会自动创建以下目录：
- `./sessions/` - Telegram 会话文件
- `./logs/` - 应用日志
- `./data/` - 数据文件

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

支持 SQLite 和 PostgreSQL：

```env
# SQLite (默认)
DATABASE_URL=sqlite:///./telegram_system.db

# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/telegram_system
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
# 备份 SQLite 数据库
cp telegram_system.db backup_$(date +%Y%m%d).db

# 备份 PostgreSQL
docker-compose exec db pg_dump -U postgres telegram_system > backup.sql
```

### 性能优化

1. **数据库优化**:
   - 定期清理旧消息
   - 添加适当的索引

2. **内存优化**:
   - 调整 Redis 配置
   - 限制消息缓存大小

## 🔧 故障排除

### 常见问题

1. **Telegram 客户端无法连接**:
   - 检查 API ID 和 API Hash 是否正确
   - 确认手机号码格式是否正确 (+8613800138000)
   - 首次启动时需要输入验证码

2. **无法接收频道消息**:
   - 确认您的账号已加入源频道
   - 检查频道 ID 是否正确

3. **数据库连接失败**:
   - 检查数据库 URL 配置
   - 确认数据库服务正在运行

4. **消息过滤不准确**:
   - 调整过滤关键词
   - 优化正则表达式规则

5. **WebSocket 连接失败**:
   - 检查服务器是否正常运行
   - 确认防火墙设置

### 调试模式

```bash
# 启用调试日志
export LOG_LEVEL=DEBUG
python main.py
```

## 📁 项目结构

```
telegram_channel_bot/
├── app/                    # 应用核心代码
│   ├── api/               # API 路由
│   ├── core/              # 核心配置
│   ├── services/          # 业务服务
│   └── telegram/          # Telegram 相关
├── static/                # 前端静态文件
│   ├── assets/            # 资源文件
│   │   ├── css/          # 样式文件
│   │   ├── js/           # JavaScript 文件
│   │   └── fonts/        # 字体文件
│   └── *.html            # HTML 页面
├── scripts/               # 管理脚本
├── sessions/              # Telegram 会话文件
├── logs/                  # 日志文件
├── data/                  # 数据文件
├── docker-compose.yml     # Docker 配置
├── requirements.txt       # Python 依赖
└── main.py               # 应用入口
```

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 发起 Pull Request

## 📄 许可证

MIT License

## 📞 支持

如有问题，请提交 Issue 或联系维护者。

---

**注意**: 本项目仅用于学习和研究目的，请遵守相关法律法规和 Telegram 服务条款。