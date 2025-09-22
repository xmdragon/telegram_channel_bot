#!/usr/bin/env python3
"""
API一致性检查工具
检查前后端API定义的一致性，确保没有硬编码和未定义的API

使用方法：
python3 tools/check_api_consistency.py

返回值：
- 0: 检查通过
- 1: 发现不一致或错误
"""

import sys
import os
import re
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.route_config import ROUTES


class APIConsistencyChecker:
    """API一致性检查器"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.frontend_config_file = self.project_root / "static/assets/js/config/api-endpoints.js"
        self.errors = []
        self.warnings = []

    def check_all(self) -> bool:
        """执行所有检查"""
        print("=" * 60)
        print("API一致性检查工具 v1.0")
        print("=" * 60)

        # 1. 检查后端硬编码路由
        print("\n[1/5] 检查后端硬编码路由...")
        self.check_backend_hardcoded_routes()

        # 2. 检查前端硬编码API调用
        print("\n[2/5] 检查前端硬编码API调用...")
        self.check_frontend_hardcoded_apis()

        # 3. 收集并比较前后端API定义
        print("\n[3/5] 分析前后端API定义...")
        backend_routes = self.collect_backend_routes()
        frontend_apis = self.parse_frontend_config()
        frontend_used = self.find_frontend_api_usage()

        # 4. 检查一致性
        print("\n[4/5] 检查API一致性...")
        self.check_consistency(backend_routes, frontend_apis, frontend_used)

        # 5. 输出报告
        print("\n[5/5] 生成检查报告...")
        return self.print_report()

    def check_backend_hardcoded_routes(self):
        """检查后端是否有硬编码路由"""
        api_dir = self.project_root / "app" / "api"
        hardcoded_files = []

        for py_file in api_dir.rglob("*.py"):
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 查找@router装饰器
            if '@router.' in content and 'ROUTES.' not in content:
                # 检查是否有硬编码的路由
                hardcoded = re.findall(r'@router\.\w+\(["\']([^"\']+)["\']', content)
                if hardcoded:
                    hardcoded_files.append((py_file.relative_to(self.project_root), hardcoded))

        if hardcoded_files:
            for file, routes in hardcoded_files:
                self.errors.append(f"后端硬编码路由: {file}")
                for route in routes:
                    self.errors.append(f"  - {route}")

    def check_frontend_hardcoded_apis(self):
        """检查前端是否有硬编码API调用"""
        static_dir = self.project_root / "static"
        hardcoded_calls = []

        for js_file in static_dir.rglob("*.js"):
            if js_file.name == "api-endpoints.js":
                continue

            with open(js_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 查找直接的API路径字符串
            hardcoded = re.findall(r'["\'](/api/[^"\']+)["\']', content)

            # 排除可能的误报（如注释中的路径）
            for api in hardcoded:
                # 检查是否在axios或fetch调用中
                if f'axios.' in content and api in content:
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if api in line and 'API.' not in line:
                            hardcoded_calls.append((js_file.relative_to(self.project_root), api, i+1))

        if hardcoded_calls:
            for file, api, line in hardcoded_calls:
                self.errors.append(f"前端硬编码API: {file}:{line} -> {api}")

    def collect_backend_routes(self) -> Dict[str, str]:
        """收集所有后端路由定义"""
        routes = {}

        def traverse(obj, prefix=''):
            for attr_name in dir(obj):
                if attr_name.startswith('_'):
                    continue
                attr = getattr(obj, attr_name)
                if isinstance(attr, str) and attr.startswith('/'):
                    full_name = f"{prefix}.{attr_name}" if prefix else attr_name
                    routes[full_name] = attr
                elif hasattr(attr, '__dict__') and not attr_name.endswith('Config'):
                    child_prefix = f"{prefix}.{attr_name}" if prefix else attr_name
                    traverse(attr, child_prefix)

        traverse(ROUTES)
        return routes

    def parse_frontend_config(self) -> Dict[str, str]:
        """解析前端API配置文件"""
        apis = {}

        with open(self.frontend_config_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取API定义
        # 匹配形式: key: '/api/path'
        pattern = r'(\w+):\s*[\'"]([^\'\"]+)[\'"]'
        current_module = None

        for line in content.split('\n'):
            # 检测模块
            module_match = re.match(r'\s*(\w+):\s*\{', line)
            if module_match:
                current_module = module_match.group(1)
                continue

            # 检测API定义
            if current_module:
                api_match = re.match(r'\s*' + pattern, line)
                if api_match:
                    key = api_match.group(1)
                    path = api_match.group(2)
                    if path.startswith('/api/'):
                        apis[f"{current_module}.{key}"] = path

        # 也要处理函数形式的定义
        func_pattern = r'(\w+):\s*\([^)]*\)\s*=>\s*`([^`]+)`'
        for match in re.finditer(func_pattern, content):
            key = match.group(1)
            path = match.group(2)
            if '/api/' in path:
                # 找到所属模块
                for line in content[:match.start()].split('\n')[::-1]:
                    module_match = re.match(r'\s*(\w+):\s*\{', line)
                    if module_match:
                        current_module = module_match.group(1)
                        apis[f"{current_module}.{key}"] = f"(function) {path}"
                        break

        return apis

    def find_frontend_api_usage(self) -> Set[str]:
        """查找前端实际使用的API"""
        used_apis = set()
        static_dir = self.project_root / "static"

        for file in static_dir.rglob("*.js"):
            if file.name == "api-endpoints.js":
                continue

            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 查找API.module.method格式的使用
            matches = re.findall(r'API\.(\w+)\.(\w+)', content)
            for module, method in matches:
                used_apis.add(f"{module}.{method}")

        # 也查找HTML文件
        for file in static_dir.rglob("*.html"):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()

            matches = re.findall(r'API\.(\w+)\.(\w+)', content)
            for module, method in matches:
                used_apis.add(f"{module}.{method}")

        return used_apis

    def check_consistency(self, backend_routes: Dict[str, str],
                         frontend_apis: Dict[str, str],
                         frontend_used: Set[str]):
        """检查前后端API一致性"""

        # 1. 前端配置了但没使用的API
        unused_frontend = set(frontend_apis.keys()) - frontend_used
        if unused_frontend:
            for api in sorted(unused_frontend):
                self.warnings.append(f"前端配置但未使用: {api} -> {frontend_apis[api]}")

        # 2. 前端使用了但没配置的API
        unconfigured = frontend_used - set(frontend_apis.keys())
        # 排除非API的模块（如pages、utils、media等）
        non_api_modules = {'pages', 'utils', 'media', 'websocket'}
        unconfigured = {api for api in unconfigured
                       if not any(api.startswith(f"{m}.") for m in non_api_modules)}
        if unconfigured:
            for api in sorted(unconfigured):
                self.errors.append(f"前端使用但未配置: {api}")

        # 3. 后端定义了但前端完全不知道的路由
        # 将后端路由转换为前端格式进行比较
        backend_paths = set(backend_routes.values())
        frontend_paths = set()
        for path in frontend_apis.values():
            if path.startswith('/api/'):
                # 去掉/api前缀来比较
                frontend_paths.add(path.replace('/api', ''))
            if '(function)' in path:
                # 提取函数路径模板
                template = re.findall(r'/api([^$`]+)', path)
                if template:
                    frontend_paths.add(template[0])

        # 找出后端有但前端没有的路径
        backend_only = []
        for name, path in backend_routes.items():
            found = False
            for fp in frontend_paths:
                # 简单匹配或模板匹配
                if path == fp or path.replace('/{', '/${') in fp or path.replace('}', '') in fp.replace('}', ''):
                    found = True
                    break
            if not found and not any(skip in name for skip in ['WebRoutes', 'web.', 'Admin.']):
                backend_only.append((name, path))

        if backend_only:
            for name, path in sorted(backend_only[:10]):
                self.warnings.append(f"后端定义但前端未配置: {name} -> {path}")
            if len(backend_only) > 10:
                self.warnings.append(f"  ... 还有 {len(backend_only)-10} 个后端独有路由")

    def print_report(self) -> bool:
        """打印检查报告"""
        print("\n" + "=" * 60)
        print("检查结果汇总")
        print("=" * 60)

        if not self.errors and not self.warnings:
            print("✅ 所有检查通过！API定义完全一致。")
            return True

        if self.errors:
            print(f"\n❌ 发现 {len(self.errors)} 个错误:")
            for error in self.errors[:20]:
                print(f"  - {error}")
            if len(self.errors) > 20:
                print(f"  ... 还有 {len(self.errors)-20} 个错误")

        if self.warnings:
            print(f"\n⚠️  发现 {len(self.warnings)} 个警告:")
            for warning in self.warnings[:20]:
                print(f"  - {warning}")
            if len(self.warnings) > 20:
                print(f"  ... 还有 {len(self.warnings)-20} 个警告")

        print("\n" + "=" * 60)
        if self.errors:
            print("❌ 检查失败，请修复错误后重试")
            return False
        else:
            print("⚠️  检查通过，但有警告需要关注")
            return True


def main():
    """主函数"""
    checker = APIConsistencyChecker()
    success = checker.check_all()

    # 返回适当的退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()