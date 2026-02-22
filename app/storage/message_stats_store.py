"""
消息统计存储模块 - SQLite后端
简化的统计系统，提供高性能消息状态跟踪

核心原则：
1. 只有3种状态：pending, approved, rejected
2. 拒绝原因是元数据，不是状态
3. 原子计数器，100%一致性
4. 消除所有特殊情况
"""
import logging
from typing import Any, Dict, Optional
from enum import Enum
from dataclasses import dataclass

from app.storage.database import db_manager
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)


class MessageState(Enum):
    """消息状态 - 只有3种，没有更多特殊情况"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class MessageStats:
    """消息统计数据结构"""
    total: int
    pending: int
    approved: int
    rejected: int

    def __post_init__(self):
        """确保数据一致性"""
        calculated = self.pending + self.approved + self.rejected
        if self.total != calculated:
            logger.warning(
                f"统计不一致: total={self.total}, calculated={calculated}")


class MessageStatsStore:
    """消息统计存储系统 - SQLite后端

    设计原则：
    1. 数据结构决定一切
    2. 消除所有特殊情况
    3. 原子操作保证一致性
    4. O(1)性能，不扫描不采样
    """

    def __init__(self, redis_url: str = None):
        """初始化 - redis_url参数仅为兼容，已忽略"""
        self._db = db_manager
        self._init_global_stats()

    def _get_conn(self):
        """获取数据库连接"""
        return self._db._get_connection()

    def _init_global_stats(self):
        """初始化全局统计计数器"""
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT OR IGNORE INTO stats_global
                   (key, total, pending, approved, rejected)
                   VALUES ('global', 0, 0, 0, 0)""")
            conn.commit()
        except Exception as e:
            logger.error(f"初始化全局统计失败: {e}")

    # =============================================
    # 核心操作
    # =============================================

    def increment_message(self, state: MessageState,
                          channel_id: str = None):
        """增加消息计数 - 原子操作"""
        try:
            conn = self._get_conn()
            field = state.value
            conn.execute(
                f"""UPDATE stats_global
                    SET total = total + 1, {field} = {field} + 1
                    WHERE key = 'global'""")
            if channel_id:
                self._ensure_channel_stats(conn, channel_id)
                conn.execute(
                    f"""UPDATE stats_channels
                        SET total = total + 1, {field} = {field} + 1
                        WHERE channel_id = ?""",
                    (str(channel_id),))
            conn.commit()
            logger.debug(
                f"消息计数已更新: {state.value} (频道: {channel_id or 'global'})")
        except Exception as e:
            logger.error(f"增加消息计数失败: {e}")

    def change_message_state(self, old_state: MessageState,
                             new_state: MessageState,
                             channel_id: str = None,
                             rejection_reason: Optional[str] = None):
        """改变消息状态 - 原子操作"""
        try:
            conn = self._get_conn()
            old_f = old_state.value
            new_f = new_state.value
            conn.execute(
                f"""UPDATE stats_global
                    SET {old_f} = MAX(0, {old_f} - 1),
                        {new_f} = {new_f} + 1
                    WHERE key = 'global'""")
            if channel_id:
                self._ensure_channel_stats(conn, channel_id)
                conn.execute(
                    f"""UPDATE stats_channels
                        SET {old_f} = MAX(0, {old_f} - 1),
                            {new_f} = {new_f} + 1
                        WHERE channel_id = ?""",
                    (str(channel_id),))
            conn.commit()
            logger.debug(f"状态已更新: {old_f} -> {new_f}")
        except Exception as e:
            logger.error(f"更新消息状态失败: {e}")

    # =============================================
    # 统计查询
    # =============================================

    def get_global_stats(self) -> MessageStats:
        """获取全局统计 - 从stats_global计数器读取"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                """SELECT total, pending, approved, rejected
                   FROM stats_global WHERE key = 'global'"""
            ).fetchone()
            if row:
                return MessageStats(
                    total=row[0] or 0,
                    pending=row[1] or 0,
                    approved=row[2] or 0,
                    rejected=row[3] or 0,
                )
            return MessageStats(0, 0, 0, 0)
        except Exception as e:
            logger.error(f"获取全局统计失败: {e}")
            return MessageStats(0, 0, 0, 0)

    def get_channel_stats(self, channel_id: str) -> MessageStats:
        """获取频道统计 - 从stats_channels计数器读取"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                """SELECT total, pending, approved, rejected
                   FROM stats_channels WHERE channel_id = ?""",
                (str(channel_id),),
            ).fetchone()
            if row:
                return MessageStats(
                    total=row[0] or 0,
                    pending=row[1] or 0,
                    approved=row[2] or 0,
                    rejected=row[3] or 0,
                )
            return MessageStats(0, 0, 0, 0)
        except Exception as e:
            logger.error(f"获取频道统计失败 (频道: {channel_id}): {e}")
            return MessageStats(0, 0, 0, 0)

    # =============================================
    # 便捷查询方法
    # =============================================

    def get_total_messages(self) -> int:
        """获取消息总数"""
        return self.get_global_stats().total

    def get_pending_count(self) -> int:
        """获取待审核消息数"""
        return self.get_global_stats().pending

    def get_approved_count(self) -> int:
        """获取已通过消息数"""
        return self.get_global_stats().approved

    def get_rejected_count(self) -> int:
        """获取已拒绝消息数"""
        return self.get_global_stats().rejected

    # =============================================
    # 重置和维护
    # =============================================

    def reset_stats(self):
        """重置所有统计 - 谨慎使用"""
        try:
            conn = self._get_conn()
            conn.execute(
                """UPDATE stats_global
                   SET total=0, pending=0, approved=0, rejected=0
                   WHERE key='global'""")
            conn.execute("DELETE FROM stats_channels")
            conn.execute("DELETE FROM stats_rejection")
            conn.commit()
            logger.info("所有统计已重置")
        except Exception as e:
            logger.error(f"重置统计失败: {e}")

    # =============================================
    # 向后兼容方法
    # =============================================

    def increment_pending(self):
        """增加pending计数"""
        self.increment_message(MessageState.PENDING)

    def increment_approved(self):
        """增加approved计数"""
        self.increment_message(MessageState.APPROVED)

    def increment_rejected(self):
        """增加rejected计数"""
        self.increment_message(MessageState.REJECTED)

    def decrement_pending(self):
        """减少pending计数"""
        try:
            conn = self._get_conn()
            conn.execute(
                """UPDATE stats_global
                   SET pending = MAX(0, pending - 1)
                   WHERE key = 'global'""")
            conn.commit()
        except Exception as e:
            logger.error(f"减少pending计数失败: {e}")

    def decrement_approved(self):
        """减少approved计数"""
        try:
            conn = self._get_conn()
            conn.execute(
                """UPDATE stats_global
                   SET approved = MAX(0, approved - 1)
                   WHERE key = 'global'""")
            conn.commit()
        except Exception as e:
            logger.error(f"减少approved计数失败: {e}")

    def decrement_rejected(self):
        """减少rejected计数"""
        try:
            conn = self._get_conn()
            conn.execute(
                """UPDATE stats_global
                   SET rejected = MAX(0, rejected - 1)
                   WHERE key = 'global'""")
            conn.commit()
        except Exception as e:
            logger.error(f"减少rejected计数失败: {e}")

    def increment_rejection_reason(self, reason: str):
        """增加拒绝原因计数"""
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO stats_rejection (reason, count)
                   VALUES (?, 1)
                   ON CONFLICT(reason) DO UPDATE
                   SET count = count + 1""",
                (reason,))
            conn.commit()
        except Exception as e:
            logger.error(f"增加拒绝原因计数失败: {e}")

    def validate_consistency(self) -> Dict[str, Any]:
        """验证统计数据一致性"""
        try:
            stats = self.get_global_stats()
            calculated = stats.pending + stats.approved + stats.rejected
            consistent = (stats.total == calculated)
            return {
                'consistent': consistent,
                'global_stats': {
                    'total': stats.total,
                    'calculated_total': calculated,
                    'consistent': consistent,
                    'pending': stats.pending,
                    'approved': stats.approved,
                    'rejected': stats.rejected,
                },
            }
        except Exception as e:
            logger.error(f"验证一致性失败: {e}")
            return {'consistent': False, 'error': str(e)}

    # =============================================
    # 内部方法
    # =============================================

    @staticmethod
    def _ensure_channel_stats(conn, channel_id: str):
        """确保频道统计行存在"""
        conn.execute(
            """INSERT OR IGNORE INTO stats_channels
               (channel_id, total, pending, approved, rejected)
               VALUES (?, 0, 0, 0, 0)""",
            (str(channel_id),))


# =============================================
# 全局实例
# =============================================

message_stats_store = None


def get_message_stats_store() -> MessageStatsStore:
    """获取消息统计存储实例"""
    global message_stats_store
    if message_stats_store is None:
        message_stats_store = MessageStatsStore()
    return message_stats_store


def init_message_stats_store(redis_url: str = None):
    """初始化消息统计存储"""
    global message_stats_store
    message_stats_store = MessageStatsStore(redis_url)
    return message_stats_store
