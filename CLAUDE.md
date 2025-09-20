# CLAUDE.md

Claude Code 工作指导文档 - Telegram消息采集审核系统

## 🧠 Linus Torvalds 设计哲学

### 核心原则（永远遵守）

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

### 执行检查点
- **复杂度检查**：函数不超过30行，缩进不超过3层
- **特殊情况检查**：是否有可以消除的if/else分支
- **数据结构检查**：是否选择了最简单的数据结构
- **破坏性检查**：是否会破坏现有功能
- **实用性检查**：是否解决了真实存在的问题

## 🎯 开发八荣八耻

1. **以暗猜接口为耻，以认真查阅为荣** - 永远先查询现有接口
2. **以模糊执行为耻，以寻求确认为荣** - 不确定时主动确认需求
3. **以盲想业务为耻，以人类确认为荣** - 业务逻辑必须与人类确认
4. **以创造接口为耻，以复用现有为荣** - 优先复用现有接口
5. **以跳过验证为耻，以主动测试为荣** - 主动进行测试验证
6. **以破坏架构为耻，以遵循规范为荣** - 严格遵循既定架构
7. **以假装理解为耻，以诚实无知为荣** - 不懂就说不懂
8. **以盲目修改为耻，以谨慎重构为荣** - 深思熟虑后再重构

## 👑 重要称谓规则

**必须称呼用户为"哥"** - 因为用户总是能一语点醒Claude的"过度保守"症候群，每次都是先保守，被"哥"一点就醒悟。这个称谓体现了对用户技术判断力的尊重和Claude需要不断学习的谦逊态度。

## 🚀 系统架构

### 服务分离架构

```
┌─────────────────────────────────────────┐
│                用户界面                  │
│          http://localhost:8080          │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│              Python应用层                │
│        由dev_supervisor.py管理          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────┐ │
│  │Web服务      │ │消息采集      │ │调度 │ │
│  │web_server.py│ │message_     │ │服务 │ │
│  │端口:8008    │ │collector.py │ │     │ │
│  │FastAPI+Redis│ │Telethon监听 │ │清理 │ │
│  └─────────────┘ └─────────────┘ └─────┘ │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│              存储层                      │
│     Redis(消息数据) + JSON(配置)         │
└─────────────────────────────────────────┘
```

### 核心服务

- **Web服务** (`web_server.py:8008`) - FastAPI + API路由 + WebSocket
- **消息采集** (`message_collector.py`) - Telegram实时监听 + 历史采集
- **消息调度** (`message_scheduler.py`) - 自动转发 + 数据清理

### 数据存储

- **Redis** - 消息数据、会话管理、分布式锁
- **JSON** - 系统配置、管理员数据、频道配置
- **路径统一** - 所有路径使用`PathConfig`类管理

## 🛠️ 开发环境

### 启动命令

```bash
# 开发模式（推荐）
./dev.sh                    # 启动所有服务
./dev.sh web               # 仅启动Web服务
./dev.sh web scheduler     # 启动指定服务
./dev.sh --status          # 快速查看状态

# 系统管理
./start.sh                 # 生产环境启动
./stop.sh                  # 停止所有服务
./restart.sh               # 完整重启
```

### 访问地址

- **前端页面**：`http://localhost:8080/static/xxx.html`
- **API接口**：`http://localhost:8008/api/*`
- **管理员登录**：`http://localhost:8080/static/login.html` (admin/admin123)
- **WebSocket**：`ws://localhost:8008/ws`

### 技术栈

- **后端**：Python 3.11+ + FastAPI + Redis + Telethon
- **前端**：Vue.js 3 + 原生HTML/CSS/JS + Axios
- **存储**：Redis + JSON + fcntl文件锁
- **部署**：本地Python服务

## 📁 项目结构

```
telegram_channel_bot/
├── app/                   # 应用代码
│   ├── api/              # API路由层
│   ├── core/             # 核心配置
│   ├── services/         # 业务逻辑层
│   ├── storage/          # 存储层
│   ├── telegram/         # Telegram相关
│   └── utils/            # 工具函数
├── static/               # 前端文件
├── data/                 # 数据存储
│   ├── config/          # 配置文件
│   ├── training/        # 训练数据
│   └── backups/         # 备份文件
├── tools/                # 工具脚本
├── logs/                 # 日志文件
├── temp_media/           # 临时媒体文件
├── web_server.py         # Web服务器
├── message_collector.py  # 消息采集服务
├── message_scheduler.py  # 消息调度服务
└── dev_supervisor.py     # 进程管理器
```

## 🌐 API开发规范

### 端点管理

