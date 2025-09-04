#!/usr/bin/env python3
"""
自动清理临时文件脚本
定期清理temp_media目录，防止文件积累导致性能问题
"""

import os
import time
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import logging

# 配置
TEMP_MEDIA_DIR = Path(__file__).parent.parent.parent / "temp_media"
MAX_FILE_AGE_HOURS = 1  # 文件最大保留时间（小时）
MAX_FILES_COUNT = 100   # 最大文件数量
LOG_DIR = Path(__file__).parent.parent.parent / "logs"

# 设置日志
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / "auto_clean.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def get_directory_size(path):
    """获取目录大小（MB）"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(filepath)
            except:
                pass
    return total_size / (1024 * 1024)  # 转换为MB

def clean_old_files():
    """清理旧文件"""
    if not TEMP_MEDIA_DIR.exists():
        logger.warning(f"目录不存在: {TEMP_MEDIA_DIR}")
        return 0
    
    current_time = time.time()
    max_age_seconds = MAX_FILE_AGE_HOURS * 3600
    deleted_count = 0
    deleted_size = 0
    
    try:
        for file_path in TEMP_MEDIA_DIR.glob("*"):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                
                # 删除超龄文件
                if file_age > max_age_seconds:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    deleted_count += 1
                    deleted_size += file_size
                    logger.debug(f"删除文件: {file_path.name} (年龄: {file_age/3600:.1f}小时)")
        
        if deleted_count > 0:
            deleted_size_mb = deleted_size / (1024 * 1024)
            logger.info(f"清理完成: 删除 {deleted_count} 个文件, 释放 {deleted_size_mb:.2f} MB")
    
    except Exception as e:
        logger.error(f"清理文件时出错: {e}")
    
    return deleted_count

def clean_by_count():
    """根据文件数量清理（保留最新的MAX_FILES_COUNT个文件）"""
    if not TEMP_MEDIA_DIR.exists():
        return 0
    
    try:
        # 获取所有文件并按修改时间排序
        files = []
        for file_path in TEMP_MEDIA_DIR.glob("*"):
            if file_path.is_file():
                files.append((file_path, file_path.stat().st_mtime))
        
        # 按修改时间排序（最新的在前）
        files.sort(key=lambda x: x[1], reverse=True)
        
        # 如果文件数超过限制，删除最旧的
        deleted_count = 0
        if len(files) > MAX_FILES_COUNT:
            files_to_delete = files[MAX_FILES_COUNT:]
            
            for file_path, _ in files_to_delete:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.debug(f"删除多余文件: {file_path.name}")
                except Exception as e:
                    logger.error(f"删除文件失败 {file_path}: {e}")
            
            if deleted_count > 0:
                logger.info(f"文件数量清理: 删除 {deleted_count} 个多余文件")
        
        return deleted_count
    
    except Exception as e:
        logger.error(f"按数量清理时出错: {e}")
        return 0

def get_stats():
    """获取目录统计信息"""
    if not TEMP_MEDIA_DIR.exists():
        return None
    
    file_count = len(list(TEMP_MEDIA_DIR.glob("*")))
    dir_size = get_directory_size(TEMP_MEDIA_DIR)
    
    # 获取最老和最新文件的时间
    oldest_time = None
    newest_time = None
    
    for file_path in TEMP_MEDIA_DIR.glob("*"):
        if file_path.is_file():
            mtime = file_path.stat().st_mtime
            if oldest_time is None or mtime < oldest_time:
                oldest_time = mtime
            if newest_time is None or mtime > newest_time:
                newest_time = mtime
    
    return {
        'file_count': file_count,
        'size_mb': dir_size,
        'oldest_file_age': (time.time() - oldest_time) / 3600 if oldest_time else 0,
        'newest_file_age': (time.time() - newest_time) / 3600 if newest_time else 0
    }

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="自动清理临时文件")
    parser.add_argument('--once', action='store_true', help='执行一次清理后退出')
    parser.add_argument('--interval', type=int, default=300, help='清理间隔（秒），默认300秒')
    parser.add_argument('--max-age', type=float, default=1, help='文件最大保留时间（小时），默认1小时')
    parser.add_argument('--max-files', type=int, default=100, help='最大文件数量，默认100个')
    parser.add_argument('--stats', action='store_true', help='显示统计信息')
    
    args = parser.parse_args()
    
    # 更新全局配置
    global MAX_FILE_AGE_HOURS, MAX_FILES_COUNT
    MAX_FILE_AGE_HOURS = args.max_age
    MAX_FILES_COUNT = args.max_files
    
    if args.stats:
        # 只显示统计信息
        stats = get_stats()
        if stats:
            print(f"\n📊 临时文件目录统计:")
            print(f"  文件数量: {stats['file_count']} 个")
            print(f"  总大小: {stats['size_mb']:.2f} MB")
            if stats['oldest_file_age'] > 0:
                print(f"  最老文件: {stats['oldest_file_age']:.1f} 小时前")
            if stats['newest_file_age'] > 0:
                print(f"  最新文件: {stats['newest_file_age']:.1f} 小时前")
        else:
            print("目录不存在或为空")
        return
    
    logger.info(f"临时文件自动清理启动")
    logger.info(f"配置: 最大保留{MAX_FILE_AGE_HOURS}小时, 最多{MAX_FILES_COUNT}个文件")
    
    if args.once:
        # 执行一次清理
        stats_before = get_stats()
        
        deleted_by_age = clean_old_files()
        deleted_by_count = clean_by_count()
        
        stats_after = get_stats()
        
        if stats_before and stats_after:
            print(f"\n🧹 清理结果:")
            print(f"  清理前: {stats_before['file_count']} 个文件, {stats_before['size_mb']:.2f} MB")
            print(f"  清理后: {stats_after['file_count']} 个文件, {stats_after['size_mb']:.2f} MB")
            print(f"  共删除: {deleted_by_age + deleted_by_count} 个文件")
    else:
        # 持续运行模式
        logger.info(f"进入持续清理模式，间隔{args.interval}秒")
        
        while True:
            try:
                # 清理旧文件
                clean_old_files()
                
                # 清理多余文件
                clean_by_count()
                
                # 显示当前状态
                stats = get_stats()
                if stats:
                    logger.info(f"当前状态: {stats['file_count']}个文件, {stats['size_mb']:.2f}MB")
                
                # 等待下次清理
                time.sleep(args.interval)
                
            except KeyboardInterrupt:
                logger.info("收到停止信号，退出清理程序")
                break
            except Exception as e:
                logger.error(f"清理循环出错: {e}")
                time.sleep(args.interval)

if __name__ == "__main__":
    main()