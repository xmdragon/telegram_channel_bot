#!/usr/bin/env python3
"""
硬编码API路径检查和修复工具

这是一个Linus式的"一次修复，永远正确"解决方案：
- 检查所有Python文件中的@router装饰器
- 发现硬编码路径违规
- 自动修复：将硬编码替换为ROUTES引用
- 生成违规报告，确保以后不再犯同样错误

作者：Linus Torvalds 思维模式
原则：消除特殊情况，简化数据结构，永不破坏用户空间
"""

import os
import re
import json
import sys
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
import argparse

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

@dataclass
class RouteViolation:
    """路由违规记录"""
    file_path: str
    line_number: int
    line_content: str
    http_method: str
    hardcoded_path: str
    suggested_route: Optional[str] = None
    severity: str = "ERROR"  # ERROR, WARNING, INFO

@dataclass
class RouteAnalysis:
    """路由分析结果"""
    violations: List[RouteViolation]
    total_routes: int
    hardcoded_routes: int
    proper_routes: int
    missing_route_configs: Set[str]

class RouteChecker:
    """路由检查器 - Linus式设计：简单、直接、无特殊情况"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.app_dir = self.project_root / "app"
        self.route_config_path = self.app_dir / "core" / "route_config.py"
        
        # 硬编码路径检测模式
        self.hardcoded_pattern = re.compile(
            r'@router\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
            re.IGNORECASE
        )
        
        # ROUTES引用模式  
        self.routes_pattern = re.compile(
            r'@router\.(get|post|put|delete|patch)\s*\(\s*ROUTES\.(\w+)\.(\w+)',
            re.IGNORECASE
        )
        
        # 加载现有路由配置
        self.existing_routes = self._load_existing_routes()
        
    def _load_existing_routes(self) -> Dict[str, Dict[str, str]]:
        """加载现有的路由配置"""
        routes = {}
        
        if not self.route_config_path.exists():
            print(f"⚠️  路由配置文件不存在: {self.route_config_path}")
            return routes
            
        try:
            with open(self.route_config_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 解析类定义
            class_pattern = re.compile(r'class\s+(\w+):\s*\n(.*?)(?=\n\s*class|\n\s*def|\Z)', re.DOTALL)
            for match in class_pattern.finditer(content):
                class_name = match.group(1).lower()
                class_content = match.group(2)
                
                # 解析路由定义
                route_pattern = re.compile(r'(\w+)\s*=\s*["\']([^"\']+)["\']')
                routes[class_name] = {}
                for route_match in route_pattern.finditer(class_content):
                    route_name = route_match.group(1)
                    route_path = route_match.group(2)
                    routes[class_name][route_name] = route_path
                    
        except Exception as e:
            print(f"❌ 解析路由配置失败: {e}")
            
        return routes
    
    def analyze_file(self, file_path: Path) -> List[RouteViolation]:
        """分析单个文件的路由违规"""
        violations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                
                # 检查硬编码路径
                hardcoded_match = self.hardcoded_pattern.search(line)
                if hardcoded_match:
                    http_method = hardcoded_match.group(1).upper()
                    hardcoded_path = hardcoded_match.group(2)
                    
                    # 排除一些合理的硬编码情况
                    if self._is_acceptable_hardcode(hardcoded_path):
                        continue
                        
                    violation = RouteViolation(
                        file_path=str(file_path.relative_to(self.project_root)),
                        line_number=line_num,
                        line_content=line,
                        http_method=http_method,
                        hardcoded_path=hardcoded_path,
                        suggested_route=self._suggest_route_config(hardcoded_path),
                        severity="ERROR"
                    )
                    violations.append(violation)
                    
        except Exception as e:
            print(f"⚠️  分析文件失败 {file_path}: {e}")
            
        return violations
    
    def _is_acceptable_hardcode(self, path: str) -> bool:
        """判断硬编码是否可接受（极少数例外情况）"""
        # Linus原则：特殊情况应该极少，且有明确理由
        acceptable_patterns = [
            r'^/static/',  # 静态文件路径
            r'^/docs/',    # 文档路径  
            r'^/health$',  # 健康检查（某些场景）
        ]
        
        for pattern in acceptable_patterns:
            if re.match(pattern, path):
                return True
                
        return False
    
    def _suggest_route_config(self, hardcoded_path: str) -> Optional[str]:
        """建议的路由配置 - 基于实际路由配置进行精确匹配"""
        
        # 直接在现有路由配置中查找匹配
        for category, routes in self.existing_routes.items():
            for route_name, route_path in routes.items():
                if route_path == hardcoded_path:
                    return f"ROUTES.{category}.{route_name}"
        
        # 如果没有精确匹配，尝试智能推断
        return self._smart_route_suggestion(hardcoded_path)
    
    def _smart_route_suggestion(self, hardcoded_path: str) -> Optional[str]:
        """智能路由建议 - Linus式简单映射"""
        
        # AI路由映射
        ai_mappings = {
            "/status": "ROUTES.ai.status",
            "/enable": "ROUTES.ai.enable", 
            "/disable": "ROUTES.ai.disable",
            "/cache/info": "ROUTES.ai.cache_info",
            "/cache/preload": "ROUTES.ai.cache_preload",
            "/cache/clear": "ROUTES.ai.cache_clear",
        }
        
        if hardcoded_path in ai_mappings:
            return ai_mappings[hardcoded_path]
        
        # Training路由映射 - 直接路径匹配
        training_mappings = {
            # 广告样本
            "/ad-samples": "ROUTES.training.ad_samples",
            "/ad-statistics": "ROUTES.training.ad_statistics", 
            "/ad-samples/{sample_id}": "ROUTES.training.ad_samples_by_id",
            "/ad-samples/batch": "ROUTES.training.ad_samples_batch",
            "/ad-samples/detect-duplicates": "ROUTES.training.ad_samples_detect_duplicates",
            "/ad-samples/deduplicate": "ROUTES.training.ad_samples_deduplicate",
            "/mark-ad-test": "ROUTES.training.mark_ad_test",
            "/mark-ad-message": "ROUTES.training.mark_ad_message",
            "/add-ad-sample": "ROUTES.training.add_ad_sample",
            "/ad-stats": "ROUTES.training.ad_stats",
            "/ad-samples/reload": "ROUTES.training.ad_samples_reload",
            
            # 基础训练
            "/channels": "ROUTES.training.channels",
            "/stats": "ROUTES.training.stats",
            "/history": "ROUTES.training.history",
            "/submit": "ROUTES.training.submit",
            "/{sample_id}": "ROUTES.training.sample_by_id",
            "/apply": "ROUTES.training.apply",
            "/clear/{channel_id}": "ROUTES.training.clear_by_channel",
            "/export": "ROUTES.training.export",
            "/auto-learn/{channel_id}": "ROUTES.training.auto_learn",
            "/sample/{sample_id}": "ROUTES.training.sample_detail",
            "/separator-patterns": "ROUTES.training.separator_patterns",
            "/reload-model": "ROUTES.training.reload_model",
            
            # OCR样本
            "/ocr-samples": "ROUTES.training.ocr_samples",
            "/ocr-samples/statistics": "ROUTES.training.ocr_statistics",
            "/ocr-samples/learn": "ROUTES.training.ocr_learn",
            "/ocr-samples/{sample_id}": "ROUTES.training.ocr_samples_by_id",
            "/ocr-samples/export": "ROUTES.training.ocr_export",
            "/ocr-samples/add": "ROUTES.training.ocr_add",
            "/ocr-samples/batch-process": "ROUTES.training.ocr_batch_process",
            "/ocr-samples/confidence-distribution": "ROUTES.training.ocr_confidence_distribution",
            
            # 管理功能
            "/optimize-storage": "ROUTES.training.optimize_storage",
            "/optimize-storage-sse": "ROUTES.training.optimize_storage_sse",
            "/learning-stats": "ROUTES.training.learning_stats",
            "/emergency-backup": "ROUTES.training.emergency_backup",
            "/integrity-report": "ROUTES.training.integrity_report",
            "/verify-integrity": "ROUTES.training.verify_integrity",
            "/cleanup-backups": "ROUTES.training.cleanup_backups",
            "/backups": "ROUTES.training.backups",
            "/restore/{backup_filename}": "ROUTES.training.restore",
            "/feedback": "ROUTES.training.feedback",
            "/statistics": "ROUTES.training.statistics",
            "/clear": "ROUTES.training.clear",
            
            # 尾部过滤器
            "/tail-filter-statistics": "ROUTES.training.tail_filter_statistics",
            "/tail-filter-history": "ROUTES.training.tail_filter_history",
            "/tail-filter-samples": "ROUTES.training.tail_filter_samples",
            "/tail-filter-samples/{sample_id}": "ROUTES.training.tail_filter_samples_by_id",
            "/tail-filter-samples/detect-duplicates": "ROUTES.training.tail_filter_detect_duplicates",
            "/tail-filter-samples/deduplicate": "ROUTES.training.tail_filter_deduplicate",
            
            # 阈值管理
            "/thresholds/stats": "ROUTES.training.thresholds_stats",
            "/thresholds/optimize": "ROUTES.training.thresholds_optimize",
            "/thresholds/{filter_name}/{metric_name}/reset": "ROUTES.training.thresholds_reset",
            
            # 媒体文件
            "/media-files": "ROUTES.training.media_files",
            "/media-files/{file_hash}": "ROUTES.training.media_files_by_hash",
            "/media-files/clean-orphaned": "ROUTES.training.media_files_clean_orphaned",
            "/media-files/duplicates": "ROUTES.training.media_files_duplicates",
            "/media-files/export": "ROUTES.training.media_files_export",
            "/media-files/deduplicate": "ROUTES.training.media_files_deduplicate",
            "/media-files/rebuild-visual-hashes": "ROUTES.training.media_files_rebuild_visual_hashes",
            "/media-files/{file_hash}/ocr": "ROUTES.training.media_files_ocr",
        }
        
        if hardcoded_path in training_mappings:
            return training_mappings[hardcoded_path]
            
        return None
    
    def scan_all_files(self) -> RouteAnalysis:
        """扫描所有Python文件"""
        print("🔍 开始扫描硬编码路由...")
        
        all_violations = []
        total_routes = 0
        hardcoded_routes = 0
        proper_routes = 0
        
        # 扫描app目录下的所有Python文件
        for py_file in self.app_dir.rglob("*.py"):
            violations = self.analyze_file(py_file)
            all_violations.extend(violations)
            
            # 统计路由数量
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 统计总路由数
            total_matches = len(self.hardcoded_pattern.findall(content))
            routes_matches = len(self.routes_pattern.findall(content))
            
            total_routes += total_matches + routes_matches
            hardcoded_routes += total_matches
            proper_routes += routes_matches
            
        return RouteAnalysis(
            violations=all_violations,
            total_routes=total_routes,
            hardcoded_routes=hardcoded_routes,
            proper_routes=proper_routes,
            missing_route_configs=self._identify_missing_configs(all_violations)
        )
    
    def _identify_missing_configs(self, violations: List[RouteViolation]) -> Set[str]:
        """识别缺失的路由配置类"""
        missing = set()
        
        for violation in violations:
            path = violation.hardcoded_path
            
            # 根据路径判断应该属于哪个路由类
            if '/training' in path:
                missing.add('Training')
            elif '/ai' in path:
                missing.add('AI')
            elif '/websocket' in path:
                missing.add('WebSocket')
                
        return missing
    
    def generate_report(self, analysis: RouteAnalysis) -> str:
        """生成Linus式的直接报告"""
        report_lines = [
            "=" * 80,
            "🚨 硬编码API路径违规报告",
            "=" * 80,
            "",
            f"📊 总体统计：",
            f"   总路由数量: {analysis.total_routes}",
            f"   硬编码路由: {analysis.hardcoded_routes} ❌",
            f"   规范路由:   {analysis.proper_routes} ✅", 
            f"   违规率:     {(analysis.hardcoded_routes/analysis.total_routes)*100:.1f}%",
            "",
        ]
        
        if analysis.hardcoded_routes == 0:
            report_lines.extend([
                "🎉 恭喜！没有发现硬编码路径违规",
                "   代码质量达到Linus标准：简洁、一致、无特殊情况",
                ""
            ])
        else:
            report_lines.extend([
                f"🔥 发现 {len(analysis.violations)} 个硬编码违规！",
                "",
                "📋 违规详情：",
                "-" * 50,
            ])
            
            # 按文件分组违规
            violations_by_file = {}
            for violation in analysis.violations:
                file_path = violation.file_path
                if file_path not in violations_by_file:
                    violations_by_file[file_path] = []
                violations_by_file[file_path].append(violation)
            
            for file_path, violations in violations_by_file.items():
                report_lines.append(f"\n📁 {file_path}")
                for violation in violations:
                    report_lines.extend([
                        f"   第{violation.line_number}行: {violation.http_method} {violation.hardcoded_path}",
                        f"   代码: {violation.line_content.strip()}",
                        f"   建议: {violation.suggested_route or '需要手动创建路由配置'}",
                        ""
                    ])
        
        # 缺失的路由配置类
        if analysis.missing_route_configs:
            report_lines.extend([
                "🔧 需要创建的路由配置类：",
                "-" * 30,
            ])
            for missing_class in analysis.missing_route_configs:
                report_lines.append(f"   class {missing_class}:")
            report_lines.append("")
        
        # Linus式建议
        report_lines.extend([
            "💡 Linus式修复建议：",
            "-" * 20,
            "1. 所有API路径必须在route_config.py中定义",
            "2. 消除硬编码特殊情况，使用统一的ROUTES引用",
            "3. 重构原则：数据结构优先，消除重复代码",
            "4. 向后兼容：确保API路径不变，只改变定义方式",
            "",
            "🎯 目标：实现0硬编码，100%路由配置化",
            "=" * 80,
        ])
        
        return "\n".join(report_lines)
    
    def auto_fix_violations(self, violations: List[RouteViolation], dry_run: bool = True) -> Dict[str, int]:
        """自动修复违规（谨慎模式）"""
        if dry_run:
            print("🔍 模拟修复模式（不会实际修改文件）")
        else:
            print("⚠️  实际修复模式 - 将修改文件！")
            
        stats = {"fixed": 0, "skipped": 0, "errors": 0}
        
        # 按文件分组处理
        files_to_fix = {}
        for violation in violations:
            file_path = violation.file_path
            if file_path not in files_to_fix:
                files_to_fix[file_path] = []
            files_to_fix[file_path].append(violation)
        
        for file_path, file_violations in files_to_fix.items():
            try:
                self._fix_file(file_path, file_violations, dry_run, stats)
            except Exception as e:
                print(f"❌ 修复文件失败 {file_path}: {e}")
                stats["errors"] += 1
                
        return stats
    
    def _fix_file(self, file_path: str, violations: List[RouteViolation], dry_run: bool, stats: Dict[str, int]):
        """修复单个文件"""
        full_path = self.project_root / file_path
        
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        modified = False
        
        for violation in violations:
            line_idx = violation.line_number - 1
            
            if violation.suggested_route:
                # 有建议的路由配置，尝试替换
                old_line = lines[line_idx]
                new_line = old_line.replace(
                    f'"{violation.hardcoded_path}"',
                    violation.suggested_route
                ).replace(
                    f"'{violation.hardcoded_path}'",
                    violation.suggested_route
                )
                
                if new_line != old_line:
                    if not dry_run:
                        lines[line_idx] = new_line
                    
                    print(f"   ✅ 第{violation.line_number}行: {violation.hardcoded_path} -> {violation.suggested_route}")
                    modified = True
                    stats["fixed"] += 1
                else:
                    print(f"   ⚠️  跳过第{violation.line_number}行: 无法自动替换")
                    stats["skipped"] += 1
            else:
                print(f"   ⚠️  跳过第{violation.line_number}行: 需要手动创建路由配置")
                stats["skipped"] += 1
        
        # 写回文件
        if modified and not dry_run:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            print(f"💾 已修复文件: {file_path}")

def main():
    parser = argparse.ArgumentParser(description="硬编码API路径检查和修复工具")
    parser.add_argument("--fix", action="store_true", help="自动修复违规（实际修改文件）")
    parser.add_argument("--dry-run", action="store_true", default=True, help="模拟修复（默认）")
    parser.add_argument("--report-only", action="store_true", help="仅生成报告")
    parser.add_argument("--output", "-o", help="报告输出文件")
    
    args = parser.parse_args()
    
    # 项目根目录
    project_root = Path(__file__).parent.parent.parent
    
    print("🚀 启动硬编码API路径检查器")
    print(f"📁 项目目录: {project_root}")
    print()
    
    # 创建检查器
    checker = RouteChecker(str(project_root))
    
    # 扫描分析
    analysis = checker.scan_all_files()
    
    # 生成报告
    report = checker.generate_report(analysis)
    print(report)
    
    # 保存报告
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"📄 报告已保存到: {args.output}")
    
    # 自动修复
    if not args.report_only and analysis.violations:
        print("\n" + "="*50)
        
        if args.fix:
            print("🔧 开始自动修复...")
            stats = checker.auto_fix_violations(analysis.violations, dry_run=False)
        else:
            print("🔍 模拟修复预览...")
            stats = checker.auto_fix_violations(analysis.violations, dry_run=True)
            
        print(f"\n📊 修复统计:")
        print(f"   已修复: {stats['fixed']}")
        print(f"   已跳过: {stats['skipped']}")  
        print(f"   错误:   {stats['errors']}")
        
        if args.dry_run or not args.fix:
            print("\n💡 使用 --fix 参数进行实际修复")
    
    # 返回状态码
    return 1 if analysis.violations else 0

if __name__ == "__main__":
    exit(main())