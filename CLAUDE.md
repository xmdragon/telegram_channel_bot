# CLAUDE.md

Claude Code 工作指导文档。

## 重大变更历史

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

### 启动命令
```bash
# 开发模式（推荐）
./dev.sh

# 生产模式
./start.sh
./stop.sh  
./restart.sh
```

### 技术栈
- 后端：Python 3.11 + FastAPI + Redis + JSON + Telethon
- 前端：Vue.js 3 + Element Plus + Axios  
- 认证：JWT + Redis会话管理

### API路由
- `/api/messages` - 消息管理
- `/api/admin` - 管理员功能
- `/api/config` - 配置管理
- `/api/auth` - Telegram认证
- `/api/training` - AI训练数据

### 重要配置
- 管理员登录：`http://localhost:8000/static/login.html` (admin/admin123)
- 静态文件路径：`/static/xxx.html`
- macOS tail命令：`tail -n 20 file.log`

## 🛠️ 开发规范

- Python虚拟环境本地开发，生产环境用Docker
- 使用`python3`而不是`python`
- 使用`docker compose`而不是`docker-compose`
- 前端Vue3 + Element Plus + Axios
- 中文简短回复
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

## 🚨 重要提醒

- Redis和JSON双层存储，禁止删除整个数据库
- 文件锁机制确保数据一致性
- 优先使用API接口修改配置
- 任何批量数据操作需要用户明确授权
- 存储结构修改时必须同步更新相关代码