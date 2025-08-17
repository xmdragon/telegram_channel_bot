# 命名规范 - 快速参考卡

> 🚀 **一页纸搞定所有命名规范** - 打印出来贴在工位上！

## 📋 核心记忆口诀

| 语言/类型 | 规范 | 口诀 |
|-----------|------|------|
| **Python文件** | snake_case | 蛇行小写，下划线连接 |
| **Python类** | PascalCase | 每词大写，紧密相连 |
| **Python函数** | snake_case | 蛇行小写，动词开头 |
| **Python常量** | UPPER_SNAKE_CASE | 全大写，下划线分隔 |
| **API路径** | kebab-case | 小写字母，短横连接 |
| **JSON字段** | snake_case | 蛇行小写，数据字段 |
| **CSS类** | kebab-case | 短横小写，样式命名 |
| **JS变量** | camelCase | 驼峰小写，首词小写 |
| **Vue组件** | PascalCase | 每词大写，组件命名 |

---

## 🎯 Python速查表

### 基础规范
```python
# 文件名
message_processor.py           ✅
telegram_collector.py         ✅

# 类名  
class MessageProcessor:        ✅
class TelegramBot:             ✅

# 函数/方法
def process_message():         ✅
def get_channel_config():      ✅
async def collect_messages():  ✅

# 变量
message_id = "123"             ✅
channel_list = []              ✅
is_active = True               ✅

# 常量
MAX_RETRY_COUNT = 3            ✅
API_BASE_URL = "..."           ✅
DEFAULT_PAGE_SIZE = 20         ✅

# 私有成员
def _internal_method():        ✅
self._protected_attr = ...     ✅
```

### 常见错误
```python
MessageProcessor.py           ❌ 文件名不用PascalCase
class message_processor:      ❌ 类名不用snake_case  
def ProcessMessage():         ❌ 函数名不用PascalCase
messageId = "123"            ❌ 变量不用camelCase
max_retry_count = 3          ❌ 常量不用snake_case
```

---

## 🌐 API速查表

### REST风格
```python
# 路径 (kebab-case)
GET /api/messages              ✅
POST /api/batch-approve        ✅  
GET /api/channel-config        ✅
PUT /api/user-settings         ✅

# 查询参数 (snake_case)
?page=1&page_size=20           ✅
?sort_by=created_at&order=desc ✅
?filter_by=status&channel_id=123 ✅
```

### JSON格式
```json
{
  "message_id": "123",          ✅
  "channel_info": {             ✅
    "channel_name": "测试",
    "is_active": true
  },
  "created_at": "2025-08-17"    ✅
}
```

### 常见错误
```python
/api/getMessage               ❌ 应该用动词+kebab-case
/api/message_list             ❌ 应该用kebab-case
?pageSize=20                  ❌ 应该用snake_case
{"messageId": "123"}          ❌ 应该用snake_case
```

---

## 🎨 前端速查表

### HTML文件
```html
message-manager.html          ✅
channel-config.html           ✅  
user-login.html               ✅
```

### CSS类名
```css
.message-card                 ✅
.message-card__header         ✅ (BEM)
.message-card--approved       ✅ (BEM)
.btn-primary                  ✅
.form-input                   ✅
```

### JavaScript
```javascript
// 变量 (camelCase)
const messageList = [];       ✅
let isLoading = false;        ✅
const selectedChannelId = ""; ✅

// 常量 (UPPER_SNAKE_CASE)  
const API_BASE_URL = "...";   ✅
const MAX_RETRY_COUNT = 3;    ✅

// 函数 (camelCase)
function processMessage() {}  ✅
async function fetchData() {} ✅
```

### Vue组件
```javascript
// 组件名 (PascalCase)
export default {
  name: 'MessageRenderer'     ✅
}

// 使用
<MessageRenderer />           ✅
<ChannelSelector />           ✅
```

---

## 💾 存储速查表

### Redis键
```python
# 格式: namespace:type:id:field
"telegram:messages:123:content"    ✅
"telegram:channels:456:config"     ✅
"session:user:789:data"            ✅
"cache:api:messages:list"          ✅
```

### JSON配置
```json
{
  "telegram": {
    "api_id": 12345,              ✅
    "session_string": "..."       ✅
  },
  "channels": {
    "source_channels": [],        ✅
    "target_channel_id": "-123"   ✅
  }
}
```

---

## 📁 文件组织速查

### 目录结构
```
app/
├── api/           # API路由层
├── services/      # 业务逻辑层  
├── storage/       # 存储层
├── telegram/      # Telegram相关
└── utils/         # 工具函数

tools/
├── git/           # Git工具
├── admin/         # 管理工具
├── testing/       # 测试脚本 (临时)
├── maintenance/   # 维护工具
└── utils/         # 通用工具
```

### 文件归类
| 文件类型 | 位置 |
|---------|------|
| 业务代码 | `app/` |
| 工具脚本 | `tools/` |
| 测试文件 | `tools/testing/` |
| 配置文件 | `data/config/` |
| 静态资源 | `static/` |
| 文档 | `docs/` |

---

## 🔧 Git速查表

### 提交类型
```bash
feat(api): 添加消息批量审核功能    ✅
fix(filter): 修复广告检测问题      ✅  
docs(readme): 更新安装说明        ✅
refactor(storage): 重构存储层      ✅
style(css): 格式化样式代码        ✅
```

### 分支命名
```bash
feature/message-batch-approval    ✅
fix/redis-connection-timeout      ✅
hotfix/critical-security-patch    ✅
```

---

## ⚡ 常用检查命令

### Python代码检查
```bash
# 格式检查
black --check app/
flake8 app/
pylint app/

# 自动格式化
black app/
isort app/
```

### JavaScript检查
```bash
# 格式检查
eslint static/assets/js/
prettier --check static/

# 自动格式化  
eslint --fix static/assets/js/
prettier --write static/
```

---

## 🚨 红线规则 (绝对不能犯)

1. **❌ 根目录放测试文件** - 必须放在 `tools/testing/`
2. **❌ API路径用snake_case** - 必须用 `kebab-case`
3. **❌ Python类用snake_case** - 必须用 `PascalCase`  
4. **❌ 混用命名风格** - 同一类型保持一致
5. **❌ 硬编码文件路径** - 必须用 `PathConfig`

---

## 🎯 一分钟记忆法

**Python**: 🐍 **snake_case** (文件、函数、变量) + 🐪 **PascalCase** (类) + 📢 **UPPER_SNAKE_CASE** (常量)

**API**: 🔗 **kebab-case** (路径) + 🐍 **snake_case** (参数、JSON)

**前端**: 🔗 **kebab-case** (CSS、HTML) + 🐪 **camelCase** (JS变量) + 🐪 **PascalCase** (Vue组件)

**存储**: 🔗 **namespace:type:id** (Redis) + 🐍 **snake_case** (JSON字段)

---

## 📞 需要帮助？

- 📖 **详细规范**: [NAMING_CONVENTIONS.md](./NAMING_CONVENTIONS.md)
- 🏗️ **系统架构**: [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)  
- 📝 **开发指南**: [../CLAUDE.md](../CLAUDE.md)

---

*💡 **提示**: 打印此页面贴在显示器旁，随时查阅！*

*📅 最后更新: 2025-08-17 | 🤖 维护者: Claude*