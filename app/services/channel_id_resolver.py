"""
频道ID解析服务
自动解析频道用户名或链接获取真实的频道ID
"""
import re
import logging
from typing import Optional, Union
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.telegram.auth import auth_manager
from app.core.database import AsyncSessionLocal, Channel

logger = logging.getLogger(__name__)

class ChannelIdResolver:
    """频道ID解析器"""
    
    def __init__(self):
        self.username_pattern = re.compile(r'^@?([A-Za-z0-9_]+)$')
        self.link_pattern = re.compile(r'https://t\.me/([A-Za-z0-9_]+)')
    
    def parse_channel_input(self, channel_input: str) -> dict:
        """解析频道输入（用户名或链接）"""
        channel_input = channel_input.strip()
        
        # 检查是否是链接
        link_match = self.link_pattern.match(channel_input)
        if link_match:
            return {
                'type': 'link',
                'username': link_match.group(1),
                'original': channel_input
            }
        
        # 检查是否是用户名
        username_match = self.username_pattern.match(channel_input)
        if username_match:
            return {
                'type': 'username',
                'username': username_match.group(1),
                'original': channel_input
            }
        
        # 检查是否已经是数字ID
        if channel_input.lstrip('-').isdigit():
            return {
                'type': 'id',
                'channel_id': channel_input,
                'original': channel_input
            }
        
        return {
            'type': 'unknown',
            'original': channel_input
        }
    
    async def resolve_channel_id(self, channel_input: str) -> Optional[str]:
        """
        解析频道输入获取真实的频道ID
        支持用户名、链接和已有ID
        """
        try:
            if not auth_manager.client:
                logger.error("Telegram客户端未连接")
                return None
            
            parsed = self.parse_channel_input(channel_input)
            
            # 如果已经是ID，直接返回
            if parsed['type'] == 'id':
                return parsed['channel_id']
            
            # 如果是用户名或链接，解析获取ID
            if parsed['type'] in ['username', 'link']:
                username = parsed['username']
                try:
                    # 使用Telethon获取实体信息
                    entity = await auth_manager.client.get_entity(username)
                    
                    if hasattr(entity, 'id'):
                        channel_id = entity.id
                        # 频道ID通常需要加上-100前缀
                        if hasattr(entity, 'broadcast') and entity.broadcast:
                            # 这是一个频道
                            return str(channel_id) if str(channel_id).startswith('-100') else f"-100{channel_id}"
                        elif hasattr(entity, 'megagroup') and entity.megagroup:
                            # 这是一个超级群组
                            return str(channel_id) if str(channel_id).startswith('-100') else f"-100{channel_id}"
                        else:
                            # 普通群组或用户
                            return str(-channel_id if channel_id > 0 else channel_id)
                    
                except Exception as e:
                    logger.error(f"解析频道 {username} 失败: {e}")
                    return None
            
            logger.warning(f"无法解析频道输入: {channel_input}")
            return None
            
        except Exception as e:
            logger.error(f"解析频道ID时出错: {e}")
            return None
    
    async def update_channel_id(self, channel_name: str, resolved_id: str) -> bool:
        """更新数据库中的频道ID"""
        try:
            async with AsyncSessionLocal() as db:
                # 查找频道记录
                result = await db.execute(
                    select(Channel).where(Channel.channel_name == channel_name)
                )
                channel = result.scalar_one_or_none()
                
                if channel:
                    # 更新频道ID
                    channel.channel_id = resolved_id
                    await db.commit()
                    logger.info(f"已更新频道 {channel_name} 的ID为: {resolved_id}")
                    return True
                else:
                    logger.error(f"未找到频道记录: {channel_name}")
                    return False
                    
        except Exception as e:
            logger.error(f"更新频道ID失败: {e}")
            return False
    
    async def resolve_and_update_channel(self, channel_name: str) -> Optional[str]:
        """
        解析并更新频道ID
        返回解析后的频道ID
        """
        try:
            # 解析频道ID
            resolved_id = await self.resolve_channel_id(channel_name)
            
            if resolved_id:
                # 更新数据库记录
                success = await self.update_channel_id(channel_name, resolved_id)
                if success:
                    logger.info(f"频道 {channel_name} ID解析成功: {resolved_id}")
                    return resolved_id
                else:
                    logger.error(f"频道 {channel_name} ID更新失败")
                    return None
            else:
                logger.error(f"频道 {channel_name} ID解析失败")
                return None
                
        except Exception as e:
            logger.error(f"解析并更新频道ID时出错: {e}")
            return None
    
    async def ensure_channel_ids_resolved(self) -> list:
        """
        确保所有频道都有解析的ID
        返回解析成功的频道列表
        """
        try:
            resolved_channels = []
            
            async with AsyncSessionLocal() as db:
                # 获取所有活跃的源频道
                result = await db.execute(
                    select(Channel).where(
                        Channel.channel_type == 'source',
                        Channel.is_active == True
                    )
                )
                channels = result.scalars().all()
                
                for channel in channels:
                    # 检查是否需要解析ID
                    if not channel.channel_id or channel.channel_id.strip() == '':
                        logger.info(f"正在解析频道 {channel.channel_name} 的ID...")
                        resolved_id = await self.resolve_and_update_channel(channel.channel_name)
                        
                        if resolved_id:
                            resolved_channels.append({
                                'name': channel.channel_name,
                                'id': resolved_id,
                                'title': channel.channel_title
                            })
                    else:
                        # 已有ID，直接添加到列表
                        resolved_channels.append({
                            'name': channel.channel_name,
                            'id': channel.channel_id,
                            'title': channel.channel_title
                        })
            
            logger.info(f"频道ID解析完成，共 {len(resolved_channels)} 个频道")
            return resolved_channels
            
        except Exception as e:
            logger.error(f"批量解析频道ID时出错: {e}")
            return []
    
    async def get_channel_info(self, channel_id_or_name: str) -> Optional[dict]:
        """获取频道详细信息"""
        try:
            if not auth_manager.client:
                logger.error("Telegram客户端未连接")
                return None
            
            entity = await auth_manager.client.get_entity(channel_id_or_name)
            
            if entity:
                return {
                    'id': str(entity.id),
                    'title': getattr(entity, 'title', ''),
                    'username': getattr(entity, 'username', ''),
                    'participants_count': getattr(entity, 'participants_count', 0),
                    'type': 'channel' if getattr(entity, 'broadcast', False) else 'group'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"获取频道信息失败: {e}")
            return None

# 全局频道ID解析器实例
channel_id_resolver = ChannelIdResolver()