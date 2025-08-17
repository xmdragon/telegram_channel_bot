#!/usr/bin/env python3
"""
代码完整性测试 - 验证training.py到training_db.py合并的正确性

测试内容：
1. 导入完整性测试 - 检查所有依赖是否正确导入
2. 路由定义完整性 - 验证所有API端点是否正确定义
3. 函数签名验证 - 检查关键函数是否存在且签名正确
4. 配置文件完整性 - 验证配置文件路径和数据结构
5. 数据模型验证 - 检查Pydantic模型定义

作者：Test Automation Expert
创建时间：2025-08-17
"""

import sys
import ast
import json
import inspect
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

class CodeIntegrityTestSuite:
    """
    代码完整性测试套件
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.test_results = {
            "import_tests": {},
            "route_tests": {},
            "function_tests": {},
            "config_tests": {},
            "model_tests": {},
            "summary": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": [],
                "start_time": None,
                "end_time": None
            }
        }
        
    def test_imports(self) -> Dict[str, Any]:
        """
        测试导入完整性
        """
        print("🔍 测试导入完整性...")
        
        try:
            # 测试训练模块导入
            from app.routers import training_db
            self.test_results["import_tests"]["training_db_import"] = "passed"
            print("  ✅ training_db模块导入成功")
            
            # 测试关键依赖导入
            from app.core.path_config import PathConfig
            from app.utils.safe_file_ops import SafeFileOperation
            self.test_results["import_tests"]["dependencies_import"] = "passed"
            print("  ✅ 核心依赖导入成功")
            
            # 测试FastAPI相关导入
            from fastapi import APIRouter, HTTPException, Depends
            from pydantic import BaseModel
            self.test_results["import_tests"]["fastapi_import"] = "passed"
            print("  ✅ FastAPI相关导入成功")
            
        except ImportError as e:
            error_msg = f"导入失败: {e}"
            self.test_results["import_tests"]["import_error"] = error_msg
            self.test_results["summary"]["errors"].append(error_msg)
            print(f"  ❌ {error_msg}")
            return False
        except Exception as e:
            error_msg = f"导入异常: {e}"
            self.test_results["import_tests"]["import_exception"] = error_msg
            self.test_results["summary"]["errors"].append(error_msg)
            print(f"  ❌ {error_msg}")
            return False
            
        return True
        
    def test_route_definitions(self) -> Dict[str, Any]:
        """
        测试路由定义完整性
        """
        print("\n🔍 测试路由定义完整性...")
        
        try:
            from app.routers.training_db import router
            
            # 检查路由器是否正确创建
            if hasattr(router, 'routes'):
                route_count = len(router.routes)
                self.test_results["route_tests"]["router_creation"] = "passed"
                self.test_results["route_tests"]["route_count"] = route_count
                print(f"  ✅ 路由器创建成功，包含 {route_count} 个路由")
            else:
                self.test_results["route_tests"]["router_creation"] = "failed: no routes attribute"
                print("  ❌ 路由器创建失败：没有routes属性")
                return False
                
            # 检查关键路由端点
            expected_routes = [
                "/stats",
                "/ad-samples", 
                "/channels",
                "/history",
                "/submit",
                "/media-files"
            ]
            
            found_routes = []
            for route in router.routes:
                if hasattr(route, 'path'):
                    found_routes.append(route.path)
                    
            missing_routes = []
            for expected in expected_routes:
                if not any(expected in route for route in found_routes):
                    missing_routes.append(expected)
                    
            if missing_routes:
                self.test_results["route_tests"]["missing_routes"] = missing_routes
                print(f"  ⚠️  缺少路由: {missing_routes}")
            else:
                self.test_results["route_tests"]["route_completeness"] = "passed"
                print("  ✅ 所有关键路由端点存在")
                
        except Exception as e:
            error_msg = f"路由测试异常: {e}"
            self.test_results["route_tests"]["route_error"] = error_msg
            self.test_results["summary"]["errors"].append(error_msg)
            print(f"  ❌ {error_msg}")
            return False
            
        return True
        
    def test_function_signatures(self) -> Dict[str, Any]:
        """
        测试关键函数签名
        """
        print("\n🔍 测试函数签名完整性...")
        
        try:
            from app.routers import training_db
            
            # 检查关键函数是否存在
            expected_functions = [
                'load_training_data',
                'save_training_data', 
                'get_training_stats',
                'get_ad_samples',
                'get_channels',
                'submit_training_data'
            ]
            
            missing_functions = []
            existing_functions = []
            
            for func_name in expected_functions:
                if hasattr(training_db, func_name):
                    existing_functions.append(func_name)
                    # 检查函数是否可调用
                    func = getattr(training_db, func_name)
                    if callable(func):
                        print(f"  ✅ {func_name}: 存在且可调用")
                    else:
                        print(f"  ⚠️  {func_name}: 存在但不可调用")
                else:
                    missing_functions.append(func_name)
                    print(f"  ❌ {func_name}: 不存在")
                    
            self.test_results["function_tests"]["existing_functions"] = existing_functions
            self.test_results["function_tests"]["missing_functions"] = missing_functions
            
            if missing_functions:
                self.test_results["function_tests"]["completeness"] = f"failed: missing {len(missing_functions)} functions"
                return False
            else:
                self.test_results["function_tests"]["completeness"] = "passed"
                return True
                
        except Exception as e:
            error_msg = f"函数测试异常: {e}"
            self.test_results["function_tests"]["function_error"] = error_msg
            self.test_results["summary"]["errors"].append(error_msg)
            print(f"  ❌ {error_msg}")
            return False
            
    def test_config_integrity(self) -> Dict[str, Any]:
        """
        测试配置文件完整性
        """
        print("\n🔍 测试配置文件完整性...")
        
        try:
            from app.core.path_config import PathConfig
            
            # 检查关键路径配置
            required_paths = [
                'MANUAL_TRAINING_FILE',
                'TRAINING_HISTORY_FILE', 
                'TAIL_FILTER_SAMPLES_FILE',
                'SEPARATOR_PATTERNS_FILE',
                'AD_TRAINING_DIR'
            ]
            
            missing_configs = []
            existing_configs = []
            
            for path_name in required_paths:
                if hasattr(PathConfig, path_name):
                    existing_configs.append(path_name)
                    path_value = getattr(PathConfig, path_name)
                    print(f"  ✅ {path_name}: {path_value}")
                else:
                    missing_configs.append(path_name)
                    print(f"  ❌ {path_name}: 不存在")
                    
            self.test_results["config_tests"]["existing_configs"] = existing_configs
            self.test_results["config_tests"]["missing_configs"] = missing_configs
            
            # 检查目录是否可以创建
            try:
                PathConfig.ensure_directories()
                self.test_results["config_tests"]["directory_creation"] = "passed"
                print("  ✅ 目录创建功能正常")
            except Exception as e:
                self.test_results["config_tests"]["directory_creation"] = f"failed: {e}"
                print(f"  ❌ 目录创建失败: {e}")
                
            return len(missing_configs) == 0
            
        except Exception as e:
            error_msg = f"配置测试异常: {e}"
            self.test_results["config_tests"]["config_error"] = error_msg
            self.test_results["summary"]["errors"].append(error_msg)
            print(f"  ❌ {error_msg}")
            return False
            
    def test_data_models(self) -> Dict[str, Any]:
        """
        测试数据模型完整性
        """
        print("\n🔍 测试数据模型完整性...")
        
        try:
            from app.routers.training_db import TrainingSubmission
            
            # 检查TrainingSubmission模型
            required_fields = ['channel_id', 'channel_name', 'original_message', 'tail_content']
            model_fields = list(TrainingSubmission.__annotations__.keys())
            
            missing_fields = [field for field in required_fields if field not in model_fields]
            existing_fields = [field for field in required_fields if field in model_fields]
            
            self.test_results["model_tests"]["existing_fields"] = existing_fields
            self.test_results["model_tests"]["missing_fields"] = missing_fields
            
            if missing_fields:
                print(f"  ❌ TrainingSubmission缺少字段: {missing_fields}")
                self.test_results["model_tests"]["model_completeness"] = f"failed: missing {missing_fields}"
                return False
            else:
                print(f"  ✅ TrainingSubmission模型完整，包含字段: {existing_fields}")
                self.test_results["model_tests"]["model_completeness"] = "passed"
                
            # 测试模型实例化
            test_data = {
                'channel_id': 'test_123',
                'channel_name': 'Test Channel',
                'original_message': 'Test message',
                'tail_content': 'Test tail'
            }
            
            try:
                instance = TrainingSubmission(**test_data)
                self.test_results["model_tests"]["model_instantiation"] = "passed"
                print("  ✅ TrainingSubmission模型实例化成功")
            except Exception as e:
                self.test_results["model_tests"]["model_instantiation"] = f"failed: {e}"
                print(f"  ❌ TrainingSubmission模型实例化失败: {e}")
                return False
                
            return True
            
        except Exception as e:
            error_msg = f"模型测试异常: {e}"
            self.test_results["model_tests"]["model_error"] = error_msg
            self.test_results["summary"]["errors"].append(error_msg)
            print(f"  ❌ {error_msg}")
            return False
            
    def analyze_file_structure(self) -> Dict[str, Any]:
        """
        分析文件结构变化
        """
        print("\n🔍 分析文件结构...")
        
        training_db_file = self.project_root / "app" / "routers" / "training_db.py"
        
        if training_db_file.exists():
            with open(training_db_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 统计代码行数
            lines = content.split('\n')
            total_lines = len(lines)
            non_empty_lines = len([line for line in lines if line.strip()])
            comment_lines = len([line for line in lines if line.strip().startswith('#')])
            
            # 统计函数和类
            tree = ast.parse(content)
            functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            
            structure_info = {
                "file_exists": True,
                "total_lines": total_lines,
                "non_empty_lines": non_empty_lines,
                "comment_lines": comment_lines,
                "function_count": len(functions),
                "class_count": len(classes),
                "function_names": [f.name for f in functions],
                "class_names": [c.name for c in classes]
            }
            
            print(f"  📊 文件统计:")
            print(f"    - 总行数: {total_lines}")
            print(f"    - 有效代码行: {non_empty_lines}")
            print(f"    - 注释行: {comment_lines}")
            print(f"    - 函数数量: {len(functions)}")
            print(f"    - 类数量: {len(classes)}")
            
            return structure_info
        else:
            print("  ❌ training_db.py文件不存在")
            return {"file_exists": False}
            
    def run_complete_integrity_test(self) -> str:
        """
        运行完整的代码完整性测试
        """
        self.test_results["summary"]["start_time"] = datetime.now().isoformat()
        
        print("🚀 开始代码完整性测试...")
        print("="*60)
        
        # 运行各项测试
        test_methods = [
            ("导入测试", self.test_imports),
            ("路由测试", self.test_route_definitions),
            ("函数测试", self.test_function_signatures),
            ("配置测试", self.test_config_integrity),
            ("模型测试", self.test_data_models)
        ]
        
        passed_tests = 0
        total_tests = len(test_methods)
        
        for test_name, test_method in test_methods:
            try:
                if test_method():
                    passed_tests += 1
                    print(f"✅ {test_name} 通过")
                else:
                    print(f"❌ {test_name} 失败")
            except Exception as e:
                print(f"💥 {test_name} 异常: {e}")
                self.test_results["summary"]["errors"].append(f"{test_name}: {e}")
                
        # 文件结构分析
        structure_info = self.analyze_file_structure()
        self.test_results["file_structure"] = structure_info
        
        # 更新总结
        self.test_results["summary"]["total_tests"] = total_tests
        self.test_results["summary"]["passed"] = passed_tests
        self.test_results["summary"]["failed"] = total_tests - passed_tests
        self.test_results["summary"]["end_time"] = datetime.now().isoformat()
        
        # 生成报告
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print("\n" + "="*60)
        print(f"📊 测试完成 - 总计: {total_tests}, 通过: {passed_tests}, 失败: {total_tests - passed_tests}")
        print(f"📈 成功率: {success_rate:.1f}%")
        
        if self.test_results["summary"]["errors"]:
            print("\n⚠️  发现的问题:")
            for error in self.test_results["summary"]["errors"]:
                print(f"  - {error}")
                
        # 保存详细结果
        results_file = Path("tools/testing") / f"code_integrity_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_file.parent.mkdir(exist_ok=True)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, indent=2, ensure_ascii=False)
            
        print(f"\n💾 详细结果已保存到: {results_file}")
        
        return self.generate_integrity_report()
        
    def generate_integrity_report(self) -> str:
        """
        生成代码完整性报告
        """
        summary = self.test_results["summary"]
        
        report = f"""
