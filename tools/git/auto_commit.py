#!/usr/bin/env python3
"""
自动Git提交工具
用于在完成bug修复或功能开发后自动总结并提交代码
"""

import subprocess
import sys
import os
from datetime import datetime
from typing import List, Tuple, Optional
import re


class GitAutoCommitter:
    """自动Git提交管理器"""
    
    def __init__(self):
        self.repo_path = os.path.dirname(os.path.abspath(__file__))
        
    def run_git_command(self, command: List[str]) -> Tuple[bool, str]:
        """执行Git命令"""
        try:
            result = subprocess.run(
                ['git'] + command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            # 成功时合并stdout和stderr（git commit的pre-commit输出在stderr）
            output = result.stdout.strip()
            if result.stderr.strip():
                # 如果stderr有内容，通常是pre-commit hook等信息输出
                if output:
                    output += "\n" + result.stderr.strip()
                else:
                    output = result.stderr.strip()
            return True, output
        except subprocess.CalledProcessError as e:
            # 失败时提供完整的错误信息
            error_output = e.stderr.strip()
            if e.stdout.strip():
                error_output = f"{e.stdout.strip()}\n{error_output}" if error_output else e.stdout.strip()
            return False, error_output
    
    def get_changed_files(self) -> List[str]:
        """获取已修改的文件列表"""
        success, output = self.run_git_command(['status', '--porcelain'])
        if not success:
            return []
        
        changed_files = []
        for line in output.strip().split('\n'):
            if line:
                # 提取文件路径（跳过状态标记）
                file_path = line[3:].strip()
                if file_path:
                    changed_files.append(file_path)
        return changed_files
    
    def analyze_changes(self) -> dict:
        """分析变更内容，生成提交摘要"""
        changed_files = self.get_changed_files()
        if not changed_files:
            return {'has_changes': False}
        
        # 分类文件
        categories = {
            'frontend': [],
            'backend': [],
            'config': [],
            'docs': [],
            'scripts': [],
            'other': []
        }
        
        for file in changed_files:
            if file.startswith('static/') or file.endswith(('.html', '.css', '.js')):
                categories['frontend'].append(file)
            elif file.startswith('app/') or file.endswith('.py'):
                categories['backend'].append(file)
            elif file.endswith(('.yml', '.yaml', '.json', '.ini', '.conf')):
                categories['config'].append(file)
            elif file.endswith(('.md', '.txt', '.rst')):
                categories['docs'].append(file)
            elif file.endswith('.sh'):
                categories['scripts'].append(file)
            else:
                categories['other'].append(file)
        
        # 获取diff统计
        success, diff_stat = self.run_git_command(['diff', '--stat'])
        
        return {
            'has_changes': True,
            'total_files': len(changed_files),
            'categories': categories,
            'diff_stat': diff_stat if success else '',
            'files': changed_files
        }
    
    def generate_commit_message(self, change_type: str, description: str, details: Optional[List[str]] = None) -> str:
        """生成规范的提交信息
        
        Args:
            change_type: 变更类型 (fix/feat/refactor/docs/style/test/chore)
            description: 简短描述
            details: 详细说明列表
        """
        # 类型映射和emoji
        type_emoji = {
            'fix': '🐛',
            'feat': '✨',
            'refactor': '♻️',
            'docs': '📝',
            'style': '💄',
            'test': '✅',
            'chore': '🔧',
            'perf': '⚡',
            'security': '🔒'
        }
        
        emoji = type_emoji.get(change_type, '🔨')
        
        # 构建提交信息
        commit_msg = f"{emoji} {change_type}: {description}\n\n"
        
        if details:
            commit_msg += "详细说明：\n"
            for detail in details:
                commit_msg += f"- {detail}\n"
            commit_msg += "\n"
        
        # 添加自动生成标记
        commit_msg += "🤖 由 auto_commit.py 自动生成\n"
        commit_msg += f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return commit_msg
    
    def auto_detect_change_type(self, files: List[str]) -> str:
        """根据文件变更自动检测变更类型"""
        # 检查是否有bug修复相关的文件
        if any('fix' in f.lower() or 'bug' in f.lower() for f in files):
            return 'fix'
        
        # 检查是否是新功能
        success, diff = self.run_git_command(['diff', '--name-status'])
        if success and 'A\t' in diff:  # 有新增文件
            return 'feat'
        
        # 检查是否是文档更新
        if all(f.endswith(('.md', '.txt', '.rst')) for f in files):
            return 'docs'
        
        # 检查是否是配置更新
        if all(f.endswith(('.yml', '.yaml', '.json', '.ini', '.conf')) for f in files):
            return 'chore'
        
        # 检查是否是样式更新
        if all(f.endswith(('.css', '.scss', '.less')) for f in files):
            return 'style'
        
        # 默认为功能更新
        return 'feat'
    
    def smart_commit(self, custom_message: Optional[str] = None) -> bool:
        """智能提交：分析变更并自动生成提交信息"""
        analysis = self.analyze_changes()
        
        if not analysis['has_changes']:
            print("❌ 没有检测到任何变更")
            return False
        
        print(f"📊 检测到 {analysis['total_files']} 个文件变更")
        
        # 显示变更摘要
        for category, files in analysis['categories'].items():
            if files:
                print(f"  {category}: {len(files)} 个文件")
        
        # 自动检测变更类型
        change_type = self.auto_detect_change_type(analysis['files'])
        
        # 生成描述
        if custom_message:
            description = custom_message
        else:
            # 根据变更内容自动生成描述
            descriptions = []
            if analysis['categories']['frontend']:
                descriptions.append("前端页面更新")
            if analysis['categories']['backend']:
                descriptions.append("后端逻辑优化")
            if analysis['categories']['config']:
                descriptions.append("配置文件调整")
            if analysis['categories']['docs']:
                descriptions.append("文档更新")
            
            description = "、".join(descriptions) if descriptions else "代码优化"
        
        # 生成详细说明
        details = []
        for category, files in analysis['categories'].items():
            if files and len(files) <= 3:
                for f in files:
                    details.append(f"修改 {f}")
            elif files:
                details.append(f"修改 {len(files)} 个{category}文件")
        
        # 生成提交信息
        commit_message = self.generate_commit_message(change_type, description, details)
        
        print("\n📝 生成的提交信息：")
        print("=" * 50)
        print(commit_message)
        print("=" * 50)
        
        # 询问确认（处理非交互环境）
        try:
            confirm = input("\n是否使用此提交信息？ (y/n/e[编辑]): ").lower()
        except EOFError:
            # 非交互环境，自动确认
            print("\n非交互环境，自动使用生成的提交信息")
            confirm = 'y'
        
        if confirm == 'e':
            # 允许编辑
            try:
                print("\n请输入自定义提交信息（输入END结束）：")
                lines = []
                while True:
                    line = input()
                    if line == 'END':
                        break
                    lines.append(line)
                commit_message = '\n'.join(lines)
            except EOFError:
                print("无法在非交互环境中编辑，使用原提交信息")
        elif confirm != 'y':
            print("❌ 取消提交")
            return False
        
        # 执行提交
        return self.execute_commit(commit_message)
    
    def execute_commit(self, message: str) -> bool:
        """执行Git提交"""
        # 添加所有变更
        success, output = self.run_git_command(['add', '.'])
        if not success:
            print(f"❌ 添加文件失败: {output}")
            return False
        
        # 执行提交
        print("🚀 执行Git提交...")
        success, output = self.run_git_command(['commit', '-m', message])
        if success:
            print(f"✅ 提交成功！")
            
            # 显示提交输出（包括pre-commit信息）
            if output:
                # 过滤和美化输出
                lines = output.split('\n')
                for line in lines:
                    if line.strip():
                        # 识别pre-commit相关输出
                        if any(keyword in line for keyword in ['Pre-commit', '🔒', '🎉', '检查']):
                            print(f"🔧 {line}")
                        elif 'files changed' in line or 'insertions' in line or 'deletions' in line:
                            print(f"📊 {line}")
                        else:
                            print(f"ℹ️  {line}")
            
            # 获取最新提交的hash
            commit_success, commit_hash = self.run_git_command(['rev-parse', '--short', 'HEAD'])
            if commit_success:
                print(f"📝 提交哈希: {commit_hash.strip()}")
            
            # 询问是否推送（处理非交互环境）
            try:
                push = input("\n是否推送到远程仓库？ (y/n): ").lower()
            except EOFError:
                print("\n非交互环境，跳过推送")
                push = 'n'
                
            if push == 'y':
                push_success, push_output = self.run_git_command(['push'])
                if push_success:
                    print("✅ 推送成功！")
                    if push_output:
                        print(f"📤 {push_output}")
                else:
                    print(f"❌ 推送失败: {push_output}")
            return True
        else:
            print(f"❌ 提交失败: {output}")
            return False
    
    def quick_fix(self, bug_description: str) -> bool:
        """快速提交bug修复"""
        return self.smart_commit(f"修复 {bug_description}")
    
    def quick_feat(self, feature_description: str) -> bool:
        """快速提交新功能"""
        return self.smart_commit(f"新增 {feature_description}")


def main():
    """主函数"""
    committer = GitAutoCommitter()
    
    # 解析命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'fix' and len(sys.argv) > 2:
            # 快速bug修复提交
            bug_desc = ' '.join(sys.argv[2:])
            committer.quick_fix(bug_desc)
        elif command == 'feat' and len(sys.argv) > 2:
            # 快速功能提交
            feat_desc = ' '.join(sys.argv[2:])
            committer.quick_feat(feat_desc)
        elif command == 'auto':
            # 自动分析并提交
            custom_msg = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
            committer.smart_commit(custom_msg)
        else:
            print("用法:")
            print("  python auto_commit.py auto [描述]  # 自动分析并提交")
            print("  python auto_commit.py fix <bug描述>  # 快速提交bug修复")
            print("  python auto_commit.py feat <功能描述>  # 快速提交新功能")
    else:
        # 交互式模式
        print("🤖 Git自动提交工具")
        print("-" * 50)
        committer.smart_commit()


if __name__ == "__main__":
    main()