# SQLAlchemy移除后需要更新的文件清单

## 已完成的任务
- ✅ 备份 `app/core/database.py` 为 `app/core/database.py.backup`
- ✅ 从 `requirements.txt` 移除以下依赖：
  - sqlalchemy>=2.0.25
  - alembic==1.12.1
  - aiosqlite==0.19.0
  - psycopg[binary]==3.2.3
  - asyncpg==0.30.0
  - greenlet>=3.0.0
- ✅ 删除 `app/core/database.py` 文件
- ✅ 更新 `main.py`：
  - 移除 `from app.core.database import init_db`
  - 添加 Redis 客户端初始化
  - 添加认证服务初始化

## 仍需更新的文件

### 核心服务文件 (app/services/)
- `channel_manager.py` - 需要替换 AsyncSessionLocal, Channel
- `visual_similarity.py` - 需要替换 AsyncSessionLocal, Message
- `history_collector.py` - 需要替换 AsyncSessionLocal, Message
- `duplicate_detector.py` - 需要替换 AsyncSessionLocal, Message
- `unified_message_processor.py` - 需要替换 AsyncSessionLocal, Message
- `message_deduplicator.py` - 需要替换 AsyncSessionLocal, Message
- `scheduler.py` - 需要替换 AsyncSessionLocal, Message
- `channel_id_resolver.py` - 需要替换 AsyncSessionLocal, Channel
- `message_grouper.py` - 需要替换 AsyncSessionLocal, Message
- `startup_checker.py` - 需要替换 AsyncSessionLocal, Channel
- `adaptive_learning.py` - 需要替换 AsyncSessionLocal, Message
- `system_monitor.py` - 需要替换 AsyncSessionLocal, Message

### API文件 (app/api/)
- `training.py` - 需要替换 get_db
- `system.py` - 需要替换 AsyncSessionLocal, Message, Channel
- `admin.py` - 需要替换 get_db, Channel, AsyncSessionLocal

### Telegram模块 (app/telegram/)
- `history_collector.py` - 需要替换 AsyncSessionLocal, Message, Channel
- `message_forwarder.py` - 需要替换 Message, Channel, AsyncSessionLocal
- `bot_backup.py` - 需要替换 AsyncSessionLocal, Message
- `bot.py` - 需要替换 AsyncSessionLocal, Message

### 工具脚本
- `init_db.py` - 需要完全重写以使用新的JSON/Redis存储
- `manual_train.py` - 需要替换 get_db, Message
- `batch_refilter.py` - 需要替换 get_db, Message
- `check_recent_messages.py` - 需要替换 get_db, Message
- `refilter_test.py` - 需要替换 get_db, Message
- `backup_permissions.py` - 需要替换相关模型
- `batch_reprocess.py` - 需要替换 AsyncSessionLocal, Message
- `export_config.py` - 需要替换 AsyncSessionLocal, SystemConfig, Channel
- `import_config.py` - 需要替换 AsyncSessionLocal, SystemConfig, Channel
- 以及其他30多个工具脚本

## 建议的替换方案

### 1. 数据模型
创建新的数据模型文件 `app/models/` 来定义数据结构（使用Pydantic）

### 2. 存储层
- 使用Redis作为主要数据存储
- 使用JSON文件作为备份存储
- 创建统一的数据访问接口

### 3. 会话管理
创建新的会话管理器来替换 AsyncSessionLocal

## 注意事项
由于涉及的文件数量庞大（47个文件），建议：
1. 先确保新的存储系统已经完整实现
2. 分批次更新文件，按重要性优先级处理
3. 保留原有的backup文件以防回滚需要