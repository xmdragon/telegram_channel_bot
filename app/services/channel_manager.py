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
                         channel_title: str = "", config: Dict = None) -> bool:
        """添加频道"""
        try:
            async with AsyncSessionLocal() as db:
                # 检查频道是否已存在（同时检查channel_id和channel_name）
                existing = await db.execute(
                    select(Channel).where(
                        (Channel.channel_id == channel_id) | 
                        (Channel.channel_name == channel_name)
                    )
                )
                if existing.scalar_one_or_none():
                    logger.warning(f"频道 {channel_id} 或 {channel_name} 已存在")
                    return False
                
                # 创建新频道
                channel = Channel(
                    channel_id=channel_id,
                    channel_name=channel_name or channel_id,
                    channel_title=channel_title or channel_name or channel_id,
                    channel_type=channel_type,
                    description=description,
                    config=config or {},
                    is_active=True
                )
                
                db.add(channel)
                await db.commit()
                
                logger.info(f"频道 {channel_name} (ID: {channel_id}) 添加成功")
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
        """获取活跃的源频道ID列表，自动解析空的channel_id"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel).where(
                        Channel.channel_type == "source",
                        Channel.is_active == True
                    )
                )
                channels = result.scalars().all()
                
                resolved_channels = []
                
                for channel in channels:
                    channel_id = channel.channel_id
                    
                    # 如果channel_id为空或None，尝试解析
                    if not channel_id or channel_id.strip() == '':
                        logger.info(f"频道 {channel.channel_name} 的ID为空，正在解析...")
                        
                        # 导入解析器（避免循环导入）
                        from app.services.channel_id_resolver import channel_id_resolver
                        resolved_id = await channel_id_resolver.resolve_and_update_channel(channel.channel_name)
                        
                        if resolved_id:
                            resolved_channels.append(resolved_id)
                            logger.info(f"频道 {channel.channel_name} ID解析成功: {resolved_id}")
                        else:
                            logger.warning(f"频道 {channel.channel_name} ID解析失败")
                    else:
                        resolved_channels.append(channel_id)
                
                # 过滤掉None值
                return [ch_id for ch_id in resolved_channels if ch_id is not None]
                
        except Exception as e:
            logger.error(f"获取活跃源频道列表失败: {e}")
            return []
    
    async def resolve_missing_channel_ids(self) -> int:
        """解析所有缺失的频道ID，返回解析成功的数量"""
        try:
            resolved_count = 0
            
            # 导入解析器
            from app.services.channel_id_resolver import channel_id_resolver
            
            async with AsyncSessionLocal() as db:
                # 获取所有channel_id为空的活跃频道
                result = await db.execute(
                    select(Channel).where(
                        Channel.is_active == True,
                        (Channel.channel_id.is_(None) | (Channel.channel_id == ''))
                    )
                )
                channels = result.scalars().all()
                
                for channel in channels:
                    logger.info(f"正在解析频道 {channel.channel_name} 的ID...")
                    resolved_id = await channel_id_resolver.resolve_and_update_channel(channel.channel_name)
                    
                    if resolved_id:
                        resolved_count += 1
                        logger.info(f"频道 {channel.channel_name} ID解析成功: {resolved_id}")
                    else:
                        logger.warning(f"频道 {channel.channel_name} ID解析失败")
            
            logger.info(f"频道ID解析完成，成功解析 {resolved_count} 个频道")
            return resolved_count
            
        except Exception as e:
            logger.error(f"批量解析频道ID失败: {e}")
            return 0
    
    async def get_channel_info_for_display(self) -> Dict[str, Dict]:
        """获取用于显示的频道信息映射"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel).where(Channel.is_active == True)
                )
                channels = result.scalars().all()
                
                channel_info = {}
                for channel in channels:
                    if channel.channel_id:
                        channel_info[channel.channel_id] = {
                            'name': channel.channel_name,
                            'title': channel.channel_title or channel.channel_name,
                            'type': channel.channel_type
                        }
                
                return channel_info
                
        except Exception as e:
            logger.error(f"获取频道显示信息失败: {e}")
            return {}
    
    async def get_channel_by_name(self, channel_name: str) -> Optional[Dict]:
        """根据频道名称获取频道信息"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Channel).where(Channel.channel_name == channel_name)
                )
                channel = result.scalar_one_or_none()
                
                if not channel:
                    return None
                
                return {
                    'id': channel.id,
                    'channel_id': channel.channel_id,
                    'channel_name': channel.channel_name,
                    'channel_title': channel.channel_title,
                    'channel_type': channel.channel_type,
                    'is_active': channel.is_active,
                    'config': channel.config or {},
                    'description': channel.description,
                    'created_at': channel.created_at,
                    'updated_at': channel.updated_at
                }
                
        except Exception as e:
            logger.error(f"根据名称获取频道信息失败: {e}")
            return None

# 全局频道管理器实例
channel_manager = ChannelManager() 