# 硬编码API路径检查和修复工具

## 概述

这是一个"一次修复，永远正确"的解决方案，用于检查和消除项目中所有硬编码API路径的问题。

## 工具功能

### 核心能力
- 🔍 **全面扫描**: 扫描所有Python文件中的`@router`装饰器
- 🚨 **违规检测**: 发现硬编码路径（如`@router.get("/status")`）
- 💡 **智能建议**: 基于`route_config.py`提供精确的ROUTES引用建议
- 🔧 **自动修复**: 安全地将硬编码替换为ROUTES引用
- 📊 **详细报告**: 生成完整的违规报告和修复统计

### 检测原则
- 检测所有`@router.(get|post|put|delete|patch)`装饰器
- 识别硬编码字符串路径
- 排除合理的例外情况（如静态文件路径）
- 提供基于现有路由配置的精确匹配建议

## 使用方法

### 1. 基础检查（仅报告）
```bash
python3 tools/analysis/check_hardcoded_routes.py --report-only
```

### 2. 模拟修复（安全预览）
```bash
python3 tools/analysis/check_hardcoded_routes.py --dry-run
```

### 3. 实际修复（修改文件）
```bash
python3 tools/analysis/check_hardcoded_routes.py --fix
```

### 4. 保存报告
```bash
python3 tools/analysis/check_hardcoded_routes.py --report-only --output report.txt
```

## 修复示例

### 修复前（硬编码）
```python
@router.get("/status")
async def get_ai_status():
    pass

@router.post("/enable")
async def enable_ai():
    pass
```

### 修复后（配置化）
```python
from app.core.route_config import ROUTES

@router.get(ROUTES.ai.status)
async def get_ai_status():
    pass

@router.post(ROUTES.ai.enable)
async def enable_ai():
    pass
```

## 支持的路由类别

当前工具支持以下路由配置类别：
- `ROUTES.messages.*` - 消息管理
- `ROUTES.admin.*` - 管理员功能
- `ROUTES.config.*` - 配置管理
- `ROUTES.system.*` - 系统相关
- `ROUTES.auth.*` - 认证相关
- `ROUTES.ai.*` - AI功能控制
- `ROUTES.training.*` - 训练数据管理

## 项目当前状态

截至最新检查：
- **总路由数量**: 193
- **硬编码路由**: 63 ❌
- **规范路由**: 130 ✅
- **违规率**: 32.6%

## 设计原则

### 1. 简洁性
- 消除所有硬编码特殊情况
- 统一的ROUTES引用模式
- 简单直接的匹配算法

### 2. 可靠性
- 安全的文件修改机制
- 模拟模式防止意外损坏
- 基于精确匹配的建议

### 3. 完整性
- 一次检查发现所有问题
- 详细的修复统计
- 清晰的问题分类

## 工具输出示例

```
🚨 硬编码API路径违规报告
================================================================================

📊 总体统计：
   总路由数量: 193
   硬编码路由: 63 ❌
   规范路由:   130 ✅
   违规率:     32.6%

📋 违规详情：
--------------------------------------------------

📁 app/api/ai_control.py
   第20行: GET /status
   代码: @router.get("/status")
   建议: ROUTES.ai.status

💡 修复建议：
1. 所有API路径必须在route_config.py中定义
2. 消除硬编码特殊情况，使用统一的ROUTES引用
3. 重构原则：数据结构优先，消除重复代码
4. 向后兼容：确保API路径不变，只改变定义方式

🎯 目标：实现0硬编码，100%路由配置化
```

## 注意事项

### 安全性
- 修复前会验证路径的准确性
- 支持模拟模式进行安全预览
- 不会修改API的实际路径，只改变定义方式

### 兼容性
- 完全向后兼容，不破坏现有功能
- 遵循"Never break userspace"原则
- 保持API路径完全不变

### 扩展性
- 易于添加新的路由类别
- 支持自定义匹配规则
- 可配置的例外情况

## 开发者指南

### 添加新路由类别
1. 在`route_config.py`中添加新的路由类
2. 在工具的`_smart_route_suggestion`方法中添加映射
3. 更新路由类的初始化

### 自定义匹配规则
- 修改`_is_acceptable_hardcode`方法添加例外情况
- 扩展`_smart_route_suggestion`的映射表
- 调整正则表达式匹配模式

## 未来改进

- [ ] 支持自动生成缺失的路由配置
- [ ] 集成到CI/CD管道进行自动检查
- [ ] 支持更多框架的路由模式
- [ ] 添加路由配置的完整性验证