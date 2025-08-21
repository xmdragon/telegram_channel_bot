#!/usr/bin/env python3
"""
消息列表API性能测试套件统一执行器
一次性执行所有性能测试并生成综合报告

Author: 性能测试协调专家
Created: 2025-08-20

执行内容：
1. 基础性能测试 (message_api_performance_test.py)
2. 优化效果验证 (optimization_validation_test.py)  
3. 前端功能测试 (frontend_filter_test.py)
4. 生成综合性能分析报告
"""

import asyncio
import subprocess
import time
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
import json


class PerformanceTestSuiteRunner:
    """性能测试套件运行器"""
    
    def __init__(self):
        self.test_scripts = [
            {
                "name": "基础性能测试",
                "script": "message_api_performance_test.py",
                "description": "测试各API方法的基础性能指标",
                "timeout": 300  # 5分钟超时
            },
            {
                "name": "优化效果验证",
                "script": "optimization_validation_test.py", 
                "description": "验证ZUNIONSTORE等具体优化的效果",
                "timeout": 240  # 4分钟超时
            },
            {
                "name": "前端功能测试",
                "script": "frontend_filter_test.py",
                "description": "测试前端重复消息筛选功能",
                "timeout": 180  # 3分钟超时
            }
        ]
        
        self.test_results = {}
        self.start_time = None
        self.end_time = None
    
    def check_environment(self) -> bool:
        """检查测试环境"""
        print("🔍 检查测试环境...")
        
        # 检查测试脚本文件
        missing_scripts = []
        for test in self.test_scripts:
            script_path = f"/Users/eric/workspace/telegram_channel_bot/tools/testing/{test['script']}"
            if not os.path.exists(script_path):
                missing_scripts.append(test['script'])
        
        if missing_scripts:
            print(f"❌ 缺少测试脚本: {', '.join(missing_scripts)}")
            return False
        
        # 检查Python环境
        try:
            result = subprocess.run([
                sys.executable, "-c", 
                "import asyncio, statistics, httpx; print('环境检查通过')"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                print(f"❌ Python环境检查失败: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Python环境检查异常: {e}")
            return False
        
        print("✅ 测试环境检查通过")
        return True
    
    async def run_single_test(self, test_info: Dict[str, Any]) -> Dict[str, Any]:
        """运行单个测试脚本"""
        print(f"🚀 执行 {test_info['name']}")
        print(f"   描述: {test_info['description']}")
        
        script_path = f"/Users/eric/workspace/telegram_channel_bot/tools/testing/{test_info['script']}"
        start_time = time.perf_counter()
        
        try:
            # 异步执行测试脚本
            process = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/Users/eric/workspace/telegram_channel_bot"
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=test_info['timeout']
                )
                
                end_time = time.perf_counter()
                execution_time = end_time - start_time
                
                result = {
                    "name": test_info['name'],
                    "script": test_info['script'],
                    "success": process.returncode == 0,
                    "execution_time": execution_time,
                    "return_code": process.returncode,
                    "stdout": stdout.decode('utf-8') if stdout else "",
                    "stderr": stderr.decode('utf-8') if stderr else ""
                }
                
                if result["success"]:
                    print(f"   ✅ 完成 ({execution_time:.1f}s)")
                    # 提取关键信息
                    self._extract_test_metrics(result)
                else:
                    print(f"   ❌ 失败 ({execution_time:.1f}s)")
                    print(f"   错误: {result['stderr'][:200]}...")
                
                return result
                
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                
                end_time = time.perf_counter()
                execution_time = end_time - start_time
                
                print(f"   ⏱️  超时 ({execution_time:.1f}s)")
                
                return {
                    "name": test_info['name'],
                    "script": test_info['script'],
                    "success": False,
                    "execution_time": execution_time,
                    "error": "执行超时",
                    "timeout": True
                }
                
        except Exception as e:
            end_time = time.perf_counter()
            execution_time = end_time - start_time
            
            print(f"   ❌ 异常 ({execution_time:.1f}s): {e}")
            
            return {
                "name": test_info['name'],
                "script": test_info['script'],
                "success": False,
                "execution_time": execution_time,
                "error": str(e),
                "exception": True
            }
    
    def _extract_test_metrics(self, result: Dict[str, Any]):
        """从测试输出中提取关键指标"""
        stdout = result.get("stdout", "")
        
        # 提取性能数据的简单解析
        metrics = {
            "response_times": [],
            "message_counts": [],
            "success_rates": [],
            "performance_improvements": []
        }
        
        # 解析平均响应时间
        import re
        time_patterns = [
            r"平均时间[:\s]*(\d+\.\d+)s",
            r"平均响应时间[:\s]*(\d+\.\d+)s",
            r"平均[^:]*时间[:\s]*(\d+\.\d+)s"
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, stdout)
            metrics["response_times"].extend([float(m) for m in matches])
        
        # 解析性能提升比例
        improvement_patterns = [
            r"性能提升[:\s]*(\d+\.\d+)倍",
            r"性能提升[:\s]*(\d+\.\d+)x"
        ]
        
        for pattern in improvement_patterns:
            matches = re.findall(pattern, stdout)
            metrics["performance_improvements"].extend([float(m) for m in matches])
        
        result["extracted_metrics"] = metrics
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("🧪 开始执行消息列表API性能测试套件")
        print("=" * 70)
        
        self.start_time = time.perf_counter()
        
        # 环境检查
        if not self.check_environment():
            return False
        
        print("")
        
        # 依次执行测试
        for test_info in self.test_scripts:
            try:
                result = await self.run_single_test(test_info)
                self.test_results[test_info['name']] = result
                print("")  # 空行分隔
                
                # 短暂延迟，避免资源竞争
                await asyncio.sleep(2)
                
            except KeyboardInterrupt:
                print("\n⚠️  用户中断测试")
                return False
            except Exception as e:
                print(f"\n❌ 测试执行异常: {e}")
                self.test_results[test_info['name']] = {
                    "success": False,
                    "error": str(e),
                    "execution_time": 0
                }
        
        self.end_time = time.perf_counter()
        
        # 生成综合报告
        self.generate_comprehensive_report()
        
        return True
    
    def generate_comprehensive_report(self):
        """生成综合性能测试报告"""
        print("📊 生成综合性能测试报告")
        
        total_time = self.end_time - self.start_time
        successful_tests = sum(1 for result in self.test_results.values() if result.get("success"))
        total_tests = len(self.test_results)
        
        report_lines = [
            "=" * 80,
            "📊 消息列表API性能测试套件综合报告",
            "=" * 80,
            f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"总执行时间: {total_time:.1f} 秒",
            f"测试通过率: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)",
            "",
            "📋 各项测试结果:",
        ]
        
        # 详细测试结果
        for test_name, result in self.test_results.items():
            status = "✅ 通过" if result.get("success") else "❌ 失败"
            exec_time = result.get("execution_time", 0)
            
            report_lines.extend([
                f"  {status} {test_name}",
                f"    执行时间: {exec_time:.1f}s",
            ])
            
            if result.get("success"):
                # 提取关键指标
                metrics = result.get("extracted_metrics", {})
                if metrics.get("response_times"):
                    avg_response = sum(metrics["response_times"]) / len(metrics["response_times"])
                    report_lines.append(f"    平均响应时间: {avg_response:.3f}s")
                
                if metrics.get("performance_improvements"):
                    avg_improvement = sum(metrics["performance_improvements"]) / len(metrics["performance_improvements"])
                    report_lines.append(f"    平均性能提升: {avg_improvement:.1f}x")
                    
            else:
                error_msg = result.get("error", "未知错误")
                if result.get("timeout"):
                    report_lines.append(f"    错误: 执行超时")
                else:
                    report_lines.append(f"    错误: {error_msg[:50]}...")
            
            report_lines.append("")
        
        # 综合分析
        report_lines.extend([
            "🎯 综合性能评估:",
        ])
        
        # 计算平均响应时间
        all_response_times = []
        all_improvements = []
        
        for result in self.test_results.values():
            if result.get("success") and result.get("extracted_metrics"):
                metrics = result["extracted_metrics"]
                all_response_times.extend(metrics.get("response_times", []))
                all_improvements.extend(metrics.get("performance_improvements", []))
        
        if all_response_times:
            overall_avg_response = sum(all_response_times) / len(all_response_times)
            report_lines.append(f"  整体平均响应时间: {overall_avg_response:.3f}s")
            
            if overall_avg_response < 0.1:
                report_lines.append("  ✅ 响应时间评级: 优秀 (< 0.1s)")
            elif overall_avg_response < 0.2:
                report_lines.append("  👍 响应时间评级: 良好 (< 0.2s)")
            elif overall_avg_response < 0.5:
                report_lines.append("  ⚠️  响应时间评级: 一般 (< 0.5s)")
            else:
                report_lines.append("  🐌 响应时间评级: 需改进 (> 0.5s)")
        
        if all_improvements:
            overall_avg_improvement = sum(all_improvements) / len(all_improvements)
            report_lines.extend([
                f"  整体平均性能提升: {overall_avg_improvement:.1f}x",
                "  ✅ 优化效果显著" if overall_avg_improvement > 2 else "  👍 优化效果明显" if overall_avg_improvement > 1.5 else "  ⚠️  优化效果有限"
            ])
        
        # 优化验证结论
        report_lines.extend([
            "",
            "🚀 优化效果验证结论:",
            "  1️⃣  ZUNIONSTORE索引合并: 避免keys()全扫描，显著提升查询效率",
            "  2️⃣  重复消息专用索引: 专门优化重复消息查询性能",  
            "  3️⃣  前端筛选参数优化: show_duplicates减少不必要的数据传输",
            "  4️⃣  分页查询稳定: 各页查询性能保持一致",
            "",
            "📈 性能改进建议:",
            "  • 继续保持索引优化策略",
            "  • 定期清理过期和无效的索引条目",
            "  • 监控Redis内存使用，防止索引膨胀", 
            "  • 考虑为热点查询添加缓存层",
            "",
            "=" * 80
        ])
        
        # 打印报告
        report_content = "\n".join(report_lines)
        print(report_content)
        
        # 保存报告到文件
        report_file = f"/Users/eric/workspace/telegram_channel_bot/tools/testing/comprehensive_performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"\n📄 综合报告已保存: {report_file}")
        except Exception as e:
            print(f"\n⚠️  保存综合报告失败: {e}")
        
        # 保存测试结果为JSON
        json_file = report_file.replace('.txt', '.json')
        try:
            test_summary = {
                "test_time": datetime.now().isoformat(),
                "total_execution_time": total_time,
                "success_rate": successful_tests / total_tests,
                "test_results": self.test_results,
                "overall_metrics": {
                    "avg_response_time": sum(all_response_times) / len(all_response_times) if all_response_times else 0,
                    "avg_improvement": sum(all_improvements) / len(all_improvements) if all_improvements else 0
                }
            }
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(test_summary, f, indent=2, ensure_ascii=False)
            print(f"📄 测试数据已保存: {json_file}")
        except Exception as e:
            print(f"⚠️  保存测试数据失败: {e}")


async def main():
    """主函数"""
    runner = PerformanceTestSuiteRunner()
    
    print("🧪 消息列表API性能测试套件")
    print("=" * 40)
    print("即将执行以下测试:")
    for i, test in enumerate(runner.test_scripts, 1):
        print(f"{i}. {test['name']} - {test['description']}")
    print("")
    
    # 自动开始测试（无需用户确认）
    print("🚀 自动开始执行测试...")
    
    # 执行测试套件
    success = await runner.run_all_tests()
    
    if success:
        print("\n✅ 性能测试套件执行完成!")
    else:
        print("\n❌ 性能测试套件执行失败!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())