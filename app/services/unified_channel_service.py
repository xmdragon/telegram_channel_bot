"""
统一频道数据管理服务
提供所有频道数据操作的统一入口，确保数据一致性
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.storage.json_store import get_json_channel_store
from app.services.telegram_resolver import telegram_resolver
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
                         description: str = "", resolve_title: bool = True) -> Dict[str, Any]:
        """
        添加频道 - 统一入口
        Args:
            channel_name: 频道用户名 (如 @username)
            channel_id: 频道ID (如果为空会自动解析)
            description: 描述
            resolve_title: 是否解析真实标题
        Returns:
            操作结果 {"success": bool, "message": str, "data": dict}
        """
        try:
            # 防止目标频道被添加到源频道列表
            from app.services.config_manager import config_manager
            # 获取目标频道配置
            target_channel_id = await config_manager.get_config('target.channel_id')
            target_channel = await config_manager.get_config('target.channel_link')
            
            # 解析要添加的频道ID（如果需要）
            resolved_id = channel_id
            if not channel_id and channel_name:
                logger.info(f"解析频道ID: {channel_name}")
                resolved_id = await telegram_resolver.resolve(channel_name)
                if not resolved_id:
                    return {"success": False, "message": f"无法解析频道ID: {channel_name}", "data": None}
            
            # 检查是否为目标频道
            if (resolved_id and resolved_id == target_channel_id) or \
               (channel_name and channel_name == target_channel):
                logger.error(f"拒绝将目标频道添加到源频道列表: {channel_name} ({resolved_id})")
                return {
                    "success": False, 
                    "message": f"错误：不能将目标频道 {channel_name} 添加到源频道列表中", 
                    "data": None
                }
            
            channel_store = self._get_channel_store()
            if not channel_store:
                return {"success": False, "message": "存储服务未初始化", "data": None}
            
            # 检查频道是否已存在（使用解析后的ID）
            existing_channels = channel_store.get_all_channels()
            for ch in existing_channels:
                # 优先使用解析后的ID进行比较
                if resolved_id and ch.get('channel_id') == resolved_id:
                    # 如果ID相同但名称不同，说明频道改名了，更新名称
                    if channel_name and ch.get('channel_name') != channel_name:
                        logger.info(f"检测到频道名称变更: {ch.get('channel_name')} -> {channel_name}")
                        # 更新频道信息
                        ch['channel_name'] = channel_name
                        ch['updated_at'] = get_current_time().isoformat()
                        # 重新解析标题
                        if resolve_title:
                            try:
                                ch['channel_title'] = await self._resolve_channel_title(channel_name, resolved_id)
                            except Exception as e:
                                logger.warning(f"解析频道标题失败: {e}")
                                ch['channel_title'] = channel_name.lstrip('@') if channel_name.startswith('@') else channel_name
                        # 更新存储
                        channel_store.update_channel(ch)
                        return {"success": True, "message": "频道信息已更新", "data": ch}
                    else:
                        logger.warning(f"频道已存在（ID相同）: {channel_name} / {resolved_id}")
                        return {"success": False, "message": "频道已存在", "data": ch}
                # 如果没有解析到ID，才用名称判断
                elif not resolved_id and ch.get('channel_name') == channel_name:
                    logger.warning(f"频道已存在（名称相同）: {channel_name}")
                    return {"success": False, "message": "频道已存在", "data": ch}
            
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
                'description': description,
                'config': {},
                'created_at': get_current_time().isoformat()
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
            # 使用双Session系统获取客户端
            from app.telegram.dual_session_manager import dual_session_manager
            client = await dual_session_manager.get_listener_client()
            
            if not client:
                logger.warning("Telegram客户端未连接，无法解析频道标题")
                return channel_name.lstrip('@')
            
            # 获取频道实体信息
            entity = await client.get_entity(int(channel_id) if channel_id.lstrip('-').isdigit() else channel_name)
            
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
    
    async def get_all_channels(self) -> List[Dict[str, Any]]:
        """
        获取所有频道 - 统一入口（简化版）
        """
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                return []
            
            channels = channel_store.get_all_channels()
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
    
    async def update_channel_last_collected_id(self, channel_id: str, message_id: int) -> bool:
        """
        更新频道的最后采集消息ID
        """
        try:
            channel_store = self._get_channel_store()
            if not channel_store:
                logger.error("存储服务未初始化")
                return False
            
            # 查找频道
            channel_data = await self._find_channel(channel_id)
            if not channel_data:
                logger.error(f"未找到频道: {channel_id}")
                return False
            
            # 更新last_collected_message_id
            channel_data['last_collected_message_id'] = message_id
            
            # 保存更新
            success = channel_store.update_channel(channel_data)
            if success:
                logger.debug(f"成功更新频道 {channel_id} 的最后采集消息ID: {message_id}")
            else:
                logger.error(f"更新频道 {channel_id} 的最后采集消息ID失败")
            
            return success
            
        except Exception as e:
            logger.error(f"更新频道最后采集消息ID失败: {e}")
            return False

# 全局实例
unified_channel_service = UnifiedChannelService()