"""
系统健康监控服务
实时监控系统状态、Telegram认证、频道配置等
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from app.telegram.auth import auth_manager
from app.core.config import db_settings
from app.core.database import AsyncSessionLocal, Message
from app.services.channel_manager import ChannelManager
from sqlalchemy import select

logger = logging.getLogger(__name__)

@dataclass
class SystemStatus:
    """系统状态数据结构"""
    timestamp: datetime
    telegram_auth: bool
    telegram_connected: bool
    source_channels: List[str]
    target_channels: List[str]
    review_group: Optional[str]
    errors: List[str]
    warnings: List[str]
    last_message_time: Optional[datetime]
    
class SystemMonitor:
    """系统监控器"""
    
    def __init__(self):
        self.is_running = False
        self.current_status = None
        self.status_callbacks = []
        self.check_interval = 30  # 30秒检查一次
        self.channel_manager = ChannelManager()
        
    async def start(self):
        """启动监控"""
        if self.is_running:
            return
            
        self.is_running = True
        logger.info("系统监控器启动")
        
        # 启动监控循环
        asyncio.create_task(self._monitor_loop())
        
    async def stop(self):
        """停止监控"""
        self.is_running = False
        logger.info("系统监控器停止")
        
    def add_status_callback(self, callback):
        """添加状态变化回调"""
        self.status_callbacks.append(callback)
        
    async def _monitor_loop(self):
        """监控循环"""
        while self.is_running:
            try:
                await self._check_system_status()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                await asyncio.sleep(5)  # 出错时短暂等待
                
    async def _check_system_status(self):
        """检查系统状态"""
        try:
            # 检查Telegram认证状态
            auth_status = await self._check_telegram_auth()
            
            # 检查频道配置
            channel_status = await self._check_channel_config()
            
            # 检查最近消息活动
            last_message = await self._check_last_message()
            
            # 构建状态对象
            status = SystemStatus(
                timestamp=datetime.utcnow(),
                telegram_auth=auth_status['authorized'],
                telegram_connected=auth_status['connected'],
                source_channels=channel_status['source_channels'],
                target_channels=channel_status['target_channels'],
                review_group=channel_status['review_group'],
                errors=auth_status['errors'] + channel_status['errors'],
                warnings=auth_status['warnings'] + channel_status['warnings'],
                last_message_time=last_message
            )
            
            # 更新当前状态
            self.current_status = status
            
            # 通知状态变化
            for callback in self.status_callbacks:
                try:
                    await callback(status)
                except Exception as e:
                    logger.error(f"状态回调出错: {e}")
                    
            # 记录重要状态变化
            await self._log_status_changes(status)
            
        except Exception as e:
            logger.error(f"检查系统状态出错: {e}")
            
    async def _check_telegram_auth(self) -> Dict:
        """检查Telegram认证状态"""
        errors = []
        warnings = []
        authorized = False
        connected = False
        
        try:
            # 检查认证状态
            auth_status = await auth_manager.get_auth_status()
            authorized = auth_status.get('authorized', False)
            
            # 首先检查是否有客户端实例
            if auth_manager.client:
                # 有客户端，尝试检查连接状态
                try:
                    # 尝试获取当前用户信息来测试连接
                    me = await auth_manager.client.get_me()
                    connected = True
                    authorized = True  # 能获取用户信息说明已认证
                    logger.debug(f"Telegram连接正常，用户: {me.username or me.first_name}")
                except Exception as e:
                    # 连接失败，但不一定是未认证
                    error_msg = str(e).lower()
                    if 'flood' in error_msg:
                        errors.append(f"Telegram API限流: {str(e)}")
                    elif 'network' in error_msg or 'connection' in error_msg or 'timeout' in error_msg:
                        errors.append(f"网络连接问题: {str(e)}")
                    elif 'unauthorized' in error_msg or 'auth' in error_msg:
                        errors.append("Telegram认证已失效，请重新登录")
                    else:
                        errors.append(f"Telegram连接异常: {str(e)}")
                    connected = False
            elif not authorized:
                # 既没有客户端也没有认证
                errors.append("Telegram未认证，请先完成登录")
            else:
                # 有认证状态但没有客户端实例
                errors.append("Telegram客户端未初始化")
                    
        except Exception as e:
            errors.append(f"检查Telegram认证出错: {str(e)}")
            
        return {
            'authorized': authorized,
            'connected': connected,
            'errors': errors,
            'warnings': warnings
        }
        
    async def _check_channel_config(self) -> Dict:
        """检查频道配置"""
        errors = []
        warnings = []
        source_channels = []
        target_channels = []
        review_group = None
        
        try:
            # 获取频道配置
            channels = await self.channel_manager.get_all_channels()
            
            for channel in channels:
                channel_type = channel.get('channel_type')
                channel_id = channel.get('channel_id', '')
                
                if channel_type == 'source':
                    source_channels.append(channel_id)
                elif channel_type == 'target':
                    target_channels.append(channel_id)
                elif channel_type == 'review':
                    review_group = channel_id
                    
            # 验证必要配置
            if not source_channels:
                errors.append("未配置源频道")
            if not target_channels:
                errors.append("未配置目标频道")
            if not review_group:
                warnings.append("未配置审核群")
                
            # 如果有认证，验证频道可访问性
            auth_status = await auth_manager.get_auth_status()
            if auth_manager.client and auth_status.get('authorized', False):
                await self._verify_channel_access(source_channels + target_channels + ([review_group] if review_group else []))
                
        except Exception as e:
            errors.append(f"检查频道配置出错: {str(e)}")
            
        return {
            'source_channels': source_channels,
            'target_channels': target_channels,
            'review_group': review_group,
            'errors': errors,
            'warnings': warnings
        }
        
    async def _verify_channel_access(self, channel_ids: List[str]):
        """验证频道访问权限"""
        if not auth_manager.client:
            return
            
        for channel_id in channel_ids:
            try:
                # 处理不同格式的频道ID
                if channel_id.startswith('@'):
                    # 用户名格式，直接使用
                    entity = await auth_manager.client.get_entity(channel_id)
                elif channel_id.startswith('-'):
                    # 数字ID格式，转换为整数
                    entity = await auth_manager.client.get_entity(int(channel_id))
                else:
                    # 尝试作为整数处理
                    try:
                        entity = await auth_manager.client.get_entity(int(channel_id))
                    except ValueError:
                        # 如果不是数字，尝试作为用户名处理
                        entity = await auth_manager.client.get_entity(channel_id)
                        
                logger.debug(f"频道 {channel_id} 可访问: {entity.title}")
            except Exception as e:
                logger.warning(f"频道 {channel_id} 不可访问: {e}")
                
    async def _check_last_message(self) -> Optional[datetime]:
        """检查最近消息时间"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message.created_at)
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
                last_message = result.scalar_one_or_none()
                return last_message
        except Exception as e:
            logger.error(f"检查最近消息时间出错: {e}")
            return None
            
    async def _log_status_changes(self, status: SystemStatus):
        """记录重要的状态变化"""
        # 这里可以添加状态变化的日志记录
        if status.errors:
            logger.error(f"系统错误: {', '.join(status.errors)}")
        if status.warnings:
            logger.warning(f"系统警告: {', '.join(status.warnings)}")
            
    async def get_current_status(self) -> Optional[SystemStatus]:
        """获取当前系统状态"""
        return self.current_status
        
    async def get_status_summary(self) -> Dict:
        """获取状态摘要"""
        if not self.current_status:
            return {"status": "unknown", "message": "系统监控未启动"}
            
        status = self.current_status
        
        if status.errors:
            return {
                "status": "error",
                "message": f"系统错误: {', '.join(status.errors[:3])}",
                "details": status
            }
        elif status.warnings:
            return {
                "status": "warning", 
                "message": f"系统警告: {', '.join(status.warnings[:3])}",
                "details": status
            }
        elif status.telegram_auth and status.telegram_connected and status.source_channels:
            return {
                "status": "healthy",
                "message": f"系统正常运行，监控 {len(status.source_channels)} 个源频道",
                "details": status
            }
        else:
            return {
                "status": "initializing",
                "message": "系统正在初始化",
                "details": status
            }

# 全局监控实例
system_monitor = SystemMonitor()