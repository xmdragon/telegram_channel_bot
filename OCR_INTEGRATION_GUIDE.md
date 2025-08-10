# OCR图片文字提取功能集成指南

## 功能概述

本次集成为Telegram消息采集系统添加了完整的OCR（光学字符识别）功能，能够从图片中提取文字和识别二维码，并将其纳入广告检测流程中。

## 核心功能

### 1. 图片文字提取 (OCR)
- **支持多语言**: 中文简体和英文
- **图像预处理**: 自适应阈值处理提高文字清晰度
- **批量处理**: 支持同时处理多张图片
- **缓存机制**: 基于图片哈希的缓存，避免重复处理

### 2. 二维码识别
- **多种格式**: 支持QR Code等标准二维码格式
- **内容解析**: 自动解码二维码中的URL、文字等信息
- **编码支持**: 支持UTF-8和GBK编码

### 3. 智能广告检测
- **模式匹配**: 30+种广告特征模式，覆盖联系方式、商业信息、赌博内容等
- **综合评分**: 基于文字和二维码内容的多维度评分系统
- **权重调整**: 根据内容组合动态调整广告置信度

## 技术架构

### 核心模块

1. **OCRService** (`app/services/ocr_service.py`)
   - 文字提取和二维码识别
   - 广告内容分析
   - 性能优化和缓存管理

2. **ContentFilter增强** (`app/services/content_filter.py`)
   - 集成OCR功能到消息过滤流程
   - 异步处理确保不阻塞主流程
   - 向后兼容的同步接口

3. **数据库扩展** (`app/core/database.py`)
   - 新增OCR相关字段：ocr_text, qr_codes, ocr_ad_score, ocr_processed
   - JSON格式存储提取的文字和二维码信息

### 依赖库
- `easyocr==1.7.0`: 文字识别核心引擎
- `opencv-python==4.8.1.78`: 图像处理和预处理
- `pyzbar==0.1.9`: 二维码识别

## 使用方式

### 异步接口（推荐）
```python
from app.services.content_filter import content_filter

# 带图片的消息处理
is_ad, filtered_content, filter_reason, ocr_result = await content_filter.filter_message(
    content="消息文字内容",
    channel_id="频道ID",
    message_obj=telegram_message_obj,
    media_files=["/path/to/image1.jpg", "/path/to/image2.png"]
)

# OCR结果包含：
# - texts: 提取的文字列表
# - qr_codes: 二维码信息列表
# - ad_score: 广告分数 (0-100)
# - ad_indicators: 广告特征指标
```

### 同步接口（向后兼容）
```python
# 仅文字处理（不包含OCR）
is_ad, filtered_content, filter_reason = content_filter.filter_message_sync(
    content="消息文字内容",
    channel_id="频道ID"
)
```

## 广告检测逻辑

### 检测优先级（从高到低）

1. **OCR图片广告检测** (30分+)
   - 图片中的联系方式、外部链接
   - 商业信息、赌博内容
   - 二维码中的广告链接

2. **智能尾部广告过滤**
   - AI语义分割检测频道推广尾部

3. **结构化广告检测**
   - 消息按钮和实体中的广告链接

4. **AI文字广告检测**
   - 基于训练样本的语义相似度检测

5. **规则匹配**
   - 传统正则表达式模式匹配

### 广告评分系统

- **文字模式匹配**: 每个匹配加10分
- **外部链接二维码**: 加25分
- **Telegram二维码**: 加5分
- **联系信息二维码**: 加15分
- **多特征组合**: 额外20%权重加成
- **简短文字+广告信息**: 额外50%权重

## 性能优化

### 异步处理
- 使用线程池(ThreadPoolExecutor)处理CPU密集的OCR任务
- 批量处理多张图片，最大并发数限制为2

### 缓存策略
- 基于图片MD5哈希的缓存机制
- LRU缓存清理，最大缓存100个结果
- 避免重复处理相同图片

### 错误处理
- 优雅降级：OCR失败时不影响其他检测
- 详细的错误日志和状态监控
- 超时保护机制

## 数据存储

### Message表新字段
```sql
ALTER TABLE messages ADD COLUMN ocr_text TEXT;          -- JSON格式的提取文字
ALTER TABLE messages ADD COLUMN qr_codes TEXT;          -- JSON格式的二维码信息  
ALTER TABLE messages ADD COLUMN ocr_ad_score INTEGER DEFAULT 0;  -- 广告分数
ALTER TABLE messages ADD COLUMN ocr_processed BOOLEAN DEFAULT FALSE;  -- 是否已处理
```

### 数据格式示例
```json
{
  "ocr_text": ["微信：abc123", "QQ：987654321"],
  "qr_codes": [
    {
      "type": "QRCODE",
      "data": "https://t.me/example",
      "position": {"x": 100, "y": 200, "width": 150, "height": 150}
    }
  ]
}
```

## 部署和配置

### 1. 安装依赖
```bash
# 系统已包含在requirements.txt中
pip install easyocr opencv-python pyzbar
```

### 2. 数据库迁移
```bash
# 启动应用时会自动创建新字段
python3 init_db.py
```

### 3. 验证功能
- OCR服务会在首次调用时自动初始化
- 检查日志确认"OCR服务初始化成功"
- 发送带图片的测试消息验证功能

## 监控和维护

### 性能监控
```python
from app.services.ocr_service import ocr_service

# 获取统计信息
stats = ocr_service.get_stats()
print(f"缓存使用: {stats['cache_size']}/{stats['cache_max_size']}")
print(f"支持语言: {stats['supported_languages']}")
```

### 缓存管理
```python
# 手动清理缓存
ocr_service.clear_cache()
```

## 注意事项

### 兼容性
- 异步接口：完整功能，包含OCR处理
- 同步接口：基础功能，不包含OCR（避免事件循环冲突）
- 旧代码调用方式保持不变

### 资源使用
- OCR处理会增加CPU和内存使用
- 建议在生产环境监控资源消耗
- 可通过配置控制并发处理数量

### 错误处理
- OCR失败时系统会自动降级到纯文字检测
- 所有错误都有详细日志记录
- 不会影响现有消息处理流程

---

**集成完成！** OCR功能现在已经完全集成到消息采集流程中，能够有效识别图片中的广告内容，大大提升了系统的广告检测能力。