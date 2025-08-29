#!/usr/bin/env python3
"""
Linus式消息处理器 - 专门从队列消费消息并处理
遵循"做一件事并做好"的原则：只管处理，不管采集

运行模式:
    python3 message_processor.py          # 启动默认工作进程池
    python3 message_processor.py --workers 10  # 自定义工作进程数
"""
import os
import sys
import asyncio
import logging
import signal
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 确保日志目录存在
os.makedirs('./logs', exist_ok=True)

from logging.handlers import TimedRotatingFileHandler

# 创建自定义的文件处理器，过滤数据库日志
class FilteredTimedRotatingFileHandler(TimedRotatingFileHandler):
    """过滤特定模块的按时间轮转文件处理器"""
    def emit(self, record):
        # 过滤掉数据库相关的日志
        if record.name.startswith(('sqlalchemy', 'asyncpg', 'databases')):
            return
        super().emit(record)

# 在日志初始化前导入PathConfig
from app.core.path_config import PathConfig

file_handler = FilteredTimedRotatingFileHandler(
    filename=str(PathConfig.LOGS_DIR / "message_processor.log"),
    when='H',  # 按小时轮转
    interval=1,  # 每1小时
    backupCount=24*7,  # 保留7天的日志
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# 创建错误级别的文件处理器
error_handler = FilteredTimedRotatingFileHandler(
    filename=str(PathConfig.ERROR_LOG_FILE),
    when='H',
    interval=1,
    backupCount=24*7,
    encoding='utf-8'
)
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# 配置根日志记录器
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(error_handler)

# 控制台输出（开发环境）
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
))
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)

from app.services.message_queue import get_message_queue, CollectedMessage, GroupedMessages, MessageType
from app.services.performance_monitor import performance_monitor
from app.utils.timezone import get_current_time

