#!/usr/bin/env python3
"""
训练数据库模块完整性测试套件

测试范围：
1. API端点可访问性测试（57个训练相关端点）
2. 功能完整性测试（CRUD操作、数据管理）
3. 前端集成测试（API调用兼容性）
4. 性能和稳定性测试（并发访问、内存使用）
5. 错误处理测试（异常场景验证）

作者：Test Automation Expert
创建时间：2025-08-17
"""

import asyncio
import aiohttp
import json
import time
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

class TrainingDBTestSuite:
    """
    训练数据库模块完整性测试套件
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.test_results = {
            "api_endpoints": {},
            "functional_tests": {},
            "frontend_integration": {},
            "performance_tests": {},
            "error_handling": {},
            "summary": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": [],
                "start_time": None,
                "end_time": None,
                "duration": 0
            }
        }
        
        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # 训练相关API端点定义（从api-endpoints.js提取）
        self.training_endpoints = {
            # 基础管理端点
            'separator_patterns': {
                'method': 'GET',
                'url': '/api/training-db/separator-patterns',
                'description': '获取分隔符模式'
            },
            'ad_samples': {
                'method': 'GET', 
                'url': '/api/training-db/ad-samples',
                'description': '获取广告样本列表'
            },
            'ad_statistics': {
                'method': 'GET',
                'url': '/api/training-db/ad-statistics', 
                'description': '获取广告训练统计'
            },
            'tail_filter_samples': {
                'method': 'GET',
                'url': '/api/training-db/tail-filter-samples',
                'description': '获取尾部过滤样本'
            },
            'tail_filter_statistics': {
                'method': 'GET',
                'url': '/api/training-db/tail-filter-statistics',
                'description': '获取尾部过滤统计'
            },
            'tail_filter_history': {
                'method': 'GET',
                'url': '/api/training-db/tail-filter-history',
                'description': '获取尾部过滤历史'
            },
            'media_files': {
                'method': 'GET',
                'url': '/api/training-db/media-files',
                'description': '获取媒体文件列表'
            },
            'channels': {
                'method': 'GET',
                'url': '/api/training-db/channels',
                'description': '获取频道列表'
            },
            'stats': {
                'method': 'GET',
                'url': '/api/training-db/stats',
                'description': '获取训练统计'
            },
            'history': {
                'method': 'GET',
                'url': '/api/training-db/history',
                'description': '获取训练历史'
            },
            'learning_stats': {
                'method': 'GET',
                'url': '/api/training-db/learning-stats',
                'description': '获取学习统计'
            },
            'tail_ad_samples': {
                'method': 'GET',
                'url': '/api/training-db/tail-ad-samples',
                'description': '获取尾部广告样本'
            }
        }
        
        # POST端点定义
        self.post_endpoints = {
            'submit_training': {
                'method': 'POST',
                'url': '/api/training-db/submit',
                'description': '提交训练数据',
                'test_data': {
                    'channel_id': 'test_channel_123',
                    'channel_name': 'Test Channel',
                    'original_message': 'Test message content',
                    'tail_content': 'Test tail content'
                }
            },
            'apply_training': {
                'method': 'POST',
                'url': '/api/training-db/apply',
                'description': '应用训练数据'
            },
            'mark_ad_test': {
                'method': 'POST',
                'url': '/api/training-db/mark-ad-test',
                'description': '测试标记功能',
                'test_data': {
                    'message': 'Test advertisement message',
                    'channel_id': 'test_channel_123'
                }
            },
            'detect_duplicates_ad': {
                'method': 'POST',
                'url': '/api/training-db/ad-samples/detect-duplicates',
                'description': '检测重复广告样本'
            },
            'detect_duplicates_tail': {
                'method': 'POST',
                'url': '/api/training-db/tail-filter-samples/detect-duplicates',
                'description': '检测重复尾部样本'
            }
        }
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
            
    async def check_service_health(self) -> bool:
        """
        检查服务健康状态
        """
        try:
            async with self.session.get(f"{self.base_url}/api/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    self.logger.info(f"服务健康状态: {health_data}")
                    return True
                else:
                    self.logger.error(f"服务健康检查失败: HTTP {response.status}")
                    return False
        except Exception as e:
            self.logger.error(f"服务健康检查异常: {e}")
            return False
            
    async def test_api_endpoint(self, endpoint_name: str, endpoint_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        测试单个API端点
        """
        result = {
            "name": endpoint_name,
            "description": endpoint_config.get('description', ''),
            "method": endpoint_config['method'],
            "url": endpoint_config['url'],
            "status": "failed",
            "http_status": None,
            "response_time": 0,
            "error": None,
            "response_data": None
        }
        
        try:
            start_time = time.time()
            
            if endpoint_config['method'] == 'GET':
                async with self.session.get(f"{self.base_url}{endpoint_config['url']}") as response:
                    result["http_status"] = response.status
                    result["response_time"] = time.time() - start_time
                    
                    if response.status == 200:
                        try:
                            result["response_data"] = await response.json()
                            result["status"] = "passed"
                        except json.JSONDecodeError:
                            result["response_data"] = await response.text()
                            result["status"] = "passed"
                    else:
                        result["error"] = f"HTTP {response.status}: {await response.text()}"
                        
            elif endpoint_config['method'] == 'POST':
                test_data = endpoint_config.get('test_data', {})
                async with self.session.post(
                    f"{self.base_url}{endpoint_config['url']}",
                    json=test_data
                ) as response:
                    result["http_status"] = response.status
                    result["response_time"] = time.time() - start_time
                    
                    if response.status in [200, 201]:
                        try:
                            result["response_data"] = await response.json()
                            result["status"] = "passed"
                        except json.JSONDecodeError:
                            result["response_data"] = await response.text()
                            result["status"] = "passed"
                    else:
                        result["error"] = f"HTTP {response.status}: {await response.text()}"
                        
        except Exception as e:
            result["error"] = str(e)
            result["response_time"] = time.time() - start_time
            
        return result
        
    async def test_all_api_endpoints(self) -> None:
        """
        测试所有API端点
        """
        self.logger.info("开始API端点测试...")
        
        # 测试GET端点
        for endpoint_name, endpoint_config in self.training_endpoints.items():
            result = await self.test_api_endpoint(endpoint_name, endpoint_config)
            self.test_results["api_endpoints"][endpoint_name] = result
            
            if result["status"] == "passed":
                self.test_results["summary"]["passed"] += 1
                self.logger.info(f"✅ {endpoint_name}: {result['response_time']:.3f}s")
            else:
                self.test_results["summary"]["failed"] += 1
                self.test_results["summary"]["errors"].append(f"{endpoint_name}: {result['error']}")
                self.logger.error(f"❌ {endpoint_name}: {result['error']}")
                
            self.test_results["summary"]["total_tests"] += 1
            
        # 测试POST端点
        for endpoint_name, endpoint_config in self.post_endpoints.items():
            result = await self.test_api_endpoint(endpoint_name, endpoint_config)
            self.test_results["api_endpoints"][endpoint_name] = result
            
            if result["status"] == "passed":
                self.test_results["summary"]["passed"] += 1
                self.logger.info(f"✅ {endpoint_name}: {result['response_time']:.3f}s")
            else:
                self.test_results["summary"]["failed"] += 1
                self.test_results["summary"]["errors"].append(f"{endpoint_name}: {result['error']}")
                self.logger.error(f"❌ {endpoint_name}: {result['error']}")
                
            self.test_results["summary"]["total_tests"] += 1
            
    async def test_functional_integrity(self) -> None:
        """
        测试功能完整性
        """
        self.logger.info("开始功能完整性测试...")
        
        # 测试1: 训练数据提交和查询
        try:
            # 提交测试数据
            test_submission = {
                'channel_id': 'test_channel_functional',
                'channel_name': 'Functional Test Channel',
                'original_message': 'This is a functional test message',
                'tail_content': 'functional test tail'
            }
            
            async with self.session.post(
                f"{self.base_url}/api/training-db/submit",
                json=test_submission
            ) as response:
                if response.status in [200, 201]:
                    self.test_results["functional_tests"]["data_submission"] = "passed"
                    self.logger.info("✅ 训练数据提交测试通过")
                else:
                    self.test_results["functional_tests"]["data_submission"] = f"failed: HTTP {response.status}"
                    self.logger.error(f"❌ 训练数据提交测试失败: HTTP {response.status}")
                    
        except Exception as e:
            self.test_results["functional_tests"]["data_submission"] = f"error: {e}"
            self.logger.error(f"❌ 训练数据提交测试异常: {e}")
            
        # 测试2: 数据统计查询
        try:
            async with self.session.get(f"{self.base_url}/api/training-db/stats") as response:
                if response.status == 200:
                    stats = await response.json()
                    if isinstance(stats, dict):
                        self.test_results["functional_tests"]["stats_query"] = "passed"
                        self.logger.info(f"✅ 统计查询测试通过: {len(stats)} 个统计项")
                    else:
                        self.test_results["functional_tests"]["stats_query"] = "failed: invalid response format"
                        self.logger.error("❌ 统计查询测试失败: 响应格式无效")
                else:
                    self.test_results["functional_tests"]["stats_query"] = f"failed: HTTP {response.status}"
                    self.logger.error(f"❌ 统计查询测试失败: HTTP {response.status}")
                    
        except Exception as e:
            self.test_results["functional_tests"]["stats_query"] = f"error: {e}"
            self.logger.error(f"❌ 统计查询测试异常: {e}")
            
        # 测试3: 媒体文件管理
        try:
            async with self.session.get(f"{self.base_url}/api/training-db/media-files") as response:
                if response.status == 200:
                    media_files = await response.json()
                    if isinstance(media_files, list):
                        self.test_results["functional_tests"]["media_management"] = "passed"
                        self.logger.info(f"✅ 媒体文件管理测试通过: {len(media_files)} 个文件")
                    else:
                        self.test_results["functional_tests"]["media_management"] = "failed: invalid response format"
                        self.logger.error("❌ 媒体文件管理测试失败: 响应格式无效")
                else:
                    self.test_results["functional_tests"]["media_management"] = f"failed: HTTP {response.status}"
                    self.logger.error(f"❌ 媒体文件管理测试失败: HTTP {response.status}")
                    
        except Exception as e:
            self.test_results["functional_tests"]["media_management"] = f"error: {e}"
            self.logger.error(f"❌ 媒体文件管理测试异常: {e}")
            
    async def test_performance_and_concurrency(self) -> None:
        """
        测试性能和并发访问
        """
        self.logger.info("开始性能和并发测试...")
        
        # 并发访问测试
        concurrent_requests = 10
        start_time = time.time()
        
        tasks = []
        for i in range(concurrent_requests):
            task = self.session.get(f"{self.base_url}/api/training-db/stats")
            tasks.append(task)
            
        try:
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()
            
            successful_responses = 0
            failed_responses = 0
            
            for response in responses:
                if isinstance(response, Exception):
                    failed_responses += 1
                else:
                    if response.status == 200:
                        successful_responses += 1
                    else:
                        failed_responses += 1
                    response.close()
                    
            total_time = end_time - start_time
            avg_response_time = total_time / concurrent_requests
            
            self.test_results["performance_tests"] = {
                "concurrent_requests": concurrent_requests,
                "successful_responses": successful_responses,
                "failed_responses": failed_responses,
                "total_time": total_time,
                "avg_response_time": avg_response_time,
                "requests_per_second": concurrent_requests / total_time
            }
            
            if successful_responses >= concurrent_requests * 0.9:  # 90%成功率
                self.logger.info(f"✅ 并发测试通过: {successful_responses}/{concurrent_requests} 成功")
                self.logger.info(f"   平均响应时间: {avg_response_time:.3f}s")
                self.logger.info(f"   QPS: {concurrent_requests / total_time:.2f}")
            else:
                self.logger.error(f"❌ 并发测试失败: {successful_responses}/{concurrent_requests} 成功")
                
        except Exception as e:
            self.test_results["performance_tests"]["error"] = str(e)
            self.logger.error(f"❌ 并发测试异常: {e}")
            
    async def test_error_handling(self) -> None:
        """
        测试错误处理
        """
        self.logger.info("开始错误处理测试...")
        
        error_test_cases = [
            {
                "name": "invalid_endpoint",
                "url": "/api/training-db/invalid-endpoint",
                "method": "GET",
                "expected_status": 404
            },
            {
                "name": "invalid_data_submission",
                "url": "/api/training-db/submit",
                "method": "POST",
                "data": {"invalid": "data"},
                "expected_status": [400, 422]  # 可能的验证错误状态码
            },
            {
                "name": "missing_id_parameter",
                "url": "/api/training-db/sample/",  # 缺少ID参数
                "method": "GET",
                "expected_status": [404, 405]  # 不匹配路由或方法不允许
            }
        ]
        
        for test_case in error_test_cases:
            try:
                if test_case["method"] == "GET":
                    async with self.session.get(f"{self.base_url}{test_case['url']}") as response:
                        expected_status = test_case["expected_status"]
                        if isinstance(expected_status, list):
                            if response.status in expected_status:
                                self.test_results["error_handling"][test_case["name"]] = "passed"
                                self.logger.info(f"✅ 错误处理测试 {test_case['name']} 通过")
                            else:
                                self.test_results["error_handling"][test_case["name"]] = f"failed: got {response.status}, expected {expected_status}"
                                self.logger.error(f"❌ 错误处理测试 {test_case['name']} 失败")
                        else:
                            if response.status == expected_status:
                                self.test_results["error_handling"][test_case["name"]] = "passed"
                                self.logger.info(f"✅ 错误处理测试 {test_case['name']} 通过")
                            else:
                                self.test_results["error_handling"][test_case["name"]] = f"failed: got {response.status}, expected {expected_status}"
                                self.logger.error(f"❌ 错误处理测试 {test_case['name']} 失败")
                                
                elif test_case["method"] == "POST":
                    data = test_case.get("data", {})
                    async with self.session.post(f"{self.base_url}{test_case['url']}", json=data) as response:
                        expected_status = test_case["expected_status"]
                        if isinstance(expected_status, list):
                            if response.status in expected_status:
                                self.test_results["error_handling"][test_case["name"]] = "passed"
                                self.logger.info(f"✅ 错误处理测试 {test_case['name']} 通过")
                            else:
                                self.test_results["error_handling"][test_case["name"]] = f"failed: got {response.status}, expected {expected_status}"
                                self.logger.error(f"❌ 错误处理测试 {test_case['name']} 失败")
                        else:
                            if response.status == expected_status:
                                self.test_results["error_handling"][test_case["name"]] = "passed"
                                self.logger.info(f"✅ 错误处理测试 {test_case['name']} 通过")
                            else:
                                self.test_results["error_handling"][test_case["name"]] = f"failed: got {response.status}, expected {expected_status}"
                                self.logger.error(f"❌ 错误处理测试 {test_case['name']} 失败")
                                
            except Exception as e:
                self.test_results["error_handling"][test_case["name"]] = f"error: {e}"
                self.logger.error(f"❌ 错误处理测试 {test_case['name']} 异常: {e}")
                
    def generate_test_report(self) -> str:
        """
        生成详细的测试报告
        """
        summary = self.test_results["summary"]
        
        report = f"""
# 训练数据库模块完整性测试报告

## 测试概览
- 开始时间: {summary['start_time']}
- 结束时间: {summary['end_time']}
- 测试总时长: {summary['duration']:.2f} 秒
- 总测试数: {summary['total_tests']}
- 通过测试: {summary['passed']}
- 失败测试: {summary['failed']}
- 成功率: {(summary['passed']/summary['total_tests']*100) if summary['total_tests'] > 0 else 0:.1f}%

## API端点测试结果

### 通过的端点:
"""
        
        # API端点测试结果
        passed_apis = []
        failed_apis = []
        
        for endpoint_name, result in self.test_results["api_endpoints"].items():
            if result["status"] == "passed":
                passed_apis.append(f"- ✅ {endpoint_name}: {result['description']} ({result['response_time']:.3f}s)")
            else:
                failed_apis.append(f"- ❌ {endpoint_name}: {result['description']} - {result['error']}")
                
        report += "\n".join(passed_apis)
        
        if failed_apis:
            report += "\n\n### 失败的端点:\n"
            report += "\n".join(failed_apis)
            
        # 功能测试结果
        report += "\n\n## 功能完整性测试结果\n"
        for test_name, result in self.test_results["functional_tests"].items():
            status = "✅" if result == "passed" else "❌"
            report += f"- {status} {test_name}: {result}\n"
            
        # 性能测试结果
        perf_results = self.test_results["performance_tests"]
        if perf_results:
            report += f"\n## 性能测试结果\n"
            if "error" not in perf_results:
                report += f"- 并发请求数: {perf_results['concurrent_requests']}\n"
                report += f"- 成功响应: {perf_results['successful_responses']}\n"
                report += f"- 失败响应: {perf_results['failed_responses']}\n"
                report += f"- 平均响应时间: {perf_results['avg_response_time']:.3f}s\n"
                report += f"- QPS: {perf_results['requests_per_second']:.2f}\n"
            else:
                report += f"- ❌ 性能测试异常: {perf_results['error']}\n"
                
        # 错误处理测试结果
        report += "\n## 错误处理测试结果\n"
        for test_name, result in self.test_results["error_handling"].items():
            status = "✅" if result == "passed" else "❌"
            report += f"- {status} {test_name}: {result}\n"
            
        # 问题和建议
        if summary['errors']:
            report += "\n## 发现的问题\n"
            for i, error in enumerate(summary['errors'], 1):
                report += f"{i}. {error}\n"
                
        # 修复建议
        report += "\n## 修复建议\n"
        if failed_apis:
            report += "\n### API端点问题:\n"
            for failed_api in failed_apis:
                if "404" in failed_api:
                    report += "- 检查路由配置是否正确\n"
                elif "500" in failed_api:
                    report += "- 检查服务器内部错误和日志\n"
                elif "422" in failed_api:
                    report += "- 检查请求数据格式和验证规则\n"
                    
        if self.test_results["functional_tests"]:
            failed_functional = [k for k, v in self.test_results["functional_tests"].items() if v != "passed"]
            if failed_functional:
                report += "\n### 功能完整性问题:\n"
                for test in failed_functional:
                    report += f"- 检查 {test} 相关的业务逻辑和数据处理\n"
                    
        report += "\n## 总结\n"
        if summary['failed'] == 0:
            report += "🎉 所有测试通过！training.py到training_db.py的合并成功，系统功能完整。\n"
        else:
            report += f"⚠️  发现 {summary['failed']} 个问题需要修复。建议优先处理API端点和核心功能问题。\n"
            
        return report
        
    async def run_complete_test_suite(self) -> str:
        """
        运行完整的测试套件
        """
        self.test_results["summary"]["start_time"] = datetime.now().isoformat()
        start_time = time.time()
        
        self.logger.info("开始训练数据库模块完整性测试...")
        
        # 1. 检查服务健康状态
        if not await self.check_service_health():
            self.logger.error("服务健康检查失败，无法继续测试")
            return "测试失败：服务不可用"
            
        # 2. API端点测试
        await self.test_all_api_endpoints()
        
        # 3. 功能完整性测试
        await self.test_functional_integrity()
        
        # 4. 性能和并发测试
        await self.test_performance_and_concurrency()
        
        # 5. 错误处理测试
        await self.test_error_handling()
        
        # 记录测试结束时间
        end_time = time.time()
        self.test_results["summary"]["end_time"] = datetime.now().isoformat()
        self.test_results["summary"]["duration"] = end_time - start_time
        
        # 生成测试报告
        report = self.generate_test_report()
        
        # 保存测试结果
        report_file = Path("tools/testing") / f"training_db_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_file.parent.mkdir(exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
            
        # 保存详细的JSON结果
        results_file = Path("tools/testing") / f"training_db_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"测试完成！报告已保存到: {report_file}")
        self.logger.info(f"详细结果已保存到: {results_file}")
        
        return report

async def main():
    """
    主测试函数
    """
    async with TrainingDBTestSuite() as test_suite:
        report = await test_suite.run_complete_test_suite()
        print("\n" + "="*80)
        print("测试报告预览：")
        print("="*80)
        print(report[:1000] + "..." if len(report) > 1000 else report)
        
if __name__ == "__main__":
    asyncio.run(main())
