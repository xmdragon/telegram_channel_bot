"""
频道信息同步服务
定期检查频道名称和标题变化，更新到channels.json
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime

from app.storage.json_store import get_json_channel_store
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class ChannelInfoSyncService:
    """频道信息同步服务 - 检测并更新频道名称和标题变化"""

    def __init__(self):
        self._client = None

    async def sync_all_channels(self) -> Dict:
        """
        同步所有频道信息
        Returns:
            {"success": bool, "updated_count": int, "updates": List[Dict]}
        """
        result = {
            "success": True,
            "updated_count": 0,
            "updates": [],
            "errors": []
        }

        try:
            # 获取所有频道
            channel_store = get_json_channel_store()
            channels = channel_store.get_all_channels()

            if not channels:
                logger.info("没有找到需要同步的频道")
                return result

            logger.info(f"开始同步 {len(channels)} 个频道信息...")

            # 获取Telegram客户端（使用sender客户端避免影响采集）
            client = await self._get_sender_client()
            if not client:
                result["success"] = False
                result["errors"].append("无法获取Telegram客户端")
                return result

            # 逐个检查频道
            for channel in channels:
                channel_id = channel.get('channel_id')
                channel_name = channel.get('channel_name', '')

                if not channel_id or not channel_id.startswith('-100'):
                    logger.debug(f"跳过无效频道ID: {channel_name} ({channel_id})")
                    continue

                try:
                    update_info = await self._sync_single_channel(client, channel)
                    if update_info:
                        result["updated_count"] += 1
                        result["updates"].append(update_info)

                        # 更新到存储
                        channel_store.update_channel(channel)
                        logger.info(f"更新频道信息: {update_info}")

                except Exception as e:
                    error_msg = f"同步频道 {channel_name} 失败: {str(e)}"
                    logger.warning(error_msg)
                    result["errors"].append(error_msg)

            logger.info(f"频道信息同步完成: 更新了 {result['updated_count']} 个频道")

        except Exception as e:
            logger.error(f"频道信息同步失败: {e}")
            result["success"] = False
            result["errors"].append(f"同步过程失败: {str(e)}")

        return result

    async def _sync_single_channel(self, client, channel: Dict) -> Optional[Dict]:
        """
        同步单个频道信息
        Returns:
            None if no changes, Dict with update info if changed
        """
        channel_id = channel.get('channel_id')
        old_name = channel.get('channel_name', '')
        old_title = channel.get('channel_title', '')

        try:
            # 获取频道最新信息
            entity = await client.get_entity(int(channel_id))

            # 获取当前用户名和标题
            current_username = f"@{entity.username}" if hasattr(entity, 'username') and entity.username else None
            current_title = entity.title if hasattr(entity, 'title') else None

            changes = []

            # 检查用户名变化
            if current_username and current_username != old_name:
                changes.append(f"名称: {old_name} -> {current_username}")
                channel['channel_name'] = current_username

            # 检查标题变化
            if current_title and current_title != old_title:
                changes.append(f"标题: {old_title} -> {current_title}")
                channel['channel_title'] = current_title

            # 如果有变化，更新时间戳
            if changes:
                channel['updated_at'] = get_current_time().isoformat()

                return {
                    "channel_id": channel_id,
                    "channel_name": channel.get('channel_name'),
                    "changes": changes,
                    "updated_at": channel['updated_at']
                }

            return None

        except Exception as e:
            logger.warning(f"获取频道信息失败 {channel_id}: {e}")
            raise

    async def _get_sender_client(self):
        """获取sender客户端"""
        try:
            if not self._client:
                from app.telegram.dual_session_manager import dual_session_manager
                self._client = await dual_session_manager.get_sender_client()

                if self._client and not self._client.is_connected():
                    await self._client.connect()

            return self._client

        except Exception as e:
            logger.error(f"获取sender客户端失败: {e}")
            return None

# 创建全局实例
channel_info_sync = ChannelInfoSyncService()