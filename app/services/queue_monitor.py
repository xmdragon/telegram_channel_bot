"""
队列监控器 - 监控队列状态并处理异常
遵循"简单直接"的原则，提供实时监控和自动恢复功能
"""
import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from app.services.message_queue import get_message_queue
from app.utils.timezone import get_current_time
from app.storage.redis_manager import redis_manager

logger = logging.getLogger(__name__)

class QueueMonitor:
    """
    队列监控器 - 简洁监控
    
    职责:
    1. 监控队列长度和处理速度
    2. 处理超时的组消息缓冲
    3. 自动重试失败的消息
    4. 提供队列健康状态
    """
    
    def __init__(self):
        self.queue = get_message_queue()
        self.redis = None
        self._ensure_redis()
        
        self.is_running = False
        self.monitor_task = None
        self.group_timeout_task = None
        self.retry_task = None
        
        # 监控配置
        self.MONITOR_INTERVAL = 30  # 监控间隔(秒)
        self.GROUP_TIMEOUT_CHECK_INTERVAL = 60  # 组超时检查间隔(秒)
        self.RETRY_INTERVAL = 300   # 重试间隔(秒)
        
        # 告警阈值
        self.ALERT_QUEUE_LENGTH = 1000    # 队列长度告警阈值
        self.ALERT_FAILED_COUNT = 100     # 失败队列告警阈值
        self.ALERT_LOW_SPEED = 0.1        # 处理速度告警阈值 (msg/s)
        
        # 统计信息
        self.last_stats = {}
        self.alert_history = []
    
    def _ensure_redis(self):
        """确保Redis连接"""
        if not self.redis:
            redis_store = redis_manager
            if not redis_store:
                raise RuntimeError("无法获取Redis连接")
            self.redis = redis_manager.client
    
    async def start(self):
        """启动监控器"""
        if self.is_running:
            logger.warning("队列监控器已在运行中")
            return
        
        self.is_running = True
        logger.info("🔍 启动队列监控器")
        
        # 启动各种监控任务
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        self.group_timeout_task = asyncio.create_task(self._group_timeout_check_loop())
        self.retry_task = asyncio.create_task(self._retry_loop())
        
        # 等待所有任务
        try:
            await asyncio.gather(
                self.monitor_task,
                self.group_timeout_task, 
                self.retry_task,
                return_exceptions=True
            )
        except KeyboardInterrupt:
            logger.info("收到停止信号...")
        finally:
            await self.stop()
    
    async def stop(self):
        """停止监控器"""
        if not self.is_running:
            return
        
        logger.info("⏹️ 停止队列监控器")
        self.is_running = False
        
        # 取消所有任务
        for task in [self.monitor_task, self.group_timeout_task, self.retry_task]:
            if task and not task.done():
                task.cancel()
        
        # 等待取消完成
        tasks = [t for t in [self.monitor_task, self.group_timeout_task, self.retry_task] if t]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _monitor_loop(self):
        """主监控循环"""
        logger.info("🔍 启动主监控循环")
        
        while self.is_running:
            try:
                await self._check_queue_health()
                await asyncio.sleep(self.MONITOR_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(5)
    
    async def _check_queue_health(self):
        """检查队列健康状态"""
        try:
            # 获取队列状态
            status = await self.queue.get_queue_status()
            current_time = get_current_time()
            
            # 计算处理速度
            processing_speed = await self._calculate_processing_speed(status)
            
            # 健康检查
            alerts = []
            
            # 检查队列长度
            raw_queue_len = status.get('raw_queue_length', 0)
            if raw_queue_len > self.ALERT_QUEUE_LENGTH:
                alerts.append(f"队列积压: {raw_queue_len} 条消息")
            
            # 检查失败队列
            failed_queue_len = status.get('failed_queue_length', 0)
            if failed_queue_len > self.ALERT_FAILED_COUNT:
                alerts.append(f"失败队列: {failed_queue_len} 条消息")
            
            # 检查处理速度
            if processing_speed is not None and processing_speed < self.ALERT_LOW_SPEED:
                alerts.append(f"处理速度过慢: {processing_speed:.2f} msg/s")
            
            # 记录或发出告警
            if alerts:
                alert_msg = f"⚠️ 队列告警: {'; '.join(alerts)}"
                logger.warning(alert_msg)
                self.alert_history.append({
                    'timestamp': current_time.isoformat(),
                    'alerts': alerts,
                    'status': status
                })
                
                # 保持告警历史不超过100条
                if len(self.alert_history) > 100:
                    self.alert_history = self.alert_history[-100:]
            else:
                # 定期记录正常状态
                if raw_queue_len > 0 or failed_queue_len > 0:
                    logger.info(f"📊 队列状态 - 待处理: {raw_queue_len}, "
                              f"失败: {failed_queue_len}, "
                              f"速度: {processing_speed:.2f} msg/s" if processing_speed else "速度: N/A")
            
            # 保存当前统计
            self.last_stats = {
                **status,
                'processing_speed': processing_speed,
                'check_time': current_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"健康检查异常: {e}")
    
    async def _calculate_processing_speed(self, current_status: Dict) -> Optional[float]:
        """计算处理速度"""
        try:
            if not self.last_stats:
                return None
            
            # 获取统计数据
            current_completed = current_status.get('stats', {}).get('completed', 0)
            last_completed = self.last_stats.get('stats', {}).get('completed', 0)
            
            # 计算时间差
            current_time = get_current_time()
            last_check_time_str = self.last_stats.get('check_time')
            if not last_check_time_str:
                return None
            
            last_check_time = datetime.fromisoformat(last_check_time_str)
            time_delta = (current_time - last_check_time).total_seconds()
            
            if time_delta <= 0:
                return None
            
            # 计算速度
            processed_count = current_completed - last_completed
            speed = processed_count / time_delta
            
            return max(0, speed)  # 确保非负
            
        except Exception as e:
            logger.error(f"计算处理速度异常: {e}")
            return None
    
    async def _group_timeout_check_loop(self):
        """组消息超时检查循环"""
        logger.info("🔍 启动组超时检查循环")
        
        while self.is_running:
            try:
                await self._check_timeout_groups()
                await asyncio.sleep(self.GROUP_TIMEOUT_CHECK_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"组超时检查异常: {e}")
                await asyncio.sleep(10)
    
    async def _check_timeout_groups(self):
        """检查并处理超时的组消息缓冲"""
        try:
            # 查找所有组缓冲
            cursor = '0'
            timeout_groups = []
            
            while True:
                cursor, keys = await self.redis.scan(
                    cursor, 
                    match='collector:group:*',
                    count=100
                )
                
                for key in keys:
                    ttl = await self.redis.ttl(key)
                    if 0 < ttl <= 30:  # 剩余30秒以内的缓冲
                        group_id = key.decode().split(':')[-1]
                        group_size = await self.redis.hlen(key)
                        timeout_groups.append({
                            'key': key,
                            'group_id': group_id,
                            'size': group_size,
                            'ttl': ttl
                        })
                
                if cursor == 0:
                    break
            
            # 处理即将超时的组
            for group_info in timeout_groups:
                if group_info['size'] > 0:  # 有消息的组
                    logger.info(f"🕐 处理即将超时的组: {group_info['group_id']} "
                              f"({group_info['size']}条消息, {group_info['ttl']}s)")
                    
                    # 强制入队
                    await self._force_enqueue_group(group_info['key'], group_info['group_id'])
            
            if timeout_groups:
                logger.info(f"处理了 {len(timeout_groups)} 个超时组")
                
        except Exception as e:
            logger.error(f"组超时检查异常: {e}")
    
    async def _force_enqueue_group(self, group_key: str, group_id: str):
        """强制入队组消息（即使不完整）"""
        try:
            # 获取组数据
            group_data = await self.redis.hgetall(group_key)
            if not group_data:
                return
            
            # 解析消息
            messages = []
            for msg_id, msg_json in group_data.items():
                try:
                    msg_data = json.loads(msg_json)
                    from app.services.message_queue import CollectedMessage
                    messages.append(CollectedMessage.from_dict(msg_data))
                except Exception as e:
                    logger.error(f"解析组消息失败 {group_id}:{msg_id}: {e}")
                    continue
            
            if not messages:
                await self.redis.delete(group_key)
                return
            
            # 按ID排序
            messages.sort(key=lambda x: x.message_id)
            
            # 创建组消息对象
            from app.services.message_queue import GroupedMessages
            grouped_messages = GroupedMessages(
                grouped_id=group_id,
                channel_id=messages[0].channel_id,
                messages=messages
            )
            
            # 入队
            queue_data = {
                'type': 'group',
                'data': grouped_messages.to_dict()
            }
            
            # 原子操作：入队并删除缓冲
            pipe = self.redis.pipeline()
            pipe.lpush('collector:queue:raw', json.dumps(queue_data))
            pipe.delete(group_key)
            pipe.hincrby('queue:stats', 'enqueued_groups', 1)
            pipe.hincrby('queue:stats', 'total_enqueued', 1)
            pipe.hincrby('queue:stats', 'forced_groups', 1)  # 强制入队统计
            await pipe.execute()
            
            logger.info(f"✅ 强制入队组消息: {group_id} ({len(messages)}条)")
            
        except Exception as e:
            logger.error(f"强制入队组消息失败 {group_id}: {e}")
    
    async def _retry_loop(self):
        """重试失败消息循环"""
        logger.info("🔍 启动重试循环")
        
        while self.is_running:
            try:
                retried_count = await self.queue.retry_failed_messages(max_retries=10)
                if retried_count > 0:
                    logger.info(f"🔄 重试了 {retried_count} 条失败消息")
                
                await asyncio.sleep(self.RETRY_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"重试循环异常: {e}")
                await asyncio.sleep(30)
    
    async def get_monitor_status(self) -> Dict[str, Any]:
        """获取监控器状态"""
        try:
            queue_status = await self.queue.get_queue_status()
            
            return {
                'monitor_running': self.is_running,
                'queue_status': queue_status,
                'last_check': self.last_stats.get('check_time'),
                'processing_speed': self.last_stats.get('processing_speed'),
                'recent_alerts': self.alert_history[-5:] if self.alert_history else [],
                'alert_count': len(self.alert_history),
                'health': queue_status.get('health', 'unknown')
            }
        except Exception as e:
            return {
                'error': str(e),
                'monitor_running': self.is_running,
                'health': 'error'
            }

# 全局监控器实例
_queue_monitor = None

def get_queue_monitor() -> QueueMonitor:
    """获取队列监控器实例"""
    global _queue_monitor
    if _queue_monitor is None:
        _queue_monitor = QueueMonitor()
    return _queue_monitor