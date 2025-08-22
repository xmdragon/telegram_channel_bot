# CLAUDE.md

Claude Code 工作指导文档。

## 重大变更历史

- 2025-08-17: 🔧 **API路由安全优化** - 解决危险的通配符路由，引入路由配置统一管理
- 2025-08-17: 📚 **开发规范完善** - 添加命名规范、代码组织、清理工具指南
- 2025-08-16 (v4.0): 🚀 **服务分离架构重构** - 解决开发体验痛点，性能大幅提升
- 2025-08-15: 🧹 根目录整理，工具分类管理（tools/目录结构化）
- 2025-08-14 (v3.0): 🚀 Redis+JSON存储架构，性能提升300%+
- 2025-08-14: 🤖 自动Git提交工具（tools/git/）
- 2025-08-10: 🔍 OCR功能优化（OpenCV图像处理）
- 2025-08-09: 🔐 训练数据保护机制
- 2025-08-08: 📁 配置导入导出工具
- 2025-08-07: 🔧 开发模式脚本（dev.sh）

## 🤖 Claude自动提交规则

### 必须自动提交的情况：
- Bug修复、新功能、重要配置修改、性能优化、安全修复

### 提交流程：
```bash
# 检查状态
git status && git diff --name-only

# 自动提交
python3 tools/git/auto_commit.py
# 或快速提交
./tools/git/commit.sh fix "描述"
./tools/git/commit.sh feat "描述"

# 验证
git status && git log --oneline -1
```

### Session开始时必须执行：
```bash
./.claude_session_init.sh
```

## 📁 项目结构管理规范

### 根目录清洁原则
**严格遵守根目录最小化！**

#### 禁止存放：
❌ 测试文件、临时脚本、批量操作脚本、实验文件、备份文件、会话文件

#### ⚠️ 重要原则：
- **测试文件、临时文件用完立即删除**
- **禁止创建代码备份文件（.bak、.backup、*-backup.*等）**
- **版本控制使用git，不需要手动备份文件**

#### 允许的核心文件：
✅ main.py, CLAUDE.md, README.md, requirements.txt, .gitignore
✅ docker-compose.yml, Dockerfile  
✅ dev.sh, start.sh, stop.sh, restart.sh
✅ app/, data/, docs/, logs/, static/, tools/, temp_media/, venv/

### tools/目录分类
```
tools/
├── git/         # Git工具
├── admin/       # 管理工具
├── batch/       # 批量处理
├── debug/       # 调试工具
├── utils/       # 通用工具
├── testing/     # 测试脚本
├── analysis/    # 分析工具
└── maintenance/ # 维护工具
```

#### 强制规则：
1. 新脚本必须放在tools/对应子目录
2. 测试文件在tools/testing/，完成后评估保留
3. 临时文件禁止放根目录
4. 批量操作脚本放tools/batch/
5. Session结束前检查根目录文件数量

## 💾 存储架构

### Redis存储
- 消息数据、会话管理、分布式锁
- 连接：`redis://localhost:6379`（本地）/ `redis://redis:6379`（Docker）

### JSON存储  
- 系统配置：`data/config/system.json`
- 管理员数据：`data/config/admins.json`
- 频道配置：`data/config/channels.json`
- 使用fcntl文件锁保护

### 路径配置
**禁止硬编码路径！统一使用PathConfig类**
- 训练数据：`PathConfig.AD_TRAINING_DIR` (data/training/ad/)
- 临时媒体：`PathConfig.TEMP_MEDIA_DIR` (temp_media/)
- API挂载：`/media/ad_training_data` → `PathConfig.AD_TRAINING_DIR`

## 🚀 开发指南

### 🎯 v4.0 服务分离架构（2025-08-16重大更新）

#### 核心突破
- **解决开发痛点**：修改代码不再导致全系统重启
- **服务独立性**：Web、采集、调度服务完全分离
- **性能提升**：状态查看从5秒优化到0.05秒（100倍提升）
- **灵活调试**：支持选择性启动和独立重启

#### 服务架构
```
系统架构 (v4.0)
├── web_server.py          # Web服务器 (端口8000)
├── telegram_collector.py  # Telegram消息采集
├── message_scheduler.py   # 消息调度和清理
├── dev_supervisor.py      # 进程管理器
└── health_monitor.py      # 健康监控系统
```

### 启动命令

#### 🔧 开发模式（推荐）
```bash
# 灵活服务选择
./dev.sh                    # 启动所有服务
./dev.sh web               # 仅启动Web服务
./dev.sh web scheduler     # 启动指定服务
./dev.sh --status          # 快速查看状态（0.05秒）
./dev.sh --legacy          # 传统模式（兼容）
```

