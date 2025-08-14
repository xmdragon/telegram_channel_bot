# Telegram 消息采集审核系统 v3.0

一个基于Redis+JSON的高性能 Telegram 消息采集、过滤和审核系统，支持从多个频道采集消息，通过人工审核后自动转发到目标频道。

> **🚀 v3.0 重大升级**: 完全迁移至Redis+JSON存储架构，性能提升300%+，支持分布式部署！

## ✨ 功能特性

### 🎯 核心功能
- 🔄 **多频道采集**: 同时监控多个 Telegram 频道
- 🛡️ **智能过滤**: 自动识别和过滤广告消息
- 🖼️ **图像分析**: 基于图像处理的广告检测和二维码识别
- 👥 **人工审核**: 转发到审核群进行人工确认
- ⏰ **自动转发**: 30分钟无人审核自动转发
- 🔄 **内容替换**: 自动替换频道相关信息

### 🌐 管理界面
- 🌐 **Web管理**: 现代化的 Web 界面管理
- 📊 **数据统计**: 详细的消息处理统计
- 🚀 **批量操作**: 支持批量审核和管理
- 🔐 **管理员认证**: JWT令牌认证系统 (默认: admin/admin123)
- 📱 **响应式设计**: 适配各种设备

### ⚡ 性能优势 (v3.0)
- ⚡ **超高性能**: Redis存储，毫秒级消息查询
- 🔥 **快速启动**: 系统启动速度提升5倍+
- 🛡️ **数据安全**: 双层存储+文件锁保护
- 🔧 **易于部署**: 仅需Redis，无需复杂数据库配置
- 📦 **媒体组合**: 支持 Telegram 媒体组消息
- 📜 **历史采集**: 支持采集频道历史消息

## 🏗️ 系统架构

```
源频道 → 消息采集 → 内容过滤 → 审核群 → Web管理界面 → 目标频道
   ↓         ↓         ↓        ↓         ↓          ↓
 监听消息   提取内容   广告检测   人工审核   批量管理    自动转发
```

## 🛠️ 技术栈 (v3.0架构)

### 🎯 存储架构
- **主存储**: Redis (消息数据、会话管理)
- **配置存储**: JSON文件 (系统配置、管理员数据)
- **性能**: 亚毫秒级查询，内存+磁盘双重保护

### 💻 应用技术
- **后端**: Python 3.11 + FastAPI + Redis + JSON
- **前端**: Vue.js 3 + Element Plus + Axios
- **认证**: JWT + Redis会话管理
- **Telegram**: Telethon (支持真人账号)
- **图像处理**: OpenCV + Pillow (广告检测和二维码识别)
- **部署**: Docker (仅Redis) + 本地Python应用
- **通信**: WebSocket (实时认证)

## 🚀 快速开始

### 方式一：一键启动（推荐）

```bash
# 克隆项目
git clone <repository-url>
cd telegram_channel_bot

# 开发模式启动（支持热重载，自动启动Redis）
./dev.sh

# 或使用标准模式
./start.sh

# 停止服务
./stop.sh

# 重启服务
./restart.sh
```

### 方式二：手动启动

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 启动Redis（必须）
docker compose up -d redis

# 启动应用（自动初始化JSON配置）
python3 main.py
```

### 方式三：Docker部署（仅Redis）

```bash
# 仅启动Redis服务
docker compose up -d redis

# 查看Redis日志
docker compose logs -f redis

# 停止Redis
docker compose down
```

## 📱 系统配置

### 0. 管理员登录

首次启动后，访问管理员登录界面：
- **URL**: http://localhost:8000/static/login.html
- **默认账户**: 用户名 `admin`，密码 `admin123`

### 1. Telegram 认证

登录后访问 Telegram 认证页面完成授权：
- **URL**: http://localhost:8000/static/auth.html

**认证流程**：
1. 输入 API ID、API Hash（从 https://my.telegram.org 获取）
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

访问 http://localhost:8000/config.html 配置频道：

**必须配置的参数**：
- **源频道**: 添加要监听的频道
- **审核群**: 设置审核群 ID
- **目标频道**: 设置转发目标频道


## 📋 使用指南

### Web 界面

| 页面 | 路径 | 功能 |
|------|------|------|
| 主界面 | `/` 或 `/index.html` | 消息审核、批量操作 |
| 配置管理 | `/config.html` | 系统配置、频道管理 |
| Telegram认证 | `/auth.html` | Telegram账号登录 |
| 管理员界面 | `/admin.html` | 高级管理功能 |
| 系统状态 | `/status.html` | 系统监控、性能指标 |

### API 接口

- `/api/messages` - 消息管理
- `/api/admin` - 管理员功能
- `/api/config` - 配置管理
- `/api/auth` - Telegram认证
- `/api/system` - 系统状态
- `/api/websocket` - WebSocket连接

## 🔄 配置迁移

配置导入导出工具用于在部署新环境时快速迁移系统配置，避免手动重新配置。

### 功能特点

- 导出除session外的所有系统配置
- 支持导出系统配置、频道配置
- 支持合并导入和替换导入两种模式
- 自动跳过敏感的session信息

### 导出配置

从现有系统导出配置：

```bash
# 在虚拟环境中运行
source venv/bin/activate
python3 export_config.py
```

导出的文件格式：`config_export_YYYYMMDD_HHMMSS.json`

### 导入配置

在新环境中导入配置：

```bash
# 激活虚拟环境
source venv/bin/activate

