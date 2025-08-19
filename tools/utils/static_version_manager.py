#!/usr/bin/env python3
"""
静态资源版本管理工具
解决浏览器缓存问题，支持开发和生产环境
"""
import os
import re
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Set
import argparse

class StaticVersionManager:
    """静态资源版本控制管理器"""
    
    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path(__file__).parent.parent.parent
        self.static_dir = self.project_root / "static"
        self.html_files = []
        self.updated_files = []
        
        # 版本参数的正则模式
        self.js_pattern = re.compile(r'<script\s+src="([^"]+\.js)(\?v=[^"]*)?">') 
        self.css_pattern = re.compile(r'<link[^>]+href="([^"]+\.css)(\?v=[^"]*)?"')
        
    def scan_html_files(self) -> List[Path]:
        """扫描所有HTML文件"""
        self.html_files = list(self.static_dir.glob("*.html"))
        print(f"🔍 发现 {len(self.html_files)} 个HTML文件")
        return self.html_files
    
    def get_version_string(self, mode: str = "dev") -> str:
        """生成版本字符串"""
        if mode == "dev":
            # 开发模式：使用当前时间戳
            return str(int(time.time()))
        elif mode == "prod":
            # 生产模式：尝试使用git commit hash
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, cwd=self.project_root
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except:
                pass
            # 备用：使用固定时间戳
            return "prod-" + str(int(time.time()))
        else:
            return mode  # 自定义版本号
    
    def analyze_file_references(self, html_file: Path) -> Dict:
        """分析HTML文件中的JS/CSS引用"""
        content = html_file.read_text(encoding='utf-8')
        
        js_matches = self.js_pattern.findall(content)
        css_matches = self.css_pattern.findall(content)
        
        return {
            'js_files': [match[0] for match in js_matches],
            'css_files': [match[0] for match in css_matches],
            'js_with_version': [match for match in js_matches if match[1]],
            'css_with_version': [match for match in css_matches if match[1]]
        }
    
    def update_html_file(self, html_file: Path, version: str, dry_run: bool = False) -> bool:
        """更新单个HTML文件的版本号"""
        content = html_file.read_text(encoding='utf-8')
        original_content = content
        changes_made = False
        
        # 更新JS文件引用
        def replace_js(match):
            nonlocal changes_made
            file_path = match.group(1)
            changes_made = True
            return f'<script src="{file_path}?v={version}">'
        
        # 更新CSS文件引用 - 修复正则替换
        def replace_css(match):
            nonlocal changes_made
            file_path = match.group(1)
            # 保留link标签的其他属性，只更新href
            full_match = match.group(0)
            # 找到href部分并替换
            new_href = f'href="{file_path}?v={version}"'
            # 替换原有的href部分
            if 'href=' in full_match:
                # 使用更精确的替换
                new_match = re.sub(r'href="[^"]*"', new_href, full_match)
                changes_made = True
                return new_match
            return full_match
        
        # 执行替换
        content = self.js_pattern.sub(replace_js, content)
        content = self.css_pattern.sub(replace_css, content)
        
        if changes_made and not dry_run:
            html_file.write_text(content, encoding='utf-8')
            self.updated_files.append(html_file)
            
        return changes_made
    
    def update_all_files(self, mode: str = "dev", dry_run: bool = False) -> Dict:
        """批量更新所有HTML文件"""
        if not self.html_files:
            self.scan_html_files()
            
        version = self.get_version_string(mode)
        results = {
            'version': version,
            'updated_files': [],
            'skipped_files': [],
            'stats': {'js_refs': 0, 'css_refs': 0}
        }
        
        print(f"🚀 {'预览模式' if dry_run else '更新模式'}: 版本号 v={version}")
        print("=" * 60)
        
        for html_file in self.html_files:
            analysis = self.analyze_file_references(html_file)
            
            print(f"📄 {html_file.name}")
            print(f"   JS引用: {len(analysis['js_files'])} 个")
            print(f"   CSS引用: {len(analysis['css_files'])} 个")
            
            if analysis['js_files'] or analysis['css_files']:
                if self.update_html_file(html_file, version, dry_run):
                    results['updated_files'].append(html_file.name)
                    results['stats']['js_refs'] += len(analysis['js_files'])
                    results['stats']['css_refs'] += len(analysis['css_files'])
                    print(f"   ✅ {'将更新' if dry_run else '已更新'}")
                else:
                    results['skipped_files'].append(html_file.name)
                    print(f"   ⏭️ 无需更新")
            else:
                results['skipped_files'].append(html_file.name)
                print(f"   ⏭️ 无静态资源引用")
            print()
        
        return results
    
    def create_dev_refresh_script(self):
        """创建开发环境快速刷新脚本"""
        script_path = self.project_root / "tools" / "utils" / "refresh_static_cache.sh"
        script_content = f"""#!/bin/bash
# 快速刷新静态资源缓存
echo "🔄 刷新静态资源缓存..."
python3 "{self.project_root}/tools/utils/static_version_manager.py" --mode dev --quiet
echo "✅ 缓存刷新完成"
"""
        script_path.write_text(script_content)
        script_path.chmod(0o755)
        print(f"📝 创建快速刷新脚本: {script_path}")
    
    def analyze_current_state(self):
        """分析当前静态资源状态"""
        if not self.html_files:
            self.scan_html_files()
            
        total_js = 0
        total_css = 0
        versioned_js = 0
        versioned_css = 0
        
        print("📊 当前静态资源分析")
        print("=" * 60)
        
        for html_file in self.html_files:
            analysis = self.analyze_file_references(html_file)
            total_js += len(analysis['js_files'])
            total_css += len(analysis['css_files'])
            versioned_js += len(analysis['js_with_version'])
            versioned_css += len(analysis['css_with_version'])
            
            if analysis['js_files'] or analysis['css_files']:
                print(f"📄 {html_file.name}")
                print(f"   JS: {len(analysis['js_files'])} ({len(analysis['js_with_version'])} 已版本化)")
                print(f"   CSS: {len(analysis['css_files'])} ({len(analysis['css_with_version'])} 已版本化)")
        
        print("=" * 60)
        print(f"📈 总计统计:")
        print(f"   JS引用: {total_js} 个 ({versioned_js} 已版本化)")
        print(f"   CSS引用: {total_css} 个 ({versioned_css} 已版本化)")
        if total_js > 0 and total_css > 0:
            print(f"   版本化率: JS {versioned_js/total_js*100:.1f}%, CSS {versioned_css/total_css*100:.1f}%")

