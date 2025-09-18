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
                    # 尝试连接监听客户端
                    from app.telegram.dual_session_manager import dual_session_manager
                    if await dual_session_manager.ensure_listener_connected():
                        self.client = await dual_session_manager.get_listener_client()
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
            
            # 🔧 修复组消息处理：初始化message_grouper的telegram_client
            await self._init_message_grouper_client()
            
            # 执行完整的启动检查
            await self._perform_startup_checks()
            
            # 先进行历史消息采集（基于checkpoint自动判断）
            await self._auto_collect_history()
            
            # 历史采集完成后，注册事件处理器开始实时监听
            from app.telegram.message_event_handler import message_event_handler
            await message_event_handler.register_event_handlers(self.client)
            
            # 自动转发已由scheduler服务处理
            logger.info("自动转发功能已迁移到scheduler服务")
            
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
    
    async def _init_message_grouper_client(self):
        """初始化消息组合器的Telegram客户端"""
        try:
            from app.services.message_grouper import message_grouper
            
            # 设置message_grouper使用相同的客户端实例
            message_grouper.telegram_client = self.client
            
            logger.info("✅ 组消息处理器客户端初始化成功")
            
        except Exception as e:
            logger.error(f"❌ 组消息处理器客户端初始化失败: {e}")
            # 不抛出异常，避免影响系统启动
    
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
                logger.info("ℹ️ 审核群未配置，审核功能将不可用（不影响目标频道转发）")
                
        except Exception as e:
            logger.error(f"启动检查失败: {e}")
    

    async def _auto_collect_history(self):
        """自动采集频道历史消息 - 已废弃，由message_collector.py处理"""
        # 历史消息采集已由message_collector.py统一处理
        logger.info("历史消息采集已由message_collector服务处理，跳过bot_manager的采集")
        pass
    
    
    async def stop(self):
        """停止Bot"""
        self.is_running = False
        
        # 停止监控任务
        if self.monitor_task:
            self.monitor_task.cancel()
        
        # 停止事件循环任务
        if self.event_loop_task:
            self.event_loop_task.cancel()
        
        # 自动转发已由scheduler服务处理
            
        # 停止系统监控
        from app.services.system_monitor import system_monitor
        await system_monitor.stop()
        
        # 停止历史采集
        # 简化版本不需要stop_all_collections
        # 简化采集器没有复杂的collection_tasks管理
        
        # 停止媒体处理器
        from app.services.media_handler import media_handler
        await media_handler.stop()
        
        # 断开所有Session连接
        from app.telegram.dual_session_manager import dual_session_manager
        await dual_session_manager.disconnect_all()
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