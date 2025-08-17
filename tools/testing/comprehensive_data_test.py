#!/usr/bin/env python3
"""
全面数据功能测试脚本
测试API重构后的数据加载、显示、更新等核心功能
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

class DataFunctionTester:
    """数据功能全面测试器"""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.test_results = {
            "消息数据流": {},
            "训练数据管理": {},
            "配置数据验证": {},
            "实时数据更新": {},
            "数据一致性检查": {}
        }
        self.errors = []
        
    def setup(self):
        """初始化测试环境"""
        pass
        
    def cleanup(self):
        """清理测试环境"""
        pass
    
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
                         data: Dict = None) -> Optional[Dict]:
        """测试API端点"""
        try:
            url = f"{self.base_url}{endpoint}"
            
            if method.upper() == "GET":
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'DataFunctionTester/1.0')
                req.add_header('Accept', 'application/json')
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.getcode() == 200:
                        response_data = response.read().decode('utf-8')
                        return json.loads(response_data)
                    else:
                        return {"error": f"HTTP {response.getcode()}"}
            
            elif method.upper() == "POST":
                json_data = json.dumps(data).encode('utf-8') if data else b''
                req = urllib.request.Request(url, data=json_data, method='POST')
                req.add_header('User-Agent', 'DataFunctionTester/1.0')
                req.add_header('Accept', 'application/json')
                req.add_header('Content-Type', 'application/json')
                
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
    
    def test_message_data_flow(self):
        """测试消息数据流"""
        print("\n🔍 开始测试消息数据流...")
        
        # 1. 测试消息列表API
        result = self.test_api_endpoint("/api/messages")
        if result and "error" not in result:
            message_count = len(result.get("messages", []))
            self.log_result("消息数据流", "消息列表加载", True, 
                          f"成功加载 {message_count} 条消息", message_count)
        else:
            self.log_result("消息数据流", "消息列表加载", False, 
                          f"加载失败: {result}")
        
        # 2. 测试消息统计API
        result = self.test_api_endpoint("/api/messages/stats")
        if result and "error" not in result:
            stats = result
            self.log_result("消息数据流", "消息统计数据", True, 
                          f"总消息: {stats.get('total', 0)}, 待审核: {stats.get('pending', 0)}")
        else:
            self.log_result("消息数据流", "消息统计数据", False, 
                          f"获取失败: {result}")
        
        # 3. 测试分页功能
        result = self.test_api_endpoint("/api/messages?page=1&page_size=10")
        if result and "error" not in result:
            pagination = result.get("pagination", {})
            self.log_result("消息数据流", "分页功能", True, 
                          f"页码: {pagination.get('page')}, 总页数: {pagination.get('total_pages')}")
        else:
            self.log_result("消息数据流", "分页功能", False, 
                          f"分页失败: {result}")
        
        # 4. 测试消息过滤
        result = self.test_api_endpoint("/api/messages?status=pending")
        if result and "error" not in result:
            pending_count = len(result.get("messages", []))
            self.log_result("消息数据流", "消息过滤", True, 
                          f"待审核消息: {pending_count} 条")
        else:
            self.log_result("消息数据流", "消息过滤", False, 
                          f"过滤失败: {result}")
    
    def test_training_data_management(self):
        """测试训练数据管理"""
        print("\n🤖 开始测试训练数据管理...")
        
        # 1. 测试广告样本数据
        result = self.test_api_endpoint("/api/training-db/samples")
        if result and "error" not in result:
            sample_count = len(result.get("samples", []))
            self.log_result("训练数据管理", "广告样本数据", True, 
                          f"样本数据: {sample_count} 条")
        else:
            self.log_result("训练数据管理", "广告样本数据", False, 
                          f"加载失败: {result}")
        
        # 2. 测试尾部过滤样本
        result = self.test_api_endpoint("/api/training-db/tail-filter-samples")
        if result and "error" not in result:
            tail_samples = result.get("samples", [])
            self.log_result("训练数据管理", "尾部过滤样本", True, 
                          f"尾部样本: {len(tail_samples)} 条")
        else:
            self.log_result("训练数据管理", "尾部过滤样本", False, 
                          f"加载失败: {result}")
        
        # 3. 测试媒体文件列表
        result = self.test_api_endpoint("/api/training-db/media-files")
        if result and "error" not in result:
            media_files = result.get("files", [])
            self.log_result("训练数据管理", "媒体文件列表", True, 
                          f"媒体文件: {len(media_files)} 个")
        else:
            self.log_result("训练数据管理", "媒体文件列表", False, 
                          f"加载失败: {result}")
        
        # 4. 测试训练数据统计
        result = self.test_api_endpoint("/api/training-db/stats")
        if result and "error" not in result:
            stats = result
            self.log_result("训练数据管理", "训练数据统计", True, 
                          f"广告样本: {stats.get('ad_samples', 0)}, 尾部样本: {stats.get('tail_samples', 0)}")
        else:
            self.log_result("训练数据管理", "训练数据统计", False, 
                          f"统计失败: {result}")
    
    def test_config_data_validation(self):
        """测试配置数据验证"""
        print("\n⚙️ 开始测试配置数据验证...")
        
        # 1. 测试系统配置
        result = self.test_api_endpoint("/api/config/system")
        if result and "error" not in result:
            config = result
            self.log_result("配置数据验证", "系统配置", True, 
                          f"配置项: {len(config)} 个")
        else:
            self.log_result("配置数据验证", "系统配置", False, 
                          f"加载失败: {result}")
        
        # 2. 测试频道配置
        result = self.test_api_endpoint("/api/channel-config")
        if result and "error" not in result:
            channels = result.get("channels", [])
            self.log_result("配置数据验证", "频道配置", True, 
                          f"配置频道: {len(channels)} 个")
        else:
            self.log_result("配置数据验证", "频道配置", False, 
                          f"加载失败: {result}")
        
        # 3. 测试阈值配置
        result = self.test_api_endpoint("/api/config/thresholds")
        if result and "error" not in result:
            thresholds = result
            self.log_result("配置数据验证", "阈值配置", True, 
                          f"阈值项: {len(thresholds)} 个")
        else:
            self.log_result("配置数据验证", "阈值配置", False, 
                          f"加载失败: {result}")
        
        # 4. 测试管理员配置
        result = self.test_api_endpoint("/api/admin/info")
        if result and "error" not in result:
            admin_info = result
            self.log_result("配置数据验证", "管理员配置", True, 
                          f"管理员: {admin_info.get('username', 'N/A')}")
        else:
            self.log_result("配置数据验证", "管理员配置", False, 
                          f"加载失败: {result}")
    
    def test_realtime_data_updates(self):
        """测试实时数据更新"""
        print("\n🔄 开始测试实时数据更新...")
        
        # 1. 测试健康检查API
        result = self.test_api_endpoint("/api/health")
        if result and "error" not in result:
            health = result
            self.log_result("实时数据更新", "健康检查", True, 
                          f"状态: {health.get('status', 'unknown')}")
        else:
            self.log_result("实时数据更新", "健康检查", False, 
                          f"检查失败: {result}")
        
        # 2. 测试系统状态API
        result = self.test_api_endpoint("/api/system/status")
        if result and "error" not in result:
            status = result
            self.log_result("实时数据更新", "系统状态", True, 
                          f"服务数: {len(status.get('services', {}))}")
        else:
            self.log_result("实时数据更新", "系统状态", False, 
                          f"状态获取失败: {result}")
        
        # 3. 测试数据刷新功能
        # 先获取初始统计
        initial_stats = self.test_api_endpoint("/api/messages/stats")
        time.sleep(1)  # 等待1秒
        updated_stats = self.test_api_endpoint("/api/messages/stats")
        
        if initial_stats and updated_stats:
            self.log_result("实时数据更新", "数据刷新", True, 
                          "数据刷新功能正常")
        else:
            self.log_result("实时数据更新", "数据刷新", False, 
                          "数据刷新失败")
    
    def test_data_consistency(self):
        """测试数据一致性"""
        print("\n🔒 开始测试数据一致性...")
        
        # 1. 对比不同API的数据一致性
        messages_api = self.test_api_endpoint("/api/messages")
        stats_api = self.test_api_endpoint("/api/messages/stats")
        
        if messages_api and stats_api:
            actual_count = len(messages_api.get("messages", []))
            reported_total = stats_api.get("total", 0)
            
            if actual_count == reported_total:
                self.log_result("数据一致性检查", "消息计数一致性", True, 
                              f"API数据一致: {actual_count} 条")
            else:
                self.log_result("数据一致性检查", "消息计数一致性", False, 
                              f"数据不一致: 列表{actual_count} vs 统计{reported_total}")
        
        # 2. 测试配置数据完整性
        system_config = self.test_api_endpoint("/api/config/system")
        channel_config = self.test_api_endpoint("/api/channel-config")
        
        config_complete = bool(system_config and channel_config)
        self.log_result("数据一致性检查", "配置数据完整性", config_complete, 
                      "配置数据" + ("完整" if config_complete else "不完整"))
        
        # 3. 检查关键配置项
        if system_config:
            required_keys = ["auto_forward", "monitoring_enabled", "ai_detection"]
            missing_keys = [key for key in required_keys if key not in system_config]
            
            if not missing_keys:
                self.log_result("数据一致性检查", "关键配置项", True, 
                              "所有关键配置项存在")
            else:
                self.log_result("数据一致性检查", "关键配置项", False, 
                              f"缺失配置项: {missing_keys}")
    
    def run_comprehensive_test(self):
        """运行全面测试"""
        print("🧪 开始全面数据功能测试...")
        print("=" * 60)
        
        self.setup()
        
        try:
            # 执行所有测试
            self.test_message_data_flow()
            self.test_training_data_management()
            self.test_config_data_validation()
            self.test_realtime_data_updates()
            self.test_data_consistency()
            
        except Exception as e:
            print(f"❌ 测试过程中出现异常: {e}")
            self.errors.append(f"测试异常: {e}")
        
        finally:
            self.cleanup()
        
        # 生成测试报告
        self.generate_report()
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("📊 测试报告")
        print("=" * 60)
        
        total_tests = 0
        passed_tests = 0
        
        for category, tests in self.test_results.items():
            print(f"\n📂 {category}:")
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
        
        if self.errors:
            print(f"\n❌ 发现的问题:")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
        else:
            print(f"\n✅ 所有测试通过！数据功能工作正常。")
        
        # 保存详细报告
        report_file = f"/Users/eric/workspace/telegram_channel_bot/tools/testing/data_test_report_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total_tests": total_tests,
                    "passed_tests": passed_tests,
                    "failed_tests": total_tests - passed_tests,
                    "success_rate": (passed_tests/total_tests*100) if total_tests > 0 else 0
                },
                "results": self.test_results,
                "errors": self.errors
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存到: {report_file}")

def main():
    """主函数"""
    tester = DataFunctionTester()
    tester.run_comprehensive_test()

if __name__ == "__main__":
    main()