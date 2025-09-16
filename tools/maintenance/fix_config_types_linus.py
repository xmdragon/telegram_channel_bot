#!/usr/bin/env python3
"""
配置类型修复工具
"Good taste means getting rid of special cases. This config type mess is a special case."

一次性彻底解决所有配置类型问题：
1. 修复配置文件中的类型错误
2. 报告代码中需要修改的位置
3. 验证修复效果
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
import re
import subprocess

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 在导入前设置环境变量
os.environ['PYTHONPATH'] = str(project_root)

from app.services.config_manager import DEFAULT_CONFIGS


class LinusConfigFixer:
    """配置修复器 - 无废话，直接干活"""
    
    def __init__(self):
        self.config_file = project_root / "data/config/system.json"
        self.backup_file = None
        self.issues_found = []
        self.fixes_applied = []
        
    def analyze_all_issues(self):
        """分析所有配置问题"""
        print("🔍 开始分析配置问题...")
        print("=" * 60)
        
        # 1. 检查配置文件
        self._analyze_config_file()
        
        # 2. 检查代码中的问题调用
        self._analyze_code_issues()
        
        # 3. 生成修复报告
        self._generate_report()
        
        return len(self.issues_found)
    
    def _analyze_config_file(self):
        """分析配置文件中的类型问题"""
        print("\n📋 检查配置文件类型一致性...")
        
        if not self.config_file.exists():
            self.issues_found.append(f"FATAL: 配置文件不存在: {self.config_file}")
            return
            
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        type_errors = []
        missing_configs = []
        
        # 检查每个配置项
        for key, expected in DEFAULT_CONFIGS.items():
            if key not in config:
                missing_configs.append(key)
                continue
                
            stored_config = config[key]
            expected_type = expected['config_type']
            actual_type = stored_config.get('config_type', 'unknown')
            actual_value = stored_config.get('value', '')
            
            # 检查类型不匹配
            if actual_type != expected_type:
                type_errors.append({
                    'key': key,
                    'expected_type': expected_type,
                    'actual_type': actual_type,
                    'value': actual_value,
                    'severity': 'HIGH' if expected_type == 'boolean' else 'MEDIUM'
                })
        
        # 报告问题
        if type_errors:
            print(f"❌ 发现 {len(type_errors)} 个类型错误:")
            for error in type_errors:
                severity = "🔥" if error['severity'] == 'HIGH' else "⚠️"
                print(f"  {severity} {error['key']}: "
                      f"期望 {error['expected_type']}, 实际 {error['actual_type']}, "
                      f"值: '{error['value']}'")
                self.issues_found.append(f"TYPE_MISMATCH: {error['key']}")
        
        if missing_configs:
            print(f"⚠️ 缺失 {len(missing_configs)} 个配置项:")
            for key in missing_configs:
                print(f"  📝 {key}: {DEFAULT_CONFIGS[key]['description']}")
                self.issues_found.append(f"MISSING_CONFIG: {key}")
    
    def _analyze_code_issues(self):
        """分析代码中的问题调用"""
        print("\n🔎 扫描代码中的错误 set_config 调用...")
        
        # 搜索所有缺少config_type参数的调用
        cmd = [
            'grep', '-r', '--include=*.py', '-n',
            r'set_config([^)]*[^,]\s*)',  # 不以逗号结尾的调用
            str(project_root / 'app')
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            problematic_calls = []
            for line in lines:
                if not line:
                    continue
                    
                # 过滤掉已经有config_type参数的调用
                if 'config_type=' in line:
                    continue
                    
                # 过滤掉函数定义
                if 'async def set_config' in line or 'def set_config' in line:
                    continue
                    
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    file_path = parts[0]
                    line_num = parts[1]
                    code = parts[2].strip()
                    
                    # 检查是否是真的问题调用
                    if 'await' in code and 'set_config(' in code:
                        problematic_calls.append({
                            'file': file_path,
                            'line': line_num,
                            'code': code
                        })
            
            if problematic_calls:
                print(f"❌ 发现 {len(problematic_calls)} 个缺少 config_type 的调用:")
                for call in problematic_calls:
                    rel_path = Path(call['file']).relative_to(project_root)
                    print(f"  🐛 {rel_path}:{call['line']}")
                    print(f"     {call['code'][:100]}...")
                    self.issues_found.append(f"MISSING_CONFIG_TYPE: {rel_path}:{call['line']}")
            else:
                print("✅ 未发现明显的 config_type 问题")
                
        except Exception as e:
            print(f"⚠️ 代码扫描失败: {e}")
    
    def _generate_report(self):
        """生成问题报告"""
        print("\n" + "=" * 60)
        print("📊 问题报告")
        print("=" * 60)
        
        if not self.issues_found:
            print("✅ 'Not bad. Nothing to fix here.'")
            return
            
        print(f"🔥 发现 {len(self.issues_found)} 个问题需要修复:")
        
        # 按类型分组
        by_type = {}
        for issue in self.issues_found:
            issue_type = issue.split(':', 1)[0]
            if issue_type not in by_type:
                by_type[issue_type] = []
            by_type[issue_type].append(issue)
        
        for issue_type, issues in by_type.items():
            print(f"\n📋 {issue_type}: {len(issues)} 个")
            for issue in issues[:3]:  # 只显示前3个
                print(f"  • {issue}")
            if len(issues) > 3:
                print(f"  ... 还有 {len(issues) - 3} 个")
    
    def fix_config_file(self):
        """修复配置文件中的类型错误"""
        print("\n🔧 开始修复配置文件...")
        
        if not self.config_file.exists():
            print(f"❌ 配置文件不存在: {self.config_file}")
            return False
            
        # 加载当前配置
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        fixes_made = []
        
        # 修复类型错误
        for key, expected in DEFAULT_CONFIGS.items():
            expected_type = expected['config_type']
            
            if key in config:
                stored_config = config[key]
                actual_type = stored_config.get('config_type', 'string')
                
                if actual_type != expected_type:
                    # 修复类型
                    old_value = stored_config['value']
                    config[key]['config_type'] = expected_type
                    
                    # 修正值的格式
                    if expected_type == 'boolean':
                        if old_value in ['False', 'false', False, '0', 0]:
                            config[key]['value'] = 'false'
                        else:
                            config[key]['value'] = 'true'
                    elif expected_type == 'integer':
                        try:
                            config[key]['value'] = str(int(old_value))
                        except (ValueError, TypeError):
                            config[key]['value'] = str(expected['value'])
                    
                    fixes_made.append(f"修复 {key}: {actual_type} -> {expected_type}")
                    
            else:
                # 添加缺失的配置
                config[key] = {
                    'value': str(expected['value']) if expected_type != 'boolean' 
                            else ('true' if expected['value'] else 'false'),
                    'config_type': expected_type,
                    'description': expected['description'],
                    'is_active': True,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                fixes_made.append(f"添加缺失配置: {key}")
        
        if fixes_made:
            # 备份原文件到专门的备份目录
            backup_dir = Path("data/backups")
            backup_dir.mkdir(exist_ok=True)
            backup_path = backup_dir / f"system_fix_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            import shutil
            shutil.copy2(self.config_file, backup_path)
            print(f"📦 已备份原配置: {backup_path}")
            
            # 保存修复后的配置
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 配置文件修复完成，共修复 {len(fixes_made)} 个问题:")
            for fix in fixes_made:
                print(f"  • {fix}")
                
            self.fixes_applied.extend(fixes_made)
            return True
        else:
            print("✅ 配置文件无需修复")
            return False
    
    def show_code_fix_plan(self):
        """显示代码修复计划"""
        print("\n📋 代码修复计划")
        print("=" * 50)
        
        # 需要修复的文件和位置
        fixes_needed = [
            ("app/api/system_maintenance.py", 68, "collection.enabled", "boolean"),
            ("app/api/system_admin.py", 22, "collection.enabled", "boolean"),
            ("app/api/system_admin.py", 25, "scheduler.enabled", "boolean"), 
            ("app/api/system_admin.py", 41, "collection.enabled", "boolean"),
            ("app/api/system_admin.py", 44, "scheduler.enabled", "boolean"),
            ("app/api/system_admin.py", 61, "collection.enabled", "boolean"),
            ("app/api/system_admin.py", 66, "collection.enabled", "boolean"),
            ("app/api/system_admin.py", 69, "scheduler.enabled", "boolean"),
            ("app/api/system_admin.py", 72, "scheduler.enabled", "boolean"),
        ]
        
        print("需要修复的调用:")
        for file_path, line_num, config_key, config_type in fixes_needed:
            print(f"  📝 {file_path}:{line_num}")
            print(f"     添加 config_type=\"{config_type}\" 参数")
        
        print(f"\n💡 建议: 下次直接写对配置类型")


def main():
    print("🔥 配置类型修复工具")
    print("'This is how you fix design mistakes properly.'")
    print()
    
    fixer = LinusConfigFixer()
    
    # 分析问题
    issues_count = fixer.analyze_all_issues()
    
    if issues_count == 0:
        print("\n✅ 'Good. Your config system doesn't completely suck.'")
        return
    
    # 询问是否修复
    print(f"\n❓ 发现 {issues_count} 个问题，是否立即修复配置文件? (y/N): ", end="")
    response = input().lower().strip()
    
    if response == 'y':
        success = fixer.fix_config_file()
        if success:
            print("\n🎉 配置文件修复完成!")
            print("💡 接下来需要手动修复代码中的 set_config 调用")
            fixer.show_code_fix_plan()
        else:
            print("\n⚠️ 配置文件修复失败")
    else:
        print("\n📋 仅分析模式，未进行修复")
        fixer.show_code_fix_plan()


if __name__ == "__main__":
    main()