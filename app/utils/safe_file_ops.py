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
    def _get_lock_file_path(cls, file_path: Path) -> Path:
        """获取伴随锁文件路径"""
        return file_path.with_suffix(file_path.suffix + '.lock')

    @classmethod
    def read_json_safe(cls, file_path: Path) -> Optional[Dict[str, Any]]:
        """安全地读取JSON文件"""
        if not file_path.exists():
            return None

        file_lock = cls._get_lock(file_path)

        with file_lock:
            return cls._read_json_internal(file_path)

    @classmethod
    def _read_json_internal(cls, file_path: Path) -> Optional[Dict[str, Any]]:
        """内部读取方法 - 调用方必须已持有threading锁"""
        if not file_path.exists():
            return None
        try:
            lock_file_path = cls._get_lock_file_path(file_path)
            lock_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_file_path, 'a+') as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_SH)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            return None

    @classmethod
    def write_json_safe(cls, file_path: Path, data: Dict[str, Any],
                       backup: bool = True) -> bool:
        """安全地写入JSON文件（原子写入）"""
        file_lock = cls._get_lock(file_path)

        with file_lock:
            return cls._write_json_internal(file_path, data, backup)

    @classmethod
    def _write_json_internal(cls, file_path: Path, data: Dict[str, Any],
                            backup: bool = True) -> bool:
        """内部写入方法 - 调用方必须已持有threading锁"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = file_path.with_suffix('.tmp')
            lock_file_path = cls._get_lock_file_path(file_path)

            # 使用伴随锁文件进行跨进程互斥
            with open(lock_file_path, 'a+') as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    # 写入临时文件
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())

                    # 备份原文件（如果存在且需要备份）
                    if backup and file_path.exists():
                        from app.core.path_config import PathConfig
                        backup_dir = PathConfig.BACKUP_DIR
                        backup_dir.mkdir(exist_ok=True)

                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        backup_path = backup_dir / f"{file_path.stem}_backup_{timestamp}.json"
                        shutil.copy2(file_path, backup_path)

                        cls._cleanup_old_backups(backup_dir, file_path.stem, keep=10)

                    # 原子替换
                    temp_path.replace(file_path)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

            logger.debug(f"成功写入文件 {file_path}")
            return True

        except Exception as e:
            logger.error(f"写入文件失败 {file_path}: {e}")
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
        """安全地更新JSON文件（读-改-写原子操作）

        Args:
            file_path: 文件路径
            update_func: 更新函数，接收当前数据，返回更新后的数据
            default_data: 文件不存在时的默认数据
        """
        file_lock = cls._get_lock(file_path)

        with file_lock:
            try:
                # 直接调用内部方法，避免重复获取threading锁导致死锁
                data = cls._read_json_internal(file_path)
                if data is None:
                    data = default_data or {}

                updated_data = update_func(data)

                return cls._write_json_internal(file_path, updated_data, backup=False)

            except Exception as e:
                logger.error(f"更新文件失败 {file_path}: {e}")
                return False

    @classmethod
    def _cleanup_old_backups(cls, backup_dir: Path, prefix: str, keep: int = 10):
        """清理旧备份文件"""
        try:
            backup_files = list(backup_dir.glob(f"{prefix}_backup_*.json"))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            for backup_file in backup_files[keep:]:
                try:
                    backup_file.unlink()
                    logger.debug(f"删除旧备份: {backup_file}")
                except Exception as e:
                    logger.error(f"删除备份失败 {backup_file}: {e}")

        except Exception as e:
            logger.error(f"清理备份失败: {e}")
