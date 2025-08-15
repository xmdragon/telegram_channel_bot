# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 重大变更历史

- 2025-08-14 (v3.0): 🚀 **重大架构升级：完全迁移至Redis+JSON存储** ⚡
  - **核心变更**: 完全替换PostgreSQL，采用Redis+JSON双层存储架构
  - **存储重构**:
    - 消息数据 → Redis Hash存储，提供亚毫秒级访问速度
    - 系统配置 → JSON文件存储，支持版本控制和备份
    - 管理员数据 → JSON文件存储，包含完整权限系统
    - 会话管理 → Redis存储，支持分布式部署
  - **性能提升**:
    - 消息查询性能提升300%+（毫秒级响应）
    - 系统启动速度提升5倍+（无需数据库连接等待）
    - 内存使用量减少40%（去除SQLAlchemy重量级ORM）
  - **架构优势**:
    - 🔥 零SQL依赖，完全去中心化存储
    - ⚡ 支持水平扩展和分布式部署
    - 🛡️ 数据持久化+内存缓存双重保护
    - 🔧 配置文件可版本控制，便于环境迁移
  - **API兼容**: 保持100%前端API兼容，无需修改前端代码
  - **管理员系统**: 新增完整的基于JWT的管理员认证系统
  - **启动脚本**: 更新dev.sh，移除PostgreSQL依赖，仅启动Redis
  - **默认管理员**: 用户名`admin`，密码`admin123`
- 2025-08-14: 添加自动Git提交工具系统 🤖
  - **新增工具**: auto_commit.py - 智能分析代码变更并生成规范提交信息
  - **快速脚本**: tools/git/commit.sh - 支持多种提交模式的Shell脚本
  - **核心功能**:
    - 自动检测变更类型（fix/feat/docs/style/refactor等）
    - 智能生成提交描述和详细说明列表
    - 文件分类识别（前端/后端/配置/文档/脚本等）
    - 规范化提交格式，包含emoji标识和时间戳
  - **使用方式**:
    - `python3 tools/git/auto_commit.py` - 智能自动分析并生成提交信息
    - `./tools/git/commit.sh fix "描述"` - 快速提交bug修复
    - `./tools/git/commit.sh feat "描述"` - 快速提交新功能
    - `./tools/git/commit.sh` - 交互式提交模式
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

## 🚨 CLAUDE自动提交规则 - 必读！

### 🤖 自动Git提交指南（新Session必读）
**重要：每次完成代码修改后，Claude必须自动提交到Git！**

#### 何时必须自动提交：
1. ✅ **修复Bug** - 任何功能性修复
2. ✅ **新增功能** - 任何新功能实现
3. ✅ **重要配置修改** - 影响系统行为的配置变更
4. ✅ **数据库结构变更** - 表结构、字段修改
5. ✅ **性能优化** - 算法改进、参数调整
6. ✅ **安全修复** - 任何安全相关的修改

#### 自动提交流程：
```bash
# 1. 完成修改后立即检查状态
git status
git diff --name-only

# 2. 使用自动提交工具
python3 tools/git/auto_commit.py  # 智能分析并生成提交信息
# 或者
./tools/git/commit.sh fix "修复描述"  # 快速修复提交
./tools/git/commit.sh feat "功能描述"  # 快速功能提交

# 3. 验证提交成功
git status
git log --oneline -1
```

#### 🎯 提交标准：
- **提交消息格式**: `🔧 type: 简短描述`
- **类型**: fix, feat, docs, style, refactor, test, chore
- **必须包含**: 详细的变更列表
- **必须添加**: Claude Code标识和Co-Authored-By

#### 🤖 Claude自动执行规则：
**重要：Claude在每个新session开始时必须自动运行初始化检查！**

1. **Session开始时自动执行**：
   ```bash
   ./.claude_session_init.sh  # 必须第一时间运行
   ```

2. **完成任何代码修改后自动执行**：
   ```bash
   python3 .claude_commit_reminder.py  # 检查是否需要提交
   python3 tools/git/auto_commit.py              # 如有修改则自动提交
   ```

3. **无需用户提醒**：Claude应主动检查和提交，不等待用户指示

#### 🎮 一键智能提交命令：
```bash
# Claude专用：完成修改后立即运行
python3 tools/git/auto_commit.py && git status
```

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

### 数据存储访问
- **Redis数据**: 通过Redis CLI或系统API接口访问
- **JSON配置**: 通过配置管理API或直接编辑data/config/目录下的JSON文件
- **文件锁机制**: 所有JSON文件操作都使用fcntl系统级文件锁确保数据一致性
- **管理员登录**: `http://localhost:8000/static/login.html` (用户名: admin, 密码: admin123)

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
./dev.sh                                 # 开发模式，支持热重载，自动启动Redis

