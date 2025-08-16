"""
消息转发任务队列服务
通过Redis队列实现Web服务器与Telegram采集器之间的消息转发任务通信
"""
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)

class ForwardTaskStatus(Enum):
    """转发任务状态枚举"""
    PENDING = "pending"      # 等待处理
    PROCESSING = "processing" # 正在处理  
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"        # 失败

class MessageForwardTask:
    """消息转发任务"""
    
    def __init__(self, message_id: str, action: str = "forward_to_target", task_id: str = None):
        self.task_id = task_id or str(uuid.uuid4())
        self.message_id = message_id
        self.action = action  # forward_to_target, forward_to_review 等
        self.status = ForwardTaskStatus.PENDING
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.error_message = None
        self.result = None
        self.retry_count = 0
        self.max_retries = 3
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "message_id": self.message_id,
            "action": self.action,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "result": self.result,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageForwardTask':
        """从字典创建任务"""
        task = cls(data["message_id"], data.get("action", "forward_to_target"), data["task_id"])
        task.status = ForwardTaskStatus(data["status"])
        task.created_at = datetime.fromisoformat(data["created_at"])
        task.started_at = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
        task.completed_at = datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        task.error_message = data.get("error_message")
        task.result = data.get("result")
        task.retry_count = data.get("retry_count", 0)
        task.max_retries = data.get("max_retries", 3)
        return task

class MessageForwardQueue:
    """消息转发任务队列管理器"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.TASK_QUEUE_KEY = "message_forward:task_queue"
        self.TASK_STORE_PREFIX = "message_forward:task:"
        self.RESULT_STORE_PREFIX = "message_forward:result:"
        self.RESULT_TTL = 3600  # 结果保存1小时
        
    def _ensure_redis(self):
        """确保Redis连接可用"""
        if not self.redis:
            from app.storage.redis_store import get_redis_message_store
            redis_store = get_redis_message_store()
            if redis_store:
                self.redis = redis_store.redis
            else:
                raise RuntimeError("无法获取Redis连接")
    
    async def submit_forward_task(self, message_id: str, action: str = "forward_to_target") -> str:
        """提交转发任务到队列
        
        Args:
            message_id: 消息ID (格式: channel_id:message_id)
            action: 转发动作 (forward_to_target, forward_to_review)
            
        Returns:
            任务ID
        """
        try:
            self._ensure_redis()
            
            # 创建任务
            task = MessageForwardTask(message_id, action)
            
            # 保存任务到Redis
            task_key = f"{self.TASK_STORE_PREFIX}{task.task_id}"
            self.redis.setex(task_key, 3600, json.dumps(task.to_dict()))  # 任务保存1小时
            
            # 将任务ID推入队列
            self.redis.lpush(self.TASK_QUEUE_KEY, task.task_id)
            
            logger.info(f"转发任务已提交: {task.task_id} (消息: {message_id}, 动作: {action})")
            return task.task_id
            
        except Exception as e:
            logger.error(f"提交转发任务失败: {e}")
            raise
    
    def get_pending_task(self, timeout: int = 1) -> Optional[MessageForwardTask]:
        """获取待处理的转发任务（阻塞式）
        
        Args:
            timeout: 阻塞超时时间（秒）
            
        Returns:
            转发任务对象，如果没有任务则返回None
        """
        try:
            self._ensure_redis()
            
            # 从队列中获取任务ID（阻塞式）
            result = self.redis.brpop(self.TASK_QUEUE_KEY, timeout=timeout)
            if not result:
                return None
            
            task_id = result[1]
            if isinstance(task_id, bytes):
                task_id = task_id.decode('utf-8')
            
            # 获取任务详情
            task_key = f"{self.TASK_STORE_PREFIX}{task_id}"
            task_data = self.redis.get(task_key)
            
            if not task_data:
                logger.warning(f"转发任务数据不存在: {task_id}")
                return None
            
            if isinstance(task_data, bytes):
                task_data = task_data.decode('utf-8')
            
            task_dict = json.loads(task_data)
            task = MessageForwardTask.from_dict(task_dict)
            
            # 更新任务状态为处理中
            task.status = ForwardTaskStatus.PROCESSING
            task.started_at = datetime.now()
            self.redis.setex(task_key, 3600, json.dumps(task.to_dict()))
            
            logger.debug(f"获取到转发任务: {task_id}")
            return task
            
        except Exception as e:
            logger.error(f"获取转发任务失败: {e}")
            return None
    
    def complete_task(self, task: MessageForwardTask, success: bool, result: Any = None, error_message: str = None):
        """完成转发任务
        
        Args:
            task: 任务对象
            success: 是否成功
            result: 任务结果
            error_message: 错误信息（如果失败）
        """
        try:
            self._ensure_redis()
            
            task.completed_at = datetime.now()
            task.status = ForwardTaskStatus.COMPLETED if success else ForwardTaskStatus.FAILED
            task.result = result
            task.error_message = error_message
            
            # 更新任务状态
            task_key = f"{self.TASK_STORE_PREFIX}{task.task_id}"
            self.redis.setex(task_key, 3600, json.dumps(task.to_dict()))
            
            # 保存结果到结果存储（用于查询）
            result_key = f"{self.RESULT_STORE_PREFIX}{task.message_id}"
            result_data = {
                "task_id": task.task_id,
                "action": task.action,
                "success": success,
                "result": result,
                "error_message": error_message,
                "completed_at": task.completed_at.isoformat()
            }
            self.redis.setex(result_key, self.RESULT_TTL, json.dumps(result_data))
            
            status_msg = "成功" if success else f"失败: {error_message}"
            logger.info(f"转发任务完成: {task.task_id} - {status_msg}")
            
        except Exception as e:
            logger.error(f"完成转发任务时出错: {e}")
    
    async def get_task_result(self, message_id: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """等待并获取转发任务结果
        
        Args:
            message_id: 消息ID
            timeout: 超时时间（秒）
            
        Returns:
            任务结果字典，包含success、result、error_message等字段
        """
        try:
            self._ensure_redis()
            
            result_key = f"{self.RESULT_STORE_PREFIX}{message_id}"
            start_time = datetime.now()
            
            while (datetime.now() - start_time).total_seconds() < timeout:
                result_data = self.redis.get(result_key)
                if result_data:
                    if isinstance(result_data, bytes):
                        result_data = result_data.decode('utf-8')
                    return json.loads(result_data)
                
                # 使用异步sleep避免阻塞事件循环
                import asyncio
                await asyncio.sleep(0.5)
            
            return None  # 超时
            
        except Exception as e:
            logger.error(f"获取转发任务结果失败: {e}")
            return None
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        try:
            self._ensure_redis()
            
            queue_length = self.redis.llen(self.TASK_QUEUE_KEY)
            
            # 统计不同状态的任务数量
            pattern = f"{self.TASK_STORE_PREFIX}*"
            task_keys = self.redis.keys(pattern)
            
            status_counts = {status.value: 0 for status in ForwardTaskStatus}
            
            for key in task_keys:
                try:
                    task_data = self.redis.get(key)
                    if task_data:
                        if isinstance(task_data, bytes):
                            task_data = task_data.decode('utf-8')
                        task_dict = json.loads(task_data)
                        status = task_dict.get('status', 'unknown')
                        if status in status_counts:
                            status_counts[status] += 1
                except:
                    continue
            
            return {
                "queue_length": queue_length,
                "task_counts": status_counts
            }
            
        except Exception as e:
            logger.error(f"获取队列状态失败: {e}")
            return {"queue_length": 0, "task_counts": {}}

# 全局实例
forward_queue = MessageForwardQueue()