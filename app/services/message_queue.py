"""
Linus式消息队列 - 采集与处理解耦的核心基础设施
遵循"做一件事并做好"的原则，提供简洁高效的消息队列服务
"""
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from enum import Enum

from app.storage.redis_manager import redis_manager
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class MessageType(Enum):
    """消息类型"""
    SINGLE = "single"    # 单独消息
    GROUP = "group"      # 组消息
    MEDIA = "media"      # 媒体消息

@dataclass
class CollectedMessage:
    """采集到的原始消息 - Linus式简洁数据结构"""
    
    # 基础标识
    channel_id: str
    message_id: int
    grouped_id: Optional[str] = None
    
    # 内容信息
    content: str = ""
    media_type: Optional[str] = None
    media_url: Optional[str] = None  # 远程URL（保持兼容）
    media_info: Optional[Dict] = None  # 完整媒体信息（包括本地路径）
    
    # 时间信息
    timestamp: datetime = None
    collected_at: datetime = None
    
    # 原始数据
    raw_data: Optional[Dict] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.timestamp is None:
            self.timestamp = get_current_time()
        if self.collected_at is None:
            self.collected_at = get_current_time()
    
    @property
    def message_key(self) -> str:
        """消息唯一标识"""
        return f"{self.channel_id}:{self.message_id}"
    
    @property
    def is_group_member(self) -> bool:
        """是否为组消息成员"""
        return self.grouped_id is not None
    
    @property
    def has_media(self) -> bool:
        """是否包含媒体"""
        return self.media_type is not None or (self.media_info and self.media_info.get('has_media', False))
    
    @property
    def local_media_path(self) -> Optional[str]:
        """本地媒体文件路径"""
        if self.media_info:
            return self.media_info.get('file_path')
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，递归处理datetime对象"""
        data = asdict(self)
        return self._serialize_datetime_recursive(data)
    
    @staticmethod
    def _serialize_datetime_recursive(obj: Any) -> Any:
        """递归序列化datetime对象 - Linus式通用解决方案"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {key: CollectedMessage._serialize_datetime_recursive(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [CollectedMessage._serialize_datetime_recursive(item) for item in obj]
        else:
            return obj
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CollectedMessage':
        """从字典创建（不修改原始数据）"""
        # 创建数据副本，避免污染原始字典
        data_copy = data.copy()
        
        # 处理datetime反序列化
        if data_copy.get('timestamp') and isinstance(data_copy['timestamp'], str):
            data_copy['timestamp'] = datetime.fromisoformat(data_copy['timestamp'])
        if data_copy.get('collected_at') and isinstance(data_copy['collected_at'], str):
            data_copy['collected_at'] = datetime.fromisoformat(data_copy['collected_at'])
        return cls(**data_copy)

@dataclass
class GroupedMessages:
    """组消息集合"""
    grouped_id: str
    channel_id: str
    messages: List[CollectedMessage]
    completed_at: datetime = None
    
    def __post_init__(self):
        if self.completed_at is None:
            self.completed_at = get_current_time()
    
    @property
    def message_count(self) -> int:
        """消息数量"""
        return len(self.messages)
    
    @property
    def total_content_length(self) -> int:
        """总内容长度"""
        return sum(len(msg.content) for msg in self.messages)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'grouped_id': self.grouped_id,
            'channel_id': self.channel_id,
            'messages': [msg.to_dict() for msg in self.messages],
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'message_count': self.message_count,
            'total_content_length': self.total_content_length
        }