# 合并模式（默认）- 保留现有配置，更新相同的配置项
python3 import_config.py config_export_20250808_095913.json

# 替换模式 - 删除现有配置（除session外），完全使用导入的配置
python3 import_config.py config_export_20250808_095913.json --mode replace
```

### 部署新环境步骤

1. **初始化新环境**
   ```bash
   # 克隆代码
   git clone <repository>
   cd telegram_channel_bot
   
   # 初始化环境
   ./start.sh  # 或 python3 init_db.py
   ```

2. **导入配置**
   ```bash
   source venv/bin/activate
   python3 import_config.py config_export_YYYYMMDD_HHMMSS.json
   ```

3. **完成认证**
   - 访问 `http://localhost:8000/auth.html` 完成Telegram认证
   - 系统会生成新的session

4. **启动服务**
   ```bash
   ./dev.sh  # 开发模式
   # 或
   ./start.sh  # 生产模式
   ```

### 配置内容说明

导出的JSON文件包含：

- **system_configs**: 系统配置项（排除telegram.session）
  - Telegram API配置
  - 频道设置
  - 过滤设置
  - 审核设置等


- **channels**: 频道配置
  - 源频道
  - 目标频道
  - 审核群

- **filter_rules**: 过滤规则（如有）

### 注意事项

1. **session不会被导出**：每个环境需要独立认证
2. **建议使用合并模式**：避免意外删除重要配置
3. **导入前备份**：建议先导出当前配置作为备份
4. **配置版本**：注意检查导出文件的版本兼容性

## 🐳 Docker 部署

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:telegram123@postgres:5432/telegram_system` | 数据库连接URL |
| `REDIS_URL` | `redis://redis:6379` | Redis连接URL |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `TZ` | `Asia/Shanghai` | 时区设置 |

### 常用命令

```bash
# 构建镜像
docker compose build

# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f app

# 停止服务
docker compose down

# 重启应用
docker compose restart app

# 进入容器
docker compose exec app bash
```

### 数据持久化

- `./logs/` - 应用日志
- `./data/` - 数据文件
- `./temp_media/` - 临时媒体文件
- PostgreSQL数据 - Docker卷持久化

## ⚙️ 高级配置

### 数据库配置

系统通过 `system_configs` 表存储所有配置：

- `telegram.*` - Telegram API配置
- `channels.*` - 频道配置
- `filter.*` - 过滤规则
- `review.*` - 审核设置
- `accounts.*` - 账号采集配置


## 📊 监控和维护

### 日志查看

```bash
# 本地开发
tail -f logs/*.log

# Docker环境
docker compose logs -f app
```

### 数据备份

```bash
# 导出配置
python3 export_config.py

# PostgreSQL备份
docker compose exec postgres pg_dump -U postgres telegram_system > backup.sql
```

## 🔧 故障排除

### 常见问题

1. **Telegram 客户端无法连接**:
   - 检查 API ID 和 API Hash
   - 确认手机号码格式 (+8613800138000)
   - 检查网络代理设置

2. **无法接收频道消息**:
   - 确认账号已加入源频道
   - 检查频道配置是否正确
   - 查看系统日志排查错误

3. **数据库连接失败**:
   - 本地开发也需要 PostgreSQL
   - Docker环境检查 PostgreSQL 容器状态

4. **WebSocket 连接失败**:
   - 检查防火墙设置
   - 确认端口 8000 未被占用

## 📁 项目结构

```
telegram_channel_bot/
├── app/                    # 应用核心代码
│   ├── api/               # API路由
│   ├── core/              # 核心配置
│   ├── services/          # 业务服务
│   └── telegram/          # Telegram相关
├── static/                # 前端静态文件
│   ├── css/              # 样式文件
│   ├── js/               # JavaScript文件
│   └── *.html            # HTML页面
├── logs/                  # 日志文件
├── data/                  # 数据文件
├── temp_media/           # 临时媒体文件
├── venv/                 # Python虚拟环境
├── dev.sh                # 开发启动脚本
├── start.sh              # 标准启动脚本
├── stop.sh               # 停止脚本
├── restart.sh            # 重启脚本
├── init_db.py            # 数据库初始化
├── export_config.py      # 配置导出工具
├── import_config.py      # 配置导入工具
├── docker-compose.yml    # Docker配置
├── Dockerfile            # Docker镜像定义
├── requirements.txt      # Python依赖
├── main.py              # 应用入口
└── CLAUDE.md            # AI助手指南
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