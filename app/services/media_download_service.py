"""
统一媒体下载服务 - Linus式设计，消除环境判断
无降级逻辑，单一处理路径
"""
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from app.storage.redis_store import redis_store
from app.services.media_handler import media_handler
from app.api.websocket import websocket_manager

logger = logging.getLogger(__name__)


class MediaTaskStatus(Enum):
    """媒体任务状态 - 简单明了"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class MediaDownloadTask:
    """媒体下载任务 - 清晰的数据结构"""
    task_id: str
    message_id: str
    channel_id: str
    media_type: str
    status: MediaTaskStatus = MediaTaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.utcnow)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class MediaDownloadService:
    """
    统一媒体下载服务
    
    Linus原则：
    1. 单一职责 - 只负责媒体下载
    2. 无环境判断 - 不区分collector/processor
    3. 异步队列 - 解耦消息处理和媒体下载
    4. fail-fast - 错误立即报告，不静默处理
    """
    
    TASK_QUEUE_KEY = "media:download:queue"
    TASK_DATA_KEY = "media:download:tasks"
    PROCESSING_KEY = "media:download:processing"
    
    def __init__(self):
        self.redis = redis_store
        self.running = False
        self.worker_task = None
        self.client = None  # Telegram客户端，由外部注入
        
    def set_client(self, client):
        """注入Telegram客户端"""
        self.client = client
        logger.info("Telegram客户端已注入到MediaDownloadService")
        
    async def start(self):
        """启动服务"""
        if self.running:
            logger.warning("MediaDownloadService已在运行")
            return
            
        self.running = True
        self.worker_task = asyncio.create_task(self._worker())
        logger.info("MediaDownloadService已启动")
        
    async def stop(self):
        """停止服务"""
        self.running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        logger.info("MediaDownloadService已停止")
        
    def submit_task(self, message_id: str, channel_id: str, message_obj: Any, media_type: str) -> str:
        """
        提交媒体下载任务
        
        Args:
            message_id: 消息ID
            channel_id: 频道ID
            message_obj: Telegram消息对象
            media_type: 媒体类型
            
        Returns:
            任务ID
        """
        import uuid
        task_id = str(uuid.uuid4())
        
        task = MediaDownloadTask(
            task_id=task_id,
            message_id=message_id,
            channel_id=channel_id,
            media_type=media_type
        )
        
        # 序列化任务数据
        task_data = {
            'task_id': task.task_id,
            'message_id': task.message_id,
            'channel_id': task.channel_id,
            'media_type': task.media_type,
            'status': task.status.value,
            'retry_count': task.retry_count,
            'created_at': task.created_at.isoformat(),
            'message_data': self._serialize_message(message_obj)
        }
        
        # 保存任务数据
        self.redis.hset(self.TASK_DATA_KEY, task_id, task_data)
        
        # 加入队列
        self.redis.rpush(self.TASK_QUEUE_KEY, task_id)
        
        logger.info(f"媒体下载任务已提交: {task_id} ({media_type})")
        return task_id
        
    async def _worker(self):
        """工作线程 - 处理下载队列"""
        logger.info("MediaDownloadService工作线程已启动")
        
        while self.running:
            try:
                # 从队列获取任务
                task_id = self.redis.lpop(self.TASK_QUEUE_KEY)
                if not task_id:
                    await asyncio.sleep(1)
                    continue
                    
                # 处理任务
                await self._process_task(task_id)
                
            except Exception as e:
                # fail-fast: 错误立即记录，不静默处理
                logger.error(f"媒体下载工作线程错误: {e}", exc_info=True)
                await asyncio.sleep(5)
                
    async def _process_task(self, task_id: str):
        """处理单个下载任务"""
        try:
            # 获取任务数据
            task_data = self.redis.hget(self.TASK_DATA_KEY, task_id)
            if not task_data:
                logger.error(f"任务数据不存在: {task_id}")
                return
                
            # 标记为处理中
            task_data['status'] = MediaTaskStatus.PROCESSING.value
            self.redis.hset(self.TASK_DATA_KEY, task_id, task_data)
            
            # 检查客户端
            if not self.client:
                raise Exception("Telegram客户端未初始化")
                
            # 反序列化消息对象
            message_obj = self._deserialize_message(task_data['message_data'])
            if not message_obj:
                raise Exception("无法反序列化消息对象")
                
            # 执行下载
            logger.info(f"开始下载媒体: {task_id} ({task_data['media_type']})")
            
            media_info = await media_handler.download_media(
                self.client,
                message_obj,
                task_data['message_id'],
                timeout=1800.0  # 统一30分钟超时
            )
            
            if media_info and media_info.get('file_path'):
                # 下载成功
                task_data['status'] = MediaTaskStatus.COMPLETED.value
                task_data['result'] = media_info
                self.redis.hset(self.TASK_DATA_KEY, task_id, task_data)
                
                # 通知前端
                await self._notify_completion(task_data)
                logger.info(f"媒体下载成功: {task_id}")
                
            else:
                # 下载失败，检查重试
                await self._handle_failure(task_id, task_data, "下载失败")
                
        except Exception as e:
            logger.error(f"处理媒体下载任务失败 {task_id}: {e}")
            if 'task_data' in locals():
                await self._handle_failure(task_id, task_data, str(e))
                
    async def _handle_failure(self, task_id: str, task_data: dict, error: str):
        """处理下载失败"""
        task_data['retry_count'] = task_data.get('retry_count', 0) + 1
        
        if task_data['retry_count'] < 3:
            # 重试
            logger.warning(f"媒体下载失败，重试 {task_data['retry_count']}/3: {task_id}")
            task_data['status'] = MediaTaskStatus.PENDING.value
            self.redis.hset(self.TASK_DATA_KEY, task_id, task_data)
            self.redis.rpush(self.TASK_QUEUE_KEY, task_id)
        else:
            # 最终失败
            task_data['status'] = MediaTaskStatus.FAILED.value
            task_data['error'] = error
            self.redis.hset(self.TASK_DATA_KEY, task_id, task_data)
            logger.error(f"媒体下载最终失败: {task_id} - {error}")
            
            # 通知前端失败
            await self._notify_failure(task_data)
            
    async def _notify_completion(self, task_data: dict):
        """通知下载完成"""
        try:
            notification = {
                'message_id': f"{task_data['channel_id']}:{task_data['message_id']}",
                'media_info': task_data.get('result'),
                'success': True
            }
            await websocket_manager.broadcast_media_refetched(notification)
        except Exception as e:
            logger.error(f"通知媒体下载完成失败: {e}")
            
    async def _notify_failure(self, task_data: dict):
        """通知下载失败"""
        try:
            notification = {
                'message_id': f"{task_data['channel_id']}:{task_data['message_id']}",
                'success': False,
                'error': task_data.get('error', '下载失败')
            }
            await websocket_manager.broadcast_media_refetched(notification)
        except Exception as e:
            logger.error(f"通知媒体下载失败错误: {e}")
            
    def _serialize_message(self, message_obj: Any) -> dict:
        """序列化Telegram消息对象用于存储"""
        # 简化实现，实际需要根据Telegram消息结构序列化
        return {
            'id': getattr(message_obj, 'id', None),
            'media': str(type(getattr(message_obj, 'media', None))),
            # 添加其他必要字段
        }
        
    def _deserialize_message(self, message_data: dict) -> Optional[Any]:
        """反序列化消息对象"""
        # 这里需要实际的反序列化逻辑
        # 暂时返回None，实际使用时需要从存储中恢复消息对象
        return None
        
    def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        task_data = self.redis.hget(self.TASK_DATA_KEY, task_id)
        return task_data if task_data else None


# 全局实例
media_download_service = MediaDownloadService()