class MessageQueue:
    """
    Linus式消息队列 - 简洁高效的生产者消费者模式
    
    设计原则:
    1. "做一件事并做好" - 只管队列操作
    2. "最笨但最清晰" - 使用Redis原生数据结构
    3. "消除特殊情况" - 统一处理单消息和组消息
    """
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._ensure_redis()
        
        # Redis键命名 - 清晰的命名空间
        self.QUEUE_KEYS = {
            'raw': 'collector:queue:raw',              # 原始消息队列
            'group_buffer': 'collector:group:{}',      # 组消息缓冲 {grouped_id}
            'processing': 'processor:working:{}',      # 处理中 {worker_id}
            'failed': 'processor:failed',              # 处理失败
            'completed': 'processor:completed',        # 处理完成
            'stats': 'queue:stats'                     # 队列统计
        }
        
        # 配置参数
        self.GROUP_BUFFER_TIMEOUT = 60  # 组消息缓冲超时(秒)
        self.MAX_GROUP_SIZE = 20        # 最大组大小
        self.FAILED_RETRY_DELAY = 300   # 失败重试延迟(秒)
    
    def _ensure_redis(self):
        """确保Redis连接"""
        if not self.redis:
            redis_store = redis_manager
            if not redis_store:
                raise RuntimeError("无法获取Redis连接")
            self.redis = redis_manager.client
    
    async def enqueue_message(self, message: CollectedMessage) -> bool:
        """
        消息入队 - Linus式统一接口
        单消息直接入队，组消息缓冲后批量入队
        """
        try:
            if message.is_group_member:
                return await self._enqueue_group_message(message)
            else:
                return await self._enqueue_single_message(message)
        except Exception as e:
            logger.error(f"消息入队失败 {message.message_key}: {e}")
            return False
    
    async def _enqueue_single_message(self, message: CollectedMessage) -> bool:
        """单消息入队"""
        try:
            queue_data = {
                'type': MessageType.SINGLE.value,
                'data': message.to_dict()
            }
            
            # 原子操作：入队 + 统计更新
            pipe = self.redis.pipeline()
            pipe.lpush(self.QUEUE_KEYS['raw'], json.dumps(queue_data))
            pipe.hincrby(self.QUEUE_KEYS['stats'], 'enqueued_single', 1)
            pipe.hincrby(self.QUEUE_KEYS['stats'], 'total_enqueued', 1)
            pipe.execute()
            
            logger.debug(f"✅ 单消息入队: {message.message_key}")
            return True
            
        except Exception as e:
            logger.error(f"单消息入队失败 {message.message_key}: {e}")
            return False
    
    async def _enqueue_group_message(self, message: CollectedMessage) -> bool:
        """组消息缓冲和入队"""
        try:
            group_key = self.QUEUE_KEYS['group_buffer'].format(message.grouped_id)
            
            # 添加到组缓冲
            pipe = self.redis.pipeline()
            pipe.hset(group_key, str(message.message_id), json.dumps(message.to_dict()))
            pipe.expire(group_key, self.GROUP_BUFFER_TIMEOUT)
            pipe.execute()
            
            # 检查组是否可以入队
            group_size = self.redis.hlen(group_key)
            if await self._should_enqueue_group(message.grouped_id, group_size):
                return await self._enqueue_complete_group(message.grouped_id, group_key)
            
            logger.debug(f"📦 组消息缓冲: {message.grouped_id} ({group_size}条)")
            return True
            
        except Exception as e:
            logger.error(f"组消息处理失败 {message.message_key}: {e}")
            return False
    
    async def _should_enqueue_group(self, grouped_id: str, current_size: int) -> bool:
        """判断组消息是否应该入队"""
        # Linus式简单启发式规则
        # 1. 达到最大大小
        if current_size >= self.MAX_GROUP_SIZE:
            return True
        
        # 2. 检查最近是否有新消息（简单的完整性判断）
        # 实际场景中，可以根据业务逻辑调整
        group_key = self.QUEUE_KEYS['group_buffer'].format(grouped_id)
        ttl = self.redis.ttl(group_key)
        
        # 如果缓冲时间超过30秒且有多条消息，可能已完整
        if ttl <= 30 and current_size >= 2:
            return True
        
        return False
    
    async def _enqueue_complete_group(self, grouped_id: str, group_key: str) -> bool:
        """完整组消息入队"""
        try:
            # 原子获取并删除组缓冲
            pipe = self.redis.pipeline()
            pipe.hgetall(group_key)
            pipe.delete(group_key)
            results = pipe.execute()
            
            group_data = results[0]
            if not group_data:
                logger.warning(f"组缓冲为空: {grouped_id}")
                return False
            
            # 构造组消息数据
            messages = []
            for msg_id, msg_json in group_data.items():
                msg_data = json.loads(msg_json)
                messages.append(CollectedMessage.from_dict(msg_data))
            
            # 按message_id排序
            messages.sort(key=lambda x: x.message_id)
            
            grouped_messages = GroupedMessages(
                grouped_id=grouped_id,
                channel_id=messages[0].channel_id,
                messages=messages
            )
            
            queue_data = {
                'type': MessageType.GROUP.value,
                'data': grouped_messages.to_dict()
            }
            
            # 入队 + 统计
            pipe = self.redis.pipeline()
            pipe.lpush(self.QUEUE_KEYS['raw'], json.dumps(queue_data))
            pipe.hincrby(self.QUEUE_KEYS['stats'], 'enqueued_groups', 1)
            pipe.hincrby(self.QUEUE_KEYS['stats'], 'total_enqueued', 1)
            pipe.execute()
            
            logger.info(f"✅ 组消息入队: {grouped_id} ({len(messages)}条)")
            return True
            
        except Exception as e:
            logger.error(f"组消息入队失败 {grouped_id}: {e}")
            return False
    
    async def dequeue_message(self, worker_id: str = "default", timeout: int = 1) -> Optional[Dict]:
        """
        消息出队 - 阻塞等待新消息
        
        Args:
            worker_id: 工作进程ID
            timeout: 阻塞超时时间(秒)
        
        Returns:
            消息数据字典或None
        """
        try:
            # 使用BRPOP阻塞等待
            result = self.redis.brpop(self.QUEUE_KEYS['raw'], timeout=timeout)
            if not result:
                return None
            
            # 解析消息数据
            queue_name, message_json = result
            message_data = json.loads(message_json)
            
            # 记录处理开始
            processing_key = self.QUEUE_KEYS['processing'].format(worker_id)
            self.redis.setex(processing_key, 300, message_json)  # 5分钟过期
            
            # 更新统计
            self.redis.hincrby(self.QUEUE_KEYS['stats'], 'dequeued', 1)
            
            logger.debug(f"📤 消息出队: {message_data.get('type')} (worker: {worker_id})")
            return message_data
            
        except Exception as e:
            logger.error(f"消息出队失败 (worker: {worker_id}): {e}")
            return None
    
    async def mark_completed(self, worker_id: str, message_data: Dict) -> bool:
        """标记消息处理完成"""
        try:
            processing_key = self.QUEUE_KEYS['processing'].format(worker_id)
            
            # 清理处理中状态
            pipe = self.redis.pipeline()
            pipe.delete(processing_key)
            pipe.hincrby(self.QUEUE_KEYS['stats'], 'completed', 1)
            pipe.execute()
            
            return True
            
        except Exception as e:
            logger.error(f"标记完成失败 (worker: {worker_id}): {e}")
            return False
    
    async def mark_failed(self, worker_id: str, message_data: Dict, error: str) -> bool:
        """标记消息处理失败"""
        try:
            processing_key = self.QUEUE_KEYS['processing'].format(worker_id)
            
            # 失败数据
            failed_data = {
                'message': message_data,
                'error': error,
                'failed_at': get_current_time().isoformat(),
                'worker_id': worker_id,
                'retry_at': (get_current_time() + timedelta(seconds=self.FAILED_RETRY_DELAY)).isoformat()
            }
            
            # 移入失败队列
            pipe = self.redis.pipeline()
            pipe.delete(processing_key)
            pipe.lpush(self.QUEUE_KEYS['failed'], json.dumps(failed_data))
            pipe.hincrby(self.QUEUE_KEYS['stats'], 'failed', 1)
            pipe.execute()
            
            logger.warning(f"消息处理失败: {error} (worker: {worker_id})")
            return True
            
        except Exception as e:
            logger.error(f"标记失败失败 (worker: {worker_id}): {e}")
            return False
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        try:
            # 获取各种统计
            raw_count = self.redis.llen(self.QUEUE_KEYS['raw'])
            failed_count = self.redis.llen(self.QUEUE_KEYS['failed'])
            stats = self.redis.hgetall(self.QUEUE_KEYS['stats']) or {}
            
            # 获取组缓冲数量
            group_buffers = 0
            cursor = '0'
            while True:
                cursor, keys = self.redis.scan(
                    cursor, 
                    match=self.QUEUE_KEYS['group_buffer'].format('*')
                )
                group_buffers += len(keys)
                if cursor == 0:
                    break
            
            return {
                'raw_queue_length': raw_count,
                'failed_queue_length': failed_count,
                'group_buffers': group_buffers,
                'stats': {
                    'total_enqueued': int(stats.get('total_enqueued', 0)),
                    'enqueued_single': int(stats.get('enqueued_single', 0)),
                    'enqueued_groups': int(stats.get('enqueued_groups', 0)),
                    'dequeued': int(stats.get('dequeued', 0)),
                    'completed': int(stats.get('completed', 0)),
                    'failed': int(stats.get('failed', 0))
                },
                'health': 'healthy' if raw_count < 1000 and failed_count < 100 else 'degraded'
            }
            
        except Exception as e:
            logger.error(f"获取队列状态失败: {e}")
            return {'error': str(e), 'health': 'error'}
    
    async def retry_failed_messages(self, max_retries: int = 10) -> int:
        """重试失败的消息"""
        retried = 0
        
        try:
            for _ in range(max_retries):
                # 获取一个失败的消息
                failed_json = self.redis.rpop(self.QUEUE_KEYS['failed'])
                if not failed_json:
                    break
                
                failed_data = json.loads(failed_json)
                retry_time = datetime.fromisoformat(failed_data['retry_at'])
                
                # 检查是否可以重试
                if get_current_time() >= retry_time:
                    # 重新入队
                    self.redis.lpush(self.QUEUE_KEYS['raw'], 
                                         json.dumps(failed_data['message']))
                    retried += 1
                    logger.info(f"重试失败消息: {failed_data.get('worker_id')}")
                else:
                    # 还没到重试时间，放回队列
                    self.redis.rpush(self.QUEUE_KEYS['failed'], failed_json)
                    break
            
            return retried
            
        except Exception as e:
            logger.error(f"重试失败消息出错: {e}")
            return 0

# 全局队列实例
_message_queue = None

def get_message_queue() -> MessageQueue:
    """获取消息队列实例"""
    global _message_queue
    if _message_queue is None:
        _message_queue = MessageQueue()
    return _message_queue