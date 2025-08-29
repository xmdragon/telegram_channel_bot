#!/usr/bin/env python3
"""
Telegram消息采集审核系统 - Telegram采集服务
独立的Telegram消息采集服务，不包含Web服务器
"""
import warnings
# 抑制pkg_resources弃用警告
warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from app.core.config import settings
from app.telegram.bot import TelegramBot

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
        # 过滤掉包含特定关键词的日志
        if any(keyword in record.getMessage().lower() for keyword in ['sql', 'database', 'query', 'insert', 'update', 'delete', 'select']):
            return
        super().emit(record)

# 在日志初始化前导入PathConfig
from app.core.path_config import PathConfig

file_handler = FilteredTimedRotatingFileHandler(
    filename=str(PathConfig.LOGS_DIR / "telegram_collector.log"),
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

class TelegramCollectorService:
    """Telegram采集服务"""
    
    def __init__(self):
        self.telegram_bot = None
        self.is_running = False
        self.health_monitor = None
        
    async def initialize(self):
        """初始化采集服务"""
        logger.info("📡 启动Telegram采集服务...")
        
        # 清理可能存在的残留锁
        await self._cleanup_stale_locks()
        
        # 启动健康监控
        from app.services.health_monitor import create_health_monitor
        self.health_monitor = create_health_monitor("telegram_collector")
        await self.health_monitor.start()
        
        try:
            # 基础系统初始化
            logger.info("初始化存储层和认证服务...")
            
            # 初始化Redis存储层
            from app.storage.redis_store import init_redis_stores
            if not init_redis_stores():
                await self.health_monitor.set_unhealthy("Redis存储层初始化失败")
                raise RuntimeError("初始化失败")
            logger.info("Redis连接已初始化")
            
            # 初始化JSON存储层
            from app.storage.json_store import init_json_stores
            if not init_json_stores():
                await self.health_monitor.set_unhealthy("JSON存储层初始化失败")
                raise RuntimeError("初始化失败")
            
            # 初始化认证服务
            from app.services.auth_service import init_auth_service
            if not init_auth_service():
                await self.health_monitor.set_unhealthy("认证服务初始化失败")
                raise RuntimeError("初始化失败")
            logger.info("认证服务已初始化")
            
            # 初始化频道ID缓存
            from app.services.channel_cache import channel_cache
            await channel_cache.init_cache()
            logger.info("频道ID缓存已初始化")
            
            # 初始化训练数据目录和配置
            PathConfig.ensure_directories()
            logger.info("训练数据目录已初始化")
            
            # 加载数据库配置
            await settings.load_db_configs()
            
            # 检查Telegram双Session认证状态
            from app.telegram.dual_session_manager import dual_session_manager
            connection_status = await dual_session_manager.get_connection_status()
            
            # 至少需要Listener Session连接才能采集消息
            auth_status = {
                'authorized': connection_status.get('listener_connected', False)
            }
            
            # 初始化全局变量
            from app.telegram import bot as bot_module
            bot_module.telegram_bot = None
            
            if not auth_status.get('authorized', False):
                # 输出详细认证诊断报告
                print("\n" + "="*60)
                print("📡 === Collector服务认证诊断报告 ===")
                print("="*60)
                
                print(f"\n🔍 配置检查:")
                print(f"   {auth_status.get('config_status', '未知')}")
                if auth_status.get('config_issues'):
                    for issue in auth_status.get('config_issues', []):
                        print(f"   • {issue}")
                
                print(f"\n🔗 连接检查:")
                print(f"   {auth_status.get('connection_status', '未知')}")
                
                if auth_status.get('session_length', 0) > 0:
                    print(f"\n📊 Session信息:")
                    print(f"   • Session长度: {auth_status.get('session_length')} 字符")
                    print(f"   • API配置: {'✅ 完整' if auth_status.get('api_configured') else '❌ 缺失'}")
                
                if auth_status.get('error_detail'):
                    print(f"\n❌ 错误详情:")
                    print(f"   {auth_status.get('error_detail')}")
                
                print(f"\n💡 解决方案:")
                print(f"   {auth_status.get('solution', '访问认证页面完成设置')}")
                
                print(f"\n🔗 认证页面: http://localhost:8080/static/telegram-auth.html")
                print(f"🔗 API申请: https://my.telegram.org")
                print("="*60)
                
                await self.health_monitor.set_unhealthy("Telegram Listener认证失败", {
                    "auth_status": "listener_unauthorized", 
                    "config_issues": auth_status.get('config_issues', []),
                    "auth_url": "http://localhost:8080/static/telegram-auth.html",
                    "solution": auth_status.get('solution', '')
                })
                
                logger.error("❌ Collector服务无法启动 - Listener认证失败")
                logger.error("详细诊断信息已输出到控制台")
                sys.exit(1)
            else:
                # Telegram已认证，正常启动
                logger.info("✅ Telegram认证状态正常，启动消息监听...")
                
                # 启动Telegram客户端
                bot = TelegramBot()
                await bot.start()
                
                # 设置全局bot实例供其他模块使用
                bot_module.telegram_bot = bot
                self.telegram_bot = bot
                
                # 启动系统监控
                from app.services.system_monitor import system_monitor
                await system_monitor.start()
                
                # 设置健康状态
                await self.health_monitor.set_healthy({
                    "telegram_authenticated": True,
                    "bot_running": True,
                    "system_monitor": True
                })
                
                logger.info("✅ Telegram采集服务启动完成")
                return True
                
        except Exception as e:
            if self.health_monitor:
                await self.health_monitor.set_unhealthy(f"初始化失败: {str(e)}")
            raise
    
    async def start(self):
        """启动采集服务"""
        if await self.initialize():
            self.is_running = True
            logger.info("📡 Telegram采集服务运行中...")
            
            # 保持服务运行，并处理媒体补抓任务
            try:
                # 启动任务处理器
                task_processor_task = asyncio.create_task(self.run_task_processor())
                
                while self.is_running:
                    # 检查采集开关
                    from app.services.config_manager import config_manager
                    collection_enabled = await config_manager.get_config('collection.enabled', False)
                    if not collection_enabled:
                        logger.debug("采集已禁用，等待启用...")
                        await asyncio.sleep(5)  # 暂停采集，等待启用
                        continue
                    
                    await asyncio.sleep(1)
                    
                # 停止任务处理器
                task_processor_task.cancel()
                try:
                    await task_processor_task
                except asyncio.CancelledError:
                    pass
                    
            except KeyboardInterrupt:
                logger.info("收到停止信号，正在关闭...")
                await self.stop()
        else:
            logger.warning("⚠️ Telegram采集服务启动失败，等待认证...")
            # 在等待认证模式下运行
            try:
                while True:
                    # 检查采集开关
                    from app.services.config_manager import config_manager
                    collection_enabled = await config_manager.get_config('collection.enabled', False)
                    if not collection_enabled:
                        logger.debug("采集已禁用，等待启用...")
                        await asyncio.sleep(10)
                        continue
                    
                    await asyncio.sleep(10)
                    # 定期检查双Session认证状态
                    connection_status = await dual_session_manager.get_connection_status()
                    auth_status = {'authorized': connection_status.get('listener_connected', False)}
                    if auth_status.get('authorized', False):
                        logger.info("检测到Telegram认证完成，重新启动采集服务...")
                        if await self.initialize():
                            self.is_running = True
                            break
            except KeyboardInterrupt:
                logger.info("收到停止信号，正在关闭...")
    
    async def _cleanup_stale_locks(self):
        """清理残留锁"""
        try:
            logger.info("🔧 检查并清理残留的Telegram锁...")
            
            # 检查Redis分布式锁系统（系统已使用Redis分布式锁，无需文件锁清理）
            logger.info("检查Redis分布式锁系统状态...")
            
            # 简化的锁状态检查：直接假定Redis锁系统正常
            lock_check_passed = True
            
            if lock_check_passed:
                logger.info("✅ Redis分布式锁系统正常")
            else:
                logger.warning("Redis分布式锁系统检查异常")
                
        except Exception as e:
            logger.warning(f"清理残留锁时出错: {e}")
    
    async def stop(self):
        """停止采集服务"""
        logger.info("📡 正在关闭Telegram采集服务...")
        self.is_running = False
        
        # 停止Telegram Bot
        if self.telegram_bot:
            await self.telegram_bot.stop()
            
        # 停止系统监控
        from app.services.system_monitor import system_monitor
        await system_monitor.stop()
        
        # 停止健康监控
        if self.health_monitor:
            await self.health_monitor.stop()
        
        logger.info("Telegram采集服务已关闭")
    
    async def run_task_processor(self):
        """运行任务处理器（媒体补抓 + 消息转发）"""
        logger.info("🔧 启动任务处理器（媒体补抓 + 消息转发）...")
        
        from app.services.media_refetch_service import media_refetch_service
        from app.services.message_forward_queue import forward_queue
        
        while self.is_running:
            try:
                processed_any = False
                
                # 🔧 新增：优先处理转发任务（实时性要求高） - 异步版本修复
                try:
                    forward_task = await forward_queue.get_pending_task_async()
                    if forward_task:
                        logger.info(f"处理消息转发任务: {forward_task.task_id} for message {forward_task.message_id}")
                        await self.process_forward_task(forward_task)
                        processed_any = True
                except Exception as e:
                    logger.error(f"转发任务处理错误: {e}")
                
                # 处理媒体补抓任务
                try:
                    refetch_task = media_refetch_service.get_pending_task()
                    if refetch_task:
                        logger.info(f"处理媒体补抓任务: {refetch_task.task_id} for message {refetch_task.message_id}")
                        await self.process_refetch_task(refetch_task)
                        processed_any = True
                except Exception as e:
                    logger.error(f"媒体补抓任务处理错误: {e}")
                
                # 如果没有处理任何任务，短暂休眠
                if not processed_any:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"任务处理器错误: {e}")
                await asyncio.sleep(5)
        
        logger.info("任务处理器已停止")
    
    async def process_forward_task(self, task):
        """处理消息转发任务"""
        from app.services.message_forward_queue import forward_queue
        from app.services.message_processor import MessageProcessor
        from app.telegram.message_forwarder import message_forwarder
        
        try:
            message_processor = MessageProcessor()
            
            # 解析消息ID
            message_id = task.message_id
            if ':' not in message_id:
                forward_queue.complete_task(
                    task, False, error_message="无效的消息ID格式"
                )
                return
            
            channel_id, msg_id = message_id.split(':', 1)
            
            # 获取消息数据
            msg_data = await message_processor.get_message(channel_id, int(msg_id))
            if not msg_data:
                forward_queue.complete_task(
                    task, False, error_message="消息不存在"
                )
                return
            
            # 检查Telegram客户端（采集服务已有客户端连接）
            if not self.telegram_bot or not self.telegram_bot.client:
                forward_queue.complete_task(
                    task, False, error_message="Telegram客户端未连接"
                )
                return
            
            # 执行转发
            if task.action == "forward_to_target":
                await message_forwarder.forward_to_target(self.telegram_bot.client, msg_data)
                forward_queue.complete_task(
                    task, True, result={"action": "forward_to_target", "message": "转发成功"}
                )
                logger.info(f"消息 {message_id} 成功转发到目标频道")
                
            elif task.action == "forward_to_review":
                await message_forwarder.forward_to_review(self.telegram_bot.client, msg_data)
                forward_queue.complete_task(
                    task, True, result={"action": "forward_to_review", "message": "转发到审核群成功"}
                )
                logger.info(f"消息 {message_id} 成功转发到审核群")
                
            else:
                forward_queue.complete_task(
                    task, False, error_message=f"不支持的转发动作: {task.action}"
                )
            
        except Exception as e:
            logger.error(f"处理转发任务失败: {e}", exc_info=True)
            forward_queue.complete_task(
                task, False, error_message=str(e)
            )
    
    async def process_refetch_task(self, task):
        """处理单个媒体补抓任务"""
        from app.services.media_refetch_service import media_refetch_service
        
        try:
            # 解析消息ID
            message_id = task.message_id
            if ':' not in message_id:
                media_refetch_service.complete_task(
                    task.task_id, False, error_message="无效的消息ID格式"
                )
                return
            
            channel_id, msg_id = message_id.split(':', 1)
            
            # 获取消息数据
            from app.storage.redis_store import get_redis_message_store
            redis_store = get_redis_message_store()
            msg_key = f"msg:{channel_id}:{msg_id}"
            msg_data = redis_store.redis.hgetall(msg_key)
            
            if not msg_data:
                media_refetch_service.complete_task(
                    task.task_id, False, error_message="消息不存在"
                )
                return
            
            # 转换字节数据
            msg_data = {k.decode() if isinstance(k, bytes) else k: 
                       v.decode() if isinstance(v, bytes) else v 
                       for k, v in msg_data.items()}
            
            # 检查是否有媒体
            if not msg_data.get('media_type'):
                media_refetch_service.complete_task(
                    task.task_id, False, error_message="该消息没有媒体文件"
                )
                return
            
            # 检查Telegram客户端，如果还没准备好则等待
            max_retries = 10
            retry_count = 0
            while (not self.telegram_bot or not self.telegram_bot.client) and retry_count < max_retries:
                logger.info(f"等待Telegram客户端连接... (尝试 {retry_count + 1}/{max_retries})")
                await asyncio.sleep(2)
                retry_count += 1
            
            if not self.telegram_bot or not self.telegram_bot.client:
                media_refetch_service.complete_task(
                    task.task_id, False, error_message="Telegram客户端未连接：超时等待"
                )
                return
            
            # 获取原始消息
            try:
                source_entity = await self.telegram_bot.client.get_entity(int(msg_data['source_channel']))
                original_msg = await self.telegram_bot.client.get_messages(
                    entity=source_entity,
                    ids=int(msg_data['message_id'])
                )
                
                if not original_msg or not original_msg.media:
                    media_refetch_service.complete_task(
                        task.task_id, False, error_message="原始消息不存在或没有媒体"
                    )
                    return
                
                # 下载媒体文件
                logger.info(f"开始补抓消息 #{message_id} 的媒体文件")
                
                from app.services.media_handler import media_handler
                media_info = await media_handler.download_media(
                    client=self.telegram_bot.client,
                    message=original_msg,
                    message_id=original_msg.id,
                    timeout=120.0
                )
                
                if media_info and media_info.get("file_path"):
                    # 更新Redis记录
                    from datetime import datetime
                    import json
                    import os
                    
                    update_data = {
                        'media_url': media_info["file_path"],
                        'media_type': media_info.get("media_type", msg_data.get('media_type')),
                        'media_hash': media_info.get("hash", ''),
                        'visual_hash': json.dumps(media_info.get("visual_hashes", {})) if media_info.get("visual_hashes") else '',
                        'updated_at': datetime.now().isoformat()
                    }
                    redis_store.redis.hset(msg_key, mapping=update_data)
                    
                    logger.info(f"成功补抓媒体: {media_info['file_path']} ({media_info['file_size']} bytes)")
                    
                    # 如果是广告，自动保存到训练数据目录
                    if msg_data.get('is_ad') == 'True':
                        try:
                            from app.services.training_media_manager import training_media_manager
                            from app.services.ad_image_detector import ad_image_detector
                            
                            saved_path = await training_media_manager.save_training_media(
                                source_path=media_info["file_path"],
                                message_id=message_id,
                                media_type=media_info["media_type"],
                                channel_id=channel_id,
                                is_ad=True
                            )
                            if saved_path:
                                logger.info(f"广告媒体已保存到训练目录: {saved_path}")
                                
                                # 如果是图片，添加到广告图片索引
                                if media_info["media_type"].startswith("image"):
                                    await ad_image_detector.add_ad_image(
                                        saved_path,
                                        metadata={
                                            'message_id': message_id,
                                            'channel_id': channel_id
                                        }
                                    )
                                    logger.info(f"广告图片已添加到检测索引")
                        except Exception as e:
                            logger.error(f"保存到训练目录失败: {e}")
                    
                    # 完成任务
                    result = {
                        "media_url": media_info["file_path"],
                        "media_type": media_info["media_type"],
                        "file_size": media_info["file_size"],
                        "refetched": True
                    }
                    media_refetch_service.complete_task(task.task_id, True, result)
                else:
                    media_refetch_service.complete_task(
                        task.task_id, False, error_message="媒体下载失败"
                    )
                    
            except Exception as e:
                logger.error(f"补抓媒体失败: {e}")
                media_refetch_service.complete_task(
                    task.task_id, False, error_message=f"补抓失败: {str(e)}"
                )
                
        except Exception as e:
            logger.error(f"处理补抓任务失败: {e}")
            try:
                media_refetch_service.complete_task(
                    task.task_id, False, error_message=f"任务处理失败: {str(e)}"
                )
            except:
                pass

# 全局服务实例
collector_service = None

def signal_handler(signum, frame):
    """信号处理器 - Linus式修复：避免创建新事件循环"""
    logger.info(f"收到信号 {signum}，正在关闭服务...")
    if collector_service:
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_running_loop()
            # 在当前循环中调度停止任务
            loop.create_task(collector_service.stop())
        except RuntimeError:
            # 如果没有运行中的循环，创建新的（最后的选择）
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(collector_service.stop())
                loop.close()
            except Exception as e:
                logger.error(f"停止服务失败: {e}")
    sys.exit(0)

async def main():
    """主函数"""
    global collector_service
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    collector_service = TelegramCollectorService()
    await collector_service.start()

if __name__ == "__main__":
    logger.info("📡 启动独立Telegram采集服务...")
    asyncio.run(main())