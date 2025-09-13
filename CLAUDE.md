# CLAUDE.md

Claude Code 工作指导文档。

## 🧠 Linus Torvalds 思维准则

### 核心原则（永远遵守）
**所有功能开发和bug修复必须遵循Linus Torvalds的设计哲学：**

1. **"好品味"(Good Taste) 优先**
   - 消除特殊情况，让边界条件变成正常情况
   - 10行带条件判断优化为4行无条件分支
   - 重新设计数据结构以消除复杂逻辑

2. **"Never break userspace" 铁律**
   - 向后兼容性是神圣不可侵犯的
   - 任何破坏现有功能的改动都是bug
   - 代码为用户服务，不是教育用户

3. **实用主义至上**
   - 解决真实存在的问题，不是假想威胁
   - 拒绝理论完美但实际复杂的方案
   - "Theory and practice clash. Theory loses."

4. **简洁执念**
   - 函数保持短小精悍，只做一件事
   - 超过3层缩进就重新设计
   - 复杂性是万恶之源

### 实施要求与执行检查点
#### 强制执行准则
- **分析阶段**：先问"这是真问题吗？有更简单方法吗？会破坏什么吗？"
- **设计阶段**：优先考虑数据结构，消除特殊情况
- **实现阶段**：用最清晰（不是最聪明）的方式实现
- **代码审查**：检查是否有不必要的抽象层和复杂性

#### 执行检查点（每次代码修改必须通过）
✓ **复杂度检查**：函数不超过30行，缩进不超过3层
✓ **特殊情况检查**：是否有可以消除的if/else分支
✓ **数据结构检查**：是否选择了最简单的数据结构
✓ **破坏性检查**：是否会破坏现有功能
✓ **实用性检查**：是否解决了真实存在的问题

## 🎯 Claude Code Development Principles

### Claude Code 八荣八耻 (Eight Honors and Eight Shames)

**所有开发活动必须遵循以下原则：**

1. **以暗猜接口为耻，以认真查阅为荣**
   - *Shame in guessing APIs, Honor in careful research*
   - 永远先查询现有接口，理解其设计意图

2. **以模糊执行为耻，以寻求确认为荣**
   - *Shame in vague execution, Honor in seeking confirmation*
   - 不确定时主动寻求明确的需求确认

3. **以盲想业务为耻，以人类确认为荣**
   - *Shame in assuming business logic, Honor in human verification*
   - 业务逻辑必须与人类确认，不能凭想象

4. **以创造接口为耻，以复用现有为荣**
   - *Shame in creating interfaces, Honor in reusing existing ones*
   - 优先复用现有接口，避免重复造轮子

5. **以跳过验证为耻，以主动测试为荣**
   - *Shame in skipping validation, Honor in proactive testing*
   - 主动进行测试验证，确保代码质量

6. **以破坏架构为耻，以遵循规范为荣**
   - *Shame in breaking architecture, Honor in following specifications*
   - 严格遵循既定架构和编码规范

7. **以假装理解为耻，以诚实无知为荣**
   - *Shame in pretending to understand, Honor in honest ignorance*
   - 不懂就说不懂，诚实面对知识边界

8. **以盲目修改为耻，以谨慎重构为荣**
   - *Shame in blind modification, Honor in careful refactoring*
   - 深思熟虑后再重构，避免盲目修改

### 执行要求
- **每次代码修改前**：先检查是否违反八荣八耻原则
- **遇到不确定情况**：优先寻求确认而非猜测
- **API使用时**：必须查询文档和现有实现
- **重构操作时**：谨慎评估影响范围和风险

## 重大变更历史

- 2025-09-09: 🚀 **Docker架构完全移除** - 彻底放弃Colima Docker，使用本地Redis+Nginx服务，架构简化，性能提升，稳定性增强
- 2025-09-06: 🐍 **Python 3.13兼容性修复** - 解决telethon导入作用域问题，所有类型导入必须在模块顶部
- 2025-09-04: 🗂️ **路由架构重构** - 统一所有路由到app/api/目录，消除app/routers特殊情况，符合Linus设计原则
- 2025-08-23: 🎯 **Element Plus完全移除** - 全项目UI重构完成，彻底删除Element Plus依赖，使用轻量化SimpleUI系统
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
✅ CLAUDE.md, README.md, requirements.txt, .gitignore
✅ docker-compose.yml, Dockerfile  
✅ dev.sh, start.sh, stop.sh, restart.sh
✅ app/, data/, docs/, logs/, static/, tools/, temp_media/, venv/

