"""
频道管理服务 - 简化版（使用统一服务）
"""
import logging
from typing import List, Dict, Optional
from app.services.unified_channel_service import unified_channel_service

logger = logging.getLogger(__name__)

class ChannelManager:
    """简化版频道管理器（代理到统一服务）"""
    
    def __init__(self):
        # 保持向后兼容的属性
        self.channel_store = None
        self._cache = {}
        self._cache_loaded = False
    
    async def get_all_channels(self) -> List[Dict]:
        """获取所有频道"""
        try:
            return await unified_channel_service.get_all_channels(active_only=True)
        except Exception as e:
            logger.error(f"获取频道列表失败: {e}")
            return []
    
    async def get_source_channels(self) -> List[Dict]:
        """获取源频道列表"""
        try:
            return await unified_channel_service.get_all_channels(channel_type="source", active_only=True)
        except Exception as e:
            logger.error(f"获取源频道列表失败: {e}")
            return []
    
    async def add_channel(self, channel_id: str, channel_name: str = "", 
                         channel_type: str = "source", description: str = "",
                         channel_title: str = "", config: Dict = None) -> bool:
        """添加频道"""
        try:
            result = await unified_channel_service.add_channel(
                channel_name=channel_name or channel_id,
                channel_id=channel_id,
                channel_type=channel_type,
                description=description,
                resolve_title=True  # 自动解析真实标题
            )
            return result["success"]
        except Exception as e:
            logger.error(f"添加频道失败: {e}")
            return False
    
    async def update_channel_status(self, channel_id: str, is_active: bool) -> bool:
        """更新频道状态"""
        try:
            result = await unified_channel_service.update_channel(
                channel_id, 
                {"is_active": is_active}
            )
            return result["success"]
        except Exception as e:
            logger.error(f"更新频道状态失败: {e}")
            return False
    
    async def get_channel_by_id(self, channel_id: str) -> Optional[Dict]:
        """根据ID获取频道"""
        try:
            return await unified_channel_service.get_channel(channel_id)
        except Exception as e:
            logger.error(f"获取频道失败: {e}")
            return None
    
    async def get_active_source_channels(self) -> List[Dict]:
        """获取活跃的源频道列表 - config.py需要的方法"""
        return await self.get_source_channels()
    
    async def resolve_missing_channel_ids(self) -> int:
        """解析缺失的频道ID"""
        try:
            # 获取所有频道
            channels = await unified_channel_service.get_all_channels(active_only=False)
            resolved_count = 0
            
            from app.services.channel_id_resolver import channel_id_resolver
            
            for channel in channels:
                channel_id = channel.get('channel_id')
                channel_name = channel.get('channel_name')
                
                # 如果没有ID或ID无效，尝试解析
                if not channel_id or not channel_id.startswith('-100'):
                    if channel_name:
                        try:
                            resolved_id = await channel_id_resolver.resolve_channel_id(channel_name)
                            if resolved_id and resolved_id.startswith('-100'):
                                # 更新频道ID
                                update_result = await unified_channel_service.update_channel(
                                    str(channel.get('id')), 
                                    {'channel_id': resolved_id}
                                )
                                if update_result['success']:
                                    resolved_count += 1
                                    logger.info(f"成功解析频道ID: {channel_name} -> {resolved_id}")
                        except Exception as e:
                            logger.warning(f"解析频道ID失败 {channel_name}: {e}")
            
            return resolved_count
        except Exception as e:
            logger.error(f"批量解析频道ID失败: {e}")
            return 0
    
    async def get_channel_info_for_display(self) -> Dict[str, Dict]:
        """获取用于前端显示的频道信息映射"""
        try:
            channels = await unified_channel_service.get_all_channels(active_only=False)
            channel_info = {}
            
            for channel in channels:
                channel_id = channel.get('channel_id', '')
                username = channel.get('username', '')
                
                # 创建显示用的频道信息
                display_info = {
                    'id': channel_id,
                    'username': username,
                    'title': channel.get('title', username),
                    'type': channel.get('type', 'source'),
                    'description': channel.get('description', ''),
                    'active': channel.get('active', True),
                    'last_collected_id': channel.get('last_collected_id'),
                    'created_at': channel.get('created_at', ''),
                    'updated_at': channel.get('updated_at', '')
                }
                
                # 使用channel_id作为主键，username作为备选键
                if channel_id:
                    channel_info[channel_id] = display_info
                if username:
                    channel_info[username] = display_info
                    # 如果username不是以@开头，也加上@版本
                    if not username.startswith('@'):
                        channel_info[f'@{username}'] = display_info
                    else:
                        # 如果是@开头，也加上去掉@的版本
                        channel_info[username[1:]] = display_info
            
            return channel_info
        except Exception as e:
            logger.error(f"获取频道显示信息失败: {e}")
            return {}

# 创建全局实例
channel_manager = ChannelManager()