#!/bin/bash
# 强制API修改验证脚本 - 防止低级错误
# 所有API修改必须通过此检查

set -e  # 遇到错误立即退出

echo "🔒 强制API修改验证开始..."

# 1. 语法检查
echo "📝 Python语法检查..."
python3 -m py_compile app/api/messages_batch.py
python3 -m py_compile app/api/messages_crud.py
echo "✅ 语法检查通过"

# 2. 导入检查
echo "📦 模块导入检查..."
python3 -c "from app.api.messages_batch import router; print('批量操作API导入成功')"
python3 -c "from app.api.messages_crud import router; print('CRUD API导入成功')"
echo "✅ 导入检查通过"

# 3. FastAPI应用启动检查
echo "🌐 FastAPI应用检查..."
timeout 10 python3 -c "
from app.api import api_router
from fastapi import FastAPI
app = FastAPI()
app.include_router(api_router)
print('FastAPI应用检查通过')
" || (echo "❌ FastAPI应用检查失败"; exit 1)
echo "✅ FastAPI应用检查通过"

# 4. 权限装饰器检查
echo "🔐 权限装饰器检查..."
python3 -c "
from app.api.messages_batch import check_permission
import inspect
# 检查装饰器是否正确保留函数签名
@check_permission('test')
async def test_func(a: int, b: str = 'default'): pass
sig = inspect.signature(test_func)
assert 'a' in sig.parameters, '权限装饰器破坏了函数签名'
print('权限装饰器检查通过')
"
echo "✅ 权限装饰器检查通过"

echo ""
echo "🎉 所有强制检查通过！"
echo "✅ 代码质量符合标准，可以安全部署"