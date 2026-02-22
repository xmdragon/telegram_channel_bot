# CLAUDE.md

Telegram消息采集审核系统 - Python FastAPI + Redis + Telethon

## 称谓

称呼用户为"哥"。

## 设计原则

- 消除特殊情况，简化分支逻辑
- 不破坏现有功能（Never break userspace）
- 实用主义，拒绝过度设计
- 函数≤30行，缩进≤3层，文件≤500行

## 硬性禁令

- **禁止硬编码API端点** - 前端必须用 `static/assets/js/config/api-endpoints.js`
- **禁止硬编码路径** - 后端必须用 `app/core/path_config.py` 的 PathConfig
- **禁止Element Plus** - 使用 SimpleUI
- **禁止HTML内联JS/CSS** - 代码分离
- **禁止根目录临时文件和.bak文件**

## 架构

```
服务(Supervisor管理):
  web_server.py:8008      - FastAPI API + WebSocket
  message_collector.py    - Telethon消息采集
  message_scheduler.py    - 自动转发 + 清理

存储: Redis(消息) + JSON(配置)
前端: Vue.js 3 + 原生JS, 端口8080
```

## 关键路径

| 用途 | 路径 |
|------|------|
| API端点配置 | `static/assets/js/config/api-endpoints.js` |
| 路径配置 | `app/core/path_config.py` |
| API路由 | `app/api/` |
| 系统配置 | `data/config/system.json` |
| 频道配置 | `data/config/channels.json` |
| 服务管理 | `supervisorctl -c config/supervisord.conf` |

## 命名规范

API路径: kebab-case, JSON字段: snake_case, JS变量: camelCase, Python: PEP 8

## 提交前检查

```bash
grep -r "localhost:8008" . --include="*.py" --include="*.js" --include="*.html"
grep -r '"/api/' static/ --include="*.js" | grep -v api-endpoints.js
```

发现硬编码即为BUG，必须修复。
