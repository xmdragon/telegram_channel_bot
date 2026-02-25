"""目标频道间消息同步服务"""
import asyncio
import logging
import re
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ChannelSyncService:
    """将已发布消息补发到新增的目标频道"""

    def __init__(self):
        self._sync_tasks: Dict[str, dict] = {}

    def get_missing_messages(self, target_id: int,
                             source_target_id: int = None) -> List[dict]:
        """查出需要同步的消息
        - source_target_id: 只同步该源频道已发布的消息
        - 找 target_results 中有 source_target_id 但缺少 target_id 的
        """
        from app.storage.redis_manager import redis_manager
        approved = redis_manager.get_messages_by_status("approved", limit=99999)
        missing = []
        for m in approved:
            results = m.get('target_results') or []
            published_ids = {r.get('target_id') for r in results}
            if target_id in published_ids:
                continue
            if source_target_id and source_target_id not in published_ids:
                continue
            missing.append(m)
        return missing

    async def start_sync(self, target_id: int,
                         source_target_id: int = None) -> dict:
        """启动同步任务，返回 {task_id, total}"""
        # 检查是否已有进行中的任务
        for tid, task in self._sync_tasks.items():
            if task['target_id'] == target_id and task['status'] == 'running':
                return {"error": "该目标频道已有同步任务进行中", "task_id": tid}

        # 查找目标频道
        from app.services.target_channel_service import target_channel_service
        store = target_channel_service._get_store()
        target = store.get_by_id(target_id)
        if not target:
            return {"error": f"目标频道 {target_id} 不存在"}

        messages = self.get_missing_messages(target_id, source_target_id)
        task_id = str(uuid.uuid4())[:8]

        self._sync_tasks[task_id] = {
            "target_id": target_id,
            "status": "running",
            "total": len(messages),
            "done": 0,
            "failed": 0,
            "errors": [],
        }

        if not messages:
            self._sync_tasks[task_id]["status"] = "completed"
            return {"task_id": task_id, "total": 0}

        asyncio.create_task(self._do_sync(task_id, target, messages))
        return {"task_id": task_id, "total": len(messages)}

    async def _do_sync(self, task_id: str, target: dict, messages: list):
        """后台逐条转发到目标频道"""
        from app.telegram.dual_session_manager import dual_session_manager
        from app.telegram.message_forwarder import message_forwarder
        from app.storage.redis_manager import redis_manager

        task = self._sync_tasks[task_id]
        try:
            if not await dual_session_manager.ensure_sender_connected():
                task["status"] = "failed"
                task["errors"].append("无法连接发送Session")
                return

            client = await dual_session_manager.get_sender_client()

            for msg in messages:
                try:
                    clean_msg = self._strip_target_link(msg)
                    result = await message_forwarder._forward_to_single_target(
                        client, clean_msg, target
                    )
                    if result:
                        self._append_target_result(redis_manager, msg, result)
                        task["done"] += 1
                    else:
                        task["failed"] += 1
                        task["errors"].append(f"{msg.get('source_channel')}:{msg.get('message_id')} 发送无结果")
                except Exception as e:
                    task["failed"] += 1
                    err = f"{msg.get('source_channel')}:{msg.get('message_id')} {e}"
                    task["errors"].append(err)
                    logger.warning(f"同步消息失败: {err}")
                    # FloodWait: 等待后继续
                    from telethon.errors import FloodWaitError
                    if isinstance(e, FloodWaitError):
                        wait = getattr(e, 'seconds', 60)
                        logger.info(f"FloodWait {wait}s, 等待后继续同步")
                        await asyncio.sleep(wait + 1)
                        continue

                await asyncio.sleep(1)

            task["status"] = "completed"
        except Exception as e:
            task["status"] = "failed"
            task["errors"].append(str(e))
            logger.error(f"同步任务 {task_id} 异常: {e}")

    def _strip_target_link(self, msg: dict) -> dict:
        """去掉 filtered_content 中的目标消息链接行"""
        clean = dict(msg)
        fc = clean.get('filtered_content') or ''
        if '✅ 目标消息链接:' in fc:
            fc = re.sub(r'\n*✅ 目标消息链接: https?://\S+', '', fc).rstrip()
            clean['filtered_content'] = fc
        return clean

    def _append_target_result(self, redis_manager, msg, result):
        """将新的 target_result 追加到消息"""
        channel_id = msg.get('source_channel')
        message_id = msg.get('message_id')
        if not channel_id or not message_id:
            return
        existing = msg.get('target_results') or []
        existing.append(result)
        redis_manager.update_message_field(
            channel_id, int(message_id), 'target_results', existing
        )

    def get_status(self, task_id: str) -> Optional[dict]:
        return self._sync_tasks.get(task_id)


channel_sync_service = ChannelSyncService()
