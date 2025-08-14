# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 重大变更历史

- 2025-08-14: 添加自动Git提交工具系统 🤖
  - **新增工具**: auto_commit.py - 智能分析代码变更并生成规范提交信息
  - **快速脚本**: commit.sh - 支持多种提交模式的Shell脚本
  - **核心功能**:
    - 自动检测变更类型（fix/feat/docs/style/refactor等）
    - 智能生成提交描述和详细说明列表
    - 文件分类识别（前端/后端/配置/文档/脚本等）
    - 规范化提交格式，包含emoji标识和时间戳
  - **使用方式**:
    - `python3 auto_commit.py` - 智能自动分析并生成提交信息
    - `./commit.sh fix "描述"` - 快速提交bug修复
    - `./commit.sh feat "描述"` - 快速提交新功能
    - `./commit.sh` - 交互式提交模式
  - **特殊处理**: 支持非交互环境，自动处理EOFError异常
  - **文档**: docs/auto_commit_usage.md - 完整使用说明和最佳实践
- 2025-08-10: OCR功能优化 - 改用基于图像处理的轻量级方案
  - **技术调整**: 从EasyOCR深度学习方案改为OpenCV图像处理方案
  - **功能实现**: 
    - 通过边缘检测和形态学操作识别文字区域
    - 颜色分析检测广告常用的醒目颜色（红色、黄色）
    - 使用OpenCV内置QRCodeDetector识别二维码
  - **性能优化**: 降低内存和CPU占用，提高处理速度
  - **依赖简化**: 移除EasyOCR和pyzbar，仅依赖OpenCV和Pillow
- 2025-08-09 (v2.0): 全面优化训练数据保护机制，确保数据永不丢失 🔐
  - **核心升级**: 完全重写TrainingRecord类，实现企业级数据保护
  - **多重保护**: 文件锁、原子写入、哈希验证、自动备份、智能恢复
  - **新增功能**:
    - 启动时自动完整性检查和修复
    - 每次写入前自动备份（防止操作失败）
    - 多级备份策略（即时备份、定期备份、紧急备份）
    - 数据完整性哈希验证（SHA256）
    - 智能损坏检测和自动修复
  - **新增API端点**:
    - `/api/training/emergency-backup` - 创建紧急备份
    - `/api/training/integrity-report` - 获取详细完整性报告
    - `/api/training/verify-integrity` - 验证所有数据文件
    - `/api/training/cleanup-backups` - 清理旧备份文件
    - 增强现有API：备份列表包含完整性状态、恢复支持回滚等
  - **新增工具**: recover_training_data.py - 强大的数据恢复工具
    - 支持自动恢复、手动恢复、备份合并、紧急恢复等模式
    - 完整的命令行界面，支持各种恢复场景
  - **关键特性**: 数据永不丢失保证 - 任何写入操作失败都能完全回滚
- 2025-08-08: 添加配置导入导出工具（export_config.py, import_config.py），支持环境间配置迁移
- 2025-08-07: 添加开发模式脚本（dev.sh），支持热重载开发
- 有大的改动，特别是涉及脚本及重大功能变化，要记录到CLAUDE.md和README.md

## 重要提醒和常见错误

### tail命令使用（macOS）
- **正确用法**: `tail -n 20 file.log` 或单独使用 `tail -20 file.log`
- **错误用法**: `tail -20 file.log | grep pattern` (在macOS上会报错)
- **解决方案**: 始终使用 `-n` 参数：`tail -n 20 file.log | grep pattern`

### 静态文件访问路径
- **所有HTML文件都通过 `/static/` 路径访问**
- 正确: `http://localhost:8000/static/training_manager.html`
- 错误: `http://localhost:8000/training_manager.html`
- JavaScript中打开页面使用: `window.open('/static/xxx.html', '_blank')`

### 数据库操作
- **禁止直接使用sqlite3命令行工具访问数据库**
- 应该通过API接口或Python脚本访问数据库
- 使用SQLAlchemy ORM进行数据库操作

## 常用命令

### 本地开发

#### 脚本说明
- **dev.sh**: 开发模式启动脚本（推荐）
  - 自动检测并使用uvicorn的`--reload`参数
  - 代码修改后自动重载，无需手动重启
  - 自动处理venv、依赖安装、数据库初始化
  - 适合开发调试使用

- **start.sh**: 标准启动脚本
  - 生产模式启动，不支持热重载
  - 自动处理venv、依赖安装、数据库初始化
  - 适合稳定运行使用

- **stop.sh**: 停止脚本
  - 安全停止运行中的应用
  - 自动查找并终止main.py进程
  - 清理可能的僵尸进程

- **restart.sh**: 重启脚本
  - 先调用stop.sh停止，再调用start.sh启动
  - 适合需要完全重启时使用

