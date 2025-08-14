#!/usr/bin/env python3
"""
Claude Code 自动提交提醒系统
在每次重要操作后检查是否需要提交
"""
import subprocess
import sys
import os
from pathlib import Path

def check_git_status():
    """检查Git状态"""
    try:
        # 检查是否有未提交的修改
        result = subprocess.run(['git', 'status', '--porcelain'], 
                              capture_output=True, text=True, cwd=Path.cwd())
        
        if result.returncode != 0:
            return None, "Git命令执行失败"
        
        changes = result.stdout.strip()
        if changes:
            return True, changes
        else:
            return False, "工作区干净"
            
    except Exception as e:
        return None, f"检查失败: {e}"

def get_modified_files():
    """获取修改的文件列表（仅代码文件）"""
    try:
        result = subprocess.run(['git', 'diff', '--name-only'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            files = result.stdout.strip().split('\n')
            # 过滤代码文件
            code_files = []
            code_extensions = {'.py', '.js', '.ts', '.html', '.css', '.sh', '.md', '.yml', '.yaml', '.json'}
            for file in files:
                if file and any(file.endswith(ext) for ext in code_extensions):
                    code_files.append(file)
            return code_files
    except:
        pass
    return []

def suggest_commit_type(files):
    """根据修改的文件建议提交类型"""
    if not files:
        return "chore"
    
    # 分析文件类型
    has_py = any(f.endswith('.py') for f in files)
    has_config = any(f.endswith(('.yml', '.yaml', '.json')) for f in files)
    has_docs = any(f.endswith('.md') for f in files)
    has_frontend = any(f.endswith(('.js', '.ts', '.html', '.css')) for f in files)
    
    # 分析文件路径
    has_services = any('services/' in f for f in files)
    has_api = any('api/' in f for f in files)
    has_core = any('core/' in f for f in files)
    
    if has_docs and len(files) == 1:
        return "docs"
    elif has_config:
        return "chore"
    elif has_services or has_core:
        return "fix" if any("fix" in f.lower() or "bug" in f.lower() for f in files) else "feat"
    elif has_api:
        return "feat"
    elif has_frontend:
        return "feat"
    else:
        return "fix"

def show_commit_reminder():
    """显示提交提醒"""
    has_changes, status = check_git_status()
    
    if has_changes is None:
        print(f"❌ {status}")
        return False
    
    if not has_changes:
        print("✅ 工作区干净，无需提交")
        return False
    
    print("\n" + "="*60)
    print("🚨 检测到未提交的修改！")
    print("="*60)
    
    # 显示修改的代码文件
    code_files = get_modified_files()
    if code_files:
        print(f"📝 修改的代码文件 ({len(code_files)}个):")
        for file in code_files[:10]:  # 最多显示10个
            print(f"   - {file}")
        if len(code_files) > 10:
            print(f"   ... 还有 {len(code_files) - 10} 个文件")
        
        # 建议提交类型
        suggested_type = suggest_commit_type(code_files)
        print(f"\n💡 建议提交类型: {suggested_type}")
        
        print(f"\n🔧 快速提交命令:")
        print(f"   ./commit.sh {suggested_type} \"你的修改描述\"")
        print(f"   # 或使用智能提交:")
        print(f"   python3 auto_commit.py")
    
    print("\n" + "="*60)
    return True

if __name__ == "__main__":
    show_commit_reminder()