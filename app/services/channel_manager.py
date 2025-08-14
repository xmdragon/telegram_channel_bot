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

# 创建全局实例
channel_manager = ChannelManager()