#### 使用方法
```bash
# 开发调试（推荐）
./dev.sh                                 # 开发模式，支持热重载

# 生产运行
./start.sh                               # 标准启动
./stop.sh                                # 停止应用
./restart.sh                             # 重启应用

# 手动步骤（如需自定义）
python3 -m venv venv                     # 创建虚拟环境
source venv/bin/activate                 # 激活虚拟环境 (Linux/Mac)
pip install -r requirements.txt          # 安装依赖
python3 init_db.py                       # 初始化数据库（首次运行）
python3 main.py                          # 启动主应用
```

### Docker部署（生产环境）
```bash
docker compose up -d --build             # 启动并构建
docker compose down                      # 停止服务
docker compose logs -f app              # 查看应用日志
docker compose ps                       # 查看服务状态
docker compose restart app              # 重启应用服务
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
- **消息分组** (`app/services/message_grouper.py`): 处理Telegram媒体组合消息
- **媒体处理** (`app/services/media_handler.py`): 媒体文件下载和处理
- **历史采集** (`app/services/history_collector.py`): 频道历史消息采集
- **系统监控** (`app/services/system_monitor.py`): 系统状态监控

### 数据库配置
- **数据库类型**: PostgreSQL 15（生产环境）
- **连接方式**: 异步连接 (asyncpg + SQLAlchemy)
- **数据库名**: telegram_system
- **默认连接**: 
  - 本地开发: `postgresql+asyncpg://postgres:telegram123@localhost:5432/telegram_system`
  - Docker环境: `postgresql+asyncpg://postgres:telegram123@postgres:5432/telegram_system`
- **数据存储位置**: `./data/postgres` (Docker挂载)
- **缓存数据库**: Redis 7-alpine
  - 连接地址: `redis://localhost:6379`
  - 数据存储位置: `./data/redis` (Docker挂载)
  - 用途: 进程锁、分布式锁机制

### 数据库模型
- **Message**: 消息存储和状态跟踪（支持媒体组合消息）
- **Channel**: 频道配置（源频道、目标频道、审核群）
- **FilterRule**: 过滤规则配置
- **SystemConfig**: 系统配置存储（包含所有运行时配置）

### API路由结构
- `/api/messages`: 消息管理API
- `/api/admin`: 管理员功能API
- `/api/config`: 配置管理API
- `/api/auth`: Telegram认证API
- `/api/system`: 系统状态API
- `/api/websocket`: WebSocket连接（用于实时认证）

### 前端组件
- **Vue.js 3 + Element Plus**: 主要前端框架
- **WebSocket认证**: 实时Telegram登录流程
- 页面功能：
  - `index.html`: 主界面（消息审核）
  - `config.html`: 配置管理界面
  - `auth.html`: Telegram认证界面
  - `admin.html`: 管理员界面
  - `status.html`: 系统状态监控

### 消息处理流程
```
源频道 → 消息采集 → 内容过滤 → 审核群 → Web管理界面 → 目标频道
```

## 配置系统

### 配置层级
1. **环境变量配置** (docker-compose.yml或直接设置): 
   - DATABASE_URL: `postgresql+asyncpg://postgres:telegram123@postgres:5432/telegram_system`
   - REDIS_URL: `redis://redis:6379`
   - LOG_LEVEL: `INFO`
   - TZ: `Asia/Shanghai`
2. **数据库配置** (`system_configs`表): 所有运行时配置通过Web界面管理
3. **默认配置** (`app/services/config_manager.py`): 初始化默认值

### 关键配置项
- `telegram.*`: Telegram API凭据和认证信息
- `channels.*`: 频道配置（源频道、目标频道、审核群）
- `filter.*`: 过滤规则和关键词
- `review.*`: 审核相关设置（自动转发延时等）
- `accounts.*`: 账号采集配置

## 项目维护原则

- 使用中文简短回复
- 避免创建测试文件，测试完成立即删除
- 保持项目目录整洁，不保留临时文件
- 前端使用Vue3 + Element Plus + Axios
- 配置统一通过Web界面管理，不使用配置文件

## 开发注意事项

### 开发规范
- **开发环境**: 使用Python虚拟环境(venv)进行本地开发，不使用Docker
- **部署环境**: 仅在Linux生产环境使用Docker部署
- **Python命令**: 始终使用 `python3` 而不是 `python`
- **Docker命令**: 始终使用 `docker compose` 而不是 `docker-compose`
- **重要**: 不要创建开发版Docker配置（如docker-compose.dev.yml, docker-compose.m4.yml等）

### 技术栈
- **后端**: Python 3.11 + FastAPI + SQLAlchemy + Telethon
- **前端**: Vue.js 3 + Element Plus + Axios
- **数据库**: PostgreSQL
- **缓存**: Redis
- **部署**: Docker Compose（生产环境）


### 工作流程

1. **初始化设置**
   - 运行 `./start.sh` 或 `python3 init_db.py` 初始化数据库
   - 访问 `http://localhost:8000/auth.html` 完成Telegram认证
   - 访问 `http://localhost:8000/config.html` 配置频道和系统参数

