"""
频道状态管理模块 - SQLite后端
处理频道采集点、状态追踪和统计
"""
import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from app.storage.database import db_manager
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)


class RedisChannelStore:
    """频道状态管理 - SQLite后端实现

    保持原有接口签名，内部使用SQLite替代Redis。
    构造函数接受redis_client参数但忽略它，保持向后兼容。
    """

    def __init__(self, redis_client=None):
        """初始化频道存储 - redis_client参数仅为兼容，已忽略"""
        self._db = db_manager

    def _get_conn(self):
        """获取数据库连接"""
        return self._db._get_connection()

    # =============================================
    # 采集点管理
    # =============================================

    def set_checkpoint(self, channel_id: str,
                       last_message_id: int) -> bool:
        """设置频道采集点 - 强制int类型"""
        try:
            message_id_int = int(last_message_id)
            now = get_current_time().isoformat()
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO channel_checkpoints
                   (channel_id, last_message_id, updated_at)
                   VALUES (?, ?, ?)""",
                (str(channel_id), message_id_int, now),
            )
            conn.commit()
            logger.debug(f"采集点已更新: {channel_id} -> {message_id_int}")
            return True
        except (ValueError, TypeError) as e:
            logger.error(f"采集点类型错误 {channel_id}: {last_message_id} -> {e}")
            return False
        except Exception as e:
            logger.error(f"设置采集点失败 {channel_id}: {e}")
            return False

    def get_checkpoint(self, channel_id: str) -> Optional[int]:
        """获取频道采集点 - 强制返回int类型"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                """SELECT last_message_id FROM channel_checkpoints
                   WHERE channel_id = ?""",
                (str(channel_id),),
            ).fetchone()
            if row and row[0] is not None:
                return int(row[0])
            return None
        except Exception as e:
            logger.error(f"获取采集点失败 {channel_id}: {e}")
            return None

    def get_all_checkpoints(self) -> Dict[str, int]:
        """获取所有频道采集点"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT channel_id, last_message_id FROM channel_checkpoints"
            ).fetchall()
            return {r[0]: int(r[1]) for r in rows if r[1] is not None}
        except Exception as e:
            logger.error(f"获取所有采集点失败: {e}")
            return {}

    def delete_checkpoint(self, channel_id: str) -> bool:
        """删除频道采集点"""
        try:
            conn = self._get_conn()
            conn.execute(
                "DELETE FROM channel_checkpoints WHERE channel_id = ?",
                (str(channel_id),),
            )
            conn.commit()
            logger.debug(f"已删除频道采集点: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"删除采集点失败 {channel_id}: {e}")
            return False

    def get_checkpoint_time(self, channel_id: str) -> Optional[str]:
        """获取频道采集点更新时间"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                """SELECT updated_at FROM channel_checkpoints
                   WHERE channel_id = ?""",
                (str(channel_id),),
            ).fetchone()
            return row[0] if row and row[0] else None
        except Exception as e:
            logger.error(f"获取采集点时间失败 {channel_id}: {e}")
            return None

    def get_checkpoint_info(self, channel_id: str) -> Dict[str, Any]:
        """获取频道采集点完整信息"""
        try:
            checkpoint = self.get_checkpoint(channel_id)
            checkpoint_time = self.get_checkpoint_time(channel_id)
            return {
                'channel_id': channel_id,
                'checkpoint': checkpoint,
                'updated_at': checkpoint_time,
                'exists': checkpoint is not None,
            }
        except Exception as e:
            logger.error(f"获取采集点信息失败 {channel_id}: {e}")
            return {
                'channel_id': channel_id, 'checkpoint': None,
                'updated_at': None, 'exists': False,
            }

    # =============================================
    # 频道状态管理
    # =============================================

    def set_channel_status(self, channel_id: str, status: str,
                           details: Dict[str, Any] = None) -> bool:
        """设置频道状态"""
        try:
            now = get_current_time().isoformat()
            status_data = {'status': status, 'updated_at': now}
            if details:
                status_data.update(details)
            details_json = json.dumps(
                status_data, ensure_ascii=False, default=str)
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO channel_status
                   (channel_id, status, details, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (str(channel_id), status, details_json, now),
            )
            conn.commit()
            logger.debug(f"频道状态已更新: {channel_id} -> {status}")
            return True
        except Exception as e:
            logger.error(f"设置频道状态失败 {channel_id}: {e}")
            return False

    def get_channel_status(self, channel_id: str
                           ) -> Optional[Dict[str, Any]]:
        """获取频道状态"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT details FROM channel_status WHERE channel_id = ?",
                (str(channel_id),),
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"获取频道状态失败 {channel_id}: {e}")
            return None

    def get_all_channel_statuses(self) -> Dict[str, Dict[str, Any]]:
        """获取所有频道状态"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT channel_id, details FROM channel_status"
            ).fetchall()
            result = {}
            for row in rows:
                try:
                    result[row[0]] = json.loads(row[1]) if row[1] else {}
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"解析频道状态失败 {row[0]}: {e}")
                    result[row[0]] = {'status': 'unknown', 'error': str(e)}
            return result
        except Exception as e:
            logger.error(f"获取所有频道状态失败: {e}")
            return {}

    def delete_channel_status(self, channel_id: str) -> bool:
        """删除频道状态"""
        try:
            conn = self._get_conn()
            conn.execute(
                "DELETE FROM channel_status WHERE channel_id = ?",
                (str(channel_id),),
            )
            conn.commit()
            logger.debug(f"已删除频道状态: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"删除频道状态失败 {channel_id}: {e}")
            return False

    # =============================================
    # 频道统计管理
    # =============================================

    def set_channel_stats(self, channel_id: str,
                          stats: Dict[str, Any]) -> bool:
        """设置频道统计信息"""
        try:
            now = get_current_time().isoformat()
            stats_data = {**stats, 'updated_at': now}
            stats_json = json.dumps(
                stats_data, ensure_ascii=False, default=str)
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO channel_stats
                   (channel_id, stats, updated_at)
                   VALUES (?, ?, ?)""",
                (str(channel_id), stats_json, now),
            )
            conn.commit()
            logger.debug(f"频道统计已更新: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"设置频道统计失败 {channel_id}: {e}")
            return False

    def get_channel_stats(self, channel_id: str
                          ) -> Optional[Dict[str, Any]]:
        """获取频道统计信息"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT stats FROM channel_stats WHERE channel_id = ?",
                (str(channel_id),),
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"获取频道统计失败 {channel_id}: {e}")
            return None

    def get_all_channel_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有频道统计信息"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT channel_id, stats FROM channel_stats"
            ).fetchall()
            result = {}
            for row in rows:
                try:
                    result[row[0]] = json.loads(row[1]) if row[1] else {}
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"解析频道统计失败 {row[0]}: {e}")
                    result[row[0]] = {'error': str(e)}
            return result
        except Exception as e:
            logger.error(f"获取所有频道统计失败: {e}")
            return {}

    # =============================================
    # 频道计数器
    # =============================================

    def increment_channel_counter(self, channel_id: str,
                                  counter_name: str,
                                  increment: int = 1) -> int:
        """增加频道计数器"""
        try:
            conn = self._get_conn()
            expires = self._calc_counter_expires()
            conn.execute(
                """INSERT INTO channel_counters
                   (channel_id, counter_name, value, expires_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(channel_id, counter_name) DO UPDATE
                   SET value = value + ?, expires_at = ?""",
                (str(channel_id), counter_name, increment,
                 expires, increment, expires),
            )
            conn.commit()
            row = conn.execute(
                """SELECT value FROM channel_counters
                   WHERE channel_id = ? AND counter_name = ?""",
                (str(channel_id), counter_name),
            ).fetchone()
            new_value = row[0] if row else 0
            logger.debug(
                f"频道计数器已更新: {channel_id}.{counter_name} = {new_value}")
            return new_value
        except Exception as e:
            logger.error(
                f"增加频道计数器失败 {channel_id}.{counter_name}: {e}")
            return 0

    def get_channel_counter(self, channel_id: str,
                            counter_name: str) -> int:
        """获取频道计数器值"""
        try:
            conn = self._get_conn()
            now = get_current_time().isoformat()
            row = conn.execute(
                """SELECT value FROM channel_counters
                   WHERE channel_id = ? AND counter_name = ?
                   AND (expires_at IS NULL OR expires_at > ?)""",
                (str(channel_id), counter_name, now),
            ).fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(
                f"获取频道计数器失败 {channel_id}.{counter_name}: {e}")
            return 0

    def get_channel_counters(self, channel_id: str) -> Dict[str, int]:
        """获取频道所有计数器"""
        try:
            conn = self._get_conn()
            now = get_current_time().isoformat()
            rows = conn.execute(
                """SELECT counter_name, value FROM channel_counters
                   WHERE channel_id = ?
                   AND (expires_at IS NULL OR expires_at > ?)""",
                (str(channel_id), now),
            ).fetchall()
            return {r[0]: r[1] for r in rows}
        except Exception as e:
            logger.error(f"获取频道计数器失败 {channel_id}: {e}")
            return {}

    def reset_channel_counter(self, channel_id: str,
                              counter_name: str) -> bool:
        """重置频道计数器"""
        try:
            conn = self._get_conn()
            expires = self._calc_counter_expires()
            conn.execute(
                """INSERT OR REPLACE INTO channel_counters
                   (channel_id, counter_name, value, expires_at)
                   VALUES (?, ?, 0, ?)""",
                (str(channel_id), counter_name, expires),
            )
            conn.commit()
            logger.debug(f"频道计数器已重置: {channel_id}.{counter_name}")
            return True
        except Exception as e:
            logger.error(
                f"重置频道计数器失败 {channel_id}.{counter_name}: {e}")
            return False

    # =============================================
    # 清理和摘要
    # =============================================

    def cleanup_channel_data(self, channel_id: str) -> bool:
        """清理频道相关的所有数据"""
        try:
            conn = self._get_conn()
            cid = str(channel_id)
            conn.execute(
                "DELETE FROM channel_checkpoints WHERE channel_id = ?",
                (cid,))
            conn.execute(
                "DELETE FROM channel_status WHERE channel_id = ?",
                (cid,))
            conn.execute(
                "DELETE FROM channel_stats WHERE channel_id = ?",
                (cid,))
            conn.execute(
                "DELETE FROM channel_counters WHERE channel_id = ?",
                (cid,))
            conn.commit()
            logger.info(f"已清理频道数据: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"清理频道数据失败 {channel_id}: {e}")
            return False

    def get_channel_summary(self, channel_id: str) -> Dict[str, Any]:
        """获取频道完整摘要信息"""
        try:
            return {
                'channel_id': channel_id,
                'checkpoint': self.get_checkpoint_info(channel_id),
                'status': self.get_channel_status(channel_id),
                'stats': self.get_channel_stats(channel_id),
                'counters': self.get_channel_counters(channel_id),
            }
        except Exception as e:
            logger.error(f"获取频道摘要失败 {channel_id}: {e}")
            return {
                'channel_id': channel_id, 'error': str(e),
                'checkpoint': None, 'status': None,
                'stats': None, 'counters': {},
            }

    # =============================================
    # 内部工具方法
    # =============================================

    @staticmethod
    def _calc_counter_expires() -> str:
        """计算计数器过期时间（30天）"""
        dt = get_current_time() + timedelta(days=30)
        return dt.isoformat()
