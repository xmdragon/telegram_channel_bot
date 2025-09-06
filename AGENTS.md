# Repository Guidelines（仓库协作指南）

## 项目结构与模块组织
- `app/api`: FastAPI 路由与 WebSocket 端点。
- `app/services`: 核心业务（过滤器、处理器、调度器）。
- `app/telegram`: Telethon Bot/Client 集成。
- `app/storage`: Redis 访问与管理器。
- `app/core`: 配置、日志、路径与 URL 工具。
- 入口：`main.py`（Web API）、`telegram_collector.py`（采集）、`message_scheduler.py`（调度）。
- 资源与文档：`static/`、`docs/`；测试位于 `tests/`（如 `tests/test_filter_integration.py`）。

## 构建、测试与本地开发命令
- 环境准备：`python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- 推荐开发：`./dev.sh` 或 `./dev.sh web|collector|processor|scheduler`（自动管理 Redis 与服务，支持热重载）。
- 直接运行 API：`uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- 仅启动依赖：`docker compose up -d redis`
- 运行测试：`pytest -q` 或 `pytest tests/test_filter_integration.py -q`

## 代码风格与命名约定
- Python 3.11+，PEP 8，4 空格缩进，优先使用类型标注。
- 命名：模块/函数/变量 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE_CASE`。
- 导入顺序：标准库 → 三方库 → 本地；避免循环引用（Telethon 类型需置于模块顶部）。
- 格式化/静态检查（本地执行）：`black app/`、`isort app/`、`flake8 app/`；日志通过 `app/core/logging_config.py`。

## 测试规范
- 使用 pytest 与 `unittest.mock`；支持异步测试（参考 `tests/test_filter_integration.py`）。
- 测试放在 `tests/`，文件名 `test_*.py`；类 `Test*`，函数 `test_*`。
- 定向执行：`pytest -k filter -q`；测试需确定性，外部 I/O（Telegram/Redis）请 Mock。

## Commit 与 Pull Request 规范
- 提交格式遵循历史：`:emoji: type: 摘要`（示例：`✨ feat: 优化重复检测 Early-Stop`、`🐛 fix: 修复 Redis 索引不一致`）。
- Commit 应聚焦、简洁、祈使语；关联 Issue 用 `#123`。
- PR 需包含：变更说明、关联问题、复现与验证步骤、必要的日志/截图、简要测试计划。

## 安全与配置提示
- 使用 `.env` 管理配置（如 `REDIS_URL`、`BASE_URL`、`API_URL`、AI 开关）；勿提交敏感信息（生产通过 compose 挂载）。
- Telegram 凭证通过 Web 流程绑定，避免将 Token/ID 写入代码。
- 启动采集/调度前确保 Redis 可用，避免硬编码 URL，优先使用 `app/core/url_config.py`。