class MessageProcessor:
    """
    Linus式消息处理器 - 纯粹的消费者
    
    设计原则:
    1. "做一件事并做好" - 只从队列消费并处理消息
    2. "最笨但最清晰" - 简单的工作进程池
    3. "Never break userspace" - 失败时不影响其他消息
    """
    
    def __init__(self, worker_count: int = 5):
        self.worker_count = worker_count
        self.workers: List[asyncio.Task] = []
        self.is_running = False
        self.queue = get_message_queue()
        
        # 统计信息
        self.stats = {
            'processed': 0,
            'failed': 0,
            'single_messages': 0,
            'group_messages': 0,
            'start_time': None
        }
    
    async def start(self):
        """启动处理器池"""
        if self.is_running:
            logger.warning("消息处理器已在运行中")
            return
        
        self.is_running = True
        self.stats['start_time'] = get_current_time()
        
        logger.info(f"🚀 启动消息处理器池 (workers: {self.worker_count})")
        
        # 启动工作进程
        self.workers = []
        for worker_id in range(self.worker_count):
            task = asyncio.create_task(self._worker_loop(f"worker-{worker_id}"))
            self.workers.append(task)
        
        # 启动统计报告任务
        stats_task = asyncio.create_task(self._stats_reporter())
        self.workers.append(stats_task)
        
        # 等待所有工作进程
        try:
            await asyncio.gather(*self.workers, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("收到停止信号...")
        finally:
            await self.stop()
    
    async def stop(self):
        """停止处理器池"""
        if not self.is_running:
            return
        
        logger.info("⏹️ 停止消息处理器池...")
        self.is_running = False
        
        # 取消所有工作进程
        for worker in self.workers:
            if not worker.done():
                worker.cancel()
        
        # 等待取消完成
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        
        # 打印最终统计
        duration = (get_current_time() - self.stats['start_time']).total_seconds()
        logger.info(f"📊 处理器统计 - 运行时间: {duration:.1f}秒")
        logger.info(f"    处理成功: {self.stats['processed']}")
        logger.info(f"    处理失败: {self.stats['failed']}")
        logger.info(f"    单消息: {self.stats['single_messages']}")
        logger.info(f"    组消息: {self.stats['group_messages']}")
        if duration > 0:
            logger.info(f"    处理速度: {self.stats['processed']/duration:.1f} msg/s")
    
    async def _worker_loop(self, worker_id: str):
        """单个工作进程的主循环"""
        logger.info(f"🔧 启动工作进程: {worker_id}")
        
        while self.is_running:
            try:
                # 从队列获取消息（阻塞等待）
                message_data = await self.queue.dequeue_message(worker_id, timeout=1)
                if not message_data:
                    continue  # 超时，继续等待
                
                # 处理消息
                await self._process_message(worker_id, message_data)
                
            except asyncio.CancelledError:
                logger.info(f"工作进程 {worker_id} 被取消")
                break
            except Exception as e:
                logger.error(f"工作进程 {worker_id} 异常: {e}")
                await asyncio.sleep(1)  # 错误后短暂等待
        
        logger.info(f"🔧 工作进程停止: {worker_id}")
    
    async def _process_message(self, worker_id: str, message_data: Dict[str, Any]):
        """处理单条消息"""
        message_type = message_data.get('type')
        
        try:
            if message_type == MessageType.SINGLE.value:
                await self._process_single_message(worker_id, message_data['data'])
                self.stats['single_messages'] += 1
                
            elif message_type == MessageType.GROUP.value:
                await self._process_group_message(worker_id, message_data['data'])
                self.stats['group_messages'] += 1
                
            else:
                raise ValueError(f"未知消息类型: {message_type}")
            
            # 标记完成
            await self.queue.mark_completed(worker_id, message_data)
            self.stats['processed'] += 1
            
        except Exception as e:
            logger.error(f"消息处理失败 ({worker_id}): {e}")
            await self.queue.mark_failed(worker_id, message_data, str(e))
            self.stats['failed'] += 1
    
    async def _process_single_message(self, worker_id: str, message_data: Dict[str, Any]):
        """处理单条消息"""
        # 重建CollectedMessage对象
        collected_msg = CollectedMessage.from_dict(message_data)
        
        # 使用性能监控
        operation_name = "process_from_queue"
        async with performance_monitor(
            operation_name,
            channel_id=collected_msg.channel_id,
            channel_name=collected_msg.raw_data.get('chat_title', 'Unknown'),
            message_id=collected_msg.message_id,
            message_type=collected_msg.media_type or 'text',
            content_length=len(collected_msg.content)
        ) as perf_ctx:
            
            # 重建Telegram消息对象（用于现有处理管道）
            telegram_message = await self._rebuild_telegram_message(collected_msg)
            
            # 使用现有的处理管道
            from app.services.processors import MessagePipeline, MessageReceiver, MessageFilterProcessor, MessageStorageProcessor
            from app.services.processors.base import MessageContext
            
            perf_ctx.start_stage("pipeline_setup")
            context = MessageContext(
                telegram_message=telegram_message,
                channel_id=collected_msg.channel_id
            )
            
            # 预填充collector已处理的媒体信息
            if collected_msg.media_info:
                context.media_info = collected_msg.media_info
                context.media_type_info = {
                    'has_media': True,
                    'media_type': collected_msg.media_type or 'unknown'
                }
                logger.debug(f"预填充媒体信息: {collected_msg.message_key}")
            
            pipeline = MessagePipeline([
                MessageReceiver(),
                # MediaDownloader已移除：collector负责媒体下载，processor专注业务逻辑
                MessageFilterProcessor(), 
                MessageStorageProcessor()
            ])
            perf_ctx.end_stage("pipeline_setup")
            
            # 执行处理
            perf_ctx.start_stage("pipeline_execution")
            result = await pipeline.process(context)
            perf_ctx.end_stage("pipeline_execution", 
                             success=result.success,
                             processors_count=len(pipeline.processors))
            
            if result.success:
                logger.debug(f"✅ 单消息处理完成: {collected_msg.message_key} ({worker_id})")
            else:
                raise Exception(f"处理管道失败: {result.error}")
    
    async def _process_group_message(self, worker_id: str, group_data: Dict[str, Any]):
        """处理组消息"""
        # 重建GroupedMessages对象
        grouped_messages = GroupedMessages(
            grouped_id=group_data['grouped_id'],
            channel_id=group_data['channel_id'],
            messages=[CollectedMessage.from_dict(msg) for msg in group_data['messages']]
        )
        
        logger.info(f"📦 处理组消息: {grouped_messages.grouped_id} ({grouped_messages.message_count}条)")
        
        # 组消息处理逻辑
        # 暂时简化：合并所有消息内容后作为单消息处理
        combined_content = "\n\n".join(msg.content for msg in grouped_messages.messages if msg.content)
        
        # 使用第一条消息作为模板
        first_msg = grouped_messages.messages[0]
        
        # 组合消息数据
        combined_message_data = {
            'channel_id': first_msg.channel_id,
            'message_id': first_msg.message_id,  # 使用第一条消息的ID
            'grouped_id': grouped_messages.grouped_id,
            'content': combined_content,
            'media_type': first_msg.media_type,
            'media_url': first_msg.media_url,
            'timestamp': first_msg.timestamp.isoformat() if first_msg.timestamp else None,
            'collected_at': first_msg.collected_at.isoformat() if first_msg.collected_at else None,
            'raw_data': {
                **first_msg.raw_data,
                'is_combined': True,
                'message_count': grouped_messages.message_count,
                'combined_messages': [msg.message_id for msg in grouped_messages.messages]
            }
        }
        
        # 处理合并消息
        await self._process_single_message(worker_id, combined_message_data)
        logger.info(f"✅ 组消息处理完成: {grouped_messages.grouped_id} ({worker_id})")
    
    async def _rebuild_telegram_message(self, collected_msg: CollectedMessage):
        """重建Telegram消息对象 - 最小化兼容现有处理器"""
        # 创建一个简单的消息对象，满足现有处理器的需求
        class MockTelegramMessage:
            def __init__(self, collected_msg: CollectedMessage):
                self.id = collected_msg.message_id
                self.message = collected_msg.content
                self.text = collected_msg.content
                self.caption = collected_msg.content if collected_msg.media_type else None
                self.date = collected_msg.timestamp
                self.media = self._create_mock_media(collected_msg.media_type) if collected_msg.media_type else None
                self.grouped_id = int(collected_msg.grouped_id) if collected_msg.grouped_id else None
                
                # 扩展信息
                self.sender = type('MockSender', (), {
                    'id': collected_msg.raw_data.get('sender_id')
                })() if collected_msg.raw_data.get('sender_id') else None
                
                self.reply_to_msg_id = collected_msg.raw_data.get('reply_to_msg_id')
                self.forward = collected_msg.raw_data.get('forward_info')
            
            def _create_mock_media(self, media_type: str):
                """创建模拟媒体对象"""
                if not media_type:
                    return None
                
                # 简单的媒体类型映射
                media_class_name = f"MessageMedia{media_type.capitalize()}"
                return type(media_class_name, (), {})()
        
        return MockTelegramMessage(collected_msg)
    
    async def _stats_reporter(self):
        """统计报告任务"""
        last_processed = 0
        
        while self.is_running:
            try:
                await asyncio.sleep(30)  # 每30秒报告一次
                
                # 计算处理速度
                current_processed = self.stats['processed']
                speed = (current_processed - last_processed) / 30
                last_processed = current_processed
                
                # 获取队列状态
                queue_status = await self.queue.get_queue_status()
                
                logger.info(f"📊 处理器状态 - 处理速度: {speed:.1f} msg/s, "
                          f"队列长度: {queue_status['raw_queue_length']}, "
                          f"已处理: {current_processed}, "
                          f"失败: {self.stats['failed']}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"统计报告异常: {e}")

def setup_signal_handlers(processor: MessageProcessor):
    """设置信号处理"""
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}, 准备停止...")
        asyncio.create_task(processor.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Linus式消息处理器")
    parser.add_argument('--workers', type=int, default=5, help='工作进程数量')
    parser.add_argument('--log-level', default='INFO', help='日志级别')
    
    args = parser.parse_args()
    
    # 设置日志级别
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    
    logger.info("🚀 启动消息处理器...")
    
    # 初始化存储层
    logger.info("初始化存储层...")
    
    # 初始化Redis存储层
    from app.storage.redis_store import init_redis_stores
    if not init_redis_stores():
        logger.error("❌ Redis存储层初始化失败")
        return 1
    logger.info("✅ Redis连接已初始化")
    
    # 初始化JSON存储层
    from app.storage.json_store import init_json_stores
    if not init_json_stores():
        logger.error("❌ JSON存储层初始化失败")
        return 1
    logger.info("✅ JSON存储层已初始化")
    
    # 创建处理器
    processor = MessageProcessor(worker_count=args.workers)
    
    # 设置信号处理
    setup_signal_handlers(processor)
    
    try:
        logger.info("🚀 启动Linus式消息处理器")
        logger.info(f"工作进程数量: {args.workers}")
        
        await processor.start()
        
    except Exception as e:
        logger.error(f"消息处理器启动失败: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))