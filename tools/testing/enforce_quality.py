#!/usr/bin/env python3
"""
强制代码质量工具 - 防止低级错误
Claude必须在每次编辑API文件后运行此工具
"""
import subprocess
import sys
import os
from pathlib import Path

class QualityEnforcer:
    """代码质量强制执行器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.failed_checks = []
        
    def check_syntax(self, file_path):
        """强制语法检查"""
        try:
            result = subprocess.run([
                sys.executable, '-m', 'py_compile', file_path
            ], capture_output=True, text=True, cwd=self.project_root)
            
            if result.returncode != 0:
                self.failed_checks.append(f"语法错误: {file_path}\n{result.stderr}")
                return False
            return True
        except Exception as e:
            self.failed_checks.append(f"语法检查异常: {file_path} - {e}")
            return False
    
    def check_imports(self, file_path):
        """强制导入检查"""
        try:
            # 对于API文件，尝试导入router
            if 'messages_batch.py' in str(file_path):
                result = subprocess.run([
                    sys.executable, '-c', 'from app.api.messages_batch import router'
                ], capture_output=True, text=True, cwd=self.project_root)
                
                if result.returncode != 0:
                    self.failed_checks.append(f"导入错误: {file_path}\n{result.stderr}")
                    return False
                    
            elif 'messages_crud.py' in str(file_path):
                result = subprocess.run([
                    sys.executable, '-c', 'from app.api.messages_crud import router'
                ], capture_output=True, text=True, cwd=self.project_root)
                
                if result.returncode != 0:
                    self.failed_checks.append(f"导入错误: {file_path}\n{result.stderr}")
                    return False
            
            return True
        except Exception as e:
            self.failed_checks.append(f"导入检查异常: {file_path} - {e}")
            return False
    
    def check_fastapi_signatures(self):
        """检查FastAPI函数签名"""
        try:
            check_code = '''
import sys
sys.path.insert(0, ".")
from app.api.messages_batch import router as batch_router
import inspect

# 检查批量操作函数的参数签名
for route in batch_router.routes:
    if hasattr(route, "endpoint") and "batch_" in route.endpoint.__name__:
        func = route.endpoint
        sig = inspect.signature(func)
        
        # 检查关键参数
        if "request" not in sig.parameters:
            raise ValueError(f"{func.__name__} 缺少 request 参数")
            
        request_param = sig.parameters["request"]
        # 检查是否有默认值且包含Body
        if request_param.default is inspect.Parameter.empty:
            raise ValueError(f"{func.__name__} 的 request 参数没有默认值")
        elif "Body" not in str(type(request_param.default)):
            raise ValueError(f"{func.__name__} 的 request 参数应该使用 Body() 作为默认值")

print("FastAPI签名检查通过")
'''
            
            result = subprocess.run([
                sys.executable, '-c', check_code
            ], capture_output=True, text=True, cwd=self.project_root)
            
            if result.returncode != 0:
                self.failed_checks.append(f"FastAPI签名错误:\n{result.stderr}")
                return False
            return True
            
        except Exception as e:
            self.failed_checks.append(f"FastAPI签名检查异常: {e}")
            return False
    
    def enforce_quality(self, files_to_check=None):
        """强制执行代码质量检查"""
        if files_to_check is None:
            files_to_check = [
                'app/api/messages_batch.py',
                'app/api/messages_crud.py'
            ]
        
        print("💀 强制代码质量检查启动...")
        print("=" * 50)
        
        all_passed = True
        
        # 检查每个文件
        for file_path in files_to_check:
            full_path = self.project_root / file_path
            if full_path.exists():
                print(f"🔍 检查: {file_path}")
                
                if not self.check_syntax(str(full_path)):
                    all_passed = False
                    
                if not self.check_imports(str(full_path)):
                    all_passed = False
        
        # FastAPI特定检查
        if not self.check_fastapi_signatures():
            all_passed = False
        
        print("=" * 50)
        
        if all_passed:
            print("✅ 所有质量检查通过 - 代码符合标准")
            return True
        else:
            print("❌ 质量检查失败:")
            for error in self.failed_checks:
                print(f"  • {error}")
            print("\n💀 必须修复所有错误才能继续!")
            return False

def main():
    enforcer = QualityEnforcer()
    success = enforcer.enforce_quality()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())