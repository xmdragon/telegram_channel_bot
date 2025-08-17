# Telegram 消息采集审核系统 v4.0

基于服务分离架构的高性能Telegram消息采集、过滤和审核系统。

> **🚀 v4.0重大重构**: 服务分离架构，解决开发体验痛点，状态查看性能提升100倍！

## ✨ 功能特性

### 🎯 核心功能
- 🔄 多频道采集：同时监控多个Telegram频道
- 🛡️ 智能过滤：自动识别和过滤广告消息
- 🖼️ 图像分析：基于OpenCV的广告检测和二维码识别
- 👥 人工审核：转发到审核群进行确认
- ⏰ 自动转发：30分钟无人审核自动转发

### 🌐 管理界面
- 🌐 Web管理：现代化Vue3界面
- 📊 数据统计：详细的消息处理统计
- 🚀 批量操作：支持批量审核和管理
- 🔐 管理员认证：JWT令牌认证 (默认: admin/admin123)
- 📱 响应式设计：适配各种设备

### 🚀 架构优势 (v4.0)
- 🔄 **服务分离**：Web、采集、调度服务完全独立
- ⚡ **开发体验**：修改代码不再导致全系统重启
- 🎯 **灵活部署**：支持选择性启动和独立调试
- 📊 **实时监控**：状态查看从5秒优化到0.05秒
- 🛡️ **高可用性**：服务自动重启和健康监控
- 🔧 **易于维护**：智能进程管理和状态追踪

## 🏗️ 系统架构

### v4.0 服务分离架构
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web服务器     │    │  Telegram采集   │    │   消息调度      │
│  web_server.py  │    │ collector.py    │    │ scheduler.py    │
│  端口:8000      │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   进程管理器    │
                    │ supervisor.py   │
                    │ + 健康监控      │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │  Redis + JSON   │
                    │   数据存储      │
                    └─────────────────┘
```

### 业务流程
```
源频道 → 消息采集 → 内容过滤 → 审核群 → Web管理界面 → 目标频道
```

## 🛠️ 技术栈

### 存储架构
- **主存储**: Redis (消息数据、会话管理)
- **配置存储**: JSON文件 (系统配置、管理员数据)
- **性能**: 亚毫秒级查询，内存+磁盘双重保护

### 应用技术
- **后端**: Python 3.11 + FastAPI + Redis + Telethon
- **前端**: Vue.js 3 + Element Plus + Axios
- **认证**: JWT + Redis会话管理

## 🚀 快速开始

### 环境要求
- Python 3.11+
- Docker & Docker Compose
- Redis 7.0+

### 安装部署

#### 1. 获取代码
```bash
git clone <repository-url>
cd telegram_channel_bot
```

#### 2. 开发环境（推荐）
```bash
# v4.0 灵活启动选项
./dev.sh                    # 启动所有服务
./dev.sh web               # 仅启动Web服务（前端开发）
./dev.sh web scheduler     # 启动指定服务组合
./dev.sh --status          # 超快状态查看（0.05秒）
./dev.sh --legacy          # 传统模式（兼容v3.0）
```

#### 3. 生产环境
```bash
# 安装依赖
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# 启动Redis
docker compose up -d redis

