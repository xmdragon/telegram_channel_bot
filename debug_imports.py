#!/usr/bin/env python3
"""
调试sentence_transformers导入问题的脚本
"""
import sys
import os
import traceback

print("🔍 调试sentence_transformers导入问题...")
print(f"Python版本: {sys.version}")
print(f"工作目录: {os.getcwd()}")
print()

def test_import(module_name, description):
    """测试模块导入"""
    try:
        print(f"🧪 测试导入 {description}...")
        exec(f"import {module_name}")
        print(f"✅ {description} 导入成功")
        return True
    except Exception as e:
        print(f"❌ {description} 导入失败: {e}")
        if "sentence_transformers" in str(e):
            print(f"🔍 详细错误信息:")
            traceback.print_exc()
        return False

def test_class_instantiation(import_statement, class_name, description):
    """测试类实例化"""
    try:
        print(f"🧪 测试实例化 {description}...")
        exec(import_statement)
        exec(f"instance = {class_name}()")
        print(f"✅ {description} 实例化成功")
        return True
    except Exception as e:
        print(f"❌ {description} 实例化失败: {e}")
        if "sentence_transformers" in str(e):
            print(f"🔍 详细错误信息:")
            traceback.print_exc()
        return False

# 测试基础模块
print("=" * 50)
print("🧪 测试基础模块导入")
print("=" * 50)
test_import("app.core.config", "app.core.config")
test_import("app.services.message_processor", "MessageProcessor")
test_import("app.services.scheduler", "MessageScheduler")

# 测试可疑的模块
print("\n" + "=" * 50)
print("🧪 测试可疑模块导入")
print("=" * 50)
test_import("app.services.promo_vector_manager", "PromoVectorManager")
test_import("app.services.model_cache_manager", "ModelCacheManager")
test_import("app.services.filters.promo_vector_filter", "PromoVectorFilter")

# 测试类实例化
print("\n" + "=" * 50)
print("🧪 测试类实例化")
print("=" * 50)
test_class_instantiation(
    "from app.services.message_processor import MessageProcessor",
    "MessageProcessor",
    "MessageProcessor"
)
test_class_instantiation(
    "from app.services.scheduler import MessageScheduler", 
    "MessageScheduler",
    "MessageScheduler"
)
test_class_instantiation(
    "from app.services.promo_vector_manager import PromoVectorManager",
    "PromoVectorManager", 
    "PromoVectorManager"
)

# 检查Python缓存
print("\n" + "=" * 50)
print("🧪 检查Python缓存")
print("=" * 50)
pycache_dirs = []
for root, dirs, files in os.walk('.'):
    if '__pycache__' in dirs:
        pycache_dirs.append(os.path.join(root, '__pycache__'))

if pycache_dirs:
    print(f"发现 {len(pycache_dirs)} 个__pycache__目录:")
    for cache_dir in pycache_dirs:
        print(f"  - {cache_dir}")
    print("建议执行: find . -name '__pycache__' -exec rm -rf {} +")
else:
    print("✅ 未发现Python缓存目录")

print("\n🎯 完成诊断")