def main():
    parser = argparse.ArgumentParser(description="静态资源版本管理工具")
    parser.add_argument("--mode", choices=["dev", "prod"], default="dev", 
                       help="版本模式: dev(时间戳) 或 prod(git hash)")
    parser.add_argument("--dry-run", action="store_true", 
                       help="预览模式，不实际修改文件")
    parser.add_argument("--analyze", action="store_true", 
                       help="仅分析当前状态")
    parser.add_argument("--create-scripts", action="store_true", 
                       help="创建便捷脚本")
    parser.add_argument("--quiet", action="store_true", 
                       help="静默模式")
    
    args = parser.parse_args()
    
    manager = StaticVersionManager()
    
    if args.analyze:
        manager.analyze_current_state()
        return
    
    if args.create_scripts:
        manager.create_dev_refresh_script()
        return
    
    # 执行版本更新
    results = manager.update_all_files(args.mode, args.dry_run)
    
    if not args.quiet:
        print("=" * 60)
        print(f"🎯 {'预览' if args.dry_run else '更新'}完成")
        print(f"版本号: v={results['version']}")
        print(f"更新文件: {len(results['updated_files'])} 个")
        print(f"跳过文件: {len(results['skipped_files'])} 个")
        print(f"JS引用: {results['stats']['js_refs']} 个")
        print(f"CSS引用: {results['stats']['css_refs']} 个")
        
        if args.dry_run:
            print("\n💡 运行 --mode dev 开始实际更新")

if __name__ == "__main__":
    main()