# 启动应用
./start.sh
```

### 访问系统
- **主界面**: http://localhost:8000/static/index.html
- **管理员登录**: http://localhost:8000/static/login.html (admin/admin123)
- **系统配置**: http://localhost:8000/static/config.html
- **Telegram认证**: http://localhost:8000/static/auth.html

## ⚙️ 配置说明

### 1. Telegram认证
访问认证页面，输入API凭据：
- API ID：从 https://my.telegram.org 获取
- API Hash：从 https://my.telegram.org 获取
- 手机号：用于接收验证码

### 2. 频道配置
在配置页面设置：
- **源频道**：需要采集的频道列表
- **目标频道**：转发消息的目标频道
- **审核群**：人工审核的群组

### 3. 过滤规则
配置关键词过滤：
- **广告关键词**：自动过滤的关键词
- **白名单关键词**：不过滤的关键词
- **过滤策略**：选择过滤模式

## 📊 系统管理

### 启停控制

#### v4.0 开发模式（推荐）
```bash
# 灵活的服务管理
./dev.sh                    # 启动所有服务
./dev.sh web               # 仅启动Web服务
./dev.sh collector         # 仅启动采集服务
./dev.sh --status          # 快速状态查看
```

#### 生产模式
```bash
./start.sh     # 启动完整系统（进程管理器）
./stop.sh      # 智能停止（优雅关闭+强制清理）
./restart.sh   # 4步骤完整重启（状态检查）
```

#### 状态监控
```bash
./dev.sh --status                    # 命令行状态
curl localhost:8000/api/health      # API健康检查
```

### 数据管理
- **Web界面**：通过配置页面进行系统配置
- **自动备份**：系统自动备份重要数据
- **紧急恢复**：`python3 tools/data/recover_training_data.py --check`

### 日志查看
- 完整日志：`./logs/app.log`
- 错误日志：`./logs/error.log`
- Web查看：http://localhost:8000/static/admin.html

## 🔧 开发指南

### 目录结构（v4.0）
```
telegram_channel_bot/
├── app/                    # 核心应用代码
│   └── services/
│       └── health_monitor.py  # 健康监控系统
├── data/                   # 数据存储
├── static/                 # Web前端文件
├── tools/                  # 工具脚本
├── logs/                   # 日志文件
├── docs/                   # 项目文档
│   └── service_architecture.md  # 架构文档
├── temp_media/             # 临时媒体文件
├── web_server.py           # Web服务器（独立）
├── telegram_collector.py   # Telegram采集服务（独立）
├── message_scheduler.py    # 消息调度服务（独立）
├── dev_supervisor.py       # 进程管理器
├── main.py                 # 传统模式入口（兼容）
└── dev.sh                  # 开发启动脚本
```

### 开发规范
- 使用Python虚拟环境
- 遵循项目结构管理规范
- 工具脚本放在`tools/`对应子目录
- 禁止硬编码文件路径，使用PathConfig
- **API端点管理**：严格禁止硬编码API路径，必须使用`static/assets/js/config/api-endpoints.js`配置

### API端点管理
为避免API端点冗余和硬编码问题，项目采用集中配置管理：

```javascript
// 正确方式 - 从配置文件引用API端点
import API from './config/api-endpoints.js';
const response = await axios.get(API.messages.list);

// 错误方式 - 禁止硬编码
const response = await axios.get('/api/messages/');
```

**核心原则**：
- 所有API端点都必须在`api-endpoints.js`中定义
- 开发时先检查配置文件，避免重复端点
- 前端代码严禁硬编码API路径
- 新增端点需同步更新配置文件

### Git提交
使用自动提交工具：
```bash
# 智能分析提交
python3 tools/git/auto_commit.py

# 快速提交
./tools/git/commit.sh fix "修复问题"
./tools/git/commit.sh feat "新功能"
```

## 🐛 故障排除

### 常见问题

1. **Redis连接失败**
   ```bash
   docker compose up -d redis
   ```

2. **Telegram认证失败**
   - 检查API凭据是否正确
   - 确认手机号格式（+86xxxxxxxxxx）

3. **消息不转发**
   - 检查频道配置是否正确
   - 确认机器人有管理员权限

4. **Web界面无法访问**
   - 确认应用已启动（http://localhost:8000）
   - 检查防火墙设置

### 获取支持
- 查看日志：`./logs/error.log`
- 系统状态：http://localhost:8000/static/status.html
- 管理界面：http://localhost:8000/static/admin.html

## 📝 更新日志

### v4.0 (2025-08-16) - 🚀 服务分离架构重大重构
#### 核心突破
- 🚀 **服务分离架构**：Web、采集、调度服务完全独立
- ⚡ **开发体验革命**：修改代码不再导致全系统重启
- 📊 **性能飞跃**：状态查看从5秒优化到0.05秒（100倍提升）
- 🎯 **灵活部署**：支持选择性启动和独立调试

#### 新增功能
- 🔧 **进程管理器**：`dev_supervisor.py` 智能进程管理
- 💚 **健康监控**：Redis存储的实时服务状态监控
- 🛠️ **脚本增强**：`stop.sh`/`restart.sh` 智能进程控制
- 📖 **完整文档**：详细的架构文档和使用指南

#### 使用体验
- 🎮 **开发模式**：`./dev.sh web` 仅启动Web服务进行前端开发
- 🏭 **生产模式**：`./start.sh` 启动完整系统和进程管理
- 📈 **状态监控**：`./dev.sh --status` 超快状态查看
- 🔄 **向后兼容**：完全兼容v3.0传统模式

### v3.0 (2025-08-14) - Redis+JSON存储架构
- 🚀 完全迁移至Redis+JSON存储架构
- ⚡ 性能提升300%+，毫秒级消息查询
- 🔥 系统启动速度提升5倍+
- 🛡️ 双层存储+文件锁数据保护
- 🤖 智能Git提交工具系统

### v2.0 (2025-08-09) - 数据保护机制
- 🔐 训练数据保护机制
- 🔧 多级备份策略
- 📊 数据完整性验证

### v1.x - 基础功能
- 🎯 基础消息采集和转发功能
- 🛡️ 内容过滤和人工审核
- 🌐 Web管理界面

## 📄 许可证

本项目仅供学习和研究使用。

## 🤝 贡献

欢迎提交Issue和Pull Request！