"""
媒体补抓任务服务
通过Redis队列实现Web服务器与Telegram采集器之间的媒体补抓任务通信
"""
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 等待处理
    PROCESSING = "processing" # 正在处理  
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"        # 失败

class MediaRefetchTask:
    """媒体补抓任务"""
    
    def __init__(self, message_id: str, task_id: str = None):
        self.task_id = task_id or str(uuid.uuid4())
        self.message_id = message_id
        self.status = TaskStatus.PENDING
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.error_message = None
        self.result = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "message_id": self.message_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "result": self.result
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MediaRefetchTask':
        """从字典创建任务"""
        task = cls(data["message_id"], data["task_id"])
        task.status = TaskStatus(data["status"])
        task.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            task.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            task.completed_at = datetime.fromisoformat(data["completed_at"])
        task.error_message = data.get("error_message")
        task.result = data.get("result")
        return task

class MediaRefetchService:
    """媒体补抓任务服务"""
    
    # Redis键前缀
    TASK_QUEUE_KEY = "media_refetch:queue"           # 任务队列
    TASK_STATUS_PREFIX = "media_refetch:task:"       # 任务状态
    PROCESSING_SET_KEY = "media_refetch:processing"  # 正在处理的任务集合
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        
    def get_redis(self):
        """获取Redis客户端"""
        if not self.redis:
            from app.storage.redis_store import get_redis_message_store
            redis_store = get_redis_message_store()
            self.redis = redis_store.redis if redis_store else None
        return self.redis
    
    def submit_task(self, message_id: str) -> str:
        """提交媒体补抓任务"""
        try:
            redis = self.get_redis()
            if not redis:
                raise Exception("Redis连接失败")
            
            # 创建任务
            task = MediaRefetchTask(message_id)
            
            # 保存任务状态
            task_key = f"{self.TASK_STATUS_PREFIX}{task.task_id}"
            redis.set(task_key, json.dumps(task.to_dict()), ex=3600)  # 1小时过期
            
            # 添加到队列
            redis.lpush(self.TASK_QUEUE_KEY, task.task_id)
            
            logger.info(f"媒体补抓任务已创建: {task.task_id} for message {message_id}")
            return task.task_id
            
        except Exception as e:
            logger.error(f"创建媒体补抓任务失败: {e}")
            raise
    
    def get_pending_task(self) -> Optional[MediaRefetchTask]:
        """获取待处理任务（采集器调用）"""
        try:
            redis = self.get_redis()
            if not redis:
                return None
            
            # 从队列获取任务ID
            task_id = redis.brpop(self.TASK_QUEUE_KEY, timeout=1)
            if not task_id:
                return None
            
            task_id = task_id[1]  # brpop返回(key, value)
            if isinstance(task_id, bytes):
                task_id = task_id.decode()
            
            # 获取任务详情
            task_key = f"{self.TASK_STATUS_PREFIX}{task_id}"
            task_data = redis.get(task_key)
            if not task_data:
                logger.warning(f"任务数据不存在: {task_id}")
                return None
            
            if isinstance(task_data, bytes):
                task_data = task_data.decode()
            
            # 解析任务
            task = MediaRefetchTask.from_dict(json.loads(task_data))
            
            # 标记为处理中
            task.status = TaskStatus.PROCESSING
            task.started_at = datetime.now()
            redis.set(task_key, json.dumps(task.to_dict()), ex=3600)
            redis.sadd(self.PROCESSING_SET_KEY, task_id)
            
            logger.info(f"开始处理媒体补抓任务: {task_id}")
            return task
            
        except Exception as e:
            logger.error(f"获取待处理任务失败: {e}")
            return None
    
    def complete_task(self, task_id: str, success: bool, result: Dict[str, Any] = None, error_message: str = None):
        """完成任务（采集器调用）"""
        try:
            redis = self.get_redis()
            if not redis:
                return
            
            task_key = f"{self.TASK_STATUS_PREFIX}{task_id}"
            task_data = redis.get(task_key)
            if not task_data:
                logger.warning(f"完成任务时找不到任务数据: {task_id}")
                return
            
            if isinstance(task_data, bytes):
                task_data = task_data.decode()
            
            # 更新任务状态
            task = MediaRefetchTask.from_dict(json.loads(task_data))
            task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.result = result
            task.error_message = error_message
            
            # 保存更新后的状态
            redis.set(task_key, json.dumps(task.to_dict()), ex=3600)
            
            # 从处理中集合移除
            redis.srem(self.PROCESSING_SET_KEY, task_id)
            
            status_msg = "成功" if success else f"失败: {error_message}"
            logger.info(f"媒体补抓任务完成: {task_id} - {status_msg}")
            
        except Exception as e:
            logger.error(f"完成任务失败: {e}")
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态（Web服务器调用）"""
        try:
            redis = self.get_redis()
            if not redis:
                return None
            
            task_key = f"{self.TASK_STATUS_PREFIX}{task_id}"
            task_data = redis.get(task_key)
            if not task_data:
                return None
            
            if isinstance(task_data, bytes):
                task_data = task_data.decode()
            
            return json.loads(task_data)
            
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return None
    
    def get_all_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有任务状态"""
        try:
            redis = self.get_redis()
            if not redis:
                return []
            
            # 获取所有任务键
            pattern = f"{self.TASK_STATUS_PREFIX}*"
            keys = redis.keys(pattern)
            
            tasks = []
            for key in keys[:limit]:
                task_data = redis.get(key)
                if task_data:
                    if isinstance(task_data, bytes):
                        task_data = task_data.decode()
                    tasks.append(json.loads(task_data))
            
            # 按创建时间排序
            tasks.sort(key=lambda x: x["created_at"], reverse=True)
            return tasks
            
        except Exception as e:
            logger.error(f"获取所有任务失败: {e}")
            return []
    
    def cleanup_expired_tasks(self):
        """清理过期任务"""
        try:
            redis = self.get_redis()
            if not redis:
                return
            
            # 清理超过1小时的处理中任务
            cutoff_time = datetime.now() - timedelta(hours=1)
            
            processing_tasks = redis.smembers(self.PROCESSING_SET_KEY)
            for task_id in processing_tasks:
                if isinstance(task_id, bytes):
                    task_id = task_id.decode()
                    
                task_key = f"{self.TASK_STATUS_PREFIX}{task_id}"
                task_data = redis.get(task_key)
                if task_data:
                    if isinstance(task_data, bytes):
                        task_data = task_data.decode()
                    task = json.loads(task_data)
                    if task.get("started_at"):
                        started_at = datetime.fromisoformat(task["started_at"])
                        if started_at < cutoff_time:
                            # 标记为失败
                            self.complete_task(task_id, False, error_message="任务超时")
                            logger.warning(f"清理超时任务: {task_id}")
            
        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")

# 全局服务实例
media_refetch_service = MediaRefetchService()