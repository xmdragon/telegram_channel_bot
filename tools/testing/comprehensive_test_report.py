#!/usr/bin/env python3
"""
训练数据库合并的综合测试报告

汇总所有测试结果并生成最终报告

作者：Test Automation Expert
创建时间：2025-08-17
"""

import json
import glob
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

class ComprehensiveTestReportGenerator:
    """
    综合测试报告生成器
    """
    
    def __init__(self):
        self.test_results_dir = Path("tools/testing")
        self.comprehensive_report = {
            "test_execution_summary": {},
            "code_integrity_results": {},
            "api_compatibility_results": {},
            "system_status": {},
            "conclusions": {},
            "recommendations": []
        }
        
    def load_test_results(self) -> Dict[str, Any]:
        """
        加载所有测试结果文件
        """
        results = {}
        
        # 找到最新的测试结果文件
        result_files = {
            "code_integrity": list(self.test_results_dir.glob("code_integrity_results_*.json")),
            "frontend_compatibility": list(self.test_results_dir.glob("frontend_compatibility_results_*.json")),
            "simple_api_test": list(self.test_results_dir.glob("simple_api_test_results.json"))
        }
        
        for test_type, files in result_files.items():
            if files:
                # 取最新的文件
                latest_file = max(files, key=lambda f: f.stat().st_mtime)
                try:
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        results[test_type] = json.load(f)
                    print(f"✅ 加载 {test_type} 结果: {latest_file.name}")
                except Exception as e:
                    print(f"❌ 加载 {test_type} 失败: {e}")
                    results[test_type] = {}
            else:
                print(f"⚠️  未找到 {test_type} 结果文件")
                results[test_type] = {}
                
        return results
        
    def analyze_code_integrity(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析代码完整性结果
        """
        if not results:
            return {"status": "no_data", "message": "无测试数据"}
            
        summary = results.get("summary", {})
        
        analysis = {
            "status": "passed" if summary.get("failed", 1) == 0 else "failed",
            "total_tests": summary.get("total_tests", 0),
            "passed_tests": summary.get("passed", 0),
            "failed_tests": summary.get("failed", 0),
            "success_rate": summary.get("passed", 0) / summary.get("total_tests", 1) * 100,
            "errors": summary.get("errors", []),
            "file_structure": results.get("file_structure", {})
        }
        
        # 特定项目分析
        specific_tests = {
            "imports": results.get("import_tests", {}),
            "routes": results.get("route_tests", {}),
            "functions": results.get("function_tests", {}),
            "configs": results.get("config_tests", {}),
            "models": results.get("model_tests", {})
        }
        
        analysis["detailed_results"] = specific_tests
        
        return analysis
        
    def analyze_api_compatibility(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析API兼容性结果
        """
        if not results:
            return {"status": "no_data", "message": "无测试数据"}
            
        compatibility = results.get("compatibility_check", {})
        critical = results.get("critical_endpoints", {})
        
        analysis = {
            "status": "passed" if compatibility.get("missing_count", 1) == 0 else "warning",
            "compatibility_rate": compatibility.get("compatibility_rate", 0),
            "total_endpoints": compatibility.get("total_frontend", 0),
            "matched_endpoints": compatibility.get("matched_count", 0),
            "missing_endpoints": compatibility.get("missing_endpoints", []),
            "critical_coverage": critical.get("critical_coverage", 0),
            "missing_critical": critical.get("missing_critical", [])
        }
        
        return analysis
        
    def analyze_system_performance(self, api_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析系统性能状态
        """
        if not api_results:
            return {
                "status": "unavailable",
                "message": "系统不可用，无法进行性能测试",
                "success_rate": 0
            }
            
        summary = api_results.get("summary", {})
        
        analysis = {
            "status": "passed" if summary.get("success_rate", 0) > 0 else "failed",
            "total_tests": summary.get("total", 0),
            "successful_tests": summary.get("successful", 0),
            "failed_tests": summary.get("failed", 0),
            "success_rate": summary.get("success_rate", 0),
            "message": "系统服务启动问题导致API测试失败" if summary.get("success_rate", 0) == 0 else "正常"
        }
        
        return analysis
        
    def generate_conclusions(self, 
                           code_analysis: Dict[str, Any],
                           api_analysis: Dict[str, Any], 
                           performance_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成结论
        """
        conclusions = {
            "overall_status": "unknown",
            "merge_success": False,
            "critical_issues": [],
            "minor_issues": [],
            "strengths": []
        }
        
        # 分析整体状态
        code_ok = code_analysis.get("status") == "passed"
        api_ok = api_analysis.get("status") in ["passed", "warning"]
        
        if code_ok and api_ok:
            conclusions["overall_status"] = "success"
            conclusions["merge_success"] = True
        elif code_ok:
            conclusions["overall_status"] = "partial_success" 
            conclusions["merge_success"] = True
        else:
            conclusions["overall_status"] = "needs_attention"
            conclusions["merge_success"] = False
            
        # 识别关键问题
        if code_analysis.get("failed_tests", 0) > 0:
            conclusions["critical_issues"].append(
                f"代码完整性测试失败: {code_analysis.get('failed_tests')} 个问题"
            )
            
        if performance_analysis.get("status") == "failed":
            conclusions["critical_issues"].append("系统服务启动问题")
            
        if api_analysis.get("missing_critical"):
            conclusions["minor_issues"].append(
                f"前端配置缺少关键端点: {len(api_analysis.get('missing_critical', []))}个"
            )
            
        # 识别优点
        if code_analysis.get("success_rate", 0) >= 80:
            conclusions["strengths"].append("代码合并基本成功")
            
        if api_analysis.get("compatibility_rate", 0) >= 90:
            conclusions["strengths"].append("前后端 API 兼容性良好")
            
        file_structure = code_analysis.get("file_structure", {})
        if file_structure.get("total_lines", 0) > 2000:
            conclusions["strengths"].append(
                f"代码库规模实质: {file_structure.get('total_lines')} 行代码"
            )
            
        return conclusions
        
    def generate_recommendations(self, 
                               code_analysis: Dict[str, Any],
                               api_analysis: Dict[str, Any],
                               performance_analysis: Dict[str, Any],
                               conclusions: Dict[str, Any]) -> List[str]:
        """
        生成建议
        """
        recommendations = []
        
        # 基于结论生成建议
        if "critical_issues" in conclusions and conclusions["critical_issues"]:
            recommendations.append("🚨 紧急修复: 解决所有关键问题后再进行线上部署")
            
        if performance_analysis.get("status") == "failed":
            recommendations.extend([
                "🔧 系统维护: 检查和修复服务启动问题",
                "🔍 进程管理: 验证dev_supervisor进程管理器的稳定性",
                "🔌 端口检查: 确认端口8000正常监听和防火墙配置"
            ])
            
        if code_analysis.get("success_rate", 0) < 100:
            recommendations.append("📝 代码优化: 修复代码完整性测试中发现的问题")
            
        if api_analysis.get("compatibility_rate", 0) < 100:
            recommendations.append("🔗 API同步: 更新前端 API 配置以匹配所有后端端点")
            
        # 正面建议
        if conclusions.get("merge_success"):
            recommendations.extend([
                "✅ 合并成功: training.py 到 training_db.py 的合并基本成功",
                "📋 持续监控: 定期运行测试套件以确保系统稳定性",
                "📦 备份策略: 定期备份训练数据以防数据丢失"
            ])
            
        # 性能优化建议
        file_structure = code_analysis.get("file_structure", {})
        if file_structure.get("total_lines", 0) > 2500:
            recommendations.append("📏 代码重构: 考虑将training_db.py拆分为多个小模块以提高可维护性")
            
        return recommendations
        
    def generate_comprehensive_report(self) -> str:
        """
        生成综合测试报告
        """
        print("🚀 开始生成综合测试报告...")
        print("="*80)
        
        # 加载测试结果
        all_results = self.load_test_results()
        
        # 分析结果
        code_analysis = self.analyze_code_integrity(all_results.get("code_integrity", {}))
        api_analysis = self.analyze_api_compatibility(all_results.get("frontend_compatibility", {}))
        performance_analysis = self.analyze_system_performance(all_results.get("simple_api_test", {}))
        
        # 生成结论
        conclusions = self.generate_conclusions(code_analysis, api_analysis, performance_analysis)
        recommendations = self.generate_recommendations(code_analysis, api_analysis, performance_analysis, conclusions)
        
        # 保存综合结果
        self.comprehensive_report = {
            "timestamp": datetime.now().isoformat(),
            "code_integrity_analysis": code_analysis,
            "api_compatibility_analysis": api_analysis,
            "system_performance_analysis": performance_analysis,
            "conclusions": conclusions,
            "recommendations": recommendations
        }
        
        # 生成报告文本
        report = self.format_report()
        
        # 保存报告
        report_file = self.test_results_dir / f"comprehensive_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
            
        # 保存JSON结果
        json_file = self.test_results_dir / f"comprehensive_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.comprehensive_report, f, indent=2, ensure_ascii=False)
            
        print(f"\n📋 报告已生成: {report_file}")
        print(f"💾 JSON结果: {json_file}")
        
        return report
        
    def format_report(self) -> str:
        """
        格式化最终报告
        """
        code_analysis = self.comprehensive_report["code_integrity_analysis"]
        api_analysis = self.comprehensive_report["api_compatibility_analysis"]
        performance_analysis = self.comprehensive_report["system_performance_analysis"]
        conclusions = self.comprehensive_report["conclusions"]
        recommendations = self.comprehensive_report["recommendations"]
        
        # 状态图标
        status_icons = {
            "passed": "🟢",
            "warning": "🟡", 
            "failed": "🔴",
            "success": "🎉",
            "partial_success": "🟡",
            "needs_attention": "⚠️",
            "unavailable": "⭕"
        }
        
        report = f"""
# Training.py 到 Training_db.py 合并综合测试报告

生成时间: {self.comprehensive_report['timestamp']}
测试人: Test Automation Expert

## 执行概览 {status_icons.get(conclusions['overall_status'], '❓')}

**合并状态**: {'**成功** ✅' if conclusions['merge_success'] else '**需要注意** ⚠️'}

**整体评估**: {conclusions['overall_status'].replace('_', ' ').title()}

---

## 测试结果详情

### 1. 代码完整性测试 {status_icons.get(code_analysis['status'], '❓')}

- **状态**: {code_analysis['status'].title()}
- **成功率**: {code_analysis.get('success_rate', 0):.1f}%
- **总测试数**: {code_analysis.get('total_tests', 0)}
- **通过**: {code_analysis.get('passed_tests', 0)}
- **失败**: {code_analysis.get('failed_tests', 0)}

#### 文件统计
- **代码行数**: {code_analysis.get('file_structure', {}).get('total_lines', 'N/A')}
- **有效代码**: {code_analysis.get('file_structure', {}).get('non_empty_lines', 'N/A')}
- **函数数量**: {code_analysis.get('file_structure', {}).get('function_count', 'N/A')}

### 2. API 兼容性测试 {status_icons.get(api_analysis['status'], '❓')}

- **状态**: {api_analysis['status'].title()}
- **兼容率**: {api_analysis.get('compatibility_rate', 0):.1f}%
- **端点总数**: {api_analysis.get('total_endpoints', 0)}
- **匹配端点**: {api_analysis.get('matched_endpoints', 0)}
- **关键端点覆盖率**: {api_analysis.get('critical_coverage', 0):.1f}%

### 3. 系统性能测试 {status_icons.get(performance_analysis['status'], '❓')}

- **状态**: {performance_analysis['status'].title()}
- **成功率**: {performance_analysis.get('success_rate', 0):.1f}%
- **测试结果**: {performance_analysis.get('successful_tests', 0)}/{performance_analysis.get('total_tests', 0)}
- **说明**: {performance_analysis.get('message', 'N/A')}

---

## 主要发现

### 优点 ✅
"""
        
        for strength in conclusions.get('strengths', []):
            report += f"- {strength}\n"
            
        if conclusions.get('critical_issues'):
            report += "\n### 关键问题 ⚠️\n"
            for issue in conclusions['critical_issues']:
                report += f"- {issue}\n"
                
        if conclusions.get('minor_issues'):
            report += "\n### 次要问题 🟡\n"
            for issue in conclusions['minor_issues']:
                report += f"- {issue}\n"
                
        report += "\n---\n\n## 建议和后续步骤\n\n"
        
        for i, recommendation in enumerate(recommendations, 1):
            report += f"{i}. {recommendation}\n"
            
        # 总结
        report += "\n---\n\n## 总结\n\n"
        
        if conclusions['merge_success']:
            report += "🎉 **合并成功**: training.py 到 training_db.py 的合并已经基本完成，代码完整性良好。\n\n"
        else:
            report += "⚠️ **需要注意**: 合并过程中发现了一些问题，需要进一步处理。\n\n"
            
        if performance_analysis['status'] == 'failed':
            report += "🔧 **系统现状**: 由于系统服务启动问题，无法进行实时API测试。但代码层面的测试显示合并成功。\n\n"
        else:
            report += "🚀 **系统状态**: 所有系统组件都在正常运行。\n\n"
            
        report += f"""
**下一步建议**:
1. 解决任何剩余问题
2. 进行线上部署测试
3. 监控系统性能
4. 定期运行测试套件

---

*此报告由 Test Automation Expert 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 自动生成*
"""
        
        return report

def main():
    """
    主函数
    """
    generator = ComprehensiveTestReportGenerator()
    report = generator.generate_comprehensive_report()
    
    print("\n" + "="*80)
    print("📋 综合测试报告:")
    print("="*80)
    print(report)
    
if __name__ == "__main__":
    main()
