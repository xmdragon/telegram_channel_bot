#!/usr/bin/env python3
"""
Claude Code专用自动提交工具
用于Claude在完成bug修复或功能开发后自动提交代码
"""

import subprocess
import sys
import os
from datetime import datetime
from typing import List, Tuple, Optional
import json


class ClaudeAutoCommitter:
    """Claude专用自动提交器"""
    
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
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stderr
    
    def get_changed_files(self) -> List[str]:
        """获取已修改的文件列表（排除数据库文件）"""
        success, output = self.run_git_command(['status', '--porcelain'])
        if not success:
            return []
        
        changed_files = []
        for line in output.strip().split('\n'):
            if line and len(line) > 2:
                # git status --porcelain 格式：XY filename
                # X和Y是状态字符，然后是文件名（可能有空格分隔）
                # 找到第一个非状态字符的位置
                file_path = line[2:].lstrip()  # 跳过前两个状态字符，然后去除左边空格
                
                # 排除数据库和日志文件
                if file_path and not self._should_ignore_file(file_path):
                    changed_files.append(file_path)
        return changed_files
    
    def _should_ignore_file(self, file_path: str) -> bool:
        """判断是否应该忽略的文件"""
        ignore_patterns = [
            'data/postgres/',
            'data/redis/',
            'logs/',
            '.log',
            'temp_media/',
            '__pycache__/',
            '.pyc',
            '.DS_Store'
        ]
        return any(pattern in file_path for pattern in ignore_patterns)
    
    def detect_change_type_and_description(self, files: List[str]) -> Tuple[str, str]:
        """智能检测变更类型和描述"""
        # 文件分类
        frontend_files = [f for f in files if f.startswith('static/') or f.endswith(('.html', '.css', '.js'))]
        backend_files = [f for f in files if f.startswith('app/') or f.endswith('.py')]
        config_files = [f for f in files if f.endswith(('.yml', '.yaml', '.json', '.ini', '.conf'))]
        doc_files = [f for f in files if f.endswith(('.md', '.txt', '.rst'))]
        script_files = [f for f in files if f.endswith('.sh')]
        
        # 检查是否有新增文件
        success, diff = self.run_git_command(['diff', '--name-status'])
        has_new_files = success and 'A\t' in diff
        
        # 检查是否是修复
        if any('fix' in f.lower() or 'bug' in f.lower() for f in files):
            return 'fix', '修复代码问题'
        
        # 根据文件类型和内容生成描述
        descriptions = []
        if frontend_files:
            if any('index.html' in f for f in frontend_files):
                descriptions.append('优化主页面')
            elif any('.js' in f for f in frontend_files):
                descriptions.append('更新前端逻辑')
            elif any('.css' in f for f in frontend_files):
                descriptions.append('调整页面样式')
            else:
                descriptions.append('前端界面更新')
        
        if backend_files:
            if any('service' in f for f in backend_files):
                descriptions.append('优化业务逻辑')
            elif any('api' in f or 'route' in f for f in backend_files):
                descriptions.append('更新API接口')
            else:
                descriptions.append('后端功能优化')
        
        if config_files:
            descriptions.append('配置文件调整')
        
        if doc_files:
            descriptions.append('文档更新')
        
        if script_files:
            descriptions.append('脚本优化')
        
        # 确定变更类型
        if doc_files and len(doc_files) == len(files):
            change_type = 'docs'
        elif config_files and len(config_files) == len(files):
            change_type = 'chore'
        elif has_new_files and frontend_files:
            change_type = 'feat'
        elif frontend_files and backend_files:
            change_type = 'feat'
        elif any('.css' in f for f in files):
            change_type = 'style'
        else:
            change_type = 'feat' if has_new_files else 'fix'
        
        description = '、'.join(descriptions) if descriptions else '代码优化'
        return change_type, description
    
    def generate_commit_message(self, change_type: str, description: str, files: List[str]) -> str:
        """生成提交信息"""
        # 类型和emoji映射
        type_emoji = {
            'fix': '🐛',
            'feat': '✨',
            'docs': '📝',
            'style': '💄',
            'refactor': '♻️',
            'chore': '🔧',
            'perf': '⚡',
            'test': '✅'
        }
        
        emoji = type_emoji.get(change_type, '🔨')
        
        # 构建提交信息
        commit_msg = f"{emoji} {change_type}: {description}\n\n"
        
        # 添加文件变更详情
        if len(files) <= 5:
            commit_msg += "变更文件：\n"
            for f in files:
                commit_msg += f"- {f}\n"
        else:
            # 按类型分组显示
            file_groups = {
                '前端': [f for f in files if f.startswith('static/') or f.endswith(('.html', '.css', '.js'))],
                '后端': [f for f in files if f.startswith('app/') or f.endswith('.py')],
                '配置': [f for f in files if f.endswith(('.yml', '.yaml', '.json', '.ini'))],
                '文档': [f for f in files if f.endswith(('.md', '.txt', '.rst'))],
                '脚本': [f for f in files if f.endswith('.sh')]
            }
            
            commit_msg += "变更统计：\n"
            for group_name, group_files in file_groups.items():
                if group_files:
                    commit_msg += f"- {group_name}: {len(group_files)} 个文件\n"
        
        commit_msg += f"\n🤖 Claude Code 自动提交\n"
        commit_msg += f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return commit_msg
    
    def auto_commit(self, custom_message: Optional[str] = None) -> bool:
        """自动提交（无交互）"""
        files = self.get_changed_files()
        
        if not files:
            print("✅ 没有需要提交的代码变更")
            return True
        
        print(f"📊 检测到 {len(files)} 个文件变更")
        for f in files[:10]:  # 最多显示10个文件
            print(f"  📄 {f}")
        if len(files) > 10:
            print(f"  ... 还有 {len(files) - 10} 个文件")
        
        # 自动生成或使用自定义消息
        if custom_message:
            # 解析自定义消息格式：type:description
            if ':' in custom_message:
                change_type, description = custom_message.split(':', 1)
                change_type = change_type.strip()
                description = description.strip()
            else:
                change_type, _ = self.detect_change_type_and_description(files)
                description = custom_message
        else:
            change_type, description = self.detect_change_type_and_description(files)
        
        commit_message = self.generate_commit_message(change_type, description, files)
        
        print("\n📝 生成的提交信息：")
        print("=" * 50)
        print(commit_message)
        print("=" * 50)
        
        # 执行提交
        return self._execute_commit(commit_message, files)
    
    def _execute_commit(self, message: str, files: List[str]) -> bool:
        """执行提交"""
        # 只添加我们要提交的文件
        for file in files:
            success, output = self.run_git_command(['add', file])
            if not success:
                print(f"❌ 添加文件 {file} 失败: {output}")
                return False
        
        # 执行提交
        success, output = self.run_git_command(['commit', '-m', message])
        if success:
            print(f"✅ 自动提交成功！")
            return True
        else:
            print(f"❌ 提交失败: {output}")
            return False
    
    def quick_fix(self, description: str) -> bool:
        """快速修复提交"""
        return self.auto_commit(f"fix:{description}")
    
    def quick_feat(self, description: str) -> bool:
        """快速功能提交"""
        return self.auto_commit(f"feat:{description}")


def main():
    """主函数"""
    committer = ClaudeAutoCommitter()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'fix' and len(sys.argv) > 2:
            description = ' '.join(sys.argv[2:])
            return committer.quick_fix(description)
        elif command == 'feat' and len(sys.argv) > 2:
            description = ' '.join(sys.argv[2:])
            return committer.quick_feat(description)
        elif command == 'auto':
            custom_msg = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
            return committer.auto_commit(custom_msg)
        else:
            print("用法:")
            print("  python3 auto_commit_claude.py auto [描述]")
            print("  python3 auto_commit_claude.py fix <描述>")
            print("  python3 auto_commit_claude.py feat <描述>")
            return False
    else:
        # 默认自动模式
        return committer.auto_commit()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)