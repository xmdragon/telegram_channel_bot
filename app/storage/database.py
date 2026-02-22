"""
SQLite数据库管理器 - 替代RedisManager的统一存储层
单例模式，线程安全，WAL模式
"""
import json
import logging
import sqlite3
import threading
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

from app.core.path_config import PathConfig
from app.utils.timezone import get_current_time
from app.storage.database_messages import DatabaseMessagesMixin
from app.storage.database_schema import SCHEMA_SQL, FTS_TRIGGERS

logger = logging.getLogger(__name__)


class DatabaseManager(DatabaseMessagesMixin):
    """SQLite数据库管理器 - 单例模式，线程安全"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._local = threading.local()
        self._db_path = str(PathConfig.DATABASE_FILE)
        self._initialized = True
        self._ensure_db_dir()
        self._create_tables()
        logger.info(f"DatabaseManager初始化完成: {self._db_path}")

    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        PathConfig.DB_DIR.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(
                self._db_path, timeout=5.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA cache_size=-65536")  # 64MB
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def _create_tables(self):
        """创建所有表"""
        conn = self._get_connection()
        conn.executescript(SCHEMA_SQL)
        conn.executescript(FTS_TRIGGERS)
        conn.commit()

    # =============================================
    # 向后兼容属性
    # =============================================

    @property
    def redis(self):
        """兼容性属性 - 返回self"""
        return self

    @property
    def client(self):
        """兼容性属性 - 返回self"""
        return self

    def is_healthy(self) -> bool:
        """检查数据库连接健康状态"""
        try:
            self._get_connection().execute("SELECT 1")
            return True
        except Exception:
            return False

    # =============================================
    # 缓存操作
    # =============================================

    def cache_set(self, key: str, value: Any, expire: int = 3600) -> bool:
        """设置缓存"""
        try:
            conn = self._get_connection()
            expires = self._calc_expires(expire) if expire > 0 else None
            val_json = json.dumps(value, ensure_ascii=False, default=str)
            conn.execute(
                """INSERT OR REPLACE INTO cache (key, value, expires_at)
                   VALUES (?, ?, ?)""",
                (key, val_json, expires),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"设置缓存失败: {e}")
            return False

    def cache_get(self, key: str) -> Any:
        """获取缓存"""
        try:
            conn = self._get_connection()
            row = conn.execute(
                """SELECT value FROM cache
                   WHERE key = ? AND (expires_at IS NULL
                   OR expires_at > ?)""",
                (key, get_current_time().isoformat()),
            ).fetchone()
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"获取缓存失败: {e}")
            return None

    def cache_delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            conn = self._get_connection()
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")
            return False

    def cache_exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            conn = self._get_connection()
            row = conn.execute(
                """SELECT 1 FROM cache WHERE key = ?
                   AND (expires_at IS NULL OR expires_at > ?)""",
                (key, get_current_time().isoformat()),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def cache_keys(self, prefix: str) -> list:
        """获取匹配前缀的缓存键列表"""
        try:
            conn = self._get_connection()
            rows = conn.execute(
                """SELECT key FROM cache
                   WHERE key LIKE ?
                   AND (expires_at IS NULL OR expires_at > ?)""",
                (prefix + "%", get_current_time().isoformat()),
            ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    # =============================================
    # 会话操作
    # =============================================

    def save_session(self, token: str, session_data: Dict[str, Any],
                     expire_seconds: int = 3600) -> bool:
        """保存会话"""
        try:
            conn = self._get_connection()
            now = get_current_time().isoformat()
            expires = self._calc_expires(expire_seconds)
            data_json = json.dumps(
                session_data, ensure_ascii=False, default=str)
            conn.execute(
                """INSERT OR REPLACE INTO sessions
                   (token, data, last_activity, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (token, data_json, now, expires),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"保存会话失败: {e}")
            return False

    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        try:
            conn = self._get_connection()
            now = get_current_time().isoformat()
            row = conn.execute(
                """SELECT data FROM sessions
                   WHERE token = ? AND expires_at > ?""",
                (token, now),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE sessions SET last_activity = ? WHERE token = ?",
                    (now, token),
                )
                conn.commit()
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"获取会话失败: {e}")
            return None

    def delete_session(self, token: str) -> bool:
        """删除会话"""
        try:
            conn = self._get_connection()
            conn.execute(
                "DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            return False

    def get_active_sessions(self) -> List[str]:
        """获取所有活跃会话token列表"""
        try:
            conn = self._get_connection()
            now = get_current_time().isoformat()
            rows = conn.execute(
                "SELECT token FROM sessions WHERE expires_at > ?",
                (now,),
            ).fetchall()
            return [r[0] for r in rows]
        except Exception as e:
            logger.error(f"获取活跃会话失败: {e}")
            return []

    # =============================================
    # 频道状态操作
    # =============================================

    def set_channel_state(self, channel_id: str,
                          state_data: Dict[str, Any]) -> bool:
        """设置频道状态"""
        try:
            conn = self._get_connection()
            now = get_current_time().isoformat()
            data_json = json.dumps(
                state_data, ensure_ascii=False, default=str)
            conn.execute(
                """INSERT OR REPLACE INTO channel_status
                   (channel_id, status, details, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (str(channel_id), state_data.get('status', ''),
                 data_json, now),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"设置频道状态失败: {e}")
            return False

    def get_channel_state(self, channel_id: str
                          ) -> Optional[Dict[str, Any]]:
        """获取频道状态"""
        try:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT details FROM channel_status WHERE channel_id = ?",
                (str(channel_id),),
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"获取频道状态失败: {e}")
            return None

    # =============================================
    # 锁操作
    # =============================================

    def acquire_lock(self, lock_name: str,
                     timeout: int = 10) -> Optional[str]:
        """获取锁"""
        try:
            conn = self._get_connection()
            identifier = f"{time.time()}_{threading.get_ident()}"
            expires = self._calc_expires(timeout)
            now = get_current_time().isoformat()
            conn.execute(
                "DELETE FROM locks WHERE lock_name = ? AND expires_at <= ?",
                (lock_name, now),
            )
            try:
                conn.execute(
                    """INSERT INTO locks
                       (lock_name, identifier, expires_at)
                       VALUES (?, ?, ?)""",
                    (lock_name, identifier, expires),
                )
                conn.commit()
                return identifier
            except sqlite3.IntegrityError:
                return None
        except Exception as e:
            logger.error(f"获取锁失败: {e}")
            return None

    def release_lock(self, lock_name: str,
                     identifier: str = None) -> bool:
        """释放锁"""
        try:
            conn = self._get_connection()
            if identifier:
                conn.execute(
                    """DELETE FROM locks
                       WHERE lock_name = ? AND identifier = ?""",
                    (lock_name, identifier),
                )
            else:
                conn.execute(
                    "DELETE FROM locks WHERE lock_name = ?",
                    (lock_name,),
                )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"释放锁失败: {e}")
            return False

    # =============================================
    # 清理和维护
    # =============================================

    def reset_all_message_data(self) -> Dict[str, int]:
        """重置所有消息数据 - 用于系统重置"""
        try:
            conn = self._get_connection()
            msg_count = conn.execute(
                "SELECT COUNT(*) FROM messages"
            ).fetchone()[0]
            conn.execute("DELETE FROM messages")
            conn.commit()
            logger.info(f"已清除所有消息数据: {msg_count} 条")
            return {"messages_deleted": msg_count}
        except Exception as e:
            logger.error(f"重置消息数据失败: {e}")
            return {"error": str(e), "messages_deleted": 0}

    def clear_all_caches(self) -> Dict[str, int]:
        """清理所有缓存"""
        try:
            conn = self._get_connection()
            tables = [
                ('cache', 'config_cache'),
                ('sessions', 'session'),
                ('text_fingerprints', 'dup_text'),
                ('text_lsh_buckets', 'lsh_bucket'),
                ('media_fingerprints', 'media_phash'),
                ('media_lsh_buckets', 'media_lsh'),
                ('media_sizes', 'media_meta'),
                ('dup_detections', 'sys_detect'),
            ]
            stats = {"total": 0}
            for table, key in tables:
                r = conn.execute(f"DELETE FROM {table}").rowcount
                stats[key] = r
                stats["total"] += r
            conn.commit()
            logger.info(f"缓存清理完成: {stats}")
            return stats
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            return {"error": str(e), "total": 0}

    def cleanup_invalid_references(self) -> Dict[str, int]:
        """清理无效索引引用 - SQLite无需清理Redis索引"""
        return {
            "cleaned_pending": 0, "cleaned_approved": 0,
            "cleaned_rejected": 0, "cleaned_channels": 0,
        }

    def cleanup_expired(self) -> Dict[str, int]:
        """清理所有expires_at已过期的行 - 替代Redis TTL"""
        try:
            conn = self._get_connection()
            now = get_current_time().isoformat()
            tables = [
                'cache', 'sessions', 'locks', 'login_attempts',
                'channel_counters', 'text_fingerprints',
                'text_lsh_buckets', 'media_fingerprints',
                'media_lsh_buckets', 'media_sizes', 'dup_detections',
            ]
            stats = {"total": 0}
            for table in tables:
                conn.execute(
                    f"""DELETE FROM {table}
                        WHERE expires_at IS NOT NULL
                        AND expires_at <= ?""",
                    (now,),
                )
                count = conn.execute(
                    "SELECT changes()").fetchone()[0]
                stats[table] = count
                stats["total"] += count
            conn.commit()
            if stats["total"] > 0:
                logger.info(f"过期数据清理完成: {stats}")
            return stats
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")
            return {"error": str(e), "total": 0}

    def find_duplicate_by_hash(self, media_hash: str) -> List[str]:
        """根据媒体哈希查找重复消息"""
        try:
            conn = self._get_connection()
            rows = conn.execute(
                """SELECT message_id FROM media_fingerprints
                   WHERE phash = ? OR dhash = ?
                   OR whash = ? OR average_hash = ?""",
                (media_hash, media_hash, media_hash, media_hash),
            ).fetchall()
            return [r[0] for r in rows]
        except Exception as e:
            logger.error(f"查找重复媒体失败: {e}")
            return []

    # =============================================
    # 工具方法
    # =============================================

    @staticmethod
    def _calc_expires(seconds):
        """计算过期时间ISO字符串"""
        dt = get_current_time() + timedelta(seconds=seconds)
        return dt.isoformat()


# =============================================
# 全局单例实例和便捷函数
# =============================================

db_manager = DatabaseManager()


def get_db_manager() -> DatabaseManager:
    """获取数据库管理器实例"""
    return db_manager


def get_message_store():
    """兼容函数 - 返回DatabaseManager实例"""
    return db_manager


def get_cache_store():
    """兼容函数 - 返回DatabaseManager实例"""
    return db_manager


def get_session_store():
    """兼容函数 - 返回DatabaseManager实例"""
    return db_manager