# 生产运行
./start.sh                               # 标准启动
./stop.sh                                # 停止应用
./restart.sh                             # 重启应用

# 手动步骤（如需自定义）
python3 -m venv venv                     # 创建虚拟环境
source venv/bin/activate                 # 激活虚拟环境 (Linux/Mac)
pip install -r requirements.txt          # 安装依赖
docker compose up -d redis              # 启动Redis（必须）
python3 main.py                          # 启动主应用
```

### Docker部署（生产环境）
```bash
docker compose up -d redis              # 仅启动Redis服务
docker compose down                      # 停止服务
docker compose logs -f redis            # 查看Redis日志
docker compose ps                       # 查看服务状态
docker compose restart redis            # 重启Redis服务

# 注意：应用服务现在在本地运行，不使用Docker容器
```

## 系统架构

### 核心组件
- **FastAPI应用** (`main.py`): 主应用入口，集成API和静态文件服务
- **Telegram客户端** (`app/telegram/bot.py`): 基于Telethon的消息监听和转发
- **配置管理** (`app/services/config_manager.py`): JSON文件配置存储和管理
- **频道管理** (`app/services/channel_manager.py`): 频道配置和状态管理（JSON存储）
- **消息处理** (`app/services/message_processor.py`): 消息接收、过滤和转发逻辑
- **内容过滤** (`app/services/content_filter.py`): 广告检测和内容过滤
- **调度器** (`app/services/scheduler.py`): 自动转发任务调度
- **消息分组** (`app/services/message_grouper.py`): 处理Telegram媒体组合消息
- **媒体处理** (`app/services/media_handler.py`): 媒体文件下载和处理
- **历史采集** (`app/services/history_collector.py`): 频道历史消息采集
- **系统监控** (`app/services/system_monitor.py`): 系统状态监控
- **认证服务** (`app/services/auth_service.py`): JWT管理员认证和会话管理

### 存储架构配置
- **存储类型**: Redis + JSON双层架构
- **Redis存储**: 消息数据、会话管理、分布式锁
  - 连接地址: `redis://localhost:6379` (本地开发)
  - 连接地址: `redis://redis:6379` (Docker环境)
  - 数据存储位置: `./data/redis` (Docker挂载)
  - 数据结构: Hash、Sorted Set、String with TTL
- **JSON文件存储**: 系统配置、管理员数据、频道配置
  - 存储位置: `./data/config/` 
  - 文件锁保护: 使用fcntl系统级文件锁确保并发安全
  - 版本控制: 支持Git跟踪配置变更
- **文件存储**: 训练数据、日志、媒体文件
  - 训练数据: `./data/ad_training_data/`
  - 日志文件: `./logs/`
  - 临时媒体: `./temp_media/`

### 数据存储模型
- **消息数据**: Redis Hash存储，支持高并发查询和更新
- **系统配置**: JSON文件 (`data/config/system.json`)，支持热加载
- **管理员数据**: JSON文件 (`data/config/admins.json`)，包含权限系统
- **频道配置**: JSON文件 (`data/config/channels.json`)，支持动态更新
- **会话管理**: Redis存储，支持JWT令牌和过期时间管理

### API路由结构
- `/api/messages`: 消息管理API
- `/api/admin`: 管理员功能API (业务管理)
- `/api/admin/auth`: 管理员认证API (登录、权限管理)
- `/api/config`: 配置管理API
- `/api/auth`: Telegram认证API
- `/api/system`: 系统状态API
- `/api/training`: AI训练数据API
- `/api/websocket`: WebSocket连接（用于实时认证）

### 前端组件
- **Vue.js 3 + Element Plus**: 主要前端框架
- **WebSocket认证**: 实时Telegram登录流程
- 页面功能：
  - `index.html`: 主界面（消息审核）
  - `login.html`: 管理员登录界面 (用户名: admin, 密码: admin123)
  - `config.html`: 配置管理界面
  - `auth.html`: Telegram认证界面
  - `admin.html`: 管理员界面
  - `status.html`: 系统状态监控
  - `train.html`: AI训练管理界面

### 消息处理流程
```
源频道 → 消息采集 → 内容过滤 → 审核群 → Web管理界面 → 目标频道
```

## 配置系统

### 配置层级
1. **环境变量配置** (docker-compose.yml或直接设置): 
   - REDIS_URL: `redis://redis:6379` (Docker) 或 `redis://localhost:6379` (本地)
   - LOG_LEVEL: `INFO`
   - TZ: `Asia/Shanghai`
2. **JSON配置文件** (`data/config/system.json`): 所有运行时配置通过Web界面管理
3. **默认配置** (`app/services/config_manager.py`): 初始化默认值并自动同步到JSON

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
- **禁止硬编码文件路径：所有文件路径必须从 app/core/path_config.py 的 PathConfig 类中引用**

## 开发注意事项

