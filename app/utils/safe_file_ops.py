"""
安全的文件操作工具
提供并发安全的文件读写操作
"""
import json
import fcntl
import threading
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SafeFileOperation:
    """线程安全的文件操作类"""
    
    _locks = {}
    _lock = threading.Lock()
    
    @classmethod
    def _get_lock(cls, file_path: Path) -> threading.Lock:
        """获取文件对应的锁"""
        file_str = str(file_path)
        with cls._lock:
            if file_str not in cls._locks:
                cls._locks[file_str] = threading.Lock()
            return cls._locks[file_str]
    
    @classmethod
    def read_json_safe(cls, file_path: Path) -> Optional[Dict[str, Any]]:
        """安全地读取JSON文件"""
        if not file_path.exists():
            return None
        
        file_lock = cls._get_lock(file_path)
        
        with file_lock:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    # 使用共享锁（读锁）
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    try:
                        return json.load(f)
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                logger.error(f"读取文件失败 {file_path}: {e}")
                return None
    
    @classmethod
    def write_json_safe(cls, file_path: Path, data: Dict[str, Any], 
                       backup: bool = True) -> bool:
        """安全地写入JSON文件（原子写入）"""
        file_lock = cls._get_lock(file_path)
        
        with file_lock:
            try:
                # 创建临时文件
                temp_path = file_path.with_suffix('.tmp')
                
                # 写入临时文件
                with open(temp_path, 'w', encoding='utf-8') as f:
                    # 使用排他锁（写锁）
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())  # 确保写入磁盘
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
                # 备份原文件（如果存在且需要备份）
                if backup and file_path.exists():
                    backup_dir = file_path.parent / "backups"
                    backup_dir.mkdir(exist_ok=True)
                    
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = backup_dir / f"{file_path.stem}_backup_{timestamp}.json"
                    shutil.copy2(file_path, backup_path)
                    
                    # 只保留最近10个备份
                    cls._cleanup_old_backups(backup_dir, file_path.stem, keep=10)
                
                # 原子替换
                temp_path.replace(file_path)
                
                logger.debug(f"成功写入文件 {file_path}")
                return True
                
            except Exception as e:
                logger.error(f"写入文件失败 {file_path}: {e}")
                # 清理临时文件
                if 'temp_path' in locals() and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except:
                        pass
                return False
    
    @classmethod
    def update_json_safe(cls, file_path: Path, 
                         update_func: callable,
                         default_data: Dict[str, Any] = None) -> bool:
        """安全地更新JSON文件
        
        Args:
            file_path: 文件路径
            update_func: 更新函数，接收当前数据，返回更新后的数据
            default_data: 文件不存在时的默认数据
        """
        file_lock = cls._get_lock(file_path)
        
        with file_lock:
            try:
                # 读取当前数据
                if file_path.exists():
                    data = cls.read_json_safe(file_path)
                    if data is None:
                        data = default_data or {}
                else:
                    data = default_data or {}
                
                # 应用更新
                updated_data = update_func(data)
                
                # 写回文件
                return cls.write_json_safe(file_path, updated_data, backup=True)
                
            except Exception as e:
                logger.error(f"更新文件失败 {file_path}: {e}")
                return False
    
    @classmethod
    def _cleanup_old_backups(cls, backup_dir: Path, prefix: str, keep: int = 10):
        """清理旧备份文件"""
        try:
            # 查找所有备份文件
            backup_files = list(backup_dir.glob(f"{prefix}_backup_*.json"))
            
            # 按修改时间排序
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # 删除超出保留数量的文件
            for backup_file in backup_files[keep:]:
                try:
                    backup_file.unlink()
                    logger.debug(f"删除旧备份: {backup_file}")
                except Exception as e:
                    logger.error(f"删除备份失败 {backup_file}: {e}")
                    
        except Exception as e:
            logger.error(f"清理备份失败: {e}")