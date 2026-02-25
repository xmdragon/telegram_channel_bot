"""
目标频道管理服务
提供目标频道的增删改查、频道解析和旧配置迁移
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TargetChannelService:
    """目标频道管理服务"""

    def __init__(self):
        self._store = None

    def _get_store(self):
        """延迟获取存储实例"""
        if self._store is None:
            from app.storage.json_store import get_json_target_channel_store
            self._store = get_json_target_channel_store()
        return self._store

    # ------------------------------------------------------------------
    # 频道解析 & 自动加入
    # ------------------------------------------------------------------

    async def _resolve_channel_title(self, channel_name: str, channel_id: str) -> str:
        """解析频道真实标题"""
        try:
            from app.telegram.dual_session_manager import dual_session_manager
            client = await dual_session_manager.get_listener_client()
            if not client:
                return channel_name.lstrip('@')
            peer = int(channel_id) if channel_id.lstrip('-').isdigit() else channel_name
            entity = await client.get_entity(peer)
            if hasattr(entity, 'title') and entity.title:
                return entity.title
            return channel_name.lstrip('@')
        except Exception as e:
            logger.debug(f"解析频道标题失败 {channel_name}: {e}")
            return channel_name.lstrip('@')

    async def _auto_join_channel(self, channel_name: str, channel_id: str):
        """添加频道后自动让采集和发送账号加入"""
        from app.telegram.dual_session_manager import dual_session_manager
        clients = {
            "listener": await dual_session_manager.get_listener_client(),
            "sender": await dual_session_manager.get_sender_client(),
        }
        for role, client in clients.items():
            if not client:
                continue
            try:
                peer = channel_name if channel_name and not channel_name.lstrip('-').isdigit() else int(channel_id)
                entity = await client.get_entity(peer)
                if hasattr(entity, 'left') and not entity.left:
                    continue
                from telethon.tl.functions.channels import JoinChannelRequest
                await client(JoinChannelRequest(entity))
                logger.info(f"{role}已自动加入目标频道: {channel_name}")
            except Exception as e:
                logger.warning(f"{role}自动加入目标频道失败 {channel_name}: {e}")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add_target(self, channel_name: str, signature: str = "") -> Dict:
        """
        添加目标频道
        解析频道ID和标题，自动加入，保存到存储
        返回 {"success": bool, "message": str, "data": dict}
        """
        try:
            from app.services.telegram_resolver import telegram_resolver
            resolved_id = await telegram_resolver.resolve(channel_name)
            if not resolved_id:
                return {"success": False, "message": f"无法解析频道: {channel_name}", "data": None}

            title = await self._resolve_channel_title(channel_name, resolved_id)

            channel_data = {
                "channel_name": channel_name,
                "channel_id": resolved_id,
                "channel_title": title,
                "signature": signature,
                "enabled": True,
            }

            store = self._get_store()
            if not store.add(channel_data):
                return {"success": False, "message": "保存失败（频道可能已存在）", "data": None}

            await self._auto_join_channel(channel_name, resolved_id)
            return {"success": True, "message": "目标频道添加成功", "data": channel_data}

        except Exception as e:
            logger.error(f"添加目标频道失败: {e}")
            return {"success": False, "message": f"添加目标频道失败: {e}", "data": None}

    async def remove_target(self, target_id: int) -> Dict:
        """删除目标频道"""
        store = self._get_store()
        if store.delete_by_id(target_id):
            return {"success": True, "message": "目标频道已删除"}
        return {"success": False, "message": f"未找到ID为 {target_id} 的目标频道"}

    async def update_target(self, target_id: int, updates: Dict) -> Dict:
        """更新目标频道（落款、启用状态等）"""
        store = self._get_store()
        if not store.get_by_id(target_id):
            return {"success": False, "message": f"未找到ID为 {target_id} 的目标频道", "data": None}

        if store.update(target_id, updates):
            updated = store.get_by_id(target_id)
            return {"success": True, "message": "目标频道已更新", "data": updated}
        return {"success": False, "message": "更新失败", "data": None}

    def get_all_targets(self) -> List[Dict]:
        """获取所有目标频道"""
        return self._get_store().get_all()

    def get_enabled_targets(self) -> List[Dict]:
        """获取启用的目标频道"""
        return [t for t in self._get_store().get_all() if t.get('enabled', True)]

    def get_targets_for_source(self, source_channel_id: str) -> List[Dict]:
        """
        根据源频道的 config.target_channel_ids 获取目标列表
        - target_channel_ids 为空或未设置 -> 返回所有启用的目标
        - 有指定 -> 返回指定的且启用的目标
        """
        from app.storage.json_store import get_json_channel_store
        channel_store = get_json_channel_store()

        # 从数组格式的频道列表中查找源频道
        source = None
        for ch in channel_store.get_all_channels():
            if ch.get('channel_id') == source_channel_id:
                source = ch
                break

        if not source:
            return self.get_enabled_targets()

        target_ids = source.get('config', {}).get('target_channel_ids', [])
        if not target_ids:
            return self.get_enabled_targets()

        # 返回指定且启用的目标（按目标频道的id匹配）
        enabled = self.get_enabled_targets()
        target_id_set = set(target_ids)
        return [t for t in enabled if t.get('id') in target_id_set]

    async def get_signature(self, target: Dict) -> str:
        """
        获取目标频道的落款
        优先使用频道自身的 signature，否则使用全局配置
        """
        sig = target.get('signature', '')
        if sig:
            return sig
        from app.services.config_manager import config_manager
        global_sig = await config_manager.get_config('target.signature', '')
        return global_sig or ''

    # ------------------------------------------------------------------
    # 旧配置迁移
    # ------------------------------------------------------------------

    async def migrate_from_legacy(self):
        """
        检查旧的 target.channel_link / target.channel_id 配置
        如果存在且 target_channels.json 为空，自动创建第一个目标频道
        """
        store = self._get_store()
        if store.get_all():
            return  # 已有数据，无需迁移

        from app.services.config_manager import config_manager
        channel_link = await config_manager.get_config('target.channel_link')
        channel_id = await config_manager.get_config('target.channel_id')
        if not channel_link and not channel_id:
            return  # 没有旧配置

        logger.info(f"迁移旧目标频道配置: {channel_link} / {channel_id}")
        title = channel_link.lstrip('@') if channel_link else str(channel_id)

        if channel_link and channel_id:
            title = await self._resolve_channel_title(channel_link, str(channel_id))

        signature = await config_manager.get_config('target.signature', '')

        channel_data = {
            "channel_name": channel_link or '',
            "channel_id": str(channel_id) if channel_id else '',
            "channel_title": title,
            "signature": signature or '',
            "enabled": True,
        }
        if store.add(channel_data):
            logger.info(f"旧目标频道迁移成功: {title}")
        else:
            logger.error("旧目标频道迁移失败")


# 全局实例
target_channel_service = TargetChannelService()
