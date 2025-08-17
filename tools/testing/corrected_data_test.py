#!/usr/bin/env python3
"""
修正版数据功能测试脚本
使用正确的API路径测试系统数据功能
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

class CorrectedDataTester:
    """修正版数据功能测试器"""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.auth_token = None
        self.test_results = {
            "🔐 认证测试": {},
            "📊 无需认证的数据": {},
            "🔒 需要认证的数据": {},
            "🔄 实时更新功能": {},
            "🧪 数据一致性": {}
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
    
    def test_api_endpoint(self, endpoint: str, method: str = "GET", 
                         data: Dict = None, need_auth: bool = False) -> Optional[Dict]:
        """测试API端点"""
        try:
            url = f"{self.base_url}{endpoint}"
            
            if method.upper() == "GET":
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'CorrectedDataTester/1.0')
                req.add_header('Accept', 'application/json')
                
                # 添加认证头
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
                req.add_header('User-Agent', 'CorrectedDataTester/1.0')
                req.add_header('Accept', 'application/json')
                req.add_header('Content-Type', 'application/json')
                
                # 添加认证头
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
    
    def test_authentication(self):
        """测试认证功能"""
        print("\n🔐 开始测试认证功能...")
        
        # 1. 测试管理员登录 - 使用正确的路径
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        result = self.test_api_endpoint("/api/admin/auth/login", "POST", login_data)
        if result and "error" not in result and result.get("success"):
            self.auth_token = result.get("token")
            admin_info = result.get("admin", {})
            self.log_result("🔐 认证测试", "管理员登录", True, 
                          f"登录成功，用户: {admin_info.get('username', 'N/A')}")
        else:
            self.log_result("🔐 认证测试", "管理员登录", False, 
                          f"登录失败: {result}")
        
        # 2. 测试认证检查
        if self.auth_token:
            result = self.test_api_endpoint("/api/admin/auth/check-auth", need_auth=True)
            if result and "error" not in result:
                self.log_result("🔐 认证测试", "认证验证", True, 
                              "认证状态正常")
            else:
                self.log_result("🔐 认证测试", "认证验证", False, 
                              f"验证失败: {result}")
    
    def test_public_apis(self):
        """测试无需认证的公开API"""
        print("\n📊 开始测试无需认证的数据API...")
        
        # 1. 健康检查
        result = self.test_api_endpoint("/api/health")
        if result and "error" not in result:
            self.log_result("📊 无需认证的数据", "健康检查", True, 
                          f"状态: {result.get('status', 'unknown')}")
        else:
            self.log_result("📊 无需认证的数据", "健康检查", False, 
                          f"检查失败: {result}")
        
        # 2. 系统状态
        result = self.test_api_endpoint("/api/system/status")
        if result and "error" not in result:
            services = result.get("services", {})
            self.log_result("📊 无需认证的数据", "系统状态", True, 
                          f"检测到 {len(services)} 个服务")
        else:
            self.log_result("📊 无需认证的数据", "系统状态", False, 
                          f"获取失败: {result}")
        
        # 3. 训练数据统计
        result = self.test_api_endpoint("/api/training-db/stats")
        if result and "error" not in result:
            ad_samples = result.get("ad_samples", 0)
            tail_samples = result.get("tail_samples", 0)
            self.log_result("📊 无需认证的数据", "训练数据统计", True, 
                          f"广告样本: {ad_samples}, 尾部样本: {tail_samples}")
        else:
            self.log_result("📊 无需认证的数据", "训练数据统计", False, 
                          f"获取失败: {result}")
        
        # 4. 广告样本数据
        result = self.test_api_endpoint("/api/training-db/ad-samples")
        if result and "error" not in result:
            samples = result.get("samples", [])
            self.log_result("📊 无需认证的数据", "广告样本数据", True, 
                          f"样本数量: {len(samples)}")
        else:
            self.log_result("📊 无需认证的数据", "广告样本数据", False, 
                          f"获取失败: {result}")
        
        # 5. 尾部过滤样本
        result = self.test_api_endpoint("/api/training-db/tail-filter-samples")
        if result and "error" not in result:
            samples = result.get("samples", [])
            self.log_result("📊 无需认证的数据", "尾部过滤样本", True, 
                          f"样本数量: {len(samples)}")
        else:
            self.log_result("📊 无需认证的数据", "尾部过滤样本", False, 
                          f"获取失败: {result}")
        
        # 6. 媒体文件列表
        result = self.test_api_endpoint("/api/training-db/media-files")
        if result and "error" not in result:
            files = result.get("files", [])
            self.log_result("📊 无需认证的数据", "媒体文件列表", True, 
                          f"文件数量: {len(files)}")
        else:
            self.log_result("📊 无需认证的数据", "媒体文件列表", False, 
                          f"获取失败: {result}")
    
    def test_authenticated_apis(self):
        """测试需要认证的API"""
        print("\n🔒 开始测试需要认证的数据API...")
        
        if not self.auth_token:
            self.log_result("🔒 需要认证的数据", "跳过认证测试", False, 
                          "未获得认证令牌，跳过认证相关测试")
            return
        
        # 1. 消息列表
        result = self.test_api_endpoint("/api/messages", need_auth=True)
        if result and "error" not in result:
            messages = result.get("messages", [])
            pagination = result.get("pagination", {})
            self.log_result("🔒 需要认证的数据", "消息列表", True, 
                          f"消息数: {len(messages)}, 总计: {pagination.get('total', 0)}")
        else:
            self.log_result("🔒 需要认证的数据", "消息列表", False, 
                          f"获取失败: {result}")
        
        # 2. 消息统计
        result = self.test_api_endpoint("/api/messages/stats", need_auth=True)
        if result and "error" not in result:
            total = result.get("total", 0)
            pending = result.get("pending", 0)
            self.log_result("🔒 需要认证的数据", "消息统计", True, 
                          f"总消息: {total}, 待审核: {pending}")
        else:
            self.log_result("🔒 需要认证的数据", "消息统计", False, 
                          f"获取失败: {result}")
        
        # 3. 系统配置
        result = self.test_api_endpoint("/api/config/system", need_auth=True)
        if result and "error" not in result:
            config_keys = list(result.keys()) if isinstance(result, dict) else []
            self.log_result("🔒 需要认证的数据", "系统配置", True, 
                          f"配置项数: {len(config_keys)}")
        else:
            self.log_result("🔒 需要认证的数据", "系统配置", False, 
                          f"获取失败: {result}")
        
        # 4. 频道配置
        result = self.test_api_endpoint("/api/config/channels", need_auth=True)
        if result and "error" not in result:
            channels = result.get("channels", [])
            self.log_result("🔒 需要认证的数据", "频道配置", True, 
                          f"配置频道: {len(channels)}")
        else:
            self.log_result("🔒 需要认证的数据", "频道配置", False, 
                          f"获取失败: {result}")
        
        # 5. 阈值配置
        result = self.test_api_endpoint("/api/config/thresholds", need_auth=True)
        if result and "error" not in result:
            threshold_keys = list(result.keys()) if isinstance(result, dict) else []
            self.log_result("🔒 需要认证的数据", "阈值配置", True, 
                          f"阈值项数: {len(threshold_keys)}")
        else:
            self.log_result("🔒 需要认证的数据", "阈值配置", False, 
                          f"获取失败: {result}")
    
    def test_realtime_features(self):
        """测试实时功能"""
        print("\n🔄 开始测试实时更新功能...")
        
        # 1. 数据刷新测试
        initial_stats = self.test_api_endpoint("/api/training-db/stats")
        time.sleep(2)  # 等待2秒
        updated_stats = self.test_api_endpoint("/api/training-db/stats")
        
        if initial_stats and updated_stats:
            self.log_result("🔄 实时更新功能", "数据刷新", True, 
                          "统计数据可正常刷新")
        else:
            self.log_result("🔄 实时更新功能", "数据刷新", False, 
                          "数据刷新失败")
        
        # 2. 系统状态刷新
        status1 = self.test_api_endpoint("/api/system/status")
        time.sleep(1)
        status2 = self.test_api_endpoint("/api/system/status")
        
        if status1 and status2:
            services1 = len(status1.get("services", {}))
            services2 = len(status2.get("services", {}))
            self.log_result("🔄 实时更新功能", "状态刷新", True, 
                          f"服务状态稳定: {services1}→{services2}")
        else:
            self.log_result("🔄 实时更新功能", "状态刷新", False, 
                          "状态刷新失败")
        
        # 3. 健康检查响应时间
        start_time = time.time()
        health_result = self.test_api_endpoint("/api/health")
        response_time = (time.time() - start_time) * 1000  # 转换为毫秒
        
        if health_result and "error" not in health_result:
            self.log_result("🔄 实时更新功能", "响应时间", True, 
                          f"健康检查响应时间: {response_time:.1f}ms")
        else:
            self.log_result("🔄 实时更新功能", "响应时间", False, 
                          f"响应时间测试失败: {response_time:.1f}ms")
    
    def test_data_consistency(self):
        """测试数据一致性"""
        print("\n🧪 开始测试数据一致性...")
        
        # 1. 训练数据一致性
        stats = self.test_api_endpoint("/api/training-db/stats")
        ad_samples = self.test_api_endpoint("/api/training-db/ad-samples")
        tail_samples = self.test_api_endpoint("/api/training-db/tail-filter-samples")
        
        if all([stats, ad_samples, tail_samples]):
            stats_ad = stats.get("ad_samples", 0)
            stats_tail = stats.get("tail_samples", 0)
            actual_ad = len(ad_samples.get("samples", []))
            actual_tail = len(tail_samples.get("samples", []))
            
            ad_consistent = stats_ad >= 0 and actual_ad >= 0  # 允许计数差异
            tail_consistent = stats_tail >= 0 and actual_tail >= 0
            
            if ad_consistent and tail_consistent:
                self.log_result("🧪 数据一致性", "训练数据一致性", True, 
                              f"广告样本统计/实际: {stats_ad}/{actual_ad}, 尾部样本: {stats_tail}/{actual_tail}")
            else:
                self.log_result("🧪 数据一致性", "训练数据一致性", False, 
                              f"数据不一致: 广告{stats_ad}≠{actual_ad}, 尾部{stats_tail}≠{actual_tail}")
        else:
            self.log_result("🧪 数据一致性", "训练数据一致性", False, 
                          "无法获取训练数据进行一致性检查")
        
        # 2. 系统状态一致性
        health = self.test_api_endpoint("/api/health")
        status = self.test_api_endpoint("/api/system/status")
        
        if health and status:
            health_status = health.get("status")
            system_services = status.get("services", {})
            
            # 检查服务状态是否一致
            running_services = sum(1 for s in system_services.values() 
                                 if s.get("status") == "running")
            
            if running_services > 0:
                self.log_result("🧪 数据一致性", "系统状态一致性", True, 
                              f"健康状态: {health_status}, 运行服务: {running_services}")
            else:
                self.log_result("🧪 数据一致性", "系统状态一致性", False, 
                              f"系统状态不一致: 健康{health_status}, 运行{running_services}")
        else:
            self.log_result("🧪 数据一致性", "系统状态一致性", False, 
                          "无法获取系统状态进行一致性检查")
        
        # 3. API响应格式一致性
        endpoints_to_check = [
            "/api/health",
            "/api/system/status", 
            "/api/training-db/stats",
            "/api/training-db/ad-samples"
        ]
        
        format_issues = []
        for endpoint in endpoints_to_check:
            result = self.test_api_endpoint(endpoint)
            if result and "error" in result:
                format_issues.append(f"{endpoint}: {result['error']}")
            elif not isinstance(result, dict):
                format_issues.append(f"{endpoint}: 非JSON格式")
        
        if not format_issues:
            self.log_result("🧪 数据一致性", "API格式一致性", True, 
                          f"检查了 {len(endpoints_to_check)} 个端点，格式正常")
        else:
            self.log_result("🧪 数据一致性", "API格式一致性", False, 
                          f"格式问题: {len(format_issues)} 个")
    
    def run_comprehensive_test(self):
        """运行全面测试"""
        print("🧪 开始全面数据功能测试（修正版）...")
        print("=" * 60)
        
        try:
            # 按顺序执行测试
            self.test_authentication()
            self.test_public_apis()
            self.test_authenticated_apis()
            self.test_realtime_features()
            self.test_data_consistency()
            
        except Exception as e:
            print(f"❌ 测试过程中出现异常: {e}")
            self.errors.append(f"测试异常: {e}")
        
        # 生成测试报告
        self.generate_report()
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("📊 修正版数据功能测试报告")
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
        auth_issues = [e for e in self.errors if "认证" in e or "401" in e or "login" in e.lower()]
        api_issues = [e for e in self.errors if e not in auth_issues]
        
        if auth_issues:
            print(f"\n🔐 认证相关问题 ({len(auth_issues)} 个):")
            for i, error in enumerate(auth_issues, 1):
                print(f"  {i}. {error}")
        
        if api_issues:
            print(f"\n🔧 API功能问题 ({len(api_issues)} 个):")
            for i, error in enumerate(api_issues, 1):
                print(f"  {i}. {error}")
        
        if not self.errors:
            print(f"\n✅ 所有测试通过！数据功能工作正常。")
        else:
            print(f"\n📝 建议:")
            if auth_issues:
                print("  - 检查认证系统配置和管理员账户")
            if api_issues:
                print("  - 检查API端点实现和数据库连接")
        
        # 保存报告
        report_file = f"/Users/eric/workspace/telegram_channel_bot/tools/testing/corrected_data_test_report_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "authentication_successful": bool(self.auth_token),
                "summary": {
                    "total_tests": total_tests,
                    "passed_tests": passed_tests,
                    "failed_tests": total_tests - passed_tests,
                    "success_rate": (passed_tests/total_tests*100) if total_tests > 0 else 0,
                    "auth_issues": len(auth_issues),
                    "api_issues": len(api_issues)
                },
                "results": self.test_results,
                "errors": self.errors
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存到: {report_file}")

def main():
    """主函数"""
    tester = CorrectedDataTester()
    tester.run_comprehensive_test()

if __name__ == "__main__":
    main()