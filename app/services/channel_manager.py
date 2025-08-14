"""
频道管理服务 - 简化版
"""
import logging
from typing import List, Dict, Optional
from app.storage.json_store import get_json_channel_store

logger = logging.getLogger(__name__)

class ChannelManager:
    """简化版频道管理器"""
    
    def __init__(self):
        self.channel_store = None
        self._cache = {}
        self._cache_loaded = False
    
    def _get_channel_store(self):
        """延迟初始化channel_store"""
        if self.channel_store is None:
            try:
                self.channel_store = get_json_channel_store()
            except RuntimeError:
                # 如果存储层还没初始化，返回None
                return None
        return self.channel_store
    
    async def get_all_channels(self) -> List[Dict]:
        """获取所有频道"""
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return []
            channels = channel_store.get_all_channels()
            
            # 过滤活跃频道
            active_channels = [ch for ch in channels if ch.get('is_active', True)]
            
            return [
                {
                    'id': channel.get('id'),
                    'channel_id': channel.get('channel_id'),
                    'channel_name': channel.get('channel_name'),
                    'channel_type': channel.get('channel_type'),
                    'is_active': channel.get('is_active', True),
                    'config': channel.get('config', {}),
                    'description': channel.get('description', ''),
                    'created_at': channel.get('created_at'),
                    'updated_at': channel.get('updated_at')
                }
                for channel in active_channels
            ]
        except Exception as e:
            logger.error(f"获取频道列表失败: {e}")
            return []
    
    async def get_source_channels(self) -> List[Dict]:
        """获取源频道列表"""
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return []
            all_channels = channel_store.get_all_channels()
            
            # 过滤源频道且活跃的
            channels = [ch for ch in all_channels 
                       if ch.get('channel_type') == 'source' and ch.get('is_active', True)]
            
            return [
                {
                    'id': channel.get('id'),
                    'channel_id': channel.get('channel_id'),
                    'channel_name': channel.get('channel_name'),
                    'is_active': channel.get('is_active', True),
                    'config': channel.get('config', {}),
                    'description': channel.get('description', ''),
                    'created_at': channel.get('created_at'),
                    'updated_at': channel.get('updated_at')
                }
                for channel in channels
            ]
        except Exception as e:
            logger.error(f"获取源频道列表失败: {e}")
            return []
    
    async def add_channel(self, channel_id: str, channel_name: str = "", 
                         channel_type: str = "source", description: str = "",
                         channel_title: str = "", config: Dict = None) -> bool:
        """添加频道"""
        try:
            # 检查频道是否已存在
            channel_store = self._get_channel_store()
            if not channel_store:
                return False
            existing_channels = channel_store.get_all_channels()
            for ch in existing_channels:
                if (ch.get('channel_id') == channel_id or 
                    ch.get('channel_name') == channel_name):
                    logger.warning(f"频道 {channel_id} 或 {channel_name} 已存在")
                    return False
            
            # 创建新频道数据
            from datetime import datetime
            channel_data = {
                'id': len(existing_channels) + 1,
                'channel_id': channel_id,
                'channel_name': channel_name or channel_id,
                'channel_title': channel_title or channel_name or channel_id,
                'channel_type': channel_type,
                'description': description,
                'config': config or {},
                'is_active': True,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            return channel_store.add_channel(channel_data)
            
        except Exception as e:
            logger.error(f"添加频道失败: {e}")
            return False
    
    async def update_channel_status(self, channel_id: str, is_active: bool) -> bool:
        """更新频道状态"""
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return False
            channel_data = channel_store.get_channel(channel_id)
            if not channel_data:
                return False
            
            channel_data['is_active'] = is_active
            return channel_store.save_channel(channel_id, channel_data)
            
        except Exception as e:
            logger.error(f"更新频道状态失败: {e}")
            return False
    
    async def get_channel_by_id(self, channel_id: str) -> Optional[Dict]:
        """根据ID获取频道"""
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return None
            return channel_store.get_channel(channel_id)
        except Exception as e:
            logger.error(f"获取频道失败: {e}")
            return None
    
    async def get_active_source_channels(self) -> List[Dict]:
        """获取活跃的源频道列表 - config.py需要的方法"""
        return await self.get_source_channels()

# 创建全局实例
channel_manager = ChannelManager()