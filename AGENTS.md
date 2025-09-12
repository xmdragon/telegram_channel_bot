# Repository Guidelines（仓库协作指南）

## 项目结构与模块组织
- `app/api`：FastAPI 路由与 WebSocket；前端 API 端点集中在 `static/assets/js/config/api-endpoints.js`（严禁硬编码）。
- `app/services`：核心业务（过滤器、处理器、调度器）；过滤流水线见 `app/services/filters/*`。
- `app/telegram`：Telethon 集成；注意 Python 3.13 作用域变更，类型导入必须在模块顶部。
- `app/storage`：Redis/JSON 存储与管理；路径统一使用 `app/core/path_config.py`。
- `app/core`：配置、日志、路径、URL 工具；避免硬编码 URL，使用 `app/core/url_config.py`。

## 构建、测试与本地开发
- 环境准备：`python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- 开发模式（推荐）：`./dev.sh` 或 `./dev.sh web|collector|processor|scheduler|--status|--legacy`
  - 端口：前端/Nginx `8080`，后端/FastAPI `8000`；仅依赖可用 `docker compose up -d redis`。
- 直接运行 API：`uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- 测试：`pytest -q`，或 `pytest tests/test_filter_integration.py -q`（异步与集成示例）。

## 代码风格与命名
- Python 3.11+，PEP 8，四空格缩进，优先使用类型标注。
- 命名：模块/函数/变量 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE_CASE`。
- 导入顺序：标准库 → 第三方 → 本地；Telethon 类型必须置于模块顶部；避免循环依赖。
- 本地格式化/检查（建议）：`black app/`、`isort app/`、`flake8 app/`；日志通过 `app/core/logging_config.py`。

## 测试指南
- 框架：pytest + `unittest.mock`；对 Telegram/Redis/网络 I/O 进行 Mock 保持确定性。
- 结构：`tests/test_*.py`，类 `Test*`，函数 `test_*`；可用 `pytest -k filter -q` 定向运行。

## 提交与 PR 规范
- 提交信息遵循历史：`emoji + type: 摘要`（例：`✨ feat: 统一路由管理架构`，`🐛 fix: 修复Redis索引不一致`）。
- PR 需包含：变更说明、关联 Issue、复现与验证步骤、必要日志/截图与简要测试计划。
- 本仓库启用了自定义 pre-commit 钩子（`.git/hooks/pre-commit`）进行语法/导入基础检查；必要时可用 `git commit --no-verify` 跳过。

## 配置与安全
- 使用 `.env` 管理 `REDIS_URL`、`BASE_URL`、`API_URL` 等；生产通过 compose 挂载，切勿提交敏感信息。
- 启动采集/调度前确保 Redis 可用；前端访问 `8080`（Nginx），API 调试 `8000`（FastAPI）。

## 目录约束与工具脚本
- 根目录文档最小化：仅保留 `README.md` 与 `CLAUDE.md`；其余 Markdown 放入 `docs/`。
- 禁止在根目录存放临时/测试/备份文件；不要提交 `.bak`/`.backup`/`*-backup.*`/`*-old.*`。
- 脚本归档到 `tools/` 对应子目录：`git/`、`admin/`、`batch/`、`debug/`、`utils/`、`testing/`、`analysis/`、`maintenance/`。
- 临时/测试脚本放 `tools/testing/`，用完评估是否保留并及时清理。
- 会话结束前检查根目录文件数量，保持根目录整洁与稳定。

## 沟通与语言规范
- 默认全程使用中文回复与撰写文档；除非明确要求，否则不切换到英文。
- 保持命令、文件路径、代码标识符为其英文原文与大小写，不翻译、不音译。
- 开发过程中的提示/日志可保留英文原样（如工具输出），但解释性文字使用中文。
