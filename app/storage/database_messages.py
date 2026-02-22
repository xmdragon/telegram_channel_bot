"""
DatabaseManager 消息操作方法 - Mixin类
拆分自 database.py，保持文件≤500行
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

# 消息表核心列 - 存为独立SQL列，其余放入data JSON
MESSAGE_CORE_FIELDS = {
    'id', 'channel_id', 'message_id', 'status',
    'content', 'filtered_content', 'created_at', 'updated_at',
}


def _split_message_data(channel_id, message_id, message_data):
    """将消息数据拆分为核心列和JSON data"""
    now = get_current_time().isoformat()
    core = {
        'id': f"{channel_id}:{message_id}",
        'channel_id': str(channel_id),
        'message_id': int(message_id),
        'status': message_data.get('status', 'pending'),
        'content': message_data.get('content', ''),
        'filtered_content': message_data.get('filtered_content', ''),
        'created_at': message_data.get('created_at', now),
        'updated_at': now,
    }
    extra = {
        k: v for k, v in message_data.items()
        if k not in MESSAGE_CORE_FIELDS
    }
    return core, extra


def _merge_message_row(row):
    """将数据库行合并为与Redis版本兼容的Dict"""
    if not row:
        return None
    result = dict(row)
    data_json = result.pop('data', None)
    if data_json:
        try:
            extra = json.loads(data_json) if isinstance(data_json, str) else data_json
            if isinstance(extra, dict):
                result.update(extra)
        except (json.JSONDecodeError, TypeError):
            pass
    return result


class DatabaseMessagesMixin:
    """消息相关的数据库操作 - 作为Mixin混入DatabaseManager"""

    def save_message(self, channel_id: str, message_id: int,
                     message_data: Dict[str, Any]) -> bool:
        """保存消息"""
        try:
            core, extra = _split_message_data(channel_id, message_id, message_data)
            conn = self._get_connection()
            conn.execute(
                """INSERT OR REPLACE INTO messages
                   (id, channel_id, message_id, status, content,
                    filtered_content, created_at, updated_at, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (core['id'], core['channel_id'], core['message_id'],
                 core['status'], core['content'], core['filtered_content'],
                 core['created_at'], core['updated_at'],
                 json.dumps(extra, ensure_ascii=False, default=str)),
            )
            conn.commit()
            logger.debug(f"消息已保存: {channel_id}:{message_id}")
            return True
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
            return False

    def get_message(self, channel_id: str, message_id: int,
                    silent: bool = False) -> Optional[Dict[str, Any]]:
        """获取消息"""
        try:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT * FROM messages WHERE id = ?",
                (f"{channel_id}:{message_id}",),
            ).fetchone()
            return _merge_message_row(row)
        except Exception as e:
            if not silent:
                logger.error(f"获取消息失败: {e}")
            return None

    def get_message_by_id(self, message_id: str,
                          silent: bool = False) -> Optional[Dict[str, Any]]:
        """通过组合ID获取消息 (channel_id:message_id)"""
        try:
            if ':' not in message_id:
                if not silent:
                    logger.error(f"消息ID格式错误: {message_id}")
                return None
            channel_id, msg_id = message_id.rsplit(':', 1)
            return self.get_message(channel_id, int(msg_id), silent)
        except (ValueError, Exception) as e:
            if not silent:
                logger.error(f"获取消息失败: {e}")
            return None

    def update_message_atomic(self, message_id: str,
                              update_data: Dict[str, Any],
                              user_id: str = None) -> bool:
        """原子更新消息 - SQLite事务天然提供原子性"""
        try:
            if ':' not in message_id:
                logger.error(f"消息ID格式错误: {message_id}")
                return False
            conn = self._get_connection()
            row = conn.execute(
                "SELECT * FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
            if not row:
                logger.error(f"消息不存在: {message_id}")
                return False

            existing = _merge_message_row(row)
            from app.core.message_status import is_valid_status
            for key, value in update_data.items():
                if value is None:
                    existing.pop(key, None)
                else:
                    existing[key] = value
            existing['updated_at'] = get_current_time().isoformat()
            if user_id:
                existing['updated_by'] = user_id
            new_status = existing.get('status', 'pending')
            if not is_valid_status(new_status):
                existing['status'] = 'pending'

            return self._write_message_back(conn, message_id, existing)
        except Exception as e:
            logger.error(f"原子更新消息失败: {e}")
            return False

    def _write_message_back(self, conn, msg_id, data):
        """将合并后的数据写回messages表"""
        core_vals = {k: data.get(k, '') for k in MESSAGE_CORE_FIELDS}
        extra = {k: v for k, v in data.items() if k not in MESSAGE_CORE_FIELDS}
        conn.execute(
            """UPDATE messages SET status=?, content=?, filtered_content=?,
               updated_at=?, data=? WHERE id=?""",
            (core_vals['status'], core_vals['content'],
             core_vals['filtered_content'], core_vals['updated_at'],
             json.dumps(extra, ensure_ascii=False, default=str), msg_id),
        )
        conn.commit()
        return True

    def update_message_field(self, channel_id: str, message_id: int,
                             field_name: str, field_value: Any,
                             user_id: str = None) -> bool:
        """更新消息的单个字段"""
        full_id = f"{channel_id}:{message_id}"
        return self.update_message_atomic(full_id, {field_name: field_value}, user_id)

    def update_message(self, channel_id: str, message_id: int,
                       update_data: Dict[str, Any]) -> bool:
        """兼容方法 - 调用原子更新"""
        return self.update_message_atomic(f"{channel_id}:{message_id}", update_data)

    def update_message_status(self, message_id: str, new_status: str,
                              user_id: str = None) -> bool:
        """更新消息状态"""
        return self.update_message_atomic(message_id, {'status': new_status}, user_id)

    def update_message_fields(self, message_id: str,
                              fields: Dict[str, Any]) -> bool:
        """更新消息的多个字段"""
        return self.update_message_atomic(message_id, fields)

    def delete_message(self, channel_id_or_full_id: str,
                       message_id: int = None) -> bool:
        """删除消息 - 支持两种调用方式"""
        try:
            if message_id is None and ':' in channel_id_or_full_id:
                full_id = channel_id_or_full_id
            elif message_id is not None:
                full_id = f"{channel_id_or_full_id}:{message_id}"
            else:
                logger.error(f"消息ID格式错误: {channel_id_or_full_id}")
                return False
            conn = self._get_connection()
            conn.execute("DELETE FROM messages WHERE id = ?", (full_id,))
            conn.commit()
            logger.debug(f"消息已删除: {full_id}")
            return True
        except Exception as e:
            logger.error(f"删除消息失败: {e}")
            return False

    def get_messages_by_channel(self, channel_id: str, limit: int = 50,
                                offset: int = 0, status: str = None,
                                reverse: bool = True) -> List[Dict[str, Any]]:
        """获取频道消息列表"""
        try:
            order = "DESC" if reverse else "ASC"
            conn = self._get_connection()
            if status:
                rows = conn.execute(
                    f"""SELECT * FROM messages
                        WHERE channel_id = ? AND status = ?
                        ORDER BY created_at {order} LIMIT ? OFFSET ?""",
                    (str(channel_id), status, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""SELECT * FROM messages
                        WHERE channel_id = ?
                        ORDER BY created_at {order} LIMIT ? OFFSET ?""",
                    (str(channel_id), limit, offset),
                ).fetchall()
            return [_merge_message_row(r) for r in rows]
        except Exception as e:
            logger.error(f"获取频道消息失败: {e}")
            return []

    def _get_messages_by_statuses(self, statuses, limit, offset, reverse):
        """根据多个状态获取消息 - 内部共享方法"""
        order = "DESC" if reverse else "ASC"
        placeholders = ','.join('?' * len(statuses))
        conn = self._get_connection()
        rows = conn.execute(
            f"""SELECT * FROM messages WHERE status IN ({placeholders})
                ORDER BY created_at {order} LIMIT ? OFFSET ?""",
            (*statuses, limit, offset),
        ).fetchall()
        return [_merge_message_row(r) for r in rows]

    def get_pending_messages(self, limit: int = 100, offset: int = 0,
                             reverse: bool = True) -> List[Dict[str, Any]]:
        """获取待审核消息"""
        try:
            from app.core.message_status import MessageStatus
            statuses = MessageStatus.get_pending_like_statuses()
            return self._get_messages_by_statuses(statuses, limit, offset, reverse)
        except Exception as e:
            logger.error(f"获取待审核消息失败: {e}")
            return []

    def get_approved_messages(self, limit: int = 100, offset: int = 0,
                              reverse: bool = True) -> List[Dict[str, Any]]:
        """获取已审核消息"""
        try:
            from app.core.message_status import MessageStatus
            return self._get_messages_by_statuses(
                MessageStatus.get_approved_statuses(), limit, offset, reverse)
        except Exception as e:
            logger.error(f"获取已审核消息失败: {e}")
            return []

    def get_rejected_messages(self, limit: int = 100, offset: int = 0,
                              reverse: bool = True) -> List[Dict[str, Any]]:
        """获取已拒绝消息"""
        try:
            from app.core.message_status import MessageStatus
            return self._get_messages_by_statuses(
                MessageStatus.get_rejected_statuses(), limit, offset, reverse)
        except Exception as e:
            logger.error(f"获取已拒绝消息失败: {e}")
            return []

    def get_messages_by_status(self, status: str, limit: int = 100,
                               offset: int = 0,
                               reverse: bool = True) -> List[Dict[str, Any]]:
        """根据状态获取消息 - 支持聚合状态和7个细分状态"""
        try:
            dispatch = {
                "pending": self.get_pending_messages,
                "approved": self.get_approved_messages,
                "rejected": self.get_rejected_messages,
            }
            if status in dispatch:
                return dispatch[status](limit, offset, reverse)
            return self._get_messages_by_statuses([status], limit, offset, reverse)
        except Exception as e:
            logger.error(f"获取{status}状态消息失败: {e}")
            return []

    def search_messages(self, query: str, limit: int = 50, offset: int = 0,
                        status: Optional[str] = None
                        ) -> Tuple[List[Dict[str, Any]], int]:
        """搜索消息 - 先尝试ID精确查找，再FTS5全文搜索"""
        try:
            if not query or not query.strip():
                return [], 0
            query_str = query.strip()
            result = self._search_by_id(query_str, status)
            if result is not None:
                return result
            return self._search_by_fts(query_str, limit, offset, status)
        except Exception as e:
            logger.error(f"搜索消息失败: {e}")
            return [], 0

    def _search_by_id(self, query_str, status):
        """尝试按消息ID精确查找，成功返回结果，不匹配返回None"""
        if ':' not in query_str or query_str.count(':') != 1:
            return None
        try:
            ch_id, msg_id = query_str.split(':')
            if not (ch_id.startswith('-') and msg_id.isdigit()):
                return None
            msg = self.get_message(ch_id, int(msg_id))
            if msg and (not status or msg.get('status') == status):
                return [msg], 1
            return [], 0
        except (ValueError, AttributeError):
            return None

    def _search_by_fts(self, query_str, limit, offset, status):
        """FTS5全文搜索"""
        conn = self._get_connection()
        safe_query = '"' + query_str.replace('"', '""') + '"'
        if status:
            rows = conn.execute(
                """SELECT m.* FROM messages m
                   JOIN messages_fts f ON m.rowid = f.rowid
                   WHERE messages_fts MATCH ? AND m.status = ?
                   ORDER BY m.created_at DESC LIMIT ? OFFSET ?""",
                (safe_query, status, limit, offset),
            ).fetchall()
            count_row = conn.execute(
                """SELECT COUNT(*) FROM messages m
                   JOIN messages_fts f ON m.rowid = f.rowid
                   WHERE messages_fts MATCH ? AND m.status = ?""",
                (safe_query, status),
            ).fetchone()
        else:
            rows = conn.execute(
                """SELECT m.* FROM messages m
                   JOIN messages_fts f ON m.rowid = f.rowid
                   WHERE messages_fts MATCH ?
                   ORDER BY m.created_at DESC LIMIT ? OFFSET ?""",
                (safe_query, limit, offset),
            ).fetchall()
            count_row = conn.execute(
                """SELECT COUNT(*) FROM messages m
                   JOIN messages_fts f ON m.rowid = f.rowid
                   WHERE messages_fts MATCH ?""",
                (safe_query,),
            ).fetchone()
        total = count_row[0] if count_row else 0
        return [_merge_message_row(r) for r in rows], total

    def get_message_count(self, channel_id: str) -> int:
        """获取频道消息数量"""
        try:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE channel_id = ?",
                (str(channel_id),),
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def get_earliest_message_timestamp(self) -> Optional[float]:
        """获取最早消息的时间戳"""
        try:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT created_at FROM messages ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if row and row[0]:
                from datetime import datetime
                dt = datetime.fromisoformat(row[0])
                return dt.timestamp()
            return None
        except Exception as e:
            logger.error(f"获取最早消息时间戳失败: {e}")
            return None

    def batch_update_message_status(self, message_ids: list,
                                    new_status: str) -> int:
        """批量更新消息状态"""
        try:
            conn = self._get_connection()
            now = get_current_time().isoformat()
            updated = 0
            for item in message_ids:
                if isinstance(item, (list, tuple)):
                    full_id = f"{item[0]}:{item[1]}"
                else:
                    full_id = str(item)
                cursor = conn.execute(
                    "UPDATE messages SET status=?, updated_at=? WHERE id=?",
                    (new_status, now, full_id),
                )
                updated += cursor.rowcount
            conn.commit()
            logger.info(f"批量更新了 {updated} 条消息状态为 {new_status}")
            return updated
        except Exception as e:
            logger.error(f"批量更新消息状态失败: {e}")
            return 0

    def batch_delete_messages(self, message_ids: list) -> int:
        """批量删除消息"""
        try:
            conn = self._get_connection()
            ids = []
            for item in message_ids:
                if isinstance(item, (list, tuple)):
                    ids.append(f"{item[0]}:{item[1]}")
                else:
                    ids.append(str(item))
            if not ids:
                return 0
            placeholders = ','.join('?' * len(ids))
            conn.execute(
                f"DELETE FROM messages WHERE id IN ({placeholders})", ids
            )
            deleted = conn.execute("SELECT changes()").fetchone()[0]
            conn.commit()
            logger.info(f"批量删除了 {deleted} 条消息")
            return deleted
        except Exception as e:
            logger.error(f"批量删除消息失败: {e}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        try:
            from app.core.message_status import MessageStatus
            conn = self._get_connection()
            pending_s = MessageStatus.get_pending_like_statuses()
            approved_s = MessageStatus.get_approved_statuses()
            rejected_s = MessageStatus.get_rejected_statuses()

            def _count(statuses):
                ph = ','.join('?' * len(statuses))
                r = conn.execute(
                    f"SELECT COUNT(*) FROM messages WHERE status IN ({ph})",
                    statuses,
                ).fetchone()
                return r[0] if r else 0

            pending = _count(pending_s)
            approved = _count(approved_s)
            rejected = _count(rejected_s)
            ch_row = conn.execute(
                "SELECT COUNT(DISTINCT channel_id) FROM messages"
            ).fetchone()

            return {
                "total_messages": pending + approved + rejected,
                "pending_messages": pending,
                "approved_messages": approved,
                "rejected_messages": rejected,
                "total_channels": ch_row[0] if ch_row else 0,
                "updated_at": get_current_time().isoformat(),
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "total_messages": 0, "pending_messages": 0,
                "approved_messages": 0, "rejected_messages": 0,
                "total_channels": 0,
                "updated_at": get_current_time().isoformat(),
            }