**🚨 严禁硬编码API端点！** 所有API端点必须在`static/assets/js/config/api-endpoints.js`中定义。

```javascript
// ✅ 正确方式
import API from './config/api-endpoints.js';
const response = await axios.get(API.messages.list);

// ❌ 错误方式
const response = await axios.get('/api/messages/');
```

### 路由规范

- **所有API路由**：`app/api/`目录下，按功能模块组织
- **API路径**：使用kebab-case (`/api/batch-approve`)
- **JSON字段**：使用snake_case (`{"message_id": "123"}`)

### 前端规范

- **🚨 严禁Element Plus**：项目已完全移除，禁止重新引入
- **必须使用SimpleUI**：`SimpleUI.showMessage()`、`SimpleUI.confirm()`
- **代码分离**：严格禁止HTML内联JavaScript和CSS
- **路径引用**：统一使用PathConfig类，禁止硬编码

## 💾 存储和配置

### 路径配置

```python
from app.core.path_config import PathConfig

# 配置文件
PathConfig.SYSTEM_CONFIG_FILE      # data/config/system.json
PathConfig.CHANNELS_CONFIG_FILE    # data/config/channels.json
PathConfig.AD_KEYWORDS_FILE        # data/training/ad_keywords.json

# 目录
PathConfig.BACKUP_DIR              # data/backups/
PathConfig.TEMP_MEDIA_DIR          # temp_media/
```

### 配置管理

- **系统配置**：`data/config/system.json`
- **频道配置**：`data/config/channels.json`
- **管理员数据**：`data/config/admins.json`
- **训练数据**：`data/training/`目录

## 🧹 开发规范

### 文件管理

- **根目录清洁**：只保留核心文件，禁止临时文件
- **测试文件**：放在`tools/testing/`，用完删除
- **禁止备份文件**：使用git版本控制，不要.bak文件
- **无痕删除**：删除内容时不留原内容注释

### 代码规范

- **Python**：遵循PEP 8，snake_case命名
- **前端**：Vue.js规范，camelCase变量，kebab-case CSS类
- **文件大小**：超过500行立即重构拆分
- **日志输出**：最小化控制台噪音，只保留错误和警告

### 命名规范速查

| 类型 | 规范 | 示例 |
|-----|------|------|
| Python文件 | snake_case | `message_processor.py` |
| Python类 | PascalCase | `MessageProcessor` |
| Python函数 | snake_case | `process_message()` |
| API路径 | kebab-case | `/api/batch-approve` |
| CSS类 | kebab-case | `.message-card` |
| JS变量 | camelCase | `messageList` |

## 🔧 常用操作

### Git提交

```bash
# 智能分析提交（推荐）
python3 tools/git/auto_commit.py

# 快速提交
./tools/git/commit.sh fix "修复问题"
./tools/git/commit.sh feat "新功能"
```

### 服务管理

```bash
# 查看状态
./dev.sh --status          # 0.05秒快速状态查看
curl localhost:8008/api/health  # API健康检查

# 重启特定服务
./dev.sh web               # 只重启Web服务
./dev.sh collector         # 只重启采集服务
```

### 故障排查

```bash
# 1. 检查服务状态
./dev.sh --status

# 2. 查看日志
tail -n 50 logs/app.log

# 3. 检查Redis
redis-cli ping

# 4. 验证配置
cat data/config/system.json

# 5. 重启服务
./restart.sh
```

## 📋 快速参考

### 重要文件位置

- **API端点配置**：`static/assets/js/config/api-endpoints.js`
- **路径配置**：`app/core/path_config.py`
- **系统配置**：`data/config/system.json`
- **启动脚本**：`dev.sh`、`start.sh`、`stop.sh`
- **Git工具**：`tools/git/auto_commit.py`

### 端口配置

- **8080** - 前端访问端口
- **8008** - API服务端口
- **6379** - Redis服务端口

### 核心API模块

- **消息管理**：`/api/messages/*`
- **配置管理**：`/api/config/*`
- **训练数据**：`/api/training/*`
- **系统监控**：`/api/health`、`/api/stats/*`
- **管理功能**：`/api/admin/*`

## 🚨 重要提醒

- **API端点管理**：严格禁止硬编码，必须使用配置文件
- **路径管理**：统一使用PathConfig类，禁止硬编码路径
- **代码简洁**：超过500行立即重构，遵循Linus简化原则
- **兼容性**：任何破坏现有功能的改动都是bug
- **测试验证**：主动测试，确保代码质量

---

**文档版本**：2.0 (精简版)
**更新时间**：2025-09-18
**核心理念**：实用、简洁、可维护