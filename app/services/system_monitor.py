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
from app.services.channel_manager import ChannelManager
from app.storage.redis_store import get_redis_message_store, get_redis_store
from app.storage.json_store import get_json_channel_store

logger = logging.getLogger(__name__)

@dataclass
class SystemStatus:
    """系统状态数据结构"""
    timestamp: datetime
    telegram_auth: bool
    telegram_connected: bool
    source_channels: List[str]
    target_channel: str
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
        self._stats_cache = {}
        self._cache_time = None
        self.last_auth_error_logged = False  # 记录是否已经记录过认证错误
        
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
                target_channel=channel_status['target_channel'],
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
        target_channel = None
        review_group = None
        
        try:
            # 获取频道配置（源频道从channels表）
            channels = await self.channel_manager.get_all_channels()
            
            for channel in channels:
                channel_type = channel.get('channel_type')
                channel_id = channel.get('channel_id', '')
                
                if channel_type == 'source':
                    source_channels.append(channel_id)
            
            # 获取目标频道和审核群配置（从系统配置表）
            from app.services.config_manager import config_manager
            
            # 优先使用缓存的ID（针对私有链接）
            target_channel_id = await config_manager.get_config('channels.target_channel_id_cached')
            if not target_channel_id:
                target_channel_id = await config_manager.get_config('target.channel_id')
            
            review_group_id = await config_manager.get_config('channels.review_group_id_cached')
            if not review_group_id:
                review_group_id = await config_manager.get_config('review.group_id')
            
            # 获取显示用的原始配置
            target_channel = await config_manager.get_config('target.channel_link')
            review_group = await config_manager.get_config('review.group_link')
                    
            # 验证必要配置
            if not source_channels:
                errors.append("未配置源频道")
            if not target_channel_id:
                if target_channel:
                    errors.append(f"目标频道 {target_channel} 未解析ID，请重启应用")
                else:
                    errors.append("未配置目标频道")
            if not review_group_id:
                if review_group:
                    warnings.append(f"审核群 {review_group} 未解析ID")
                else:
                    warnings.append("未配置审核群")
                
            # 验证频道可访问性（只验证ID，不验证私有链接）
            auth_status = await auth_manager.get_auth_status()
            if auth_manager.client and auth_status.get('authorized', False):
                channels_to_verify = source_channels.copy()
                
                # 只添加已解析的ID进行验证
                if target_channel_id and target_channel_id.startswith('-100'):
                    channels_to_verify.append(target_channel_id)
                if review_group_id and review_group_id.startswith('-100'):
                    channels_to_verify.append(review_group_id)
                
                await self._verify_channel_access(channels_to_verify)
                
        except Exception as e:
            errors.append(f"检查频道配置出错: {str(e)}")
            
        return {
            'source_channels': source_channels,
            'target_channel': target_channel,
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
                if channel_id.startswith('https://t.me/+') or channel_id.startswith('t.me/+'):
                    # 私有邀请链接格式，需要特殊处理
                    # 这种链接只能通过加入来验证，不能直接get_entity
                    # 为了避免意外加入群组，我们跳过这种链接的验证
                    logger.debug(f"跳过私有邀请链接验证: {channel_id}")
                    continue
                elif channel_id.startswith('@'):
                    # 用户名格式，直接使用
                    entity = await auth_manager.client.get_entity(channel_id)
                elif channel_id.startswith('-'):
                    # 数字ID格式，转换为整数
                    entity = await auth_manager.client.get_entity(int(channel_id))
                elif channel_id.startswith('https://t.me/'):
                    # 公开链接格式，提取用户名部分
                    username = channel_id.replace('https://t.me/', '')
                    if not username.startswith('+'):  # 确保不是私有链接
                        entity = await auth_manager.client.get_entity(username)
                    else:
                        logger.debug(f"跳过私有链接验证: {channel_id}")
                        continue
                elif channel_id.startswith('t.me/'):
                    # t.me链接格式，提取用户名部分
                    username = channel_id.replace('t.me/', '')
                    if not username.startswith('+'):  # 确保不是私有链接
                        entity = await auth_manager.client.get_entity(username)
                    else:
                        logger.debug(f"跳过私有链接验证: {channel_id}")
                        continue
                else:
                    # 尝试作为整数处理
                    try:
                        entity = await auth_manager.client.get_entity(int(channel_id))
                    except ValueError:
                        # 如果不是数字，尝试作为用户名处理
                        entity = await auth_manager.client.get_entity(channel_id)
                        
                logger.debug(f"频道 {channel_id} 可访问: {entity.title}")
            except Exception as e:
                # 对于私有邀请链接，不记录为错误，因为无法直接验证
                if 'https://t.me/+' in channel_id or 't.me/+' in channel_id:
                    logger.debug(f"私有邀请链接无法验证访问性: {channel_id}")
                else:
                    logger.warning(f"频道 {channel_id} 不可访问: {e}")
                
    async def _check_last_message(self) -> Optional[datetime]:
        """检查最近消息时间"""
        try:
            redis_store = get_redis_message_store()
            # 获取最近的消息
            recent_messages = redis_store.get_all_messages(limit=1)
            if recent_messages:
                last_message_time = recent_messages[0].get('created_at')
                if last_message_time:
                    return datetime.fromisoformat(last_message_time.replace('Z', '+00:00'))
            return None
        except Exception as e:
            logger.error(f"检查最近消息时间出错: {e}")
            return None
    
    async def get_system_stats(self) -> Dict:
        """获取系统统计信息"""
        try:
            # 使用缓存减少Redis查询频率
            now = datetime.utcnow()
            if (self._cache_time is None or 
                (now - self._cache_time).seconds > 60):  # 1分钟缓存
                
                redis_store = get_redis_message_store()
                
                # 获取各状态消息统计
                stats = {
                    'total_messages': redis_store.get_message_count(),
                    'pending_messages': redis_store.get_message_count(status='pending'),
                    'approved_messages': redis_store.get_message_count(status='approved'),
                    'rejected_messages': redis_store.get_message_count(status='rejected'),
                    'auto_forwarded_messages': redis_store.get_message_count(status='auto_forwarded'),
                    'timestamp': now.isoformat()
                }
                
                # 获取频道统计
                try:
                    channel_store = get_json_channel_store()
                    source_channels = channel_store.get_channels_by_type('source')
                    stats['source_channels_count'] = len(source_channels)
                except Exception as e:
                    logger.warning(f"获取频道统计失败: {e}")
                    stats['source_channels_count'] = 0
                
                self._stats_cache = stats
                self._cache_time = now
            
            return self._stats_cache
            
        except Exception as e:
            logger.error(f"获取系统统计信息失败: {e}")
            return {
                'total_messages': 0,
                'pending_messages': 0,
                'approved_messages': 0, 
                'rejected_messages': 0,
                'auto_forwarded_messages': 0,
                'source_channels_count': 0,
                'timestamp': datetime.utcnow().isoformat()
            }
            
    async def _log_status_changes(self, status: SystemStatus):
        """记录重要的状态变化"""
        # 对于Telegram未认证的情况，只记录一次
        auth_error_msgs = ["Telegram未认证，请先完成登录", "Telegram认证已失效，请重新登录", "Telegram客户端未初始化"]
        has_auth_error = any(msg in status.errors for msg in auth_error_msgs)
        
        if status.errors:
            # 过滤出非认证相关的错误
            non_auth_errors = [e for e in status.errors if e not in auth_error_msgs]
            
            if has_auth_error:
                if not self.last_auth_error_logged:
                    # 第一次出现认证错误，记录为警告而非错误
                    logger.warning(f"系统需要认证: {next(e for e in status.errors if e in auth_error_msgs)}")
                    self.last_auth_error_logged = True
                # 后续不再重复记录认证错误
            else:
                # 认证成功，重置标志
                self.last_auth_error_logged = False
                
            # 记录其他非认证相关的错误
            if non_auth_errors:
                logger.error(f"系统错误: {', '.join(non_auth_errors)}")
                
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
        
        # 添加系统统计信息
        try:
            stats = await self.get_system_stats()
            status_dict = {
                "timestamp": status.timestamp.isoformat() if status.timestamp else None,
                "telegram_auth": status.telegram_auth,
                "telegram_connected": status.telegram_connected,
                "source_channels": status.source_channels,
                "target_channel": status.target_channel,
                "review_group": status.review_group,
                "errors": status.errors,
                "warnings": status.warnings,
                "last_message_time": status.last_message_time.isoformat() if status.last_message_time else None,
                "stats": stats
            }
        except Exception as e:
            logger.warning(f"获取统计信息失败: {e}")
            status_dict = {
                "timestamp": status.timestamp.isoformat() if status.timestamp else None,
                "telegram_auth": status.telegram_auth,
                "telegram_connected": status.telegram_connected,
                "source_channels": status.source_channels,
                "target_channel": status.target_channel,
                "review_group": status.review_group,
                "errors": status.errors,
                "warnings": status.warnings,
                "last_message_time": status.last_message_time.isoformat() if status.last_message_time else None
            }
        
        if status.errors:
            return {
                "status": "error",
                "message": f"系统错误: {', '.join(status.errors[:3])}",
                "details": status_dict
            }
        elif status.warnings:
            return {
                "status": "warning", 
                "message": f"系统警告: {', '.join(status.warnings[:3])}",
                "details": status_dict
            }
        elif status.telegram_auth and status.telegram_connected and status.source_channels:
            return {
                "status": "healthy",
                "message": f"系统正常运行，监控 {len(status.source_channels)} 个源频道",
                "details": status_dict
            }
        else:
            return {
                "status": "initializing",
                "message": "系统正在初始化",
                "details": status_dict
            }

# 全局监控实例
system_monitor = SystemMonitor()