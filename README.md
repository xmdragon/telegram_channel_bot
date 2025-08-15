# Telegram 消息采集审核系统 v3.0

基于Redis+JSON的高性能Telegram消息采集、过滤和审核系统。

> **🚀 v3.0重大升级**: Redis+JSON存储架构，性能提升300%+，支持分布式部署！

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

### ⚡ 性能优势 (v3.0)
- ⚡ 超高性能：Redis存储，毫秒级查询
- 🔥 快速启动：系统启动速度提升5倍+
- 🛡️ 数据安全：双层存储+文件锁保护
- 🔧 易于部署：仅需Redis，无需复杂数据库

## 🏗️ 系统架构

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
# 一键启动开发环境
./dev.sh
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
```bash
./dev.sh       # 开发模式（支持热重载）
./start.sh     # 启动
./stop.sh      # 停止
./restart.sh   # 重启
```

### 数据管理
```bash
# 配置导入导出
python3 export_config.py
python3 import_config.py

# 数据恢复
python3 recover_training_data.py --check
python3 recover_training_data.py --auto-recover
```

### 日志查看
- 完整日志：`./logs/app.log`
- 错误日志：`./logs/error.log`
- Web查看：http://localhost:8000/static/admin.html

## 🔧 开发指南

### 目录结构
```
telegram_channel_bot/
├── app/              # 核心应用代码
├── data/             # 数据存储
├── static/           # Web前端文件
├── tools/            # 工具脚本
├── logs/             # 日志文件
├── temp_media/       # 临时媒体文件
├── main.py           # 应用入口
└── dev.sh            # 开发启动脚本
```

### 开发规范
- 使用Python虚拟环境
- 遵循项目结构管理规范
- 工具脚本放在`tools/`对应子目录
- 禁止硬编码文件路径，使用PathConfig

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

### v3.0 (2025-08-14)
- 🚀 完全迁移至Redis+JSON存储架构
- ⚡ 性能提升300%+，毫秒级消息查询
- 🔥 系统启动速度提升5倍+
- 🛡️ 双层存储+文件锁数据保护
- 🤖 智能Git提交工具系统

### v2.0 (2025-08-09)
- 🔐 训练数据保护机制
- 🔧 多级备份策略
- 📊 数据完整性验证

### v1.x
- 🎯 基础消息采集和转发功能
- 🛡️ 内容过滤和人工审核
- 🌐 Web管理界面

## 📄 许可证

本项目仅供学习和研究使用。

## 🤝 贡献

欢迎提交Issue和Pull Request！