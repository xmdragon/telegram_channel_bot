#!/usr/bin/env python3
"""
前端数据加载测试脚本
测试前端页面的数据加载和显示功能
"""

import json
import time
import sys
import os
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Dict, List, Any, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

class FrontendDataTester:
    """前端数据加载测试器"""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.auth_token = None
        self.test_results = {
            "🔐 认证系统": {},
            "📄 静态页面": {},
            "🔌 API集成": {},
            "📊 数据显示": {},
            "🔄 实时更新": {}
        }
        self.errors = []
        
    def log_result(self, category: str, test_name: str, success: bool, 
                   details: str = "", data: Any = None):
        """记录测试结果"""
        result = {
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "details": details,
            "data": data
        }
        self.test_results[category][test_name] = result
        
        status = "✅" if success else "❌"
        print(f"{status} [{category}] {test_name}: {details}")
        
        if not success:
            self.errors.append(f"[{category}] {test_name}: {details}")
    
    def test_static_page(self, path: str, page_name: str) -> bool:
        """测试静态页面访问"""
        try:
            url = f"{self.base_url}{path}"
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'FrontendDataTester/1.0')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.getcode() == 200:
                    content = response.read().decode('utf-8')
                    # 检查页面是否包含基本HTML结构
                    has_html = '<html' in content.lower()
                    has_head = '<head' in content.lower()
                    has_body = '<body' in content.lower()
                    
                    if has_html and has_head and has_body:
                        # 检查是否包含Vue.js相关内容
                        has_vue = 'vue' in content.lower()
                        has_element = 'element' in content.lower()
                        
                        details = f"页面加载成功"
                        if has_vue:
                            details += " (包含Vue.js)"
                        if has_element:
                            details += " (包含Element Plus)"
                        
                        return True, details
                    else:
                        return False, "页面缺少基本HTML结构"
                else:
                    return False, f"HTTP {response.getcode()}"
                    
        except Exception as e:
            return False, f"访问失败: {str(e)}"
    
    def test_api_endpoint(self, endpoint: str, method: str = "GET", 
                         data: Dict = None, need_auth: bool = False) -> Optional[Dict]:
        """测试API端点"""
        try:
            url = f"{self.base_url}{endpoint}"
            
            if method.upper() == "GET":
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'FrontendDataTester/1.0')
                req.add_header('Accept', 'application/json')
                
                if need_auth and self.auth_token:
                    req.add_header('Authorization', f'Bearer {self.auth_token}')
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.getcode() == 200:
                        response_data = response.read().decode('utf-8')
                        return json.loads(response_data)
                    else:
                        return {"error": f"HTTP {response.getcode()}"}
            
            elif method.upper() == "POST":
                json_data = json.dumps(data).encode('utf-8') if data else b''
                req = urllib.request.Request(url, data=json_data, method='POST')
                req.add_header('User-Agent', 'FrontendDataTester/1.0')
                req.add_header('Accept', 'application/json')
                req.add_header('Content-Type', 'application/json')
                
                if need_auth and self.auth_token:
                    req.add_header('Authorization', f'Bearer {self.auth_token}')
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.getcode() == 200:
                        response_data = response.read().decode('utf-8')
                        return json.loads(response_data)
                    else:
                        return {"error": f"HTTP {response.getcode()}"}
                        
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"error": f"URL Error: {e.reason}"}
        except Exception as e:
            return {"error": str(e)}
    
    def test_authentication_system(self):
        """测试认证系统"""
        print("\n🔐 开始测试认证系统...")
        
        # 1. 测试登录页面
        success, details = self.test_static_page("/static/login.html", "登录页面")
        self.log_result("🔐 认证系统", "登录页面访问", success, details)
        
        # 2. 测试管理员登录API
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        result = self.test_api_endpoint("/api/admin/auth/login", "POST", login_data)
        if result and "error" not in result and result.get("success"):
            self.auth_token = result.get("token")
            admin_info = result.get("admin", {})
            self.log_result("🔐 认证系统", "管理员登录API", True, 
                          f"登录成功，用户: {admin_info.get('username', 'N/A')}")
        else:
            self.log_result("🔐 认证系统", "管理员登录API", False, 
                          f"登录失败: {result}")
        
        # 3. 测试认证状态检查
        if self.auth_token:
            result = self.test_api_endpoint("/api/admin/auth/check-auth", need_auth=True)
            if result and "error" not in result:
                self.log_result("🔐 认证系统", "认证状态检查", True, 
                              "认证状态正常")
            else:
                self.log_result("🔐 认证系统", "认证状态检查", False, 
                              f"检查失败: {result}")
    
    def test_static_pages(self):
        """测试静态页面"""
        print("\n📄 开始测试静态页面...")
        
        pages_to_test = [
            ("/static/index.html", "消息管理主页"),
            ("/static/tail-filter-manager.html", "尾部过滤管理"),
            ("/static/media-manager.html", "媒体管理页面"),
            ("/static/config.html", "系统配置页面"),
            ("/static/threshold-dashboard.html", "阈值监控页面"),
            ("/static/training-data-manager.html", "训练数据管理"),
        ]
        
        for path, name in pages_to_test:
            success, details = self.test_static_page(path, name)
            self.log_result("📄 静态页面", name, success, details)
    
    def test_api_integration(self):
        """测试API集成"""
        print("\n🔌 开始测试API集成...")
        
        # 测试各个页面可能用到的API端点
        api_tests = [
            # 消息相关API
            ("/api/health", "健康检查API", False),
            ("/api/system/status", "系统状态API", False),
            ("/api/messages", "消息列表API", True),
            
            # 训练数据相关API
            ("/api/training-db/stats", "训练数据统计", False),
            ("/api/training-db/ad-samples", "广告样本API", False),
            ("/api/training-db/tail-filter-samples", "尾部过滤样本", False),
            ("/api/training-db/media-files", "媒体文件列表", False),
        ]
        
        for endpoint, name, needs_auth in api_tests:
            result = self.test_api_endpoint(endpoint, need_auth=needs_auth)
            if result and "error" not in result:
                data_info = ""
                if isinstance(result, dict):
                    if "messages" in result:
                        data_info = f" (消息数: {len(result['messages'])})"
                    elif "samples" in result:
                        data_info = f" (样本数: {len(result['samples'])})"
                    elif "files" in result:
                        data_info = f" (文件数: {len(result['files'])})"
                    elif "services" in result:
                        data_info = f" (服务数: {len(result['services'])})"
                
                self.log_result("🔌 API集成", name, True, f"API正常{data_info}")
            else:
                self.log_result("🔌 API集成", name, False, f"API异常: {result}")
    
    def test_data_display_features(self):
        """测试数据显示功能"""
        print("\n📊 开始测试数据显示功能...")
        
        # 1. 测试消息数据显示
        messages_result = self.test_api_endpoint("/api/messages", need_auth=True)
        if messages_result and "error" not in messages_result:
            messages = messages_result.get("messages", [])
            pagination = messages_result.get("pagination", {})
            
            self.log_result("📊 数据显示", "消息数据结构", True, 
                          f"消息数: {len(messages)}, 分页信息完整: {bool(pagination)}")
            
            # 检查消息数据字段
            if messages:
                sample_message = messages[0]
                required_fields = ["id", "content", "channel_title", "created_at"]
                missing_fields = [field for field in required_fields if field not in sample_message]
                
                if not missing_fields:
                    self.log_result("📊 数据显示", "消息字段完整性", True, 
                                  "消息包含所有必要字段")
                else:
                    self.log_result("📊 数据显示", "消息字段完整性", False, 
                                  f"缺失字段: {missing_fields}")
        else:
            self.log_result("📊 数据显示", "消息数据结构", False, 
                          f"获取消息失败: {messages_result}")
        
        # 2. 测试训练数据显示
        ad_samples = self.test_api_endpoint("/api/training-db/ad-samples")
        if ad_samples and "error" not in ad_samples:
            samples = ad_samples.get("samples", [])
            self.log_result("📊 数据显示", "广告样本数据", True, 
                          f"广告样本: {len(samples)} 条")
            
            # 检查样本数据结构
            if samples:
                sample = samples[0]
                if "content" in sample and "label" in sample:
                    self.log_result("📊 数据显示", "样本数据结构", True, 
                                  "样本包含内容和标签字段")
                else:
                    self.log_result("📊 数据显示", "样本数据结构", False, 
                                  "样本缺少必要字段")
        else:
            self.log_result("📊 数据显示", "广告样本数据", False, 
                          f"获取样本失败: {ad_samples}")
        
        # 3. 测试媒体文件显示
        media_files = self.test_api_endpoint("/api/training-db/media-files")
        if media_files and "error" not in media_files:
            files = media_files.get("files", [])
            self.log_result("📊 数据显示", "媒体文件数据", True, 
                          f"媒体文件: {len(files)} 个")
            
            # 检查文件信息结构
            if files:
                file_info = files[0]
                if "filename" in file_info:
                    self.log_result("📊 数据显示", "文件信息结构", True, 
                                  "文件信息包含必要字段")
                else:
                    self.log_result("📊 数据显示", "文件信息结构", False, 
                                  "文件信息缺少必要字段")
        else:
            self.log_result("📊 数据显示", "媒体文件数据", False, 
                          f"获取文件失败: {media_files}")
    
    def test_realtime_updates(self):
        """测试实时更新功能"""
        print("\n🔄 开始测试实时更新功能...")
        
        # 1. 测试系统状态更新
        status1 = self.test_api_endpoint("/api/system/status")
        time.sleep(2)
        status2 = self.test_api_endpoint("/api/system/status")
        
        if status1 and status2 and "error" not in str(status1) and "error" not in str(status2):
            services1 = len(status1.get("services", {}))
            services2 = len(status2.get("services", {}))
            self.log_result("🔄 实时更新", "系统状态更新", True, 
                          f"状态持续可用: {services1}→{services2} 个服务")
        else:
            self.log_result("🔄 实时更新", "系统状态更新", False, 
                          "系统状态更新失败")
        
        # 2. 测试健康检查响应
        start_time = time.time()
        health = self.test_api_endpoint("/api/health")
        response_time = (time.time() - start_time) * 1000
        
        if health and "error" not in health:
            self.log_result("🔄 实时更新", "健康检查响应", True, 
                          f"响应时间: {response_time:.1f}ms")
        else:
            self.log_result("🔄 实时更新", "健康检查响应", False, 
                          f"健康检查失败: {health}")
        
        # 3. 测试训练数据统计刷新
        stats1 = self.test_api_endpoint("/api/training-db/stats")
        time.sleep(1)
        stats2 = self.test_api_endpoint("/api/training-db/stats")
        
        if stats1 and stats2:
            self.log_result("🔄 实时更新", "训练数据刷新", True, 
                          "训练数据统计可正常刷新")
        else:
            self.log_result("🔄 实时更新", "训练数据刷新", False, 
                          "训练数据刷新失败")
    
    def run_comprehensive_test(self):
        """运行全面测试"""
        print("🧪 开始前端数据加载测试...")
        print("=" * 60)
        
        try:
            # 按顺序执行测试
            self.test_authentication_system()
            self.test_static_pages()
            self.test_api_integration()
            self.test_data_display_features()
            self.test_realtime_updates()
            
        except Exception as e:
            print(f"❌ 测试过程中出现异常: {e}")
            self.errors.append(f"测试异常: {e}")
        
        # 生成测试报告
        self.generate_report()
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("📊 前端数据加载测试报告")
        print("=" * 60)
        
        total_tests = 0
        passed_tests = 0
        
        for category, tests in self.test_results.items():
            if tests:  # 只显示有测试的分类
                print(f"\n{category}:")
                for test_name, result in tests.items():
                    total_tests += 1
                    if result["success"]:
                        passed_tests += 1
                    status = "✅" if result["success"] else "❌"
                    print(f"  {status} {test_name}: {result['details']}")
        
        print(f"\n📈 测试统计:")
        print(f"  总测试数: {total_tests}")
        print(f"  通过测试: {passed_tests}")
        print(f"  失败测试: {total_tests - passed_tests}")
        print(f"  成功率: {(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "  成功率: N/A")
        
        # 分析问题类型
        page_issues = [e for e in self.errors if "页面" in e]
        api_issues = [e for e in self.errors if "API" in e]
        auth_issues = [e for e in self.errors if "认证" in e or "登录" in e]
        other_issues = [e for e in self.errors if e not in page_issues + api_issues + auth_issues]
        
        if page_issues:
            print(f"\n📄 页面访问问题 ({len(page_issues)} 个):")
            for i, error in enumerate(page_issues, 1):
                print(f"  {i}. {error}")
        
        if api_issues:
            print(f"\n🔌 API集成问题 ({len(api_issues)} 个):")
            for i, error in enumerate(api_issues, 1):
                print(f"  {i}. {error}")
        
        if auth_issues:
            print(f"\n🔐 认证系统问题 ({len(auth_issues)} 个):")
            for i, error in enumerate(auth_issues, 1):
                print(f"  {i}. {error}")
        
        if other_issues:
            print(f"\n🔧 其他问题 ({len(other_issues)} 个):")
            for i, error in enumerate(other_issues, 1):
                print(f"  {i}. {error}")
        
        if not self.errors:
            print(f"\n✅ 所有测试通过！前端数据加载功能工作正常。")
        else:
            print(f"\n📝 建议:")
            if page_issues:
                print("  - 检查静态文件服务配置")
            if api_issues:
                print("  - 检查API端点实现和路由配置")
            if auth_issues:
                print("  - 检查认证系统和权限配置")
        
        # 保存报告
        report_file = f"/Users/eric/workspace/telegram_channel_bot/tools/testing/frontend_data_test_report_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "authentication_successful": bool(self.auth_token),
                "summary": {
                    "total_tests": total_tests,
                    "passed_tests": passed_tests,
                    "failed_tests": total_tests - passed_tests,
                    "success_rate": (passed_tests/total_tests*100) if total_tests > 0 else 0,
                    "page_issues": len(page_issues),
                    "api_issues": len(api_issues),
                    "auth_issues": len(auth_issues),
                    "other_issues": len(other_issues)
                },
                "results": self.test_results,
                "errors": self.errors
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存到: {report_file}")

def main():
    """主函数"""
    tester = FrontendDataTester()
    tester.run_comprehensive_test()

if __name__ == "__main__":
    main()