#### 📚 文档管理规范：
- **根目录只保留**：`CLAUDE.md` 和 `README.md`
- **所有其他md文档必须放在docs/目录**
- **禁止在根目录创建新的md文件**（除非是CLAUDE.md或README.md的更新）

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
├── message_collector.py   # 消息采集服务
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
- 前端：Vue.js 3 + SimpleUI系统 + Axios + 原生HTML/CSS/JS
- 认证：JWT + Redis会话管理

### API路由
- `/api/messages` - 消息管理
- `/api/admin` - 管理员功能
- `/api/config` - 配置管理
- `/api/telegram-auth` - Telegram用户认证（非管理员认证）
- `/api/training` - AI训练数据（注意：不是training-db，是training）

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

### 🌐 服务端口和访问配置

#### 双服务架构（Nginx + FastAPI）
- **Nginx静态文件服务**：`http://localhost:8080`
  - 管理员登录：`http://localhost:8080/static/login.html` (admin/admin123)
  - 所有前端页面：`http://localhost:8080/static/xxx.html`
  - 静态资源：CSS、JS、图片、字体等
- **FastAPI后端服务**：`http://localhost:8000`
  - API端点：`http://localhost:8000/api/*`
  - WebSocket：`ws://localhost:8000/ws`
  - 系统健康检查：`http://localhost:8000/api/health`

#### ⚠️ 调试时的端口注意事项
1. **前端页面访问**：始终使用 `8080` 端口（Nginx）
2. **API调试**：直接使用 `8000` 端口（FastAPI）
3. **404错误排查**：
   - 静态文件404 → 检查8080端口和文件路径
   - API接口404 → 检查8000端口和路由配置
4. **性能优势**：Nginx专门优化静态文件服务，FastAPI专注API处理

### macOS开发配置
- macOS tail命令：`tail -n 20 file.log`

## 🏗️ 系统架构概览

### 🏛️ v5.0本地服务架构设计 (2025-09-09)

系统采用**完全本地化**的部署架构，消除Docker复杂性，实现Linus式简化：

```
┌─────────────────────────────────────────────────────┐
│                     用户访问层                       │
│                 http://localhost:8080                │
└─────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│         🍺 Homebrew本地服务层 (Infrastructure)        │
│  ┌─────────────────┐    ┌─────────────────────────┐  │
│  │  本地Nginx      │    │      本地Redis          │  │
│  │  端口: 8080     │    │      端口: 6379         │  │
│  │  • 静态文件服务  │    │      • 消息数据缓存     │  │
│  │  • 反向代理      │    │      • 会话管理         │  │
│  │  • 负载均衡      │    │      • 分布式锁         │  │
│  │  • 配置简单     │    │      • 启动快速         │  │
│  └─────────────────┘    └─────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                           │
                    (反向代理到8000端口)
                           ▼
┌─────────────────────────────────────────────────────┐
│          💻 Python应用服务层 (Application)           │
│                由dev_supervisor.py统一管理           │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────┐ │
│  │ Web服务         │ │ Telegram采集    │ │ 调度服务│ │
│  │ web_server.py   │ │ telegram_       │ │ message_│ │
│  │ 端口: 8000      │ │ collector.py    │ │ sched-  │ │
│  │ • FastAPI       │ │ • 实时消息监听  │ │ uler.py │ │
│  │ • REST API      │ │ • 历史消息采集  │ │ • 自动  │ │
│  │ • WebSocket     │ │ • 消息过滤处理  │ │   转发  │ │
│  │ • Gunicorn      │ │ • 媒体文件处理  │ │ • 数据  │ │
│  │   启动          │ │                 │ │   清理  │ │
│  └─────────────────┘ └─────────────────┘ └─────────┘ │
└─────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│                   📁 存储层                          │
│     Redis(消息数据) + JSON(配置文件) + NPZ(向量)      │
└─────────────────────────────────────────────────────┘
```

### 🔧 服务分层架构

#### Homebrew本地服务层 (Infrastructure)
- **本地Nginx** (`brew install nginx`)
  - 端口：`8080`
  - 职责：高性能静态文件服务、API反向代理
  - 配置文件：`/opt/homebrew/etc/nginx/servers/telegram_bot.conf`
  - 文件路径：直接访问本地绝对路径，无需挂载
  - 优势：启动快速，配置简单，性能更优

- **本地Redis** (`brew install redis`)  
  - 端口：`6379`
  - 职责：消息数据缓存、会话管理、分布式锁
  - 配置文件：`/opt/homebrew/etc/redis.conf`
  - 优势：内存直接访问，无虚拟化开销

