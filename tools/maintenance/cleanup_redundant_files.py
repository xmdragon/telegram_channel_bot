#!/usr/bin/env python3
"""
系统冗余文件清理工具
根据架构分析结果，安全删除冗余和测试文件
"""
import os
import shutil
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

class RedundantFileCleaner:
    """冗余文件清理器"""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.project_root = Path(__file__).parent.parent.parent
        self.deleted_files = []
        self.skipped_files = []
        self.backup_dir = self.project_root / "backup_before_cleanup"
        
    def get_redundant_files(self) -> Dict[str, List[str]]:
        """获取冗余文件列表，按优先级分类"""
        return {
            "high_priority": [
                # 测试文件 - tools/test目录
                "tools/test/test_telegram_semantic.py",
                "tools/test/test_web_edit.py",
                "tools/test/test_hybrid_filter.py",
                "tools/test/test_actual_edit.py",
                "tools/test/test_star_issue.py",
                "tools/test/test_route_debug.py",
                "tools/test/test_filter.py",
                "tools/test/test_semantic_simple.py",
                "tools/test/test_fixed_filter.py",
                "tools/test/test_update_log.py",
                "tools/test/test_actual_corruption.py",
                "tools/test/test_refilter_simple.py",
                "tools/test/test_refilter.py",
                "tools/test/test_content_filter.py",
                "tools/test/test_intelligent_filter.py",
                "tools/test/test_filter_bug.py",
                "tools/test/test_edit_message.py",
                "tools/test/test_edit_simple.py",
                "tools/test/test_multiple_matches.py",
                "tools/test/test_unified_filter.py",
                "tools/test/test_semantic_tail_filter.py",
                "tools/test/test_redis_visual_hash.py",
                
                # 测试文件 - tools/testing目录
                "tools/testing/test_main_console_stats.py",
                "tools/testing/test_group_message_collection.py",
                "tools/testing/test_message_approval.py",
                "tools/testing/test_forward_queue.py",
                
                # filters目录下的测试和示例文件
                "app/services/filters/test_filters.py",
                "app/services/filters/test_new_filters.py",
                "app/services/filters/test_tail_filter.py",
                "app/services/filters/example_usage.py",
                "app/services/filters/usage_example.py",
                "app/services/filters/tail_filter_usage_example.py",
                
                # 其他测试文件
                "tools/utils/direct_edit_test.py",
                "tools/utils/submit_test.py",
                "tools/admin/test_grouper_fix.py",
                
                # 备份文件
                "app/telegram/bot_backup.py",
                
                # 明确的冗余文件
                "app/services/content_filter_new.py",
                
                # 特定修复脚本（已完成）
                "tools/admin/fix_message_57757.py",
            ],
            
            "medium_priority": [
                # 冗余的过滤器实现
                "app/services/smart_tail_filter.py",
                "app/services/hybrid_tail_filter.py",
                "app/services/message_deduplicator.py",
                
                # 可能过时的工具
                "tools/admin/reset_channels.py",
                "tools/admin/create_missing_messages.py",
            ],
            
            "low_priority": [
                # 正在迁移中的文件，暂不删除
                # "app/services/message_processor.py",
                # "app/services/intelligent_tail_filter.py",
            ]
        }
    
    def backup_file(self, filepath: Path) -> bool:
        """备份文件到备份目录"""
        try:
            if not filepath.exists():
                return False
                
            # 创建备份目录结构
            relative_path = filepath.relative_to(self.project_root)
            backup_path = self.backup_dir / relative_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 复制文件到备份目录
            shutil.copy2(filepath, backup_path)
            return True
        except Exception as e:
            print(f"备份失败 {filepath}: {e}")
            return False
    
    def delete_file(self, relative_path: str) -> Tuple[bool, str]:
        """删除单个文件"""
        filepath = self.project_root / relative_path
        
        if not filepath.exists():
            return False, "文件不存在"
        
        if not self.dry_run:
            try:
                # 先备份
                if self.backup_file(filepath):
                    # 删除文件
                    filepath.unlink()
                    return True, "已删除"
                else:
                    return False, "备份失败，跳过删除"
            except Exception as e:
                return False, f"删除失败: {e}"
        else:
            return True, "模拟删除"
    
    def clean_empty_dirs(self) -> int:
        """清理空目录"""
        empty_dirs = []
        
        for dirpath, dirnames, filenames in os.walk(self.project_root):
            # 跳过特殊目录
            if any(skip in dirpath for skip in ['.git', '__pycache__', 'venv', '.idea']):
                continue
                
            # 检查是否为空目录
            full_path = Path(dirpath)
            if not any(full_path.iterdir()):
                empty_dirs.append(full_path)
        
        # 删除空目录
        count = 0
        for empty_dir in sorted(empty_dirs, reverse=True):  # 从深到浅删除
            try:
                if not self.dry_run:
                    empty_dir.rmdir()
                count += 1
                print(f"{'删除' if not self.dry_run else '将删除'}空目录: {empty_dir.relative_to(self.project_root)}")
            except:
                pass
                
        return count
    
    def run(self, priority_levels: List[str] = None) -> Dict:
        """执行清理"""
        if priority_levels is None:
            priority_levels = ["high_priority"]
        
        redundant_files = self.get_redundant_files()
        stats = {
            "total_files": 0,
            "deleted": 0,
            "skipped": 0,
            "not_found": 0,
            "errors": 0,
            "size_freed": 0
        }
        
        print(f"\n{'='*60}")
        print(f"冗余文件清理工具 - {'模拟模式' if self.dry_run else '执行模式'}")
        print(f"{'='*60}\n")
        
        if not self.dry_run:
            print(f"备份目录: {self.backup_dir}")
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            print()
        
        for priority in priority_levels:
            if priority not in redundant_files:
                continue
                
            files = redundant_files[priority]
            print(f"\n处理 {priority.replace('_', ' ').title()} 文件 ({len(files)} 个):")
            print("-" * 40)
            
            for file_path in files:
                stats["total_files"] += 1
                full_path = self.project_root / file_path
                
                # 获取文件大小
                file_size = 0
                if full_path.exists():
                    file_size = full_path.stat().st_size
                
                success, message = self.delete_file(file_path)
                
                if success:
                    stats["deleted"] += 1
                    stats["size_freed"] += file_size
                    self.deleted_files.append(file_path)
                    status = "✓"
                    size_str = f" ({file_size:,} bytes)" if file_size > 0 else ""
                elif "不存在" in message:
                    stats["not_found"] += 1
                    status = "○"
                    size_str = ""
                else:
                    stats["errors"] += 1
                    self.skipped_files.append((file_path, message))
                    status = "✗"
                    size_str = ""
                
                print(f"  {status} {file_path}{size_str} - {message}")
        
        # 清理空目录
        print(f"\n清理空目录:")
        print("-" * 40)
        empty_count = self.clean_empty_dirs()
        
        # 输出统计
        print(f"\n{'='*60}")
        print("清理统计:")
        print(f"  总文件数: {stats['total_files']}")
        print(f"  已删除: {stats['deleted']}")
        print(f"  不存在: {stats['not_found']}")
        print(f"  错误: {stats['errors']}")
        print(f"  空目录: {empty_count}")
        print(f"  释放空间: {stats['size_freed']:,} bytes ({stats['size_freed']/1024/1024:.2f} MB)")
        
        if not self.dry_run and self.deleted_files:
            print(f"\n备份位置: {self.backup_dir}")
            print("提示: 如需恢复，可从备份目录复制文件")
        
        return stats


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="清理系统冗余文件")
    parser.add_argument(
        "--execute", 
        action="store_true", 
        help="实际执行删除（默认为模拟模式）"
    )
    parser.add_argument(
        "--priority",
        choices=["high", "medium", "all"],
        default="high",
        help="清理优先级 (默认: high)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="不创建备份（不推荐）"
    )
    
    args = parser.parse_args()
    
    # 确定要清理的优先级
    if args.priority == "high":
        priorities = ["high_priority"]
    elif args.priority == "medium":
        priorities = ["high_priority", "medium_priority"]
    else:  # all
        priorities = ["high_priority", "medium_priority", "low_priority"]
    
    # 创建清理器
    cleaner = RedundantFileCleaner(dry_run=not args.execute)
    
    # 如果是执行模式，要求确认
    if args.execute:
        print("⚠️  警告: 您即将执行实际删除操作！")
        print(f"将删除 {args.priority} 优先级的冗余文件")
        if not args.no_backup:
            print("文件将先备份到 backup_before_cleanup 目录")
        else:
            print("⚠️  不创建备份！")
        
        confirm = input("\n确认执行? (输入 'yes' 继续): ")
        if confirm.lower() != 'yes':
            print("已取消")
            return
    
    # 执行清理
    stats = cleaner.run(priority_levels=priorities)
    
    # 如果是模拟模式，提示如何执行
    if not args.execute:
        print(f"\n这是模拟运行。要实际删除文件，请使用: --execute")
        print(f"示例: python3 {__file__} --execute --priority=high")


if __name__ == "__main__":
    main()