#!/usr/bin/env python3
"""
训练数据恢复工具

这个脚本提供了强大的训练数据恢复功能，包括：
1. 自动检测和修复损坏的文件
2. 从备份中恢复数据
3. 合并多个备份文件
4. 数据完整性验证
5. 紧急恢复模式

使用方法:
  python3 recover_training_data.py --check                    # 检查数据完整性
  python3 recover_training_data.py --auto-recover            # 自动恢复
  python3 recover_training_data.py --restore backup.json     # 从指定备份恢复
  python3 recover_training_data.py --merge-backups           # 合并多个备份
  python3 recover_training_data.py --emergency               # 紧急恢复模式

作者: Claude Code
版本: 2.0
"""

import os
import sys
import json
import argparse
import logging
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('recovery.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class TrainingDataRecovery:
    """训练数据恢复工具类"""
    
    def __init__(self):
        self.data_dir = Path("data")
        self.backup_dir = Path("data/backups")
        self.main_data_file = Path("data/manual_training_data.json")
        # 训练历史功能已移除
        self.recovery_log = []
        
        # 确保目录存在
        self.data_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
    
    def log_operation(self, operation: str, details: str = "", success: bool = True):
        """记录恢复操作"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "details": details,
            "success": success
        }
        self.recovery_log.append(log_entry)
        
        if success:
            logger.info(f"✅ {operation}: {details}")
        else:
            logger.error(f"❌ {operation}: {details}")
    
    def calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """计算文件SHA256哈希"""
        if not file_path.exists():
            return None
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败 {file_path}: {e}")
            return None
    
    def verify_json_integrity(self, file_path: Path) -> Tuple[bool, str]:
        """验证JSON文件完整性"""
        if not file_path.exists():
            return False, "文件不存在"
        
        if file_path.stat().st_size == 0:
            return False, "文件为空"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 验证基本结构
            if file_path.name.startswith('manual_training_data'):
                if not isinstance(data, dict) or 'channels' not in data:
                    return False, "训练数据结构无效"
                
                # 验证channels结构
                channels = data['channels']
                if not isinstance(channels, dict):
                    return False, "channels字段无效"
                
                for channel_id, channel_data in channels.items():
                    if not isinstance(channel_data, dict) or 'samples' not in channel_data:
                        return False, f"频道 {channel_id} 数据结构无效"
            
            # training_history 功能已移除
            
            return True, "JSON格式正确"
            
        except json.JSONDecodeError as e:
            return False, f"JSON解析错误: {e}"
        except Exception as e:
            return False, f"验证失败: {e}"
    
    def get_file_info(self, file_path: Path) -> Dict:
        """获取文件详细信息"""
        info = {
            "path": str(file_path),
            "exists": file_path.exists(),
            "size": 0,
            "valid": False,
            "error": "",
            "hash": None,
            "modified": None,
            "content_summary": {}
        }
        
        if not file_path.exists():
            info["error"] = "文件不存在"
            return info
        
        try:
            stat = file_path.stat()
            info["size"] = stat.st_size
            info["modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
            info["hash"] = self.calculate_file_hash(file_path)
            
            valid, error = self.verify_json_integrity(file_path)
            info["valid"] = valid
            info["error"] = error
            
            # 如果文件有效，获取内容摘要
            if valid:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if 'channels' in data:
                        info["content_summary"] = {
                            "type": "training_data",
                            "channels_count": len(data["channels"]),
                            "total_samples": sum(len(c.get("samples", [])) for c in data["channels"].values()),
                            "last_updated": data.get("updated_at", "unknown")
                        }
                    elif 'history' in data:
                        info["content_summary"] = {
                            "type": "other",  # training_history功能已移除 
                            "history_count": len(data.get("history", [])),
                            "total_samples": data.get("stats", {}).get("total_samples", 0)
                        }
                except:
                    pass
            
        except Exception as e:
            info["error"] = f"获取文件信息失败: {e}"
        
        return info
    
    def check_data_integrity(self) -> Dict:
        """检查所有数据文件的完整性"""
        logger.info("🔍 开始检查数据完整性...")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "main_files": {},
            "backup_files": [],
            "summary": {
                "healthy_files": 0,
                "corrupted_files": 0,
                "missing_files": 0,
                "total_backups": 0,
                "valid_backups": 0
            }
        }
        
        # 检查主要文件
        for file_path in [self.main_data_file, self.history_file]:
            info = self.get_file_info(file_path)
            report["main_files"][file_path.name] = info
            
            if not info["exists"]:
                report["summary"]["missing_files"] += 1
            elif info["valid"]:
                report["summary"]["healthy_files"] += 1
            else:
                report["summary"]["corrupted_files"] += 1
        
        # 检查备份文件
        backup_files = list(self.backup_dir.glob("*.json"))
        report["summary"]["total_backups"] = len(backup_files)
        
        for backup_file in sorted(backup_files, key=lambda f: f.stat().st_mtime, reverse=True):
            info = self.get_file_info(backup_file)
            report["backup_files"].append(info)
            
            if info["valid"]:
                report["summary"]["valid_backups"] += 1
        
        # 记录检查结果
        healthy = report["summary"]["healthy_files"]
        corrupted = report["summary"]["corrupted_files"]
        missing = report["summary"]["missing_files"]
        valid_backups = report["summary"]["valid_backups"]
        
        self.log_operation(
            "数据完整性检查",
            f"健康: {healthy}, 损坏: {corrupted}, 丢失: {missing}, 有效备份: {valid_backups}"
        )
        
        return report
    
    def find_best_backup(self, file_type: str) -> Optional[Path]:
        """查找最佳备份文件"""
        pattern = f"*{file_type}*.json"
        backup_files = list(self.backup_dir.glob(pattern))
        
        if not backup_files:
            return None
        
        # 按修改时间排序，优先选择最新的有效备份
        for backup_file in sorted(backup_files, key=lambda f: f.stat().st_mtime, reverse=True):
            valid, _ = self.verify_json_integrity(backup_file)
            if valid:
                logger.info(f"找到最佳备份: {backup_file}")
                return backup_file
        
        logger.warning(f"未找到有效的 {file_type} 备份文件")
        return None
    
    def create_backup(self, source_file: Path, backup_name: str) -> Optional[Path]:
        """创建备份文件"""
        if not source_file.exists() or source_file.stat().st_size == 0:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        backup_file = self.backup_dir / f"{backup_name}_{timestamp}.json"
        
        try:
            shutil.copy2(source_file, backup_file)
            self.log_operation("创建备份", f"{source_file} -> {backup_file}")
            return backup_file
        except Exception as e:
            self.log_operation("创建备份", f"失败: {e}", False)
            return None
    
    def restore_from_backup(self, target_file: Path, backup_file: Path) -> bool:
        """从备份恢复文件"""
        try:
            # 验证备份文件
            valid, error = self.verify_json_integrity(backup_file)
            if not valid:
                self.log_operation("恢复验证", f"备份无效: {error}", False)
                return False
            
            # 备份当前文件（如果存在且有效）
            if target_file.exists() and target_file.stat().st_size > 0:
                backup_current = self.create_backup(target_file, f"{target_file.stem}_before_restore")
                if backup_current:
                    self.log_operation("恢复前备份", f"已备份当前文件: {backup_current}")
            
            # 执行恢复
            shutil.copy2(backup_file, target_file)
            
            # 验证恢复结果
            valid, error = self.verify_json_integrity(target_file)
            if valid:
                self.log_operation("文件恢复", f"{backup_file} -> {target_file}")
                return True
            else:
                self.log_operation("恢复验证", f"恢复后验证失败: {error}", False)
                return False
                
        except Exception as e:
            self.log_operation("文件恢复", f"失败: {e}", False)
            return False
    
    def auto_recover(self) -> bool:
        """自动恢复损坏的文件"""
        logger.info("🚑 开始自动恢复...")
        
        integrity_report = self.check_data_integrity()
        recovery_needed = False
        recovery_success = True
        
        # 恢复主数据文件
        main_file_info = integrity_report["main_files"].get("manual_training_data.json", {})
        if not main_file_info.get("valid", False):
            recovery_needed = True
            best_backup = self.find_best_backup("manual_training_data")
            if best_backup:
                if not self.restore_from_backup(self.main_data_file, best_backup):
                    recovery_success = False
            else:
                self.log_operation("自动恢复", "未找到训练数据备份", False)
                recovery_success = False
        
        # 恢复历史文件
        # training_history 恢复功能已移除
        
        if not recovery_needed:
            self.log_operation("自动恢复", "所有文件状态正常，无需恢复")
        else:
            result_msg = "自动恢复完成" if recovery_success else "自动恢复部分失败"
            self.log_operation("自动恢复", result_msg, recovery_success)
        
        return recovery_success
    
    def merge_backups(self) -> bool:
        """合并多个备份文件，创建最完整的数据集"""
        logger.info("🔄 开始合并备份文件...")
        
        # 收集所有有效的训练数据备份
        training_backups = []
        for backup_file in self.backup_dir.glob("*manual_training_data*.json"):
            valid, _ = self.verify_json_integrity(backup_file)
            if valid:
                training_backups.append(backup_file)
        
        if len(training_backups) < 2:
            self.log_operation("合并备份", "可用备份少于2个，无需合并")
            return True
        
        try:
            # 合并所有训练数据
            merged_data = {
                "channels": {},
                "updated_at": datetime.now().isoformat(),
                "version": "2.0_merged",
                "merged_from": []
            }
            
            for backup_file in training_backups:
                try:
                    with open(backup_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    merged_data["merged_from"].append({
                        "file": backup_file.name,
                        "timestamp": data.get("updated_at", "unknown")
                    })
                    
                    # 合并频道数据
                    for channel_id, channel_data in data.get("channels", {}).items():
                        if channel_id not in merged_data["channels"]:
                            merged_data["channels"][channel_id] = channel_data
                        else:
                            # 合并样本数据，去重
                            existing_samples = merged_data["channels"][channel_id].get("samples", [])
                            new_samples = channel_data.get("samples", [])
                            
                            # 使用哈希去重
                            existing_hashes = set()
                            for sample in existing_samples:
                                sample_hash = hashlib.sha256(f"{sample.get('original', '')}|{sample.get('tail', '')}".encode()).hexdigest()
                                existing_hashes.add(sample_hash)
                            
                            for sample in new_samples:
                                sample_hash = hashlib.sha256(f"{sample.get('original', '')}|{sample.get('tail', '')}".encode()).hexdigest()
                                if sample_hash not in existing_hashes:
                                    existing_samples.append(sample)
                                    existing_hashes.add(sample_hash)
                            
                            merged_data["channels"][channel_id]["samples"] = existing_samples
                            merged_data["channels"][channel_id]["sample_count"] = len(existing_samples)
                            
                except Exception as e:
                    logger.error(f"处理备份文件失败 {backup_file}: {e}")
            
            # 保存合并结果
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            merged_file = self.backup_dir / f"merged_training_data_{timestamp}.json"
            
            with open(merged_file, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)
            
            total_channels = len(merged_data["channels"])
            total_samples = sum(len(c.get("samples", [])) for c in merged_data["channels"].values())
            
            self.log_operation(
                "合并备份",
                f"成功合并 {len(training_backups)} 个备份，包含 {total_channels} 个频道，{total_samples} 个样本"
            )
            
            logger.info(f"合并结果已保存到: {merged_file}")
            return True
            
        except Exception as e:
            self.log_operation("合并备份", f"失败: {e}", False)
            return False
    
    def emergency_recovery(self) -> bool:
        """紧急恢复模式，尝试所有可能的恢复方法"""
        logger.info("🆘 启动紧急恢复模式...")
        
        recovery_success = True
        
        # 步骤1: 检查完整性
        integrity_report = self.check_data_integrity()
        
        # 步骤2: 尝试自动恢复
        if not self.auto_recover():
            recovery_success = False
        
        # 步骤3: 合并备份
        try:
            self.merge_backups()
        except Exception as e:
            logger.error(f"合并备份失败: {e}")
            recovery_success = False
        
        # 步骤4: 创建紧急备份
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        emergency_report = {
            "emergency_recovery": {
                "timestamp": timestamp,
                "integrity_report": integrity_report,
                "recovery_log": self.recovery_log,
                "success": recovery_success
            }
        }
        
        emergency_report_file = self.backup_dir / f"emergency_recovery_report_{timestamp}.json"
        try:
            with open(emergency_report_file, 'w', encoding='utf-8') as f:
                json.dump(emergency_report, f, ensure_ascii=False, indent=2)
            logger.info(f"紧急恢复报告已保存到: {emergency_report_file}")
        except Exception as e:
            logger.error(f"保存紧急恢复报告失败: {e}")
        
        result_msg = "紧急恢复完成" if recovery_success else "紧急恢复遇到问题"
        self.log_operation("紧急恢复", result_msg, recovery_success)
        
        return recovery_success
    
    def save_recovery_log(self):
        """保存恢复日志"""
        if not self.recovery_log:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.backup_dir / f"recovery_log_{timestamp}.json"
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "recovery_session": {
                        "timestamp": timestamp,
                        "operations": self.recovery_log
                    }
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"恢复日志已保存到: {log_file}")
        except Exception as e:
            logger.error(f"保存恢复日志失败: {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="训练数据恢复工具")
    parser.add_argument("--check", action="store_true", help="检查数据完整性")
    parser.add_argument("--auto-recover", action="store_true", help="自动恢复损坏的文件")
    parser.add_argument("--restore", metavar="BACKUP_FILE", help="从指定备份文件恢复")
    parser.add_argument("--merge-backups", action="store_true", help="合并多个备份文件")
    parser.add_argument("--emergency", action="store_true", help="紧急恢复模式")
    parser.add_argument("--target", choices=["training", "history", "both"], default="both",
                       help="指定恢复目标类型")
    
    args = parser.parse_args()
    
    if not any([args.check, args.auto_recover, args.restore, args.merge_backups, args.emergency]):
        parser.print_help()
        return
    
    recovery = TrainingDataRecovery()
    
    try:
        if args.check:
            print("📊 数据完整性检查报告")
            print("=" * 50)
            report = recovery.check_data_integrity()
            
            # 打印主要文件状态
            for filename, info in report["main_files"].items():
                status = "✅ 健康" if info["valid"] else "❌ 损坏" if info["exists"] else "⚠️ 丢失"
                print(f"{filename}: {status}")
                if info.get("content_summary"):
                    summary = info["content_summary"]
                    if summary.get("type") == "training_data":
                        print(f"  📁 频道数: {summary.get('channels_count', 0)}")
                        print(f"  📝 样本数: {summary.get('total_samples', 0)}")
                    # elif summary.get("type") == "training_history":  # 功能已移除
                        # print(f"  📜 历史记录: {summary.get('history_count', 0)}")  # 功能已移除
                print()
            
            # 打印备份统计
            summary = report["summary"]
            print(f"📦 备份文件统计:")
            print(f"  总数: {summary['total_backups']}")
            print(f"  有效: {summary['valid_backups']}")
            print(f"  无效: {summary['total_backups'] - summary['valid_backups']}")
        
        elif args.auto_recover:
            success = recovery.auto_recover()
            if success:
                print("✅ 自动恢复完成")
            else:
                print("❌ 自动恢复失败，请查看日志")
                sys.exit(1)
        
        elif args.restore:
            backup_file = Path("data/backups") / args.restore
            if not backup_file.exists():
                print(f"❌ 备份文件不存在: {backup_file}")
                sys.exit(1)
            
            # 确定目标文件
            targets = []
            if args.target in ["training", "both"]:
                targets.append((recovery.main_data_file, "训练数据"))
            if args.target in ["history", "both"]:
                targets.append((recovery.history_file, "历史数据"))
            
            success = True
            for target_file, description in targets:
                if recovery.restore_from_backup(target_file, backup_file):
                    print(f"✅ {description}恢复成功")
                else:
                    print(f"❌ {description}恢复失败")
                    success = False
            
            if not success:
                sys.exit(1)
        
        elif args.merge_backups:
            if recovery.merge_backups():
                print("✅ 备份合并完成")
            else:
                print("❌ 备份合并失败")
                sys.exit(1)
        
        elif args.emergency:
            print("🆘 启动紧急恢复模式...")
            if recovery.emergency_recovery():
                print("✅ 紧急恢复完成")
            else:
                print("⚠️ 紧急恢复完成，但发现问题，请查看日志")
        
    except KeyboardInterrupt:
        print("\n⏸️ 操作被用户中断")
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        print(f"❌ 程序执行失败: {e}")
        sys.exit(1)
    finally:
        # 保存恢复日志
        recovery.save_recovery_log()

if __name__ == "__main__":
    main()