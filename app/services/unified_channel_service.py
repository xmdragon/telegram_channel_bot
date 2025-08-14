"""
统一频道数据管理服务
提供所有频道数据操作的统一入口，确保数据一致性
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.storage.json_store import get_json_channel_store
from app.services.channel_id_resolver import channel_id_resolver
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class UnifiedChannelService:
    """统一频道数据管理服务"""
    
    def __init__(self):
        self._channel_store = None
    
    def _get_channel_store(self):
        """延迟获取存储实例"""
        if self._channel_store is None:
            try:
                self._channel_store = get_json_channel_store()
            except RuntimeError:
                logger.error("JSON存储层未初始化")
                return None
        return self._channel_store
    
    async def add_channel(self, channel_name: str, channel_id: str = "", 
                         channel_type: str = "source", description: str = "",
                         resolve_title: bool = True) -> Dict[str, Any]:
        """
        添加频道 - 统一入口
        Args:
            channel_name: 频道用户名 (如 @username)
            channel_id: 频道ID (如果为空会自动解析)
            channel_type: 频道类型
            description: 描述
            resolve_title: 是否解析真实标题
        Returns:
            操作结果 {"success": bool, "message": str, "data": dict}
        """
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return {"success": False, "message": "存储服务未初始化", "data": None}
            
            # 检查频道是否已存在
            existing_channels = channel_store.get_all_channels()
            for ch in existing_channels:
                if (ch.get('channel_id') == channel_id and channel_id) or \
                   (ch.get('channel_name') == channel_name):
                    logger.warning(f"频道已存在: {channel_name} / {channel_id}")
                    return {"success": False, "message": "频道已存在", "data": ch}
            
            # 如果没有提供channel_id，尝试解析
            resolved_id = channel_id
            if not channel_id:
                logger.info(f"解析频道ID: {channel_name}")
                resolved_id = await channel_id_resolver.resolve_channel_id(channel_name)
                if not resolved_id:
                    return {"success": False, "message": f"无法解析频道ID: {channel_name}", "data": None}
            
            # 解析真实频道标题
            channel_title = ""
            if resolve_title:
                try:
                    channel_title = await self._resolve_channel_title(channel_name, resolved_id)
                except Exception as e:
                    logger.warning(f"解析频道标题失败: {e}")
                    # 如果解析失败，使用用户名作为fallback
                    channel_title = channel_name.lstrip('@') if channel_name.startswith('@') else channel_name
            else:
                channel_title = channel_name.lstrip('@') if channel_name.startswith('@') else channel_name
            
            # 生成新的ID
            existing_ids = [ch.get('id', 0) for ch in existing_channels if ch.get('id')]
            new_id = max(existing_ids, default=0) + 1
            
            # 创建频道数据
            channel_data = {
                'id': new_id,
                'channel_name': channel_name,
                'channel_id': resolved_id,
                'channel_title': channel_title,  # 存储真实标题
                'channel_type': channel_type,
                'description': description,
                'is_active': True,
                'config': {},
                'created_at': get_current_time().isoformat(),
                'updated_at': get_current_time().isoformat()
            }
            
            # 保存到存储
            success = channel_store.add_channel(channel_data)
            if success:
                logger.info(f"成功添加频道: {channel_name} -> {resolved_id} ({channel_title})")
                return {"success": True, "message": "频道添加成功", "data": channel_data}
            else:
                return {"success": False, "message": "保存频道数据失败", "data": None}
                
        except Exception as e:
            logger.error(f"添加频道失败: {e}")
            return {"success": False, "message": f"添加频道失败: {str(e)}", "data": None}
    
    async def _resolve_channel_title(self, channel_name: str, channel_id: str) -> str:
        """
        解析频道的真实标题
        """
        try:
            # 尝试通过Telegram客户端获取频道信息
            from app.telegram.auth import auth_manager
            if not auth_manager.client:
                logger.warning("Telegram客户端未连接，无法解析频道标题")
                return channel_name.lstrip('@')
            
            # 获取频道实体信息
            entity = await auth_manager.client.get_entity(int(channel_id) if channel_id.lstrip('-').isdigit() else channel_name)
            
            # 返回频道标题
            if hasattr(entity, 'title') and entity.title:
                return entity.title
            elif hasattr(entity, 'username') and entity.username:
                return f"@{entity.username}"
            else:
                return channel_name.lstrip('@')
                
        except Exception as e:
            logger.debug(f"解析频道标题失败 {channel_name}: {e}")
            return channel_name.lstrip('@')
    
    async def update_channel(self, channel_identifier: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新频道信息 - 统一入口
        Args:
            channel_identifier: 频道标识符(ID、用户名或数字ID)
            updates: 要更新的字段
        """
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return {"success": False, "message": "存储服务未初始化", "data": None}
            
            # 查找频道
            channel_data = await self._find_channel(channel_identifier)
            if not channel_data:
                return {"success": False, "message": "频道不存在", "data": None}
            
            # 更新数据
            channel_data.update(updates)
            channel_data['updated_at'] = get_current_time().isoformat()
            
            # 保存更新
            success = channel_store.update_channel(channel_data)
            if success:
                logger.info(f"成功更新频道: {channel_identifier}")
                return {"success": True, "message": "频道更新成功", "data": channel_data}
            else:
                return {"success": False, "message": "保存频道更新失败", "data": None}
                
        except Exception as e:
            logger.error(f"更新频道失败: {e}")
            return {"success": False, "message": f"更新频道失败: {str(e)}", "data": None}
    
    async def get_channel(self, channel_identifier: str) -> Optional[Dict[str, Any]]:
        """
        获取单个频道信息 - 统一入口
        """
        try:
            return await self._find_channel(channel_identifier)
        except Exception as e:
            logger.error(f"获取频道失败: {e}")
            return None
    
    async def get_all_channels(self, channel_type: str = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        获取所有频道 - 统一入口
        """
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return []
            
            if channel_type:
                channels = channel_store.get_channels_by_type(channel_type)
            else:
                channels = channel_store.get_all_channels()
            
            # 过滤活跃频道
            if active_only:
                channels = [ch for ch in channels if ch.get('is_active', True)]
            
            return channels
            
        except Exception as e:
            logger.error(f"获取频道列表失败: {e}")
            return []
    
    async def delete_channel(self, channel_identifier: str) -> Dict[str, Any]:
        """
        删除频道 - 统一入口
        """
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return {"success": False, "message": "存储服务未初始化", "data": None}
            
            # 查找频道确认存在
            channel_data = await self._find_channel(channel_identifier)
            if not channel_data:
                return {"success": False, "message": "频道不存在", "data": None}
            
            # 执行删除
            success = channel_store.delete_channel(channel_identifier)
            if success:
                logger.info(f"成功删除频道: {channel_identifier}")
                return {"success": True, "message": "频道删除成功", "data": channel_data}
            else:
                return {"success": False, "message": "删除频道失败", "data": None}
                
        except Exception as e:
            logger.error(f"删除频道失败: {e}")
            return {"success": False, "message": f"删除频道失败: {str(e)}", "data": None}
    
    async def _find_channel(self, channel_identifier: str) -> Optional[Dict[str, Any]]:
        """
        通过各种标识符查找频道
        """
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return None
            
            all_channels = channel_store.get_all_channels()
            
            # 尝试各种匹配方式
            for channel in all_channels:
                # 按ID匹配
                if str(channel.get('id', '')) == str(channel_identifier):
                    return channel
                # 按channel_id匹配
                if channel.get('channel_id') == channel_identifier:
                    return channel
                # 按channel_name匹配
                if channel.get('channel_name') == channel_identifier:
                    return channel
                # 按用户名匹配(带@或不带@)
                name = channel.get('channel_name', '')
                if name == f"@{channel_identifier}" or name.lstrip('@') == channel_identifier.lstrip('@'):
                    return channel
            
            return None
            
        except Exception as e:
            logger.error(f"查找频道失败: {e}")
            return None
    
    async def refresh_channel_titles(self) -> Dict[str, Any]:
        """
        刷新所有频道的真实标题
        """
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return {"success": False, "message": "存储服务未初始化", "updated": 0}
            
            all_channels = channel_store.get_all_channels()
            updated_count = 0
            
            for channel in all_channels:
                try:
                    channel_name = channel.get('channel_name', '')
                    channel_id = channel.get('channel_id', '')
                    
                    if not channel_id:
                        continue
                    
                    # 解析真实标题
                    real_title = await self._resolve_channel_title(channel_name, channel_id)
                    old_title = channel.get('channel_title', '')
                    
                    # 如果标题不同，更新它
                    if real_title != old_title:
                        channel['channel_title'] = real_title
                        channel['updated_at'] = get_current_time().isoformat()
                        
                        # 保存更新
                        if channel_store.update_channel(channel):
                            updated_count += 1
                            logger.info(f"更新频道标题: {channel_name} -> {real_title}")
                        
                except Exception as e:
                    logger.warning(f"更新频道标题失败 {channel.get('channel_name', '')}: {e}")
                    continue
            
            return {
                "success": True, 
                "message": f"成功更新 {updated_count} 个频道标题", 
                "updated": updated_count,
                "total": len(all_channels)
            }
            
        except Exception as e:
            logger.error(f"刷新频道标题失败: {e}")
            return {"success": False, "message": f"刷新失败: {str(e)}", "updated": 0}

# 全局实例
unified_channel_service = UnifiedChannelService()