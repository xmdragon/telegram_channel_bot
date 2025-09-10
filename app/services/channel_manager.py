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
            return await unified_channel_service.get_all_channels()
        except Exception as e:
            logger.error(f"获取频道列表失败: {e}")
            return []
    
    async def get_source_channels(self) -> List[Dict]:
        """获取源频道列表"""
        try:
            return await unified_channel_service.get_all_channels()
        except Exception as e:
            logger.error(f"获取源频道列表失败: {e}")
            return []
    
    async def add_channel(self, channel_id: str, channel_name: str = "",
                         description: str = "", channel_title: str = "", config: Dict = None) -> bool:
        """添加频道"""
        try:
            result = await unified_channel_service.add_channel(
                channel_name=channel_name or channel_id,
                channel_id=channel_id,
                description=description,
                resolve_title=True  # 自动解析真实标题
            )
            return result["success"]
        except Exception as e:
            logger.error(f"添加频道失败: {e}")
            return False
    
    async def delete_channel(self, channel_identifier: str) -> bool:
        """删除频道"""
        try:
            result = await unified_channel_service.delete_channel(channel_identifier)
            return result["success"]
        except Exception as e:
            logger.error(f"删除频道失败: {e}")
            return False
    
    
    async def get_channel_by_id(self, channel_id: str) -> Optional[Dict]:
        """根据ID获取频道"""
        try:
            return await unified_channel_service.get_channel(channel_id)
        except Exception as e:
            logger.error(f"获取频道失败: {e}")
            return None
    
    
    async def resolve_missing_channel_ids(self) -> int:
        """解析缺失的频道ID"""
        try:
            # 获取所有频道
            channels = await unified_channel_service.get_all_channels()
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
            channels = await unified_channel_service.get_all_channels()
            channel_info = {}
            
            for channel in channels:
                channel_id = channel.get('channel_id', '')
                username = channel.get('channel_name', '')  # 实际字段名是channel_name
                
                # 生成消息链接前缀
                link_prefix = ''
                if username:
                    # 优先使用username生成t.me链接
                    clean_username = username.lstrip('@')
                    link_prefix = f'https://t.me/{clean_username}'
                elif channel_id:
                    # 如果没有username，使用数字ID（但这种链接用户无法直接访问）
                    # 去掉-100前缀，使用c/格式
                    if channel_id.startswith('-100'):
                        numeric_id = channel_id[4:]  # 去掉-100
                        link_prefix = f'https://t.me/c/{numeric_id}'
                
                # 创建显示用的频道信息
                display_info = {
                    'id': channel_id,
                    'username': username,
                    'title': channel.get('channel_title', username),
                    'description': channel.get('description', ''),
                    'link_prefix': link_prefix,
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