#### 🏭 生产模式
```bash
# 完整系统管理
./start.sh                 # 启动完整系统
./stop.sh                  # 智能停止所有服务
./restart.sh               # 4步骤完整重启
```

#### 📊 状态监控
```bash
# 实时状态查看
./dev.sh --status          # 超快状态查看
curl localhost:8000/api/health  # API健康检查
```

### 技术栈
- 后端：Python 3.11 + FastAPI + Redis + JSON + Telethon
- 前端：Vue.js 3 + Element Plus + Axios  
- 认证：JWT + Redis会话管理

### API路由
- `/api/messages` - 消息管理
- `/api/admin` - 管理员功能
- `/api/config` - 配置管理
- `/api/telegram-auth` - Telegram用户认证（非管理员认证）
- `/api/training-db` - AI训练数据

## 🌐 API端点管理规范

### 集中配置原则
**严格禁止硬编码API端点！所有API端点必须统一管理**

#### 核心配置文件
- **API配置**：`static/assets/js/config/api-endpoints.js`
- **版本控制**：配置文件纳入版本管理
- **引用方式**：所有前端代码必须从配置文件引用API端点

#### 使用规范
```javascript
// ✅ 正确方式 - 从配置文件引用
import API from './config/api-endpoints.js';
const response = await axios.get(API.messages.list);
const response = await axios.delete(API.messages.deleteById(messageId));

// ❌ 错误方式 - 硬编码
const response = await axios.get('/api/messages/');
```

#### API端点分类
```javascript
API_ENDPOINTS = {
    messages: {},        // 消息管理模块
    adminAuth: {},       // 管理员认证模块
    telegramAuth: {},    // Telegram认证模块
    training: {},        // 训练数据模块
    config: {},          // 配置管理模块
    system: {},          // 系统状态模块
    admin: {},           // 管理功能模块
    websocket: {}        // WebSocket端点
}
```

#### 开发和调试规范
1. **查找端点**：开发时先检查`api-endpoints.js`文件
2. **添加端点**：新增API端点必须先在配置文件中定义
3. **路由同步**：确保前端配置与后端路由一致
4. **命名规范**：API路径使用kebab-case（如`/batch-approve`）

#### 防止冗余端点
- 新增端点前检查是否已存在
- 调查Git历史确认端点变更
- 避免重复实现相同功能的端点
- 定期审查和清理无用端点

### 重要配置
- 管理员登录：`http://localhost:8000/static/login.html` (admin/admin123)
- 静态文件路径：`/static/xxx.html`
- macOS tail命令：`tail -n 20 file.log`

## 🏗️ 系统架构概览

### 核心服务说明
- **web_server.py**: Web API服务器，提供REST API、WebSocket和静态文件服务
- **telegram_collector.py**: Telegram消息采集服务，负责实时监听和历史消息采集
- **message_scheduler.py**: 后台调度服务，处理自动转发和数据清理任务

