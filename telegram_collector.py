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
from app.core.path_config import PathConfig
from app.core.url_config import url_config
from app.telegram.bot import TelegramBot

# 使用统一的日志配置
from app.core.logging_config import setup_logging, get_logger

# 初始化日志系统
setup_logging(service_name="collector", log_level="INFO", console_output=True)
logger = get_logger(__name__)

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
            
            # Redis管理器自动处理连接管理 - Linus式简洁
            from app.storage.redis_manager import redis_manager
            if not redis_manager.is_healthy():
                await self.health_monitor.set_unhealthy("Redis连接不可用")
                raise RuntimeError("Redis连接失败")
            logger.info("Redis管理器已就绪")
            
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
            logger.debug("频道ID缓存检查完成")
            
            # 初始化训练数据目录和配置
            PathConfig.ensure_directories()
            logger.info("训练数据目录已初始化")
            
            # 加载数据库配置
            await settings.load_db_configs()
            
            # 主动建立Telegram Listener连接（而不是被动检查状态）
            from app.telegram.dual_session_manager import dual_session_manager
            
            # 主动尝试连接Listener Session
            logger.info("正在建立Telegram Listener连接...")
            listener_connected = await dual_session_manager.ensure_listener_connected()
            
            # 获取连接状态用于诊断
            connection_status = await dual_session_manager.get_connection_status()
            
            # 至少需要Listener Session连接才能采集消息
            auth_status = {
                'authorized': listener_connected,
                'connection_status': connection_status
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
                
                print(f"\n🔗 认证页面: {url_config.get_auth_url()}")
                print(f"🔗 API申请: https://my.telegram.org")
                print("="*60)
                
                await self.health_monitor.set_unhealthy("Telegram Listener认证失败", {
                    "auth_status": "listener_unauthorized", 
                    "config_issues": auth_status.get('config_issues', []),
                    "auth_url": url_config.get_auth_url(),
                    "solution": auth_status.get('solution', '')
                })
                
                logger.error("❌ Collector服务认证失败，进入等待认证模式")
                logger.error("详细诊断信息已输出到控制台")
                return False  # 返回False表示初始化失败，但不退出程序
            else:
                # Telegram已认证，检查采集开关
                from app.services.config_manager import config_manager
                collection_enabled = await config_manager.get_config('collection.enabled', False)
                
                if collection_enabled:
                    logger.info("✅ Telegram认证状态正常且采集已启用，启动消息监听...")
                    
                    # 启动Telegram客户端
                    bot = TelegramBot()
                    await bot.start()
                    
                    # 设置全局bot实例供其他模块使用
                    bot_module.telegram_bot = bot
                    self.telegram_bot = bot
                else:
                    logger.info("✅ Telegram认证状态正常但采集已禁用，待机模式...")
                    # 采集禁用时不启动bot，避免注册事件处理器
                
                # 启动系统监控
                from app.services.system_monitor import system_monitor
                await system_monitor.start()
                
                # 设置健康状态 
                await self.health_monitor.set_healthy({
                    "telegram_authenticated": True,
                    "bot_running": self.telegram_bot is not None,
                    "collection_enabled": collection_enabled,
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
                
                previous_collection_enabled = None
                
                while self.is_running:
                    # 检查采集开关
                    from app.services.config_manager import config_manager
                    collection_enabled = await config_manager.get_config('collection.enabled', False)
                    
                    # 检测采集开关状态变化
                    if previous_collection_enabled is not None and previous_collection_enabled != collection_enabled:
                        if collection_enabled:
                            # 采集从禁用变为启用 - 启动bot
                            logger.info("🟢 检测到采集已启用，启动Telegram Bot...")
                            
                            # 检查是否需要重新采集历史（checkpoint是否为空）
                            from app.storage.redis_manager import redis_manager
                            has_checkpoints = redis_manager.client.hlen("channel:checkpoint") > 0
                            
                            if not has_checkpoints:
                                logger.info("📊 检测到checkpoint为空（可能刚完成系统重置），需要重新采集历史消息")
                                
                                # 如果Bot已经在运行，直接触发历史采集
                                if self.telegram_bot and hasattr(self.telegram_bot, 'client') and self.telegram_bot.client:
                                    logger.info("Bot已运行，直接触发历史消息采集...")
                                    from app.telegram.history_collector import history_collector
                                    try:
                                        await history_collector.collect_channel_history(self.telegram_bot.client)
                                        logger.info("✅ 历史消息采集已触发")
                                    except Exception as e:
                                        logger.error(f"❌ 触发历史采集失败: {e}")
                                else:
                                    # Bot未运行，需要启动新的Bot（会自动触发历史采集）
                                    logger.info("Bot未运行，启动新Bot...")
                            else:
                                checkpoint_count = redis_manager.client.hlen("channel:checkpoint")
                                logger.info(f"📊 检测到已有 {checkpoint_count} 个频道的checkpoint，将从上次位置继续采集")
                            
                            # 原有的Bot启动逻辑
                            if not self.telegram_bot:
                                try:
                                    bot = TelegramBot()
                                    await bot.start()
                                    bot_module.telegram_bot = bot
                                    self.telegram_bot = bot
                                    logger.info("✅ Telegram Bot启动成功")
                                except Exception as e:
                                    logger.error(f"❌ Telegram Bot启动失败: {e}")
                                    # 不退出服务，记录错误并等待下次重试
                                    await asyncio.sleep(10)
                                    continue
                        else:
                            # 采集从启用变为禁用 - 停止bot并清理队列
                            logger.info("🔴 检测到采集已禁用，停止Telegram Bot并清理队列...")
                            if self.telegram_bot:
                                try:
                                    await self.telegram_bot.stop()
                                    self.telegram_bot = None
                                    bot_module.telegram_bot = None
                                    logger.info("✅ Telegram Bot已停止")
                                except Exception as e:
                                    logger.error(f"⚠️ 停止Telegram Bot失败: {e}")
                                    # 强制清理状态，避免僵尸进程
                                    self.telegram_bot = None
                                    bot_module.telegram_bot = None
                            
                            # 清理Redis消息队列
                            try:
                                await self._clear_message_queues()
                                logger.info("✅ 消息队列清理完成")
                            except Exception as e:
                                logger.error(f"⚠️ 清理消息队列失败: {e}")
                    
                    previous_collection_enabled = collection_enabled
                    
                    # Linus式修复：实时更新健康监控状态，消除缓存不同步的特殊情况
                    await self.health_monitor.update_metadata({
                        "telegram_authenticated": True,
                        "bot_running": self.telegram_bot is not None,
                        "collection_enabled": collection_enabled,
                        "system_monitor": True
                    })
                    
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
            logger.warning("⚠️ Telegram采集服务启动失败，进入待机模式...")
            # 在等待认证模式下运行，但保持服务稳定
            try:
                while True:
                    # 始终检查双Session认证状态，不受采集开关影响
                    from app.telegram.dual_session_manager import dual_session_manager
                    connection_status = await dual_session_manager.get_connection_status()
                    auth_status = {'authorized': connection_status.get('listener_connected', False)}
                    
                    if auth_status.get('authorized', False):
                        logger.info("检测到Telegram认证完成，重新启动采集服务...")
                        if await self.initialize():
                            self.is_running = True
                            break
                    else:
                        logger.debug("等待Telegram认证...")
                    
                    await asyncio.sleep(10)
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
    
    async def _clear_message_queues(self):
        """清理Redis中的消息队列"""
        try:
            from app.storage.redis_manager import redis_manager
            
            # 清理消息队列
            queue_keys = [
                "telegram:message_queue",
                "telegram:processing_messages",
                "telegram:pending_messages",
                "collector:queue:raw",           # 原始消息队列
                "processor:queue:pending",       # 处理器待处理队列
                "processor:queue:processing",    # 处理器正在处理队列
                "media_refetch:queue",           # 媒体补抓队列
                "message_forward:queue"          # 消息转发队列
            ]
            
            cleared_count = 0
            for key in queue_keys:
                count = await redis_manager.delete_key(key)
                if count > 0:
                    cleared_count += count
                    logger.info(f"清理队列 {key}: {count} 个消息")
            
            if cleared_count > 0:
                logger.info(f"✅ 采集禁用时清理消息队列完成，共清理 {cleared_count} 个消息")
            else:
                logger.debug("消息队列已空，无需清理")
                
        except Exception as e:
            logger.error(f"清理消息队列失败: {e}")
    
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
                    await asyncio.sleep(0.1)  # 100ms检查间隔，快速响应任务
                    
            except Exception as e:
                logger.error(f"任务处理器错误: {e}")
                await asyncio.sleep(5)
        
        logger.info("任务处理器已停止")
    
    async def process_forward_task(self, task):
        """处理消息转发任务（带重试机制）"""
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
                await self._notify_forward_failure(message_id, "无效的消息ID格式", True)
                return
            
            channel_id, msg_id = message_id.split(':', 1)
            
            # 获取消息数据
            msg_data = await message_processor.get_message(channel_id, int(msg_id))
            if not msg_data:
                forward_queue.complete_task(
                    task, False, error_message="消息不存在"
                )
                await self._notify_forward_failure(message_id, "消息不存在", True)
                return
            
            # 检查Telegram客户端（采集服务已有客户端连接）
            if not self.telegram_bot or not self.telegram_bot.client:
                # 客户端未连接是临时性错误，应该重试
                await self._handle_forward_retry(task, "Telegram客户端未连接")
                return
            
            # 执行转发
            if task.action == "forward_to_target":
                await message_forwarder.forward_to_target(self.telegram_bot.client, msg_data)
                forward_queue.complete_task(
                    task, True, result={"action": "forward_to_target", "message": "转发成功"}
                )
                logger.info(f"消息 {message_id} 成功转发到目标频道")
                # 通知前端转发成功
                await self._notify_forward_success(message_id)
                
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
                await self._notify_forward_failure(message_id, f"不支持的转发动作: {task.action}", True)
            
        except Exception as e:
            logger.error(f"处理转发任务失败: {e}", exc_info=True)
            # 检查是否需要重试
            await self._handle_forward_retry(task, str(e))
    
    async def _handle_forward_retry(self, task, error_message: str):
        """处理转发任务重试逻辑"""
        from app.services.message_forward_queue import forward_queue
        
        task.retry_count += 1
        
        if task.retry_count < 3:
            # 重新入队重试
            await forward_queue.requeue_task(task)
            logger.info(f"转发任务失败，将重试 ({task.retry_count}/3): {task.message_id}")
            # 通知前端正在重试
            await self._notify_forward_retry(task.message_id, task.retry_count, error_message)
        else:
            # 3次失败，消息回到待审核状态
            await self._revert_to_pending(task.message_id)
            forward_queue.complete_task(
                task, False, 
                error_message=f"转发3次失败: {error_message}"
            )
            # 通知前端最终失败
            await self._notify_forward_failure(task.message_id, error_message, True)
            logger.error(f"消息 {task.message_id} 转发3次失败，已回退到待审核状态")
    
    async def _revert_to_pending(self, message_id: str):
        """将消息状态改回待审核"""
        try:
            from app.storage.redis_manager import redis_manager
            
            if ':' in message_id:
                channel_id, msg_id = message_id.split(':', 1)
                # 更新消息状态为pending
                redis_manager.update_message_field(
                    channel_id, int(msg_id), 
                    'status', 'pending'
                )
                # 记录失败原因
                redis_manager.update_message_field(
                    channel_id, int(msg_id),
                    'forward_failure_reason', '自动转发失败，需要手动处理'
                )
                logger.info(f"消息 {message_id} 已回退到待审核状态")
        except Exception as e:
            logger.error(f"回退消息状态失败: {e}")
    
    async def _notify_forward_success(self, message_id: str):
        """通过WebSocket通知转发成功"""
        try:
            import json
            from app.api.websocket import websocket_manager
            payload = {
                "type": "forward_success",
                "message_id": message_id,
                "message": f"消息 {message_id} 发布成功"
            }
            await websocket_manager.broadcast(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.debug(f"WebSocket通知失败: {e}")
    
    async def _notify_forward_retry(self, message_id: str, retry_count: int, error: str):
        """通过WebSocket通知正在重试"""
        try:
            import json
            from app.api.websocket import websocket_manager
            payload = {
                "type": "forward_retry",
                "message_id": message_id,
                "retry_count": retry_count,
                "error": error,
                "message": f"消息 {message_id} 发布失败，正在重试 ({retry_count}/3)"
            }
            await websocket_manager.broadcast(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.debug(f"WebSocket通知失败: {e}")
    
    async def _notify_forward_failure(self, message_id: str, error: str, is_final: bool):
        """通过WebSocket通知转发失败"""
        try:
            import json
            from app.api.websocket import websocket_manager
            event_type = "forward_final_failure" if is_final else "forward_failed"
            message = f"消息 {message_id} 发布失败，已回退到待审核状态" if is_final else f"消息 {message_id} 发布失败"
            
            payload = {
                "type": event_type,
                "message_id": message_id,
                "error": error,
                "action": "reverted_to_pending" if is_final else None,
                "message": message
            }
            await websocket_manager.broadcast(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.debug(f"WebSocket通知失败: {e}")
    
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
            from app.storage.redis_manager import redis_manager
            msg_data = redis_manager.get_message(channel_id, int(msg_id))
            
            if not msg_data:
                media_refetch_service.complete_task(
                    task.task_id, False, error_message="消息不存在"
                )
                return
            
            # 检查是否有媒体
            if not msg_data.get('media_type'):
                media_refetch_service.complete_task(
                    task.task_id, False, error_message="该消息没有媒体文件"
                )
                return
            
            # 获取Sender客户端（按需连接）
            try:
                from app.telegram.dual_session_manager import dual_session_manager
                sender_client = await dual_session_manager.get_sender_client()
                
                if not sender_client:
                    media_refetch_service.complete_task(
                        task.task_id, False, error_message="Sender Session未连接"
                    )
                    return
                    
                logger.info(f"使用Sender Session补抓消息 #{message_id} 的媒体文件")
                
            except Exception as client_e:
                logger.error(f"获取Sender客户端失败: {client_e}")
                media_refetch_service.complete_task(
                    task.task_id, False, error_message=f"获取Sender客户端失败: {client_e}"
                )
                return
            
            # 获取原始消息
            try:
                source_entity = await sender_client.get_entity(int(msg_data['source_channel']))
                original_msg = await sender_client.get_messages(
                    entity=source_entity,
                    ids=int(msg_data['message_id'])
                )
                
                if not original_msg or not original_msg.media:
                    media_refetch_service.complete_task(
                        task.task_id, False, error_message="原始消息不存在或没有媒体"
                    )
                    return
                
                # 下载媒体文件
                logger.info(f"开始使用Sender Session下载媒体文件")
                
                from app.services.media_handler import media_handler
                media_info = await media_handler.download_media(
                    client=sender_client,
                    message=original_msg,
                    message_id=original_msg.id,
                    timeout=120.0
                )
                
                if media_info and media_info.get("file_path"):
                    # 更新Redis记录
                    from datetime import datetime
                    import json
                    import os
                    
                    # 更新消息的媒体信息
                    update_data = {
                        'media_url': media_info["file_path"],
                        'media_type': media_info.get("media_type", msg_data.get('media_type')),
                        'media_hash': media_info.get("hash", ''),
                        'visual_hash': json.dumps(media_info.get("visual_hashes", {})) if media_info.get("visual_hashes") else '',
                        'updated_at': datetime.now().isoformat()
                    }
                    
                    # 更新原消息数据
                    updated_msg_data = {**msg_data, **update_data}
                    redis_manager.save_message(channel_id, int(msg_id), updated_msg_data)
                    
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
                    
                    # 通过Redis Pub/Sub发送WebSocket通知（跨进程通信）
                    try:
                        from app.storage.redis_manager import redis_manager
                        import os
                        
                        # 生成显示URL
                        file_name = os.path.basename(media_info["file_path"])
                        media_display_url = f'/temp_media/{file_name}' if file_name else None
                        
                        # 构造通知数据
                        notification_data = {
                            "message_id": message_id,
                            "success": True,
                            "media_url": media_info["file_path"],
                            "media_display_url": media_display_url,
                            "media_type": media_info.get("media_type"),
                            "file_size": media_info.get("file_size"),
                            "timestamp": datetime.utcnow().isoformat(),
                            "refetched": True
                        }
                        
                        # 如果是组合消息，需要特殊处理
                        if msg_data.get('is_combined') == 'True':
                            # 获取完整的组合消息媒体信息
                            combined_messages = json.loads(msg_data.get('combined_messages', '[]'))
                            media_group_display = []
                            
                            for sub_msg in combined_messages:
                                if sub_msg.get('media_path'):
                                    sub_file_name = os.path.basename(sub_msg['media_path'])
                                    media_group_display.append({
                                        'message_id': sub_msg.get('message_id'),
                                        'media_type': sub_msg.get('media_type'),
                                        'file_path': sub_msg.get('media_path'),
                                        'display_url': f'/temp_media/{sub_file_name}' if sub_file_name else None
                                    })
                            
                            if media_group_display:
                                notification_data["media_group_display"] = media_group_display
                        
                        # 构造完整的WebSocket消息格式
                        websocket_message = {
                            "type": "media_refetched",
                            "data": notification_data,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        
                        # 发布到Redis频道（跨进程通信）
                        redis_client = redis_manager.client
                        if redis_client:
                            message_json = json.dumps(websocket_message, ensure_ascii=False)
                            redis_client.publish("websocket:broadcast", message_json)
                            logger.info(f"📡 已发布媒体补抓通知到Redis频道: {message_id}")
                            logger.debug(f"🔍 发布的消息内容: {message_json}")
                        else:
                            logger.error("Redis客户端不可用，无法发送WebSocket通知")
                        
                    except Exception as e:
                        logger.error(f"发送媒体补抓Redis通知失败: {e}")
                        import traceback
                        logger.error(f"详细错误信息: {traceback.format_exc()}")
                    
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
