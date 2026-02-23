# Telegram消息采集审核系统

Telegram频道消息采集、智能过滤和自动化转发系统。AI驱动的内容过滤 + 人工审核，实现高质量内容的自动化筛选和分发。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![Vue.js](https://img.shields.io/badge/Vue.js-3-brightgreen.svg)](https://vuejs.org)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-orange.svg)](https://sqlite.org)

## 核心特性

- **实时监听**：多频道同时监听，毫秒级消息捕获
- **智能过滤**：AI广告检测、关键词过滤、内容去重、尾部清理
- **7状态审核**：待审核/发送失败/自动发布/手动发布/广告拒绝/重复拒绝/手动拒绝
- **自动转发**：规则引擎 + 定时发布 + 失败重试
- **管理控制台**：实时监控、统计图表、批量操作、权限控制

## 系统架构

```
客户端 → Nginx:80/443 → FastAPI:8008 (API + WebSocket)
                       → /static (静态文件直接serve)

进程管理: Supervisor
  ├── telegram_web        (web_server.py:8008)
  ├── telegram_collector  (message_collector.py)
  └── telegram_scheduler  (message_scheduler.py)

存储: SQLite WAL + FTS5 (主存储) + Redis (仅WebSocket pub/sub)
配置: JSON文件 (data/config/)
```

### 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI + Uvicorn, asyncio, Telethon |
| 存储 | SQLite WAL模式 + FTS5全文搜索 |
| 缓存/消息 | Redis (仅WebSocket跨进程广播) |
| 前端 | Vue.js 3 + 自研SimpleUI + Axios + WebSocket |
| 部署 | Nginx + Supervisor, 增量部署脚本 |

## 快速开始

### 环境要求

- Python 3.12+
- Linux (推荐 Ubuntu 24.04)
- 1GB+ RAM, 25GB+ 磁盘

### 服务器部署

```bash
# 1. 克隆项目
git clone https://github.com/xmdragon/telegram_channel_bot.git
cd telegram_channel_bot

# 2. 首次全量部署（安装依赖 + 配置 nginx/supervisor + 部署代码）
./tools/deploy.sh init

# 3. 后续增量部署（只传改动文件，自动判断是否重启）
./tools/deploy.sh

# 4. 回滚到上一版本
./tools/deploy.sh rollback

# 5. 只同步配置文件
./tools/deploy.sh sync
```

部署脚本会自动：
- 安装系统依赖（Python、Redis、Nginx、Supervisor）
- 创建目录结构和Python虚拟环境
- 配置Nginx反向代理和Supervisor进程管理
- 基于 `git archive` 打包部署，保留最近5个版本
- 增量部署时通过 `git diff` 只传改动文件

### 本地开发

```bash
# 创建虚拟环境
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 复制环境变量
cp .env.example .env  # 按需修改

# 启动服务
supervisorctl -c config/supervisord.conf start all
```

### 访问系统

- **管理控制台**: http://your-domain/static/login.html
- **默认账号**: admin / admin123
- **API文档**: http://your-domain/docs

### 配置Telegram

在管理控制台的「Telegram认证」页面填入从 https://my.telegram.org 获取的 API ID 和 API Hash，然后完成双Session认证。

## 环境变量 (.env)

```bash
WEB_PORT=8008
NGINX_PORT=80

# Redis（仅WebSocket pub/sub）
REDIS_URL=redis://localhost:6379/0

# Telegram代理（服务器通常不需要）
TELEGRAM_USE_PROXY=false
TELEGRAM_PROXY_TYPE=http
TELEGRAM_PROXY_HOST=127.0.0.1
TELEGRAM_PROXY_PORT=10808
```

## 项目结构

```
telegram_channel_bot/
├── app/
│   ├── api/               # API路由层
│   ├── core/              # 核心配置 (config, path_config, route_config)
│   ├── services/          # 业务逻辑 (过滤器, 处理器, 认证)
│   ├── storage/           # 存储层
│   │   ├── database.py          # SQLite主管理器
│   │   ├── database_messages.py # 消息CRUD
│   │   ├── database_schema.py   # Schema定义
│   │   ├── redis_manager.py     # 桥接别名 → database
│   │   └── json_store.py        # JSON配置存储
│   ├── telegram/          # Telegram集成 (双Session, 转发, 事件处理)
│   └── utils/             # 工具函数
├── static/                # 前端 (HTML + CSS + JS)
│   └── assets/js/config/api-endpoints.js  # API端点配置（禁止硬编码）
├── data/
│   ├── config/            # JSON配置文件
│   └── db/messages.db     # SQLite数据库
├── tools/
│   ├── deploy.sh              # 部署主脚本（本地执行）
│   └── deploy_server_init.sh  # 服务器初始化脚本
├── web_server.py          # Web服务入口
├── message_collector.py   # 消息采集服务入口
└── message_scheduler.py   # 消息调度服务入口
```

## 服务器目录结构

```
/opt/tcb/
├── current -> releases/vXXXX  # 符号链接指向当前版本
├── releases/                  # 版本目录（保留最近5个）
└── shared/                    # 跨版本共享
    ├── data/                  # 配置 + 数据库
    ├── logs/
    ├── venv/                  # Python虚拟环境
    └── .env                   # 环境变量
```

## 开发规范

- **Python**: PEP 8, snake_case
- **JavaScript**: camelCase变量, kebab-case CSS类
- **API路径**: kebab-case, JSON字段: snake_case
- **文件限制**: 500行, 函数30行, 缩进3层
- **禁止硬编码**: API端点用 `api-endpoints.js`，路径用 `path_config.py`

## 许可证

MIT License
