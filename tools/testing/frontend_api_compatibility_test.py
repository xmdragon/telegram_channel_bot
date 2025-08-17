#!/usr/bin/env python3
"""
前端 API 兼容性测试

验证前端 api-endpoints.js 配置与后端路由的匹配性

作者：Test Automation Expert
创建时间：2025-08-17
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set

class FrontendAPICompatibilityTest:
    """
    前端 API 兼容性测试器
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.api_config_file = self.project_root / "static" / "assets" / "js" / "config" / "api-endpoints.js"
        self.training_router_file = self.project_root / "app" / "routers" / "training_db.py"
        
        self.test_results = {
            "api_config_analysis": {},
            "router_analysis": {},
            "compatibility_check": {},
            "summary": {
                "total_endpoints": 0,
                "matched_endpoints": 0,
                "mismatched_endpoints": 0,
                "missing_endpoints": [],
                "extra_endpoints": []
            }
        }
        
    def extract_api_endpoints_from_config(self) -> Dict[str, str]:
        """
        从 api-endpoints.js 提取 API 端点
        """
        print("🔍 分析前端 API 配置...")
        
        endpoints = {}
        
        try:
            with open(self.api_config_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 提取 training 相关的端点
            training_section_match = re.search(
                r'training:\s*\{([^}]+)\}',
                content,
                re.DOTALL
            )
            
            if training_section_match:
                training_content = training_section_match.group(1)
                
                # 提取所有端点定义
                endpoint_patterns = [
                    r"(\w+):\s*['\"]([^'\"]+)['\"],?",  # 简单端点
                    r"(\w+):\s*\([^)]+\)\s*=>\s*`([^`]+)`",  # 模板字符串函数
                    r"(\w+):\s*\([^)]+\)\s*=>\s*['\"]([^'\"]+)['\"]"  # 带参数的函数
                ]
                
                for pattern in endpoint_patterns:
                    matches = re.findall(pattern, training_content)
                    for name, url in matches:
                        # 清理 URL 模板变量
                        clean_url = re.sub(r'\$\{[^}]+\}', '{param}', url)
                        endpoints[name] = clean_url
                        
            self.test_results["api_config_analysis"]["endpoints_found"] = len(endpoints)
            self.test_results["api_config_analysis"]["endpoints"] = endpoints
            
            print(f"  ✅ 找到 {len(endpoints)} 个训练相关端点")
            for name, url in list(endpoints.items())[:5]:  # 显示前5个
                print(f"    - {name}: {url}")
            if len(endpoints) > 5:
                print(f"    ... 及其他 {len(endpoints) - 5} 个")
                
        except Exception as e:
            print(f"  ❌ 分析 API 配置失败: {e}")
            self.test_results["api_config_analysis"]["error"] = str(e)
            
        return endpoints
        
    def extract_routes_from_router(self) -> Dict[str, str]:
        """
        从路由文件提取实际路由
        """
        print("\n🔍 分析后端路由定义...")
        
        routes = {}
        
        try:
            with open(self.training_router_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 提取所有 @router 装饰器定义的路由
            route_pattern = r'@router\.(get|post|put|delete)\(["\']([^"\')]+)["\']\)\s*\nasync def (\w+)'
            matches = re.findall(route_pattern, content, re.MULTILINE)
            
            for method, path, func_name in matches:
                # 将路径参数标准化
                clean_path = re.sub(r'\{[^}]+\}', '{param}', path)
                route_key = f"{func_name}_{method}"
                routes[route_key] = f"/api/training-db{clean_path}"
                
            self.test_results["router_analysis"]["routes_found"] = len(routes)
            self.test_results["router_analysis"]["routes"] = routes
            
            print(f"  ✅ 找到 {len(routes)} 个路由定义")
            for name, path in list(routes.items())[:5]:  # 显示前5个
                print(f"    - {name}: {path}")
            if len(routes) > 5:
                print(f"    ... 及其他 {len(routes) - 5} 个")
                
        except Exception as e:
            print(f"  ❌ 分析路由失败: {e}")
            self.test_results["router_analysis"]["error"] = str(e)
            
        return routes
        
    def check_api_compatibility(self, frontend_endpoints: Dict[str, str], backend_routes: Dict[str, str]) -> Dict[str, any]:
        """
        检查前后端 API 兼容性
        """
        print("\n🔍 检查前后端 API 兼容性...")
        
        # 将后端路由转换为更易匹配的格式
        backend_paths = set()
        for route_name, full_path in backend_routes.items():
            # 去掉 /api/training-db 前缀
            path = full_path.replace('/api/training-db', '')
            if not path:
                path = '/'
            backend_paths.add(path)
            
        # 检查前端端点是否在后端存在
        matched = set()
        missing = set()
        
        for name, endpoint_url in frontend_endpoints.items():
            # 去掉 /api/training-db 前缀
            path = endpoint_url.replace('/api/training-db', '')
            if not path:
                path = '/'
                
            if path in backend_paths:
                matched.add(name)
                print(f"  ✅ {name}: {path} - 匹配")
            else:
                missing.add(name)
                print(f"  ❌ {name}: {path} - 缺失")
                
        # 检查后端是否有额外的路由
        frontend_paths = set()
        for endpoint_url in frontend_endpoints.values():
            path = endpoint_url.replace('/api/training-db', '')
            if not path:
                path = '/'
            frontend_paths.add(path)
            
        extra_routes = backend_paths - frontend_paths
        
        # 统计结果
        compatibility_result = {
            "matched_count": len(matched),
            "missing_count": len(missing),
            "extra_count": len(extra_routes),
            "total_frontend": len(frontend_endpoints),
            "total_backend": len(backend_routes),
            "matched_endpoints": list(matched),
            "missing_endpoints": list(missing),
            "extra_routes": list(extra_routes),
            "compatibility_rate": len(matched) / len(frontend_endpoints) * 100 if frontend_endpoints else 0
        }
        
        if extra_routes:
            print(f"\n  📝 后端额外的路由 ({len(extra_routes)} 个):")
            for route in list(extra_routes)[:10]:  # 显示前10个
                print(f"    - {route}")
            if len(extra_routes) > 10:
                print(f"    ... 及其他 {len(extra_routes) - 10} 个")
                
        return compatibility_result
        
    def check_critical_endpoints(self, frontend_endpoints: Dict[str, str]) -> Dict[str, any]:
        """
        检查关键端点是否存在
        """
        print("\n🔍 检查关键端点...")
        
        critical_endpoints = [
            'stats',
            'submit', 
            'adSamples',
            'channels',
            'history',
            'mediaFiles',
            'tailFilterSamples',
            'separatorPatterns'
        ]
        
        missing_critical = []
        existing_critical = []
        
        for endpoint in critical_endpoints:
            if endpoint in frontend_endpoints:
                existing_critical.append(endpoint)
                print(f"  ✅ {endpoint}: 存在")
            else:
                missing_critical.append(endpoint)
                print(f"  ❌ {endpoint}: 缺失")
                
        return {
            "total_critical": len(critical_endpoints),
            "existing_critical": existing_critical,
            "missing_critical": missing_critical,
            "critical_coverage": len(existing_critical) / len(critical_endpoints) * 100
        }
        
    def run_compatibility_test(self) -> str:
        """
        运行完整的兼容性测试
        """
        print("🚀 开始前端 API 兼容性测试...")
        print("="*80)
        
        # 1. 提取前端 API 配置
        frontend_endpoints = self.extract_api_endpoints_from_config()
        
        # 2. 提取后端路由
        backend_routes = self.extract_routes_from_router()
        
        # 3. 检查兼容性
        if frontend_endpoints and backend_routes:
            compatibility_result = self.check_api_compatibility(frontend_endpoints, backend_routes)
            self.test_results["compatibility_check"] = compatibility_result
            
            # 4. 检查关键端点
            critical_result = self.check_critical_endpoints(frontend_endpoints)
            self.test_results["critical_endpoints"] = critical_result
            
            # 更新总结
            self.test_results["summary"].update({
                "total_endpoints": compatibility_result["total_frontend"],
                "matched_endpoints": compatibility_result["matched_count"],
                "mismatched_endpoints": compatibility_result["missing_count"],
                "missing_endpoints": compatibility_result["missing_endpoints"],
                "extra_endpoints": list(compatibility_result["extra_routes"])
            })
            
        # 生成报告
        return self.generate_compatibility_report()
        
    def generate_compatibility_report(self) -> str:
        """
        生成兼容性测试报告
        """
        summary = self.test_results["summary"]
        compatibility = self.test_results.get("compatibility_check", {})
        critical = self.test_results.get("critical_endpoints", {})
        
        report = f"""
# 前端 API 兼容性测试报告

## 测试概览
- 前端端点总数: {summary['total_endpoints']}
- 匹配的端点: {summary['matched_endpoints']}
- 缺失的端点: {summary['mismatched_endpoints']}
- 兼容率: {compatibility.get('compatibility_rate', 0):.1f}%

## 关键端点检查
- 关键端点总数: {critical.get('total_critical', 0)}
- 存在的关键端点: {len(critical.get('existing_critical', []))}
- 缺失的关键端点: {len(critical.get('missing_critical', []))}
- 关键端点覆盖率: {critical.get('critical_coverage', 0):.1f}%

"""
        
        if summary.get('missing_endpoints'):
            report += "## 缺失的端点\n"
            for endpoint in summary['missing_endpoints']:
                report += f"- ❌ {endpoint}\n"
                
        if critical.get('missing_critical'):
            report += "\n## 缺失的关键端点\n"
            for endpoint in critical['missing_critical']:
                report += f"- ⚠️  {endpoint}\n"
                
        # 结论
        report += "\n## 结论\n"
        if summary['mismatched_endpoints'] == 0:
            report += "🎉 所有前端 API 端点都与后端路由匹配！\n"
        else:
            report += f"⚠️  发现 {summary['mismatched_endpoints']} 个不匹配的端点需要修复。\n"
            
        if compatibility.get('compatibility_rate', 0) >= 90:
            report += "📈 前后端 API 兼容性良好！\n"
        elif compatibility.get('compatibility_rate', 0) >= 70:
            report += "📈 前后端 API 兼容性尚可，建议优化。\n"
        else:
            report += "🚨 前后端 API 兼容性较低，需要紧急修复！\n"
            
        return report

def main():
    """
    主测试函数
    """
    tester = FrontendAPICompatibilityTest()
    report = tester.run_compatibility_test()
    
    print("\n" + "="*80)
    print("📋 兼容性测试报告:")
    print("="*80)
    print(report)
    
    # 保存结果
    from datetime import datetime
    results_file = Path("tools/testing") / f"frontend_compatibility_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_file.parent.mkdir(exist_ok=True)
    
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(tester.test_results, f, indent=2, ensure_ascii=False)
        
    print(f"\n💾 详细结果已保存到: {results_file}")
    
if __name__ == "__main__":
    main()