# 代码完整性测试报告

## 测试概览
- 开始时间: {summary['start_time']}
- 结束时间: {summary['end_time']}
- 总测试数: {summary['total_tests']}
- 通过测试: {summary['passed']}
- 失败测试: {summary['failed']}
- 成功率: {(summary['passed']/summary['total_tests']*100) if summary['total_tests'] > 0 else 0:.1f}%

## 测试结果详情

### 导入测试
"""
        
        for category, results in self.test_results.items():
            if category == "summary" or category == "file_structure":
                continue
                
            report += f"\n### {category.replace('_', ' ').title()}\n"
            for test_name, result in results.items():
                status = "✅" if result == "passed" else "❌"
                report += f"- {status} {test_name}: {result}\n"
                
        # 文件结构信息
        if "file_structure" in self.test_results:
            structure = self.test_results["file_structure"]
            if structure.get("file_exists"):
                report += f"\n### 文件结构分析\n"
                report += f"- 总行数: {structure.get('total_lines', 'N/A')}\n"
                report += f"- 有效代码行: {structure.get('non_empty_lines', 'N/A')}\n"
                report += f"- 函数数量: {structure.get('function_count', 'N/A')}\n"
                report += f"- 类数量: {structure.get('class_count', 'N/A')}\n"
                
        # 问题和建议
        if summary['errors']:
            report += "\n## 发现的问题\n"
            for i, error in enumerate(summary['errors'], 1):
                report += f"{i}. {error}\n"
                
        # 结论
        report += "\n## 结论\n"
        if summary['failed'] == 0:
            report += "🎉 所有代码完整性测试通过！training.py到training_db.py的合并是成功的。\n"
        else:
            report += f"⚠️  发现 {summary['failed']} 个问题需要修复。建议优先解决导入和路由相关问题。\n"
            
        return report

def main():
    """
    主测试函数
    """
    tester = CodeIntegrityTestSuite()
    report = tester.run_complete_integrity_test()
    
    print("\n" + "="*80)
    print("📋 完整性测试报告预览:")
    print("="*80)
    print(report[:1500] + "..." if len(report) > 1500 else report)
    
if __name__ == "__main__":
    main()
