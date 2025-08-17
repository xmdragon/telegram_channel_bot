# Telegram消息采集审核系统 - 命名规范文档

## 目录
1. [Python代码规范](#1-python代码规范)
2. [目录组织规范](#2-目录组织规范)
3. [API接口规范](#3-api接口规范)
4. [前端开发规范](#4-前端开发规范)
5. [数据库规范](#5-数据库规范)
6. [Git提交规范](#6-git提交规范)
7. [文档规范](#7-文档规范)
8. [常见错误案例](#8-常见错误案例)
9. [重构建议](#9-重构建议)
10. [实施计划](#10-实施计划)

---

## 1. Python代码规范

### 1.1 文件命名
- **规范**: 使用 `snake_case`，全小写，单词间用下划线分隔
- **文件扩展名**: `.py`
- **长度限制**: 建议不超过30个字符

```python
# ✅ 正确示例
message_processor.py
telegram_collector.py
unified_filter_engine.py
config_manager.py

# ❌ 错误示例
MessageProcessor.py       # 使用了PascalCase
message-processor.py      # 使用了kebab-case
messageprocessor.py       # 缺少分隔符
```

### 1.2 类命名 (PascalCase)
- **规范**: 每个单词首字母大写，无分隔符
- **长度**: 建议2-4个单词
- **语义**: 名词或名词短语

```python
# ✅ 正确示例
class MessageProcessor:
    pass

class TelegramCollector:
    pass

class UnifiedFilterEngine:
    pass

class RedisStore:
    pass

# ❌ 错误示例
class message_processor:    # 使用了snake_case
class Message_Processor:    # 混合了下划线
class messageProcessor:     # 使用了camelCase
```

### 1.3 函数和方法命名 (snake_case)
- **规范**: 全小写，单词间用下划线分隔
- **语义**: 动词或动词短语，表达功能
- **特殊前缀**: `get_`、`set_`、`is_`、`has_`、`create_`、`delete_`

```python
# ✅ 正确示例
def process_message(self, message):
    pass

def get_channel_config(self):
    pass

def is_advertisement(self, content):
    pass

def has_valid_signature(self):
    pass

async def collect_messages(self):
    pass

# ❌ 错误示例
def ProcessMessage():         # 使用了PascalCase
def get-channel-config():     # 使用了kebab-case
def isAdvertisement():        # 使用了camelCase
```

### 1.4 变量命名 (snake_case)
- **规范**: 全小写，单词间用下划线分隔
- **语义**: 名词，描述存储的数据
- **布尔变量**: 使用 `is_`、`has_`、`can_`、`should_` 前缀

```python
# ✅ 正确示例
message_id = "123"
channel_list = []
user_count = 0
is_active = True
has_permission = False
can_edit = True

# ❌ 错误示例
messageId = "123"           # 使用了camelCase
MessageId = "123"           # 使用了PascalCase
message-id = "123"          # 使用了kebab-case
msg_id = "123"              # 过度缩写
```

### 1.5 常量命名 (UPPER_SNAKE_CASE)
- **规范**: 全大写，单词间用下划线分隔
- **位置**: 模块顶部或专门的常量文件
- **语义**: 不变的值

```python
# ✅ 正确示例
MAX_RETRY_COUNT = 3
DEFAULT_PAGE_SIZE = 20
API_BASE_URL = "http://localhost:8000"
TELEGRAM_SESSION_TIMEOUT = 3600
ERROR_MESSAGES = {
    "INVALID_TOKEN": "Token无效",
    "RATE_LIMITED": "请求过于频繁"
}

# ❌ 错误示例
max_retry_count = 3         # 使用了snake_case
MaxRetryCount = 3           # 使用了PascalCase
MAX-RETRY-COUNT = 3         # 使用了kebab-case
```

### 1.6 私有成员命名
- **私有方法/属性**: 单下划线前缀 `_`
- **强私有**: 双下划线前缀 `__`（触发名称改编）
- **特殊方法**: 双下划线包围 `__init__`

```python
class MessageProcessor:
    def __init__(self):
        self.public_attr = "公开属性"
        self._protected_attr = "受保护属性"
        self.__private_attr = "私有属性"
    
    def public_method(self):
        """公开方法"""
        pass
    
    def _protected_method(self):
        """受保护方法，子类可访问"""
        pass
    
    def __private_method(self):
        """私有方法，触发名称改编"""
        pass

# ✅ 正确示例
def _validate_config(self):
    pass

def _internal_cleanup(self):
    pass

# ❌ 错误示例
def __public_method(self):    # 误用强私有
def private_method(self):     # 缺少下划线前缀
```

---

## 2. 目录组织规范

### 2.1 项目根目录结构
```
telegram_channel_bot/
├── app/                    # 应用核心代码
├── data/                   # 数据存储目录
├── docs/                   # 项目文档
├── logs/                   # 日志文件
├── static/                 # 静态资源
├── tools/                  # 工具脚本
├── temp_media/             # 临时媒体文件
├── venv/                   # Python虚拟环境
├── main.py                 # 应用入口
├── CLAUDE.md               # Claude工作指导
├── README.md               # 项目说明
├── requirements.txt        # Python依赖
├── docker-compose.yml      # Docker配置
├── Dockerfile              # Docker镜像
├── dev.sh                  # 开发脚本
├── start.sh                # 启动脚本
├── stop.sh                 # 停止脚本
└── restart.sh              # 重启脚本
```

### 2.2 app/ 目录结构（分层架构）
```
app/
├── __init__.py
├── api/                    # API路由层
│   ├── __init__.py
│   ├── messages.py         # 消息相关API
│   ├── admin.py            # 管理功能API
│   ├── config.py           # 配置管理API
│   ├── auth.py             # 认证API
│   └── system.py           # 系统API
├── core/                   # 核心配置
│   ├── __init__.py
│   ├── config.py           # 应用配置
│   └── exceptions.py       # 自定义异常
├── services/               # 业务逻辑层
│   ├── __init__.py
│   ├── filters/            # 过滤器子模块
│   ├── message_processor.py
│   ├── config_manager.py
│   └── channel_manager.py
├── storage/                # 存储层
│   ├── __init__.py
│   ├── redis_store.py
│   └── json_store.py
├── telegram/               # Telegram相关
│   ├── __init__.py
│   ├── bot.py
│   ├── auth.py
│   └── client_manager.py
└── utils/                  # 工具函数
    ├── __init__.py
    ├── logger.py
    └── helpers.py
```

### 2.3 tools/ 目录分类
```
tools/
├── git/                    # Git相关工具
├── admin/                  # 管理工具
├── batch/                  # 批量处理脚本
├── debug/                  # 调试工具
├── utils/                  # 通用工具
├── testing/                # 测试脚本（完成后清理）
├── analysis/               # 分析工具
├── maintenance/            # 维护工具
└── data/                   # 数据处理工具
```

### 2.4 文件归类原则
| 文件类型 | 应放置位置 | 说明 |
|---------|------------|------|
| 核心应用代码 | `app/` | 业务逻辑、API、服务 |
| 配置文件 | `data/config/` | JSON配置文件 |
| 日志文件 | `logs/` | 应用日志 |
| 静态资源 | `static/` | HTML、CSS、JS |
| 工具脚本 | `tools/` | 按功能分类到子目录 |
| 测试文件 | `tools/testing/` | 临时测试，完成后删除 |
| 文档 | `docs/` | 项目文档 |
| 临时文件 | `temp_media/` | 临时媒体文件 |

---

## 3. API接口规范

### 3.1 路径命名 (kebab-case)
- **规范**: 全小写，单词间用连字符分隔
- **版本**: 使用 `/api/v1/` 前缀
- **资源**: 使用复数名词
- **操作**: 使用HTTP动词，不在URL中体现

```python
# ✅ 正确示例
GET /api/messages                    # 获取消息列表
POST /api/messages                   # 创建消息
GET /api/messages/{id}               # 获取单个消息
PUT /api/messages/{id}               # 更新消息
DELETE /api/messages/{id}            # 删除消息

GET /api/channel-config              # 获取频道配置
POST /api/batch-approve              # 批量审核
GET /api/system-status               # 系统状态
POST /api/user-login                 # 用户登录

# ❌ 错误示例
GET /api/getMessage                  # 使用了camelCase
GET /api/get_message                 # 使用了snake_case
GET /api/GetMessage                  # 使用了PascalCase
POST /api/messages/create            # 在URL中包含动词
GET /api/message                     # 使用单数而非复数
```

### 3.2 查询参数 (snake_case)
- **规范**: 使用snake_case
- **分页**: `page`、`page_size`、`limit`、`offset`
- **排序**: `sort_by`、`order`
- **过滤**: `filter_by`、`status`、`type`

```python
# ✅ 正确示例
GET /api/messages?page=1&page_size=20
GET /api/messages?sort_by=created_at&order=desc
GET /api/messages?status=pending&channel_id=123
GET /api/messages?filter_by=content&search_term=广告

# ❌ 错误示例
GET /api/messages?pageSize=20        # 使用了camelCase
GET /api/messages?page-size=20       # 使用了kebab-case
GET /api/messages?sortBy=created_at  # 使用了camelCase
```

### 3.3 请求和响应格式 (snake_case)
- **JSON字段**: 使用snake_case
- **嵌套对象**: 保持一致的命名风格
- **数组**: 使用复数名词

```json
// ✅ 正确示例 - 请求体
{
  "message_content": "消息内容",
  "channel_id": "123456789",
  "is_advertisement": false,
  "metadata": {
    "source_channel": "@example",
    "message_type": "text",
    "created_at": "2025-08-17T10:00:00Z"
  },
  "tags": ["news", "important"]
}

// ✅ 正确示例 - 响应体
{
  "status": "success",
  "data": {
    "message_id": "msg_123",
    "content": "消息内容",
    "approval_status": "pending",
    "channel_info": {
      "channel_id": "123456789",
      "channel_name": "示例频道"
    }
  },
  "pagination": {
    "current_page": 1,
    "total_pages": 10,
    "page_size": 20,
    "total_count": 200
  }
}

// ❌ 错误示例
{
  "messageContent": "...",      // 使用了camelCase
  "MessageId": "...",           // 使用了PascalCase
  "message-id": "...",          // 使用了kebab-case
  "channelInfo": {              // 不一致的命名
    "ChannelId": "..."          // 混合使用不同风格
  }
}
```

### 3.4 状态码规范
- **2xx**: 成功
  - `200 OK`: 请求成功
  - `201 Created`: 资源创建成功
  - `204 No Content`: 成功但无返回内容
- **4xx**: 客户端错误
  - `400 Bad Request`: 请求参数错误
  - `401 Unauthorized`: 未认证
  - `403 Forbidden`: 无权限
  - `404 Not Found`: 资源不存在
  - `422 Unprocessable Entity`: 数据验证失败
- **5xx**: 服务器错误
  - `500 Internal Server Error`: 服务器内部错误
  - `503 Service Unavailable`: 服务不可用

---

## 4. 前端开发规范

### 4.1 HTML文件命名
- **规范**: 使用 `snake_case` 或 `kebab-case`
- **语义**: 描述页面功能
- **扩展名**: `.html`

```html
<!-- ✅ 正确示例 -->
message_manager.html
channel_config.html
user_login.html
system_dashboard.html

<!-- 或者使用kebab-case -->
message-manager.html
channel-config.html
user-login.html

<!-- ❌ 错误示例 -->
MessageManager.html          <!-- 使用了PascalCase -->
messageManager.html          <!-- 使用了camelCase -->
msg_mgr.html                 <!-- 过度缩写 -->
```

### 4.2 Vue组件命名 (PascalCase)
- **规范**: 每个单词首字母大写
- **文件名**: 与组件名保持一致
- **语义**: 描述组件功能

```javascript
// ✅ 正确示例
// 文件: MessageRenderer.vue
export default {
  name: 'MessageRenderer',
  // ...
}

// 文件: ChannelSelector.vue
export default {
  name: 'ChannelSelector',
  // ...
}

// 使用组件
<MessageRenderer :message="currentMessage" />
<ChannelSelector @select="onChannelSelect" />

// ❌ 错误示例
// 文件: messageRenderer.vue    // 文件名应该是PascalCase
export default {
  name: 'message-renderer',     // 组件名应该是PascalCase
  // ...
}
```

### 4.3 CSS类命名 (kebab-case)
- **规范**: 全小写，单词间用连字符分隔
- **BEM方法**: `block__element--modifier`
- **语义**: 描述外观或功能

```css
/* ✅ 正确示例 */
.message-card {
  padding: 16px;
}

.message-card__header {
  font-weight: bold;
}

.message-card__content {
  margin: 8px 0;
}

.message-card--approved {
  border-color: green;
}

.message-card--rejected {
  border-color: red;
}

.btn-primary {
  background: #007bff;
}

.form-input {
  border: 1px solid #ccc;
}

/* ❌ 错误示例 */
.messageCard { }              /* 使用了camelCase */
.MessageCard { }              /* 使用了PascalCase */
.message_card { }             /* 使用了snake_case */
.btn_1 { }                    /* 使用数字，语义不明 */
```

### 4.4 JavaScript变量命名 (camelCase)
- **规范**: 第一个单词小写，后续单词首字母大写
- **常量**: 使用 `UPPER_SNAKE_CASE`
- **私有变量**: 使用下划线前缀

```javascript
// ✅ 正确示例
// 变量
const messageList = [];
const currentUser = null;
let isLoading = false;
const selectedChannelId = "123";

// 常量
const API_BASE_URL = 'http://localhost:8000';
const MAX_MESSAGE_LENGTH = 4096;
const ERROR_MESSAGES = {
  NETWORK_ERROR: '网络错误',
  INVALID_INPUT: '输入无效'
};

// 函数
function processMessage(message) {
  return message;
}

function getCurrentUser() {
  return currentUser;
}

async function fetchMessages() {
  // ...
}

// 私有变量/函数
const _internal_cache = new Map();
function _validateInput(input) {
  // ...
}

// ❌ 错误示例
const message_list = [];        // 使用了snake_case
const MessageList = [];         // 使用了PascalCase
const message-list = [];        // 使用了kebab-case
let IsLoading = false;          // 使用了PascalCase
const api_base_url = '...';     // 常量应该全大写
```

### 4.5 静态资源组织
```
static/
├── assets/
│   ├── css/
│   │   ├── main.css
│   │   ├── components.css
│   │   └── utilities.css
│   ├── js/
│   │   ├── main.js
│   │   ├── components/
│   │   │   ├── message-renderer.js
│   │   │   └── channel-selector.js
│   │   └── utils/
│   │       ├── api-client.js
│   │       └── helpers.js
│   └── images/
│       ├── icons/
│       └── logos/
├── login.html
├── dashboard.html
└── config.html
```

---

## 5. 数据库规范

### 5.1 Redis键命名
- **规范**: 使用冒号分隔的层级结构
- **模式**: `namespace:type:identifier:field`
- **小写**: 全部使用小写字母

```python
# ✅ 正确示例
# 消息相关
"telegram:messages:123:content"
"telegram:messages:123:metadata"
"telegram:messages:pending"
"telegram:messages:approved"

# 频道相关
"telegram:channels:456:config"
"telegram:channels:456:stats"
"telegram:channels:list"

# 用户会话
"session:user:789:data"
"session:user:789:expires"

# 系统配置
"system:config:settings"
"system:stats:daily"

# 缓存
"cache:api:messages:list:page_1"
"cache:filter:results:hash_abc123"

# ❌ 错误示例
"TelegramMessages"             # 使用了PascalCase
"telegram_messages_123"        # 使用了下划线
"telegram-messages-123"        # 使用了连字符
"messages/123/content"         # 使用了斜杠
"telegram::messages::123"      # 使用了双冒号
```

### 5.2 JSON配置字段
- **规范**: 使用snake_case
- **嵌套**: 保持一致的命名风格
- **布尔值**: 使用明确的true/false

```json
{
  "telegram": {
    "api_id": 12345,
    "api_hash": "abcdef123456",
    "session_string": "...",
    "bot_token": ""
  },
  "channels": {
    "source_channels": ["@channel1", "@channel2"],
    "target_channel_id": "-123456789",
    "review_group_id": "-987654321"
  },
  "filter": {
    "enabled": true,
    "ad_keywords": ["广告", "推广"],
    "tail_filter_enabled": true,
    "ocr_enabled": false
  },
  "system": {
    "log_level": "INFO",
    "max_message_age_days": 30,
    "cleanup_enabled": true
  }
}
```

---

## 6. Git提交规范

### 6.1 提交类型
- `feat`: 新功能
- `fix`: Bug修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构（不是新功能也不是修复）
- `test`: 测试相关
- `chore`: 构建过程或辅助工具的变动

### 6.2 提交信息格式
```
<type>(<scope>): <description>

<body>

<footer>
```

### 6.3 提交示例
```bash
# ✅ 正确示例
feat(api): 添加消息批量审核功能
fix(filter): 修复广告检测误判问题
docs(readme): 更新安装说明
refactor(storage): 统一Redis键命名规范
style(frontend): 格式化CSS代码
test(processor): 添加消息处理器单元测试
chore(deps): 更新Python依赖版本

# ❌ 错误示例
Add new feature                    # 缺少类型前缀
fix: fix bug                       # 描述不明确
FEAT: new api                      # 类型应该小写
feat(API): add function            # scope应该小写
```

### 6.4 分支命名
- **主分支**: `main`
- **功能分支**: `feature/feature-name`
- **修复分支**: `fix/bug-description`
- **发布分支**: `release/v1.0.0`
- **热修复**: `hotfix/critical-fix`

```bash
# ✅ 正确示例
feature/message-batch-approval
feature/telegram-auth-improvement
fix/redis-connection-timeout
fix/filter-memory-leak
hotfix/critical-security-patch

# ❌ 错误示例
MessageBatchApproval               # 使用了PascalCase
message_batch_approval             # 使用了snake_case
feature-message-batch-approval     # 缺少斜杠分隔
fix_redis_connection               # 使用了下划线
```

---

## 7. 文档规范

### 7.1 文档文件命名
- **规范**: 使用 `UPPER_SNAKE_CASE` 或 `kebab-case`
- **扩展名**: `.md`
- **语义**: 描述文档内容

```markdown
# ✅ 正确示例
README.md
CHANGELOG.md
CONTRIBUTING.md
API_REFERENCE.md
DEPLOYMENT_GUIDE.md
NAMING_CONVENTIONS.md

# 或者使用kebab-case
api-reference.md
deployment-guide.md
user-manual.md

# ❌ 错误示例
readme.md                      # 重要文档应该全大写
apiReference.md                # 使用了camelCase
api_reference.md               # 混合了不同风格
```

### 7.2 文档内部结构
- **标题**: 使用层级结构（#、##、###）
- **代码块**: 指定语言类型
- **链接**: 使用相对路径

```markdown
# ✅ 正确示例
# 项目标题

## 安装指南

### 系统要求
- Python 3.11+
- Redis 6.0+

### 安装步骤
```bash
pip install -r requirements.txt
```

### 配置文件
参见 [配置说明](./CONFIG.md)

## API文档
详细API说明请查看 [API参考](./api/README.md)
```

---

## 8. 常见错误案例

### 8.1 Python命名错误
```python
# ❌ 错误：混合命名风格
class messageProcessor:          # 类名应该用PascalCase
    def GetMessage(self):        # 方法名应该用snake_case
        message_ID = "123"       # 变量名不一致
        return message_ID

# ✅ 正确：统一命名风格
class MessageProcessor:
    def get_message(self):
        message_id = "123"
        return message_id
```

### 8.2 API路径命名错误
```python
# ❌ 错误：不一致的命名
"/api/getMessages"               # 应该用kebab-case和HTTP动词
"/api/message_list"              # 应该用kebab-case
"/api/CreateNewMessage"          # 应该用HTTP POST动词

# ✅ 正确：RESTful命名
"GET /api/messages"              # 获取消息列表
"POST /api/messages"             # 创建新消息
"GET /api/message-templates"     # 获取消息模板
```

### 8.3 前端命名错误
```javascript
// ❌ 错误：不一致的命名
const Message_List = [];         // 应该用camelCase
const MessageCount = 0;          // 应该用camelCase
const is-loading = false;        // 应该用camelCase

// CSS
.Message-Card { }                // 应该用kebab-case
.message_card { }                // 应该用kebab-case

// ✅ 正确：统一命名
const messageList = [];
const messageCount = 0;
const isLoading = false;

// CSS
.message-card { }
.message-card__header { }
```

### 8.4 文件组织错误
```
# ❌ 错误：文件放置位置不当
/test_message_filter.py          # 测试文件在根目录
/backup_bot.py                   # 备份文件在根目录
/temp_script.py                  # 临时脚本在根目录
/debug.py                        # 调试脚本在根目录

# ✅ 正确：按功能分类
/tools/testing/test_message_filter.py
/tools/backup/backup_bot.py
/tools/utils/temp_script.py
/tools/debug/debug_helper.py
```

---

## 9. 重构建议

### 9.1 高优先级（立即修改）
1. **API路径重命名**
   ```python
   # 当前 → 目标
   "/api/batch_approve" → "/api/batch-approve"
   "/api/channel_config" → "/api/channel-config"
   "/api/system_status" → "/api/system-status"
   "/api/user_login" → "/api/user-login"
   ```

2. **常量命名统一**
   ```python
   # 当前 → 目标
   max_retry_count = 3 → MAX_RETRY_COUNT = 3
   api_base_url = "..." → API_BASE_URL = "..."
   default_page_size = 20 → DEFAULT_PAGE_SIZE = 20
   ```

3. **删除测试文件**
   - 清理 `tools/test/` 目录下的所有测试文件
   - 移除 `app/services/filters/` 中的示例文件

### 9.2 中优先级（一周内完成）
1. **合并功能重复的文件**
   ```
   app/services/smart_tail_filter.py → 合并到 semantic_tail_filter.py
   app/services/message_deduplicator.py → 合并到 duplicate_detector.py
   app/services/content_filter_new.py → 合并到 content_filter.py
   ```

2. **整理tools目录**
   - 按功能分类现有工具脚本
   - 删除一次性使用的修复脚本

3. **前端文件重命名**
   ```html
   <!-- 统一使用kebab-case -->
   messageManager.html → message-manager.html
   channelConfig.html → channel-config.html
   userLogin.html → user-login.html
   ```

### 9.3 低优先级（长期改进）
1. **大文件拆分**
   - `app/api/messages.py` (69KB) 拆分为多个小文件
   - `app/services/unified_message_processor.py` 按功能模块拆分

2. **建立自动化检查**
   - 配置 `pylint` 或 `flake8` 检查Python命名
   - 配置 `ESLint` 检查JavaScript命名
   - 使用 `black` 自动格式化代码

3. **文档完善**
   - 为每个模块添加详细的docstring
   - 创建API文档自动生成机制

---

## 10. 实施计划

### 10.1 第一阶段（立即执行）
- [x] 创建命名规范文档
- [x] 清理测试文件和冗余代码
- [ ] 修改API路径命名
- [ ] 统一常量命名

### 10.2 第二阶段（本周内）
- [ ] 重构前端文件命名
- [ ] 合并功能重复的模块
- [ ] 整理tools目录结构
- [ ] 更新所有相关文档

### 10.3 第三阶段（持续改进）
- [ ] 配置代码质量检查工具
- [ ] 建立自动化格式化流程
- [ ] 完善模块文档
- [ ] 定期审查和优化

### 10.4 质量保证
1. **代码审查检查清单**
   - [ ] 命名是否符合规范
   - [ ] 文件是否放在正确位置
   - [ ] API是否遵循RESTful规范
   - [ ] 前端代码是否分离

2. **自动化检查**
   ```bash
   # Python代码检查
   pylint app/
   flake8 app/
   black --check app/

   # JavaScript代码检查
   eslint static/assets/js/
   ```

3. **定期清理**
   - 每周检查并清理临时文件
   - 每月审查工具脚本的必要性
   - 每季度评估命名规范的执行情况

---

## 总结

本命名规范文档建立了统一的代码组织和命名标准，确保项目的可维护性和可读性。所有团队成员都应严格遵循这些规范，并在代码审查中强制执行。

**关键要点**：
- Python遵循PEP 8标准
- API使用RESTful kebab-case命名
- 前端遵循Vue.js最佳实践
- 文件按功能分类组织
- 定期清理和优化代码结构

**快速参考**：详见 [NAMING_QUICK_REFERENCE.md](./NAMING_QUICK_REFERENCE.md)

---

*文档版本: v1.0*  
*最后更新: 2025-08-17*  
*维护者: Claude*