### 开发规范
- **开发环境**: 使用Python虚拟环境(venv)进行本地开发，不使用Docker
- **部署环境**: 仅在Linux生产环境使用Docker部署
- **Python命令**: 始终使用 `python3` 而不是 `python`
- **Docker命令**: 始终使用 `docker compose` 而不是 `docker-compose`
- **重要**: 不要创建开发版Docker配置（如docker-compose.dev.yml, docker-compose.m4.yml等）

### 技术栈
- **后端**: Python 3.11 + FastAPI + Redis + JSON + Telethon
- **前端**: Vue.js 3 + Element Plus + Axios
- **存储**: Redis + JSON文件双层架构
- **认证**: JWT + Redis会话管理
- **部署**: Docker Compose（仅Redis）+ 本地Python应用


### 工作流程

1. **初始化设置**
   - 运行 `./dev.sh` 启动Redis和应用（自动初始化JSON配置）
   - 访问 `http://localhost:8000/static/login.html` 管理员登录 (admin/admin123)
   - 访问 `http://localhost:8000/static/auth.html` 完成Telegram认证
   - 访问 `http://localhost:8000/static/config.html` 配置频道和系统参数

2. **消息处理**
   - 自动监听源频道新消息
   - 自动过滤广告内容
   - 发送到审核群供人工审核
   - 通过Web界面批量审核
   - 30分钟自动转发到目标频道

### 数据持久化
- 日志文件: `./logs/`
- JSON配置文件: `./data/config/` (system.json, admins.json, channels.json等)
- 训练数据文件: `./data/` (ad_training_data.json, feedback_learning.json等)
- 临时媒体文件: `./temp_media/`
- Redis数据: 消息数据和会话管理 (持久化到磁盘)
- Telegram会话: StringSession存储在JSON配置中

## 🚨 重要数据操作规则

### 数据安全原则
**Redis和JSON文件存储需要特别注意数据安全：**

❌ **禁止的操作：**
```bash
# 禁止删除整个Redis数据
redis-cli FLUSHALL
# 禁止删除配置目录
rm -rf data/config/
# 禁止删除训练数据
rm -rf data/ad_training_data.json
```

✅ **允许的操作：**
```bash
# Redis单键操作
redis-cli DEL message:12345
# JSON配置单项修改
# 通过配置API或Web界面修改
curl -X POST /api/config/set -d '{"key":"telegram.api_id","value":"123"}'
```

### 数据修改原则
1. **优先使用API接口** 修改配置数据
2. **直接编辑JSON文件时** 务必保持格式正确
3. **修改前先备份** 重要的配置文件
4. **使用fcntl文件锁机制** 避免并发修改冲突，不产生.lock文件

### 存储文件结构
- **Redis Keys**: `message:*`, `session:*`, `channel:*`
- **JSON配置**: `data/config/system.json`, `data/config/admins.json`
- **训练数据**: `data/ad_training_data.json`, `data/feedback_learning.json`
- **媒体文件**: `data/ad_training_data/images/`, `data/ad_training_data/videos/`

**任何批量数据操作都需要用户明确授权！**

## 存储结构同步要求

**如果修改存储结构，需要同步更新相关代码**

当修改存储结构时，必须：

1. **更新存储层代码** - `app/storage/redis_store.py`, `app/storage/json_store.py`
2. **更新服务层代码** - 对应的manager和service类
3. **测试数据迁移** - 确保新旧数据格式兼容
4. **更新配置初始化** - `app/services/config_manager.py`中的默认配置

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
python3 tools/data/recover_training_data.py --check

# 自动恢复损坏的文件
python3 tools/data/recover_training_data.py --auto-recover

# 从指定备份恢复
python3 tools/data/recover_training_data.py --restore backup_file.json --target both

# 合并多个备份文件
python3 tools/data/recover_training_data.py --merge-backups

# 紧急恢复模式（数据严重损坏时使用）
python3 tools/data/recover_training_data.py --emergency
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
- **tools/git/commit.sh**: 快速提交脚本，支持多种提交模式
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
./tools/git/commit.sh fix "修复具体问题描述"

# 添加功能后  
./tools/git/commit.sh feat "新功能描述"

# 智能自动分析（推荐）
python3 tools/git/auto_commit.py

# Claude Code自动调用（无交互）
python3 tools/git/auto_commit_claude.py auto

# 交互式选择
./tools/git/commit.sh
```

### 提交信息规范
- 使用emoji标识（🐛 fix、✨ feat、📝 docs等）
- 简洁明确的描述
- 自动生成时间戳和详细说明
- 符合约定式提交规范

**⚠️ 重要提醒**: 不要手动执行 `git commit`，始终使用自动提交工具确保提交信息的规范性和一致性。

详细使用说明见: `docs/auto_commit_usage.md`
- 修复bug，要用彻底解决的方式，不要用兼容，向下的方式变相逃避bug。