#### 本地应用服务层 (Application)  
- **Web服务** (`web_server.py`)
  - 端口：`8000` (仅本地访问，通过Nginx代理)
  - 技术栈：FastAPI + Gunicorn + UvicornWorker
  - 职责：REST API、WebSocket实时通信、业务逻辑处理
  
- **消息采集服务** (`message_collector.py`)
  - 技术栈：Telethon + asyncio
  - 职责：实时消息监听、历史消息采集、智能过滤
  
- **消息调度服务** (`message_scheduler.py`)
  - 职责：自动转发队列、定时数据清理、统计广播

### 🔄 服务协作流程

1. **用户访问** → Nginx容器(8080) → 静态文件直接服务
2. **API请求** → Nginx容器(8080) → 反向代理 → FastAPI服务(8000)
3. **WebSocket** → Nginx容器(8080) → WebSocket代理 → FastAPI服务(8000)
4. **服务管理** → `dev_supervisor.py` → 统一管理三个本地服务生命周期
5. **数据存储** → Redis容器(6379) + JSON文件系统

### 🎯 架构优势

- **性能分工**：Nginx专门优化静态文件(100x性能)，FastAPI专注API处理
- **独立部署**：容器化基础设施，本地化应用服务，方便开发调试  
- **服务分离**：Web、采集、调度独立进程，故障隔离，按需重启
- **统一管理**：`dev_supervisor.py`统一进程管理，智能健康检查
- **混合存储**：Redis高性能缓存 + JSON配置持久化 + NPZ向量索引

