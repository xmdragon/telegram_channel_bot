"""
Bot生命周期管理器
负责Bot的启动、停止、监控和连接管理
"""
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class BotManager:
    """Bot生命周期管理器"""
    
    def __init__(self):
        self.client = None
        self.is_running = False
        self.monitor_task = None
        self.event_loop_task = None
        self.auto_forward_task = None
        self.auto_collection_done = False
        
    async def start(self):
        """启动Bot和监控"""
        # 启动系统监控
        from app.services.system_monitor import system_monitor
        await system_monitor.start()
        logger.info("系统监控已启动")
        
        # 启动客户端监控循环
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
    
    async def _monitoring_loop(self):
        """监控循环 - 持续检查系统状态并尝试连接"""
        while True:
            try:
                if not self.is_running:
                    # 尝试连接客户端（无锁模式，用于监听）
                    from app.telegram.client_manager import client_manager
                    if await client_manager.connect_without_lock():
                        self.client = await client_manager.get_client()
                        self.is_running = True
                        
                        # 执行连接成功回调
                        await self._on_client_connected()
                        
                await asyncio.sleep(30)  # 30秒检查一次
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                await asyncio.sleep(10)
    
    async def _on_client_connected(self):
        """客户端连接成功时的回调"""
        try:
            # 启动媒体处理器
            from app.services.media_handler import media_handler
            await media_handler.start()
            
            # 注册事件处理器
            from app.telegram.message_event_handler import message_event_handler
            await message_event_handler.register_event_handlers(self.client)
            
            # 执行完整的启动检查
            await self._perform_startup_checks()
            
            # 首次连接时进行历史消息采集
            if not self.auto_collection_done:
                await self._auto_collect_history()
                self.auto_collection_done = True
            
            # 启动自动转发任务 - Linus式简单解决方案
            logger.info("启动自动转发任务...")
            self.auto_forward_task = asyncio.create_task(self._auto_forward_loop())
            
            # 创建并启动事件循环任务
            logger.info("启动事件循环...")
            self.event_loop_task = asyncio.create_task(self._run_event_loop())
            
        except Exception as e:
            logger.error(f"客户端连接回调失败: {e}")
    
    async def _on_client_disconnected(self):
        """客户端断开连接时的回调"""
        self.is_running = False
        self.client = None
        
        if self.event_loop_task:
            self.event_loop_task.cancel()
        
        if self.auto_forward_task:
            self.auto_forward_task.cancel()
    
    async def _run_event_loop(self):
        """运行客户端事件循环"""
        try:
            logger.info("开始监听消息...")
            await self.client.run_until_disconnected()
            logger.info("客户端事件循环已结束")
        except Exception as e:
            logger.error(f"客户端运行出错: {e}")
        finally:
            self.is_running = False
    
    async def _perform_startup_checks(self):
        """执行启动时的完整配置检查"""
        try:
            from app.services.startup_checker import startup_checker
            
            # 执行完整检查，传递已连接的客户端
            check_results = await startup_checker.check_and_resolve_all_channels(self.client)
            
            # 如果有严重错误，记录但继续运行
            if not check_results['success']:
                logger.error("启动检查发现配置问题，请通过Web界面修复配置")
            
            # 更新内存中的频道列表
            if check_results['source_channels']:
                logger.info(f"已加载 {len(check_results['source_channels'])} 个源频道")
            
            if check_results['target_channel']:
                logger.info(f"目标频道已配置: {check_results['target_channel']}")
            else:
                logger.warning("⚠️ 目标频道未配置，消息将无法转发")
                
            if check_results['review_group']:
                logger.info(f"审核群已配置: {check_results['review_group']}")
            else:
                logger.error("❌ 审核群未配置！为了安全起见，消息不会被转发到目标频道")
                logger.error("请通过Web界面配置审核群，否则所有消息将被阻止！")
                
        except Exception as e:
            logger.error(f"启动检查失败: {e}")
    
    async def _auto_collect_history(self):
        """自动采集频道历史消息"""
        try:
            logger.info("开始采集频道历史消息...")
            from app.telegram.history_collector import history_collector
            await history_collector.collect_channel_history(self.client)
        except Exception as e:
            logger.error(f"自动采集历史消息失败: {e}")
    
    async def _auto_forward_loop(self):
        """自动转发循环 - 在collector服务内直接执行"""
        logger.info("启动自动转发监控循环")
        
        while self.is_running:
            try:
                # 检查是否启用自动转发
                from app.services.config_manager import ConfigManager
                config_manager = ConfigManager()
                auto_forward_enabled = await config_manager.get_config("target.auto_forward_enabled", False)
                
                if auto_forward_enabled:
                    # 获取需要转发的消息
                    from app.services.message_processor import MessageProcessor
                    message_processor = MessageProcessor()
                    messages = await message_processor.get_auto_forward_messages()
                    
                    if messages:
                        logger.info(f"发现 {len(messages)} 条消息需要自动转发")
                        
                        # 使用临时客户端进行转发，避免锁冲突
                        from app.telegram.message_forwarder import message_forwarder
                        from app.storage.redis_store import get_redis_message_store
                        redis_store = get_redis_message_store()
                        
                        for message in messages:
                            try:
                                channel_id = message.get('source_channel')
                                message_id = message.get('message_id')
                                
                                if not channel_id or not message_id:
                                    logger.error("消息缺少ID信息")
                                    continue
                                    
                                msg_id = f"{channel_id}:{message_id}"
                                
                                # 获取完整的消息对象
                                full_message = redis_store.get_message(channel_id, message_id, silent=True)
                                if not full_message:
                                    logger.error(f"无法获取消息详情: {msg_id}")
                                    continue
                                
                                # 使用临时客户端转发，自动管理锁
                                await message_forwarder.forward_to_target_with_temp_client(full_message)
                                
                                # 只有在没有抛出异常的情况下才更新状态为已发布
                                redis_store.update_message_status(msg_id, "published", "auto_forward")
                                
                                logger.info(f"自动转发成功: {msg_id}")
                                
                            except Exception as e:
                                logger.error(f"转发消息失败: {msg_id if 'msg_id' in locals() else 'unknown'}, 错误: {e}")
                
                # 等待60秒后再次检查
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                logger.info("自动转发任务已被取消")
                break
            except Exception as e:
                logger.error(f"自动转发循环出错: {e}")
                await asyncio.sleep(60)  # 出错后等待再重试
    
    async def stop(self):
        """停止Bot"""
        self.is_running = False
        
        # 停止监控任务
        if self.monitor_task:
            self.monitor_task.cancel()
        
        # 停止事件循环任务
        if self.event_loop_task:
            self.event_loop_task.cancel()
        
        # 停止自动转发任务
        if self.auto_forward_task:
            self.auto_forward_task.cancel()
            
        # 停止系统监控
        from app.services.system_monitor import system_monitor
        await system_monitor.stop()
        
        # 停止历史采集
        from app.services.history_collector import history_collector as old_history_collector
        await old_history_collector.stop_all_collections()
        
        # 停止媒体处理器
        from app.services.media_handler import media_handler
        await media_handler.stop()
        
        # 断开客户端连接
        from app.telegram.client_manager import client_manager
        await client_manager.disconnect()
        self.client = None
        
        logger.info("Bot管理器已停止")
    
    def get_client(self) -> Optional:
        """获取当前客户端"""
        return self.client
    
    def is_client_running(self) -> bool:
        """检查客户端是否运行中"""
        return self.is_running

# 全局实例
bot_manager = BotManager()