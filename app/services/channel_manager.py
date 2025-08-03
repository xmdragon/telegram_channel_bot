"""
频道管理服务
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, Channel

logger = logging.getLogger(__name__)

class ChannelManager:
    """频道管理器"""
    
    def __init__(self):
        self._cache = {}
        self._cache_loaded = False
    
    async def get_all_channels(self) -> List[Dict]:
        """获取所有频道"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel).where(Channel.is_active == True)
                )
                channels = result.scalars().all()
                
                return [
                    {
                        'id': channel.id,
                        'channel_id': channel.channel_id,
                        'channel_name': channel.channel_name,
                        'channel_type': channel.channel_type,
                        'is_active': channel.is_active,
                        'config': channel.config or {},
                        'description': channel.description,
                        'created_at': channel.created_at,
                        'updated_at': channel.updated_at
                    }
                    for channel in channels
                ]
        except Exception as e:
            logger.error(f"获取频道列表失败: {e}")
            return []
    
    async def get_source_channels(self) -> List[Dict]:
        """获取源频道列表"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel).where(
                        Channel.channel_type == "source",
                        Channel.is_active == True
                    )
                )
                channels = result.scalars().all()
                
                return [
                    {
                        'id': channel.id,
                        'channel_id': channel.channel_id,
                        'channel_name': channel.channel_name,
                        'is_active': channel.is_active,
                        'config': channel.config or {},
                        'description': channel.description,
                        'created_at': channel.created_at,
                        'updated_at': channel.updated_at
                    }
                    for channel in channels
                ]
        except Exception as e:
            logger.error(f"获取源频道列表失败: {e}")
            return []
    
    async def add_channel(self, channel_id: str, channel_name: str = "", 
                         channel_type: str = "source", description: str = "",
                         config: Dict = None) -> bool:
        """添加频道"""
        try:
            async with AsyncSessionLocal() as db:
                # 检查频道是否已存在
                existing = await db.execute(
                    select(Channel).where(Channel.channel_id == channel_id)
                )
                if existing.scalar_one_or_none():
                    logger.warning(f"频道 {channel_id} 已存在")
                    return False
                
                # 创建新频道
                channel = Channel(
                    channel_id=channel_id,
                    channel_name=channel_name or channel_id,
                    channel_type=channel_type,
                    description=description,
                    config=config or {},
                    is_active=True
                )
                
                db.add(channel)
                await db.commit()
                
                logger.info(f"频道 {channel_id} 添加成功")
                return True
                
        except Exception as e:
            logger.error(f"添加频道失败: {e}")
            return False
    
    async def update_channel(self, channel_id: str, **kwargs) -> bool:
        """更新频道信息"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel).where(Channel.channel_id == channel_id)
                )
                channel = result.scalar_one_or_none()
                
                if not channel:
                    logger.warning(f"频道 {channel_id} 不存在")
                    return False
                
                # 更新字段
                for key, value in kwargs.items():
                    if hasattr(channel, key):
                        setattr(channel, key, value)
                
                await db.commit()
                
                logger.info(f"频道 {channel_id} 更新成功")
                return True
                
        except Exception as e:
            logger.error(f"更新频道失败: {e}")
            return False
    
    async def delete_channel(self, channel_id: str) -> bool:
        """删除频道"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel).where(Channel.channel_id == channel_id)
                )
                channel = result.scalar_one_or_none()
                
                if not channel:
                    logger.warning(f"频道 {channel_id} 不存在")
                    return False
                
                await db.delete(channel)
                await db.commit()
                
                logger.info(f"频道 {channel_id} 删除成功")
                return True
                
        except Exception as e:
            logger.error(f"删除频道失败: {e}")
            return False
    
    async def toggle_channel_status(self, channel_id: str) -> bool:
        """切换频道状态"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel).where(Channel.channel_id == channel_id)
                )
                channel = result.scalar_one_or_none()
                
                if not channel:
                    logger.warning(f"频道 {channel_id} 不存在")
                    return False
                
                channel.is_active = not channel.is_active
                await db.commit()
                
                logger.info(f"频道 {channel_id} 状态切换为: {channel.is_active}")
                return True
                
        except Exception as e:
            logger.error(f"切换频道状态失败: {e}")
            return False
    
    async def get_channel_by_id(self, channel_id: str) -> Optional[Dict]:
        """根据频道ID获取频道信息"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel).where(Channel.channel_id == channel_id)
                )
                channel = result.scalar_one_or_none()
                
                if not channel:
                    return None
                
                return {
                    'id': channel.id,
                    'channel_id': channel.channel_id,
                    'channel_name': channel.channel_name,
                    'channel_type': channel.channel_type,
                    'is_active': channel.is_active,
                    'config': channel.config or {},
                    'description': channel.description,
                    'created_at': channel.created_at,
                    'updated_at': channel.updated_at
                }
                
        except Exception as e:
            logger.error(f"获取频道信息失败: {e}")
            return None
    
    async def get_active_source_channels(self) -> List[str]:
        """获取活跃的源频道ID列表"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel.channel_id).where(
                        Channel.channel_type == "source",
                        Channel.is_active == True
                    )
                )
                channels = result.scalars().all()
                return list(channels)
                
        except Exception as e:
            logger.error(f"获取活跃源频道列表失败: {e}")
            return []

# 全局频道管理器实例
channel_manager = ChannelManager() 