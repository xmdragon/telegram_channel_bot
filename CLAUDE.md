# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

### 开发和运行
```bash
# 本地开发
python main.py                          # 启动主应用
python init_db.py                       # 初始化数据库
python setup_telethon.py               # Telethon设置脚本

# 使用管理脚本
python scripts/manage.py stats          # 显示系统统计
python scripts/manage.py cleanup --days 30  # 清理30天前的消息
python scripts/manage.py add-channel @channel "频道名"  # 添加源频道
python scripts/manage.py list-channels  # 列出所有频道
python scripts/manage.py add-rule keyword "广告词"  # 添加过滤规则
python scripts/manage.py config list    # 列出所有配置
python scripts/manage.py config get key # 获取配置值
python scripts/manage.py config set key value --type string  # 设置配置

# Docker部署
docker-compose up -d                     # 启动服务
docker-compose build                     # 构建镜像
docker-compose logs -f app              # 查看应用日志
docker-compose down                      # 停止服务
docker-compose -f docker-compose.dev.yml up -d  # 开发环境

# 数据库操作
python init_config.py                   # 初始化默认配置
```

### 测试和调试
```bash
# 目前没有正式的测试套件
# 测试文件在根目录：test_*.py
python test_admin_functionality.py
python test_channel_management.py
python test_config_management.py
python test_docker.py
python test_telethon.py
python test_web_auth.py
```

## 系统架构

### 核心组件
- **FastAPI应用** (`main.py`): 主应用入口，集成API和静态文件服务
- **Telegram客户端** (`app/telegram/bot.py`): 基于Telethon的消息监听和转发
- **配置管理** (`app/services/config_manager.py`): 数据库配置存储和管理
- **频道管理** (`app/services/channel_manager.py`): 频道配置和状态管理
- **消息处理** (`app/services/message_processor.py`): 消息接收、过滤和转发逻辑
- **内容过滤** (`app/services/content_filter.py`): 广告检测和内容过滤
- **调度器** (`app/services/scheduler.py`): 自动转发任务调度

### 数据库模型
- **Message**: 消息存储和状态跟踪
- **Channel**: 频道配置（源频道、目标频道、审核群）
- **FilterRule**: 过滤规则配置
- **SystemConfig**: 系统配置存储
- **Account**: 账号信息收集

### API路由结构
- `/api/messages`: 消息管理API
- `/api/admin`: 管理员功能API
- `/api/config`: 配置管理API
- `/api/auth`: Telegram认证API

### 前端组件
- **Vue.js 3 + Element Plus**: 主要前端框架
- **WebSocket认证**: 实时Telegram登录流程
- 静态文件结构：
  - `static/index.html`: 主界面（消息审核）
  - `static/config.html`: 配置管理界面
  - `static/auth.html`: Telegram认证界面
  - `static/admin.html`: 管理员界面
  - `static/status.html`: 系统状态监控

### 消息处理流程
```
源频道 → 消息采集 → 内容过滤 → 审核群 → Web管理界面 → 目标频道
```

## 配置系统

### 配置层级
1. **环境变量配置** (`.env`): DATABASE_URL, REDIS_URL, LOG_LEVEL
2. **数据库配置** (`SystemConfig`表): 运行时动态配置
3. **默认配置** (`app/services/config_manager.py`): 初始化默认值

### 关键配置项
- `telegram.*`: Telegram API凭据和认证信息
- `channels.*`: 频道配置（源频道、目标频道、审核群）
- `filter.*`: 过滤规则和关键词
- `review.*`: 审核相关设置（自动转发延时等）
- `accounts.*`: 账号采集配置

## Cursor规则要点

- 使用中文简短回复
- 只保留README.md一个markdown文件
- 目录结构清晰，CSS/JS/HTML分离
- 使用Element Plus组件库和Vue3框架
- 使用Axios进行网络请求
- 删除调试代码和测试文件（用完即删）

## 开发注意事项

### 技术栈
- 后端: Python 3.11 + FastAPI + SQLAlchemy + Telethon
- 前端: Vue.js 3 + Element Plus + Axios
- 数据库: SQLite（默认）/ PostgreSQL
- 缓存: Redis
- 部署: Docker + Docker Compose

### 认证流程
- 使用WebSocket进行实时认证
- 认证状态存储在`app/telegram/auth.py`
- 首次使用需要通过Web界面完成Telegram登录

### 消息处理机制
- 异步事件驱动的消息监听
- 自动过滤广告内容
- 人工审核机制（30分钟自动转发）
- 支持批量操作和内容替换

### 数据持久化
- 会话文件: `./sessions/`
- 日志文件: `./logs/`
- 数据文件: `./data/`
- 数据库文件: `telegram_system.db`

## 🚨 重要数据库操作规则

### 严禁删除整个数据库
**除非用户明确要求删除整个数据库，否则绝对不允许执行以下操作：**

❌ **禁止的操作：**
```bash
# 禁止删除数据库文件
rm telegram_system.db
rm *.db

# 禁止删除整个数据库
DROP DATABASE telegram_system;
```

✅ **允许的操作：**
```sql
-- 只允许单表操作
DROP TABLE IF EXISTS table_name;
ALTER TABLE table_name ADD COLUMN new_column VARCHAR;
DELETE FROM table_name WHERE condition;
UPDATE table_name SET column = value WHERE condition;
```

### 表结构修改原则
1. **优先使用 ALTER TABLE** 添加列
2. **如需重建表，必须先备份数据**
3. **一次只操作一个表**
4. **保护其他表的数据完整性**

### 数据库包含的表
- `messages`: 消息数据
- `channels`: 频道配置
- `filter_rules`: 过滤规则
- `system_configs`: 系统配置（重要！包含21条初始配置）

**任何影响多个表的操作都需要用户明确授权！**

## 数据库结构同步要求

**如果修改数据表结构，在数据库初始化的代码中要同步修改**

当修改了 `app/core/database.py` 中的模型定义时，必须：

1. **更新 init_db.py** - 确保数据库初始化脚本与新的表结构一致
2. **更新 docker-compose.yml** - 如果需要挂载数据库文件，确保路径正确
3. **测试新环境** - 在全新环境中验证初始化脚本能正确创建表结构