### 📂 关键模块
- **app/api/**: API路由层，处理所有HTTP请求
- **app/services/**: 业务逻辑层，包含消息处理和过滤引擎  
- **app/telegram/**: Telegram相关功能，包括Bot和认证
- **app/storage/**: 存储层，管理Redis和JSON数据
- **nginx/**: Nginx配置文件
- **dev_supervisor.py**: 服务进程管理器

### 📋 架构演进记录
- **v3.0 (2025-08-14)**: Redis+JSON双存储架构
- **v4.0 (2025-08-16)**: 服务分离架构，性能提升100倍
- **v4.1 (2025-08-17)**: Element Plus完全移除，SimpleUI系统  
- **v4.2 (2025-08-25)**: Docker+本地混合架构，Nginx静态文件服务

## 🛠️ 开发规范

### 基础要求
- **后端**：Python 3.11+虚拟环境本地开发，基础设施用Docker容器
- **命令规范**：使用`python3`而不是`python`，使用`docker compose`而不是`docker-compose`
- **前端技术栈**：Vue.js 3 + SimpleUI系统 + Axios + 原生HTML/CSS/JS
- **部署架构**：混合部署 - Docker容器(Nginx+Redis) + 本地服务(Python应用)
- **开发语言**：中文简短回复，注释和文档使用中文

### 🐍 Python 3.13兼容性要求
**重要：Python 3.13对变量作用域有更严格的检查**
- **Telethon类型导入必须在模块顶部**：避免在函数内部或try块中导入
- **错误示例**：
  ```python
  # ❌ 错误：在函数内部导入会导致作用域错误
  def process():
      from telethon.tl.types import MessageMediaWebPage
      if isinstance(media, MessageMediaWebPage):  # Error: cannot access local variable
  ```
- **正确示例**：
  ```python
  # ✅ 正确：在模块顶部导入
  from telethon.tl.types import MessageMediaWebPage
  
  def process():
      if isinstance(media, MessageMediaWebPage):  # 正常工作
  ```
- **影响范围**：所有使用telethon的模块必须遵守此规则

### 🧹 文件管理规范
- **测试文件、临时文件用完立即删除**
- **禁止创建任何形式的备份文件**（.bak、.backup、*-backup.*、*-old.*等）
- **版本控制依赖git，不需要手动文件备份**
- **调试页面、测试脚本使用完毕必须清理**

### 强制规范
- **禁止硬编码文件路径**：必须从PathConfig类引用
- **🚨 禁止硬编码API端点**：所有API端点必须使用`api-endpoints.js`配置文件统一管理
- **🚨 禁止硬编码关键词**：所有关键词必须使用`filter_rules.json`配置文件统一管理
- **无需向后兼容**：始终选择最优方案，不考虑兼容性约束
- **自适应阈值**：AI检测阈值动态优化，禁止硬编码阈值参数
- **🚨 严禁Element Plus**：项目已完全移除Element Plus，禁止任何形式的重新引入
  - ❌ 禁止使用任何`el-*`组件（el-button、el-table、el-dialog等）
  - ❌ 禁止添加Element Plus CSS/JS引用
  - ❌ 禁止使用`ElementPlus`、`ElMessage`、`ElMessageBox`等API
  - ✅ 必须使用SimpleUI系统：`SimpleUI.showMessage()`、`SimpleUI.confirm()`
  - ✅ 必须使用原生HTML标签配合自定义CSS类
- **代码分离原则**：严格禁止HTML内联JavaScript和CSS
  - ❌ 禁止使用`<script>`标签内联JS代码
  - ❌ 禁止使用`<style>`标签内联CSS代码
  - ❌ 禁止使用`style=""`属性内联样式
  - ✅ JS代码必须放在独立的`.js`文件中
  - ✅ CSS样式必须放在独立的`.css`文件中
  - ✅ 实现HTML、CSS、JavaScript完全分离
- **🔇 日志输出规范**：最小化控制台噪音
  - ❌ 禁止使用`console.log`输出调试信息
  - ❌ 禁止输出系统启动、状态、成功等非必要日志
  - ✅ 仅保留`console.error`用于错误调试
  - ✅ 仅保留`console.warn`用于重要警告
  - ✅ 调试完成后必须删除所有临时日志输出

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
│   └── training/  # 训练相关路由模块
├── core/          # 核心配置和工具
├── services/      # 业务逻辑层
│   └── filters/   # 过滤器子模块
├── storage/       # 存储层
├── telegram/      # Telegram相关
└── utils/         # 工具函数
```

### 🗂️ 路由管理规范（2025-09-04更新）

**统一路由位置 - Linus原则：消除特殊情况**
- **所有API路由必须定义在 `app/api/` 目录下**
- 禁止在其他位置（如 `app/routers/`）创建路由
- 路由按功能模块组织，如 `app/api/training/` 包含所有训练相关路由

**禁止事项**：
- ❌ 禁止在 `app/routers/` 目录创建路由
- ❌ 禁止路由功能重复定义
- ❌ 禁止路由分散在多个位置

**强制要求**：
- ✅ 所有新路由必须在 `app/api/` 对应模块下创建
- ✅ 路由冲突时，保留功能更完整的实现
- ✅ 同类功能路由必须在同一模块下

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

# 系统管理 (推荐使用本地服务版)
./start_native.sh          # 启动本地服务版 (推荐)
./stop_native.sh           # 停止本地服务版
./restart_native.sh        # 重启本地服务版

# 系统管理 (传统Docker版，已废弃)
./start.sh                 # 启动生产环境 (Docker版)
./stop.sh                  # 停止所有服务 (Docker版)  
./restart.sh               # 重启系统 (Docker版)

# Git操作
python3 tools/git/auto_commit.py  # 自动提交
./tools/git/commit.sh fix "xxx"   # 快速修复提交

# 清理维护
python3 tools/maintenance/cleanup_redundant_files.py --analyze  # 分析冗余

# 消息诊断
python3 tools/testing/get_local_message.py CHANNEL_ID:MSG_ID     # 查询本地消息
python3 tools/testing/fetch_telegram_message.py TELEGRAM_URL    # 抓取原始消息
```

### 🌐 端口和访问速查
- **前端页面**：`http://localhost:8080/static/xxx.html` (Nginx静态文件服务)
- **API接口**：`http://localhost:8000/api/*` (FastAPI后端服务)
- **管理员登录**：`http://localhost:8080/static/login.html` (admin/admin123)
- **WebSocket**：`ws://localhost:8000/ws`
- **健康检查**：`http://localhost:8000/api/health`

### 文件位置速查
- API端点配置：`static/assets/js/config/api-endpoints.js`
- 配置文件：`data/config/`
- 日志文件：`logs/`
- 测试脚本：`tools/testing/`
- 本地消息查询：`tools/testing/get_local_message.py`
- Telegram消息抓取：`tools/testing/fetch_telegram_message.py`
- 清理工具：`tools/maintenance/cleanup_redundant_files.py`

### 📚 文档速查（docs/目录）
- 系统架构文档：`docs/SYSTEM_ARCHITECTURE.md`
- 命名规范文档：`docs/NAMING_CONVENTIONS.md`
- 部署文档：`docs/DEPLOYMENT.md`
- API响应格式：`docs/API_RESPONSE_FORMAT.md`
- Colima优化指南：`docs/COLIMA_OPTIMIZATION_SUMMARY.md`

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