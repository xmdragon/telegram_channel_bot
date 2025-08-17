#!/usr/bin/env python3
"""
数据功能测试综合报告
汇总所有测试结果，生成最终的数据功能评估报告
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

class ComprehensiveDataTestSummary:
    """数据功能测试综合汇总"""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.auth_token = None
        self.test_results = {}
        self.errors = []
        self.summary_data = {
            "测试时间": datetime.now().isoformat(),
            "系统信息": {},
            "数据存储状态": {},
            "API功能状态": {},
            "前端页面状态": {},
            "数据一致性状态": {},
            "性能指标": {},
            "发现的问题": [],
            "改进建议": []
        }
        
    def authenticate(self):
        """执行认证"""
        try:
            login_data = {
                "username": "admin",
                "password": "admin123"
            }
            
            json_data = json.dumps(login_data).encode('utf-8')
            req = urllib.request.Request(
                f"{self.base_url}/api/admin/auth/login", 
                data=json_data, 
                method='POST'
            )
            req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.getcode() == 200:
                    result = json.loads(response.read().decode('utf-8'))
                    if result.get("success"):
                        self.auth_token = result.get("token")
                        return True
            return False
        except:
            return False
    
    def test_api_endpoint(self, endpoint: str, need_auth: bool = False) -> Optional[Dict]:
        """测试API端点"""
        try:
            req = urllib.request.Request(f"{self.base_url}{endpoint}")
            req.add_header('Accept', 'application/json')
            
            if need_auth and self.auth_token:
                req.add_header('Authorization', f'Bearer {self.auth_token}')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.getcode() == 200:
                    return json.loads(response.read().decode('utf-8'))
                else:
                    return {"error": f"HTTP {response.getcode()}"}
        except Exception as e:
            return {"error": str(e)}
    
    def test_static_page(self, path: str) -> bool:
        """测试静态页面"""
        try:
            req = urllib.request.Request(f"{self.base_url}{path}")
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.getcode() == 200:
                    content = response.read().decode('utf-8')
                    return '<html' in content.lower()
            return False
        except:
            return False
    
    def analyze_system_info(self):
        """分析系统信息"""
        print("🔍 分析系统信息...")
        
        # 系统健康状态
        health = self.test_api_endpoint("/api/health")
        system_status = self.test_api_endpoint("/api/system/status")
        
        if health:
            self.summary_data["系统信息"]["健康状态"] = health.get("status", "unknown")
        
        if system_status and "services" in system_status:
            services = system_status["services"]
            running_services = sum(1 for s in services.values() if s.get("status") == "running")
            self.summary_data["系统信息"]["运行服务数"] = f"{running_services}/{len(services)}"
            self.summary_data["系统信息"]["服务列表"] = list(services.keys())
        
        print(f"✅ 系统信息分析完成")
    
    def analyze_data_storage(self):
        """分析数据存储状态"""
        print("💾 分析数据存储状态...")
        
        # 消息数据
        if self.auth_token:
            messages = self.test_api_endpoint("/api/messages", need_auth=True)
            if messages and "error" not in messages:
                message_count = len(messages.get("messages", []))
                pagination = messages.get("pagination", {})
                self.summary_data["数据存储状态"]["消息数据"] = {
                    "当前页消息数": message_count,
                    "总消息数": pagination.get("total", "未知"),
                    "状态": "正常"
                }
            else:
                self.summary_data["数据存储状态"]["消息数据"] = {
                    "状态": "异常",
                    "错误": str(messages)
                }
        
        # 训练数据
        training_stats = self.test_api_endpoint("/api/training-db/stats")
        ad_samples = self.test_api_endpoint("/api/training-db/ad-samples")
        tail_samples = self.test_api_endpoint("/api/training-db/tail-filter-samples")
        media_files = self.test_api_endpoint("/api/training-db/media-files")
        
        training_data_status = {}
        if training_stats and "error" not in training_stats:
            training_data_status["统计数据"] = training_stats
        
        if ad_samples and "error" not in ad_samples:
            training_data_status["广告样本数"] = len(ad_samples.get("samples", []))
        
        if tail_samples and "error" not in tail_samples:
            training_data_status["尾部过滤样本数"] = len(tail_samples.get("samples", []))
        
        if media_files and "error" not in media_files:
            training_data_status["媒体文件数"] = len(media_files.get("files", []))
        
        self.summary_data["数据存储状态"]["训练数据"] = training_data_status
        
        print(f"✅ 数据存储状态分析完成")
    
    def analyze_api_functionality(self):
        """分析API功能状态"""
        print("🔌 分析API功能状态...")
        
        api_tests = [
            ("/api/health", "健康检查", False),
            ("/api/system/status", "系统状态", False),
            ("/api/training-db/stats", "训练数据统计", False),
            ("/api/training-db/ad-samples", "广告样本", False),
            ("/api/training-db/tail-filter-samples", "尾部过滤样本", False),
            ("/api/training-db/media-files", "媒体文件", False),
            ("/api/messages", "消息列表", True),
        ]
        
        api_status = {}
        working_apis = 0
        total_apis = len(api_tests)
        
        for endpoint, name, needs_auth in api_tests:
            result = self.test_api_endpoint(endpoint, need_auth=needs_auth)
            if result and "error" not in result:
                api_status[name] = "正常"
                working_apis += 1
            else:
                api_status[name] = f"异常: {result}"
                self.errors.append(f"API异常 - {name}: {result}")
        
        self.summary_data["API功能状态"] = {
            "总体状态": f"{working_apis}/{total_apis} API正常",
            "成功率": f"{(working_apis/total_apis*100):.1f}%",
            "详细状态": api_status
        }
        
        print(f"✅ API功能状态分析完成 ({working_apis}/{total_apis} 正常)")
    
    def analyze_frontend_pages(self):
        """分析前端页面状态"""
        print("📄 分析前端页面状态...")
        
        pages_to_test = [
            ("/static/login.html", "登录页面"),
            ("/static/index.html", "消息管理主页"),
            ("/static/tail-filter-manager.html", "尾部过滤管理"),
            ("/static/media-manager.html", "媒体管理页面"),
            ("/static/config.html", "系统配置页面"),
            ("/static/threshold-dashboard.html", "阈值监控页面"),
            ("/static/training-data-manager.html", "训练数据管理"),
        ]
        
        page_status = {}
        working_pages = 0
        total_pages = len(pages_to_test)
        
        for path, name in pages_to_test:
            if self.test_static_page(path):
                page_status[name] = "可访问"
                working_pages += 1
            else:
                page_status[name] = "不可访问"
                self.errors.append(f"页面访问异常 - {name}: {path}")
        
        self.summary_data["前端页面状态"] = {
            "总体状态": f"{working_pages}/{total_pages} 页面可访问",
            "成功率": f"{(working_pages/total_pages*100):.1f}%",
            "详细状态": page_status
        }
        
        print(f"✅ 前端页面状态分析完成 ({working_pages}/{total_pages} 可访问)")
    
    def analyze_data_consistency(self):
        """分析数据一致性"""
        print("🔒 分析数据一致性...")
        
        consistency_issues = []
        
        # 训练数据一致性检查
        stats = self.test_api_endpoint("/api/training-db/stats")
        ad_samples = self.test_api_endpoint("/api/training-db/ad-samples")
        tail_samples = self.test_api_endpoint("/api/training-db/tail-filter-samples")
        
        if all([stats, ad_samples, tail_samples]):
            stats_ad = stats.get("ad_samples", 0)
            stats_tail = stats.get("tail_samples", 0)
            actual_ad = len(ad_samples.get("samples", []))
            actual_tail = len(tail_samples.get("samples", []))
            
            if stats_ad != actual_ad:
                consistency_issues.append(f"广告样本计数不一致: 统计{stats_ad} vs 实际{actual_ad}")
            
            if stats_tail != actual_tail:
                consistency_issues.append(f"尾部样本计数不一致: 统计{stats_tail} vs 实际{actual_tail}")
        
        # API响应格式一致性
        format_issues = []
        test_endpoints = ["/api/health", "/api/system/status", "/api/training-db/stats"]
        
        for endpoint in test_endpoints:
            result = self.test_api_endpoint(endpoint)
            if not isinstance(result, dict):
                format_issues.append(f"{endpoint}: 响应格式异常")
        
        self.summary_data["数据一致性状态"] = {
            "一致性问题": consistency_issues,
            "格式问题": format_issues,
            "总体状态": "正常" if not consistency_issues and not format_issues else "存在问题"
        }
        
        print(f"✅ 数据一致性分析完成")
    
    def analyze_performance(self):
        """分析性能指标"""
        print("⚡ 分析性能指标...")
        
        # 测试API响应时间
        response_times = {}
        
        test_endpoints = [
            "/api/health",
            "/api/system/status",
            "/api/training-db/stats"
        ]
        
        for endpoint in test_endpoints:
            start_time = time.time()
            result = self.test_api_endpoint(endpoint)
            end_time = time.time()
            
            response_time = (end_time - start_time) * 1000  # 转换为毫秒
            response_times[endpoint] = f"{response_time:.1f}ms"
        
        avg_response_time = sum(float(t.replace('ms', '')) for t in response_times.values()) / len(response_times)
        
        self.summary_data["性能指标"] = {
            "平均API响应时间": f"{avg_response_time:.1f}ms",
            "各端点响应时间": response_times,
            "性能评级": "优秀" if avg_response_time < 100 else "良好" if avg_response_time < 500 else "需要优化"
        }
        
        print(f"✅ 性能指标分析完成 (平均响应时间: {avg_response_time:.1f}ms)")
    
    def generate_improvement_suggestions(self):
        """生成改进建议"""
        print("💡 生成改进建议...")
        
        suggestions = []
        
        # 基于错误分析生成建议
        api_errors = [e for e in self.errors if "API异常" in e]
        page_errors = [e for e in self.errors if "页面访问异常" in e]
        
        if api_errors:
            suggestions.append({
                "类型": "API功能改进",
                "问题": f"发现 {len(api_errors)} 个API异常",
                "建议": "检查API路由配置、数据库连接和权限设置"
            })
        
        if page_errors:
            suggestions.append({
                "类型": "前端页面改进",
                "问题": f"发现 {len(page_errors)} 个页面访问问题",
                "建议": "检查静态文件路径和服务器配置"
            })
        
        # 检查数据存储问题
        training_data = self.summary_data["数据存储状态"].get("训练数据", {})
        if "广告样本数" in training_data and "统计数据" in training_data:
            stats = training_data["统计数据"]
            actual = training_data["广告样本数"]
            if stats.get("ad_samples", 0) != actual:
                suggestions.append({
                    "类型": "数据一致性改进",
                    "问题": "训练数据统计与实际数据不一致",
                    "建议": "同步更新统计缓存或修复计数逻辑"
                })
        
        # 检查性能问题
        perf = self.summary_data["性能指标"]
        avg_time = float(perf["平均API响应时间"].replace('ms', ''))
        if avg_time > 200:
            suggestions.append({
                "类型": "性能优化",
                "问题": f"API平均响应时间较高 ({avg_time:.1f}ms)",
                "建议": "优化数据库查询、添加缓存机制或优化算法"
            })
        
        if not suggestions:
            suggestions.append({
                "类型": "系统维护",
                "问题": "系统整体运行良好",
                "建议": "继续保持当前的监控和维护策略"
            })
        
        self.summary_data["改进建议"] = suggestions
        
        print(f"✅ 改进建议生成完成 ({len(suggestions)} 条建议)")
    
    def run_comprehensive_analysis(self):
        """运行全面分析"""
        print("🧪 开始全面数据功能分析...")
        print("=" * 60)
        
        # 先尝试认证
        auth_success = self.authenticate()
        if auth_success:
            print("✅ 认证成功")
        else:
            print("❌ 认证失败，部分功能可能无法测试")
        
        try:
            self.analyze_system_info()
            self.analyze_data_storage()
            self.analyze_api_functionality()
            self.analyze_frontend_pages()
            self.analyze_data_consistency()
            self.analyze_performance()
            self.generate_improvement_suggestions()
            
        except Exception as e:
            print(f"❌ 分析过程中出现异常: {e}")
            self.errors.append(f"分析异常: {e}")
        
        # 汇总发现的问题
        self.summary_data["发现的问题"] = self.errors
        
        # 生成最终报告
        self.generate_final_report()
    
    def generate_final_report(self):
        """生成最终报告"""
        print("\n" + "=" * 60)
        print("📊 数据功能全面测试综合报告")
        print("=" * 60)
        
        # 显示系统信息
        print(f"\n🖥️  系统信息:")
        system_info = self.summary_data["系统信息"]
        print(f"  健康状态: {system_info.get('健康状态', '未知')}")
        print(f"  运行服务: {system_info.get('运行服务数', '未知')}")
        
        # 显示数据存储状态
        print(f"\n💾 数据存储状态:")
        storage = self.summary_data["数据存储状态"]
        if "消息数据" in storage:
            msg_data = storage["消息数据"]
            print(f"  消息数据: {msg_data.get('状态', '未知')}")
        if "训练数据" in storage:
            training = storage["训练数据"]
            print(f"  广告样本: {training.get('广告样本数', 0)} 条")
            print(f"  尾部样本: {training.get('尾部过滤样本数', 0)} 条")
            print(f"  媒体文件: {training.get('媒体文件数', 0)} 个")
        
        # 显示API功能状态
        print(f"\n🔌 API功能状态:")
        api_status = self.summary_data["API功能状态"]
        print(f"  总体状态: {api_status.get('总体状态', '未知')}")
        print(f"  成功率: {api_status.get('成功率', '未知')}")
        
        # 显示前端页面状态
        print(f"\n📄 前端页面状态:")
        page_status = self.summary_data["前端页面状态"]
        print(f"  总体状态: {page_status.get('总体状态', '未知')}")
        print(f"  成功率: {page_status.get('成功率', '未知')}")
        
        # 显示性能指标
        print(f"\n⚡ 性能指标:")
        perf = self.summary_data["性能指标"]
        print(f"  平均响应时间: {perf.get('平均API响应时间', '未知')}")
        print(f"  性能评级: {perf.get('性能评级', '未知')}")
        
        # 显示发现的问题
        problems = self.summary_data["发现的问题"]
        if problems:
            print(f"\n❌ 发现的问题 ({len(problems)} 个):")
            for i, problem in enumerate(problems, 1):
                print(f"  {i}. {problem}")
        else:
            print(f"\n✅ 未发现问题")
        
        # 显示改进建议
        suggestions = self.summary_data["改进建议"]
        print(f"\n💡 改进建议 ({len(suggestions)} 条):")
        for i, suggestion in enumerate(suggestions, 1):
            print(f"  {i}. [{suggestion['类型']}] {suggestion['问题']}")
            print(f"     建议: {suggestion['建议']}")
        
        # 总体评估
        total_errors = len(problems)
        api_success_rate = float(self.summary_data["API功能状态"].get("成功率", "0%").replace("%", ""))
        page_success_rate = float(self.summary_data["前端页面状态"].get("成功率", "0%").replace("%", ""))
        
        overall_score = (api_success_rate + page_success_rate) / 2
        
        print(f"\n📈 总体评估:")
        print(f"  综合得分: {overall_score:.1f}/100")
        if overall_score >= 90:
            rating = "优秀 🌟"
        elif overall_score >= 80:
            rating = "良好 👍"
        elif overall_score >= 70:
            rating = "及格 ✅"
        else:
            rating = "需要改进 ⚠️"
        print(f"  评级: {rating}")
        
        # 保存详细报告
        report_file = f"/Users/eric/workspace/telegram_channel_bot/tools/testing/comprehensive_data_test_summary_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.summary_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存到: {report_file}")
        
        # 输出测试结论
        print(f"\n🏁 测试结论:")
        if total_errors == 0:
            print("  ✅ 数据功能运行正常，API重构成功")
        elif total_errors <= 3:
            print("  ⚠️  数据功能基本正常，存在少量问题需要修复")
        else:
            print("  ❌ 数据功能存在多个问题，需要重点关注和修复")

def main():
    """主函数"""
    analyzer = ComprehensiveDataTestSummary()
    analyzer.run_comprehensive_analysis()

if __name__ == "__main__":
    main()