### 关键模块
- **app/api/**: API路由层，处理所有HTTP请求
- **app/services/**: 业务逻辑层，包含消息处理和过滤引擎
- **app/telegram/**: Telegram相关功能，包括Bot和认证
- **app/storage/**: 存储层，管理Redis和JSON数据

### 架构文档
完整的系统架构说明请查看：`docs/SYSTEM_ARCHITECTURE.md`

## 🛠️ 开发规范

### 基础要求
- Python虚拟环境本地开发，生产环境用Docker
- 使用`python3`而不是`python`
- 使用`docker compose`而不是`docker-compose`
- 前端Vue3 + Element Plus + Axios
- 中文简短回复

### 🧹 文件管理规范
- **测试文件、临时文件用完立即删除**
- **禁止创建任何形式的备份文件**（.bak、.backup、*-backup.*、*-old.*等）
- **版本控制依赖git，不需要手动文件备份**
- **调试页面、测试脚本使用完毕必须清理**

### 强制规范
- **禁止硬编码文件路径**：必须从PathConfig类引用
- **无需向后兼容**：始终选择最优方案，不考虑兼容性约束
- **自适应阈值**：AI检测阈值动态优化，禁止硬编码阈值参数
- **代码分离原则**：严格禁止HTML内联JavaScript和CSS
  - ❌ 禁止使用`<script>`标签内联JS代码
  - ❌ 禁止使用`<style>`标签内联CSS代码
  - ❌ 禁止使用`style=""`属性内联样式
  - ✅ JS代码必须放在独立的`.js`文件中
  - ✅ CSS样式必须放在独立的`.css`文件中
  - ✅ 实现HTML、CSS、JavaScript完全分离

### 📏 文件大小控制规范
- **🚨 超过500行立即重构**：任何文件超过500行必须考虑重构拆分
- **重构触发条件**：
  - 单个Python文件 > 500行
  - 单个JavaScript文件 > 400行
  - 单个CSS文件 > 300行
- **重构策略**：
  - 按功能职责拆分模块
  - 遵循单一职责原则
  - 保持向后兼容性
  - 使用依赖注入避免循环依赖
- **重构工具**：优先使用Task工具启动专门的重构代理

### 命名规范要求
- **必须遵循PEP 8命名规范**
- **API路径必须使用kebab-case**
- **前端代码遵循Vue.js规范**
- **测试文件只能放在tools/test或tools/testing**
- **禁止在根目录创建任何临时文件**

## 📋 代码组织规范

### 文件命名标准
- Python文件：使用`snake_case`（如`message_processor.py`）
- 类名：使用`PascalCase`（如`MessageProcessor`）
- 函数/方法：使用`snake_case`（如`process_message()`）
- 常量：使用`UPPER_SNAKE_CASE`（如`MAX_RETRY_COUNT`）

### 目录结构规范
```
app/
├── api/           # API路由层（所有路由端点）
├── core/          # 核心配置和工具
├── services/      # 业务逻辑层
│   └── filters/   # 过滤器子模块
├── storage/       # 存储层
├── telegram/      # Telegram相关
└── utils/         # 工具函数
```

### 模块依赖原则
1. 上层模块可以依赖下层模块
2. 同层模块尽量避免相互依赖
3. 避免循环依赖
4. 依赖注入优于直接导入

### 测试文件管理
- **禁止在根目录创建测试文件**
- 所有测试文件必须放在`tools/testing/`
- 测试完成后评估是否保留
- 使用描述性的测试文件名

详细的命名规范请查看：`docs/NAMING_CONVENTIONS.md`

## 📐 命名规范速查

### Python规范（PEP 8）
| 类型 | 规范 | 示例 |
|-----|------|------|
| 文件名 | snake_case | `message_processor.py` |
| 类名 | PascalCase | `MessageProcessor` |
| 函数/方法 | snake_case | `process_message()` |
| 变量 | snake_case | `message_count` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| 私有成员 | 前缀`_` | `_private_method()` |

### API规范
| 类型 | 规范 | 示例 |
|-----|------|------|
| 路径 | kebab-case | `/api/batch-approve` |
| 查询参数 | snake_case | `?page_size=20` |
| JSON字段 | snake_case | `{"message_id": "123"}` |

### 前端规范（Vue.js）
| 类型 | 规范 | 示例 |
|-----|------|------|
| HTML文件 | snake_case/kebab-case | `message_manager.html` |
| Vue组件 | PascalCase | `MessageRenderer` |
| CSS类 | kebab-case | `.message-card` |
| JS变量 | camelCase | `messageList` |
| JS常量 | UPPER_SNAKE_CASE | `API_BASE_URL` |

### 存储规范
| 类型 | 规范 | 示例 |
|-----|------|------|
| Redis键 | 冒号分隔 | `telegram:messages:123` |
| JSON字段 | snake_case | `"channel_id"` |
| 配置键 | snake_case | `"max_retry_count"` |

## 🧹 代码清理规范

### 定期清理任务
1. **每周清理测试文件**
   - 检查`tools/testing/`目录
   - 删除已完成的测试脚本
   - 归档重要的测试用例

2. **使用清理工具**
   ```bash
   # 分析冗余文件
   python3 tools/maintenance/cleanup_redundant_files.py --analyze
   
   # 清理测试文件（带备份）
   python3 tools/maintenance/cleanup_redundant_files.py --clean-tests
   
   # 清理冗余模块（需确认）
   python3 tools/maintenance/cleanup_redundant_files.py --clean-redundant
   ```

3. **备份和恢复**
   - 清理前自动创建备份
   - 备份保存在`backups/`目录
   - 可通过备份恢复误删文件

### 清理优先级
- **高优先级**：测试文件、示例文件、临时脚本
- **中优先级**：备份文件、冗余模块
- **低优先级**：可能还在使用的旧模块

### 清理前检查
- 确认服务正常运行
- 检查模块依赖关系
- 备份重要数据

## 🔍 消息诊断工具

### 查询本地消息
当用户提供类似 `-1002557968812:2251` 的消息ID时，使用：
```bash
python3 tools/testing/get_local_message.py -1002557968812:2251
python3 tools/testing/get_local_message.py -1002557968812:2251 --raw      # 原始JSON
python3 tools/testing/get_local_message.py -1002557968812:2251 --media    # 媒体详情
python3 tools/testing/get_local_message.py -1002557968812:2251 --related  # 相关消息
```

### 抓取Telegram原始消息
当用户提供Telegram链接如 `https://t.me/cn_zhm0/2247` 时，使用：
```bash
python3 tools/testing/fetch_telegram_message.py https://t.me/cn_zhm0/2247
python3 tools/testing/fetch_telegram_message.py https://t.me/cn_zhm0/2247 --json     # JSON格式
python3 tools/testing/fetch_telegram_message.py https://t.me/cn_zhm0/2247 --compare  # 与系统对比
```

### 诊断流程
1. **先查本地**：`get_local_message.py` 查看系统中的消息状态
2. **再查原始**：`fetch_telegram_message.py` 获取Telegram原始消息
3. **对比分析**：使用 `--compare` 参数自动对比差异，定位问题根源

### 使用场景
- 消息内容丢失或显示异常
- 组合消息不完整
- 媒体文件缺失
- 文本过滤异常
- 需要验证消息采集的准确性

## 🔧 配置导入导出

```bash
# 导出配置
python3 export_config.py

# 导入配置  
python3 import_config.py
```

## 🤖 自动Git提交工具

### 核心工具
- `tools/git/auto_commit.py` - 智能分析提交
- `tools/git/commit.sh` - 快速提交脚本
- `tools/git/auto_commit_claude.py` - Claude专用

### 使用方式
```bash
# 智能分析（推荐）
python3 tools/git/auto_commit.py

# 快速提交
./tools/git/commit.sh fix "修复问题"
./tools/git/commit.sh feat "新功能"

# 交互式
./tools/git/commit.sh
```

⚠️ **重要**: 不要手动执行`git commit`，使用自动提交工具确保规范性。

## 🔐 数据管理（紧急情况）

```bash
# 配置导入导出（环境迁移）
python3 tools/data/export_config.py
python3 tools/data/import_config.py

# 数据恢复（系统故障时）
python3 tools/data/recover_training_data.py --check
```

## 📚 快速参考

### 常用命令列表
```bash
# 开发相关
./dev.sh                    # 启动开发环境
./dev.sh --status          # 查看服务状态
./dev.sh web               # 仅启动Web服务

# 系统管理
./start.sh                 # 启动生产环境
./stop.sh                  # 停止所有服务
./restart.sh               # 重启系统

# Git操作
python3 tools/git/auto_commit.py  # 自动提交
./tools/git/commit.sh fix "xxx"   # 快速修复提交

# 清理维护
python3 tools/maintenance/cleanup_redundant_files.py --analyze  # 分析冗余

# 消息诊断
python3 tools/testing/get_local_message.py CHANNEL_ID:MSG_ID     # 查询本地消息
python3 tools/testing/fetch_telegram_message.py TELEGRAM_URL    # 抓取原始消息
```

### 文件位置速查
- API端点配置：`static/assets/js/config/api-endpoints.js`
- 系统架构文档：`docs/SYSTEM_ARCHITECTURE.md`
- 命名规范文档：`docs/NAMING_CONVENTIONS.md`
- 清理工具：`tools/maintenance/cleanup_redundant_files.py`
- 配置文件：`data/config/`
- 日志文件：`logs/`
- 测试脚本：`tools/testing/`
- 本地消息查询：`tools/testing/get_local_message.py`
- Telegram消息抓取：`tools/testing/fetch_telegram_message.py`

### 故障排查步骤
1. 检查服务状态：`./dev.sh --status`
2. 查看日志：`tail -n 50 logs/app.log`
3. 检查Redis：`redis-cli ping`
4. 验证配置：`cat data/config/system.json`
5. 重启服务：`./restart.sh`

### API端点速查
**所有API端点请查看：`static/assets/js/config/api-endpoints.js`**

常用端点示例：
- 消息列表：`API.messages.list` → `GET /api/messages/`
- 批量审核：`API.messages.batchApprove` → `POST /api/messages/batch-approve`
- 训练数据：`API.training.adSamples` → `GET /api/training-db/ad-samples`
- 系统健康：`API.system.health` → `GET /api/health`
- WebSocket：`API.websocket.main` → `ws://localhost:8000/ws`

## 🚨 重要提醒

- **API端点管理**：严格禁止硬编码API路径，必须使用`api-endpoints.js`配置
- Redis和JSON双层存储，禁止删除整个数据库
- 文件锁机制确保数据一致性
- 优先使用API接口修改配置
- 任何批量数据操作需要用户明确授权
- 存储结构修改时必须同步更新相关代码
- 测试文件必须放在tools/testing/目录
- 遵循PEP 8和项目命名规范
- 定期执行代码清理和优化