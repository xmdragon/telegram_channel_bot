# Telegram 消息审核系统 - 配置管理指南

## 概述

本系统提供了一个完整的前端配置管理界面，支持所有设置项的前端维护，包括：

- 📺 **频道监听管理**：添加/移除监听频道，设置频道状态
- 👥 **账号采集管理**：配置账号采集功能，管理黑白名单
- 🔍 **广告过滤管理**：配置两类关键词过滤（文中过滤和行中过滤）
- 📱 **Telegram 配置**：API 凭据和连接设置
- 🔧 **系统配置**：高级系统参数设置

## 快速开始

### 1. 初始化系统

```bash
# 初始化数据库和默认配置
python init_config.py
```

### 2. 启动系统

```bash
# 启动 Web 服务
python main.py
```

### 3. 访问配置管理界面

打开浏览器访问：`http://localhost:8000/config`

## 配置管理功能详解

### 📱 Telegram 配置

配置 Telegram API 凭据：

- **API ID**：从 https://my.telegram.org 获取
- **API Hash**：从 https://my.telegram.org 获取  
- **Phone Number**：格式为 +8613800138000

### 📺 频道监听管理

#### 添加监听频道
1. 在"频道监听"标签页中
2. 输入频道ID或用户名
3. 可选：输入频道显示名称
4. 点击"添加频道"

#### 管理频道状态
- 使用开关控制频道的启用/禁用状态
- 可以随时移除不需要的频道

#### 基础配置
- **审核群ID**：消息审核群组的ID
- **目标频道ID**：转发消息的目标频道ID

### 👥 账号采集管理

#### 基础设置
- **启用账号采集**：是否开启账号采集功能
- **自动采集**：是否自动采集新账号

#### 白名单管理
- 添加账号到白名单（只采集这些账号）
- 管理白名单账号列表

#### 黑名单管理  
- 添加账号到黑名单（不采集这些账号）
- 管理黑名单账号列表

### 🔍 广告过滤管理

#### 基础设置
- **启用关键词过滤**：是否启用关键词过滤功能
- **启用行过滤**：是否启用行过滤功能
- **自动过滤广告**：是否自动过滤广告消息
- **自动转发延迟**：自动转发延迟时间（秒）

#### 文中过滤关键词
- 消息内容包含这些关键词时过滤整条消息
- 支持添加/删除关键词
- 预设了常见的广告关键词

#### 行中过滤关键词
- 消息行包含这些关键词时过滤整行
- 支持添加/删除关键词
- 预设了常见的联系方式关键词

### 🔧 系统配置

#### 高级设置
- **系统密钥**：用于加密和认证
- **数据库URL**：数据库连接地址
- **Redis URL**：Redis连接地址

#### 配置管理
- **重新加载配置**：重新加载所有配置
- **重置所有配置**：重置为默认值
- **导出配置**：导出当前配置到JSON文件
- **导入配置**：从JSON文件导入配置

## 关键词过滤说明

### 文中过滤关键词
当消息内容包含这些关键词时，整条消息会被过滤掉。

**常见关键词示例：**
- 广告、推广、代理
- 加微信、联系方式
- 优惠、折扣、限时
- 抢购、秒杀、代理

### 行中过滤关键词
当消息的某一行包含这些关键词时，该行会被过滤掉，其他行保留。

**常见关键词示例：**
- 联系QQ、联系微信
- QQ群、微信群
- QQ:、微信:
- 各种联系方式关键词

## API 接口说明

### 频道管理 API

```bash
# 添加频道
POST /api/config/channels/add
{
  "channel_id": "频道ID",
  "channel_name": "显示名称"
}

# 移除频道
DELETE /api/config/channels/{channel_id}

# 更新频道状态
PUT /api/config/channels/{channel_id}/status
{
  "enabled": true
}
```

### 关键词管理 API

```bash
# 添加文中关键词
POST /api/config/keywords/text/add
{
  "keyword": "关键词"
}

# 移除文中关键词
DELETE /api/config/keywords/text/{keyword}

# 添加行中关键词
POST /api/config/keywords/line/add
{
  "keyword": "关键词"
}

# 移除行中关键词
DELETE /api/config/keywords/line/{keyword}
```

### 账号管理 API

```bash
# 添加到白名单
POST /api/config/accounts/whitelist/add
{
  "account": "账号ID"
}

# 从白名单移除
DELETE /api/config/accounts/whitelist/{account}

# 添加到黑名单
POST /api/config/accounts/blacklist/add
{
  "account": "账号ID"
}

# 从黑名单移除
DELETE /api/config/accounts/blacklist/{account}
```

## 配置数据结构

### 频道配置
```json
{
  "channels.source_channels": ["频道ID1", "频道ID2"],
  "channels.channel_names": {
    "频道ID1": "显示名称1",
    "频道ID2": "显示名称2"
  },
  "channels.channel_status": {
    "频道ID1": true,
    "频道ID2": false
  }
}
```

### 过滤配置
```json
{
  "filter.ad_keywords_text": ["广告", "推广", "代理"],
  "filter.ad_keywords_line": ["联系QQ", "联系微信", "QQ群"],
  "review.enable_keyword_filter": true,
  "review.enable_line_filter": true
}
```

### 账号配置
```json
{
  "accounts.collect_accounts": true,
  "accounts.auto_collect": true,
  "accounts.account_whitelist": ["账号1", "账号2"],
  "accounts.account_blacklist": ["账号3", "账号4"]
}
```

## 最佳实践

### 1. 关键词配置
- 定期更新关键词列表
- 根据实际需求调整过滤规则
- 避免过于宽泛的关键词

### 2. 频道管理
- 定期检查频道状态
- 及时移除无效频道
- 合理设置频道显示名称

### 3. 账号管理
- 维护准确的黑白名单
- 定期清理无效账号
- 根据业务需求调整采集策略

### 4. 系统维护
- 定期备份配置
- 监控系统状态
- 及时更新配置

## 故障排除

### 常见问题

1. **配置不生效**
   - 检查是否点击了"保存"按钮
   - 尝试"重新加载配置"
   - 检查数据库连接

2. **关键词过滤不工作**
   - 确认启用了关键词过滤功能
   - 检查关键词是否正确添加
   - 查看系统日志

3. **频道监听失败**
   - 检查频道ID是否正确
   - 确认频道状态是否启用
   - 验证Telegram API配置

4. **账号采集异常**
   - 检查黑白名单配置
   - 确认账号采集功能已启用
   - 查看采集日志

### 日志查看

```bash
# 查看系统日志
tail -f logs/system.log

# 查看错误日志
tail -f logs/error.log
```

## 技术支持

如果遇到问题，请：

1. 查看系统日志
2. 检查配置是否正确
3. 确认网络连接正常
4. 联系技术支持

---

**版本：** v2.0  
**更新时间：** 2024年12月  
**作者：** Telegram 消息审核系统团队 