2. **消息处理**
   - 自动监听源频道新消息
   - 自动过滤广告内容
   - 发送到审核群供人工审核
   - 通过Web界面批量审核
   - 30分钟自动转发到目标频道

### 数据持久化
- 日志文件: `./logs/`
- 数据文件: `./data/`
- 临时媒体文件: `./temp_media/`
- 数据库: PostgreSQL (数据库名: telegram_system)
- Telegram会话: 使用StringSession存储在数据库中

## 🚨 重要数据库操作规则

### 严禁删除整个数据库
**除非用户明确要求删除整个数据库，否则绝对不允许执行以下操作：**

❌ **禁止的操作：**
```bash
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
- `filter_rules`: 过滤规则（已弃用，使用ad_keywords表）
- `system_configs`: 系统配置（重要！包含所有系统配置项）
- `ad_keywords`: 广告关键词（支持文中关键词和行过滤）

**任何影响多个表的操作都需要用户明确授权！**

## 数据库结构同步要求

**如果修改数据表结构，在数据库初始化的代码中要同步修改**

当修改了 `app/core/database.py` 中的模型定义时，必须：

1. **更新 init_db.py** - 确保数据库初始化脚本与新的表结构一致
2. **更新 docker-compose.yml** - 如果需要挂载数据库文件，确保路径正确
3. **测试新环境** - 在全新环境中验证初始化脚本能正确创建表结构

## 配置导入导出工具

系统提供了配置导入导出工具，用于在不同环境间迁移配置：

- **export_config.py**: 导出系统配置（排除session）
  - 导出系统配置、广告关键词、频道配置、过滤规则
  - 生成带时间戳的JSON文件
  
- **import_config.py**: 导入配置
  - 支持合并模式（默认）：保留现有配置，更新相同项
  - 支持替换模式：删除现有配置（除session外），完全使用导入的配置
  - 自动跳过session信息，需要每个环境独立认证

这些工具在部署新环境或备份配置时非常有用。详见README.md中的配置迁移章节。

## 训练数据恢复工具 🔧

**recover_training_data.py** - 企业级数据恢复工具，确保训练数据永不丢失

### 主要功能
- **完整性检查**: 自动检测损坏、丢失或无效的数据文件
- **智能恢复**: 从最新有效备份自动恢复损坏文件
- **备份合并**: 合并多个备份文件，创建最完整的数据集
- **紧急恢复**: 一键执行所有可能的恢复操作
- **详细报告**: 生成完整的恢复操作日志和状态报告

### 使用方法
```bash
# 检查数据完整性（推荐定期执行）
python3 recover_training_data.py --check

# 自动恢复损坏的文件
python3 recover_training_data.py --auto-recover

# 从指定备份恢复
python3 recover_training_data.py --restore backup_file.json --target both

# 合并多个备份文件
python3 recover_training_data.py --merge-backups

# 紧急恢复模式（数据严重损坏时使用）
python3 recover_training_data.py --emergency
```

### 使用场景
- **日常维护**: 定期检查数据完整性
- **故障恢复**: 系统异常后快速恢复数据
- **数据迁移**: 环境迁移时合并和整理数据
- **紧急情况**: 数据严重损坏时的最后防线
- 有数据库结构变化要更新到相关文件中
- html页面要做到html,css,js代码分离,html代码中不要有stle="xxx"这样的内联样式
- 代码支持热加载，非必要不重启应用
- 测试功能要在虚拟环境下

## 自动Git提交工具 🤖

项目配备了完整的自动提交工具系统，**完成任何bug修复或功能开发后都应该使用这些工具进行提交**。

### 核心工具
- **auto_commit.py**: 智能分析工具，自动检测变更类型并生成规范提交信息
- **commit.sh**: 快速提交脚本，支持多种提交模式
- **auto_commit_claude.py**: Claude Code专用无交互自动提交工具（Claude可以直接调用）

### 必须使用的场景
- ✅ 每次完成bug修复后
- ✅ 每次添加新功能后  
- ✅ 每次完成代码重构后
- ✅ 每次更新文档后
- ✅ 每次修改配置后

### 快速使用指南
```bash
# 修复bug后
./commit.sh fix "修复具体问题描述"

# 添加功能后  
./commit.sh feat "新功能描述"

# 智能自动分析（推荐）
python3 auto_commit.py

# Claude Code自动调用（无交互）
python3 auto_commit_claude.py auto

# 交互式选择
./commit.sh
```

### 提交信息规范
- 使用emoji标识（🐛 fix、✨ feat、📝 docs等）
- 简洁明确的描述
- 自动生成时间戳和详细说明
- 符合约定式提交规范

**⚠️ 重要提醒**: 不要手动执行 `git commit`，始终使用自动提交工具确保提交信息的规范性和一致性。

详细使用说明见: `docs/auto_commit_usage.md`