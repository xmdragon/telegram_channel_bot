#!/usr/bin/env python3
"""
API修改验证工具 - 防止低级错误
确保所有API修改都经过严格验证
"""
import subprocess
import sys
import os
import importlib.util
from pathlib import Path

def test_syntax(file_path):
    """检查Python文件语法"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            compile(f.read(), file_path, 'exec')
        print(f"✅ 语法检查通过: {file_path}")
        return True
    except SyntaxError as e:
        print(f"❌ 语法错误: {file_path}")
        print(f"   行 {e.lineno}: {e.text}")
        print(f"   错误: {e.msg}")
        return False
    except Exception as e:
        print(f"❌ 文件错误: {file_path} - {e}")
        return False

def test_imports(file_path):
    """检查模块导入"""
    try:
        # 添加项目根目录到sys.path
        project_root = Path(__file__).parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        # 动态导入模块
        spec = importlib.util.spec_from_file_location("test_module", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(f"✅ 导入检查通过: {file_path}")
        return True
    except ImportError as e:
        print(f"❌ 导入错误: {file_path}")
        print(f"   错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 模块错误: {file_path} - {e}")
        return False

def test_fastapi_endpoints():
    """测试FastAPI端点定义"""
    try:
        # 测试关键API模块
        from app.api.messages_batch import router as batch_router
        from app.api.messages_crud import router as crud_router
        print("✅ FastAPI路由检查通过")
        return True
    except Exception as e:
        print(f"❌ FastAPI路由错误: {e}")
        return False

def main():
    """主验证流程"""
    print("🔍 API修改验证开始...")
    
    # 要检查的关键文件
    critical_files = [
        "app/api/messages_batch.py",
        "app/api/messages_crud.py",
        "app/api/__init__.py"
    ]
    
    all_passed = True
    
    # 1. 语法检查
    print("\n📝 语法检查:")
    for file_path in critical_files:
        if not test_syntax(file_path):
            all_passed = False
    
    # 2. 导入检查
    print("\n📦 导入检查:")
    for file_path in critical_files:
        if not test_imports(file_path):
            all_passed = False
    
    # 3. FastAPI端点检查
    print("\n🌐 FastAPI端点检查:")
    if not test_fastapi_endpoints():
        all_passed = False
    
    # 4. 结果汇总
    print("\n" + "="*50)
    if all_passed:
        print("✅ 所有检查通过 - 可以安全部署")
        return 0
    else:
        print("❌ 检查失败 - 必须修复错误后再部署")
        return 1

if __name__ == "__main__":
    sys.exit(main())