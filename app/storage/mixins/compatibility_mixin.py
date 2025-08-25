"""
消息向后兼容Mixin
提供向后兼容的API方法，确保现有代码无需修改
"""
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class MessageCompatibilityMixin:
    """向后兼容功能"""
    
    def get_message_by_id(self, message_key: str) -> Optional[Dict[str, Any]]:
        """
        兼容方法：根据消息键获取消息
        支持格式：channel_id:message_id 或 msg:channel_id:message_id
        """
        try:
            # 处理不同格式的message_key
            if message_key.startswith('msg:'):
                # 格式: msg:channel_id:message_id
                parts = message_key.split(':', 2)
                if len(parts) >= 3:
                    channel_id, message_id = parts[1], parts[2]
                else:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return None
            elif ':' in message_key:
                # 格式: channel_id:message_id
                try:
                    channel_id, message_id = message_key.rsplit(':', 1)
                except ValueError:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return None
            else:
                logger.warning(f"不支持的消息键格式: {message_key}")
                return None
            
            # 转换message_id为整数
            try:
                message_id = int(message_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的消息ID: {message_id}")
                return None
            
            # 使用现有的get_message方法，静默模式避免不必要的警告
            return self.get_message(channel_id, message_id, silent=True)
            
        except Exception as e:
            logger.error(f"获取消息失败 {message_key}: {e}")
            return None
    
    def update_message_status_by_key(self, message_key: str, new_status: str, reviewer_id: str = None, reason: str = None) -> bool:
        """
        兼容方法：根据消息键更新消息状态
        """
        try:
            # 解析消息键获取channel_id和message_id
            if message_key.startswith('msg:'):
                parts = message_key.split(':', 2)
                if len(parts) >= 3:
                    channel_id, message_id = parts[1], parts[2]
                else:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return False
            elif ':' in message_key:
                try:
                    channel_id, message_id = message_key.rsplit(':', 1)
                except ValueError:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return False
            else:
                logger.warning(f"不支持的消息键格式: {message_key}")
                return False
            
            # 转换message_id为整数
            try:
                message_id = int(message_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的消息ID: {message_id}")
                return False
            
            # 使用内部的update_message_status方法
            return self._update_message_status_core(channel_id, message_id, new_status, reviewer_id)
            
        except Exception as e:
            logger.error(f"更新消息状态失败 {message_key}: {e}")
            return False
    
    def delete_message_by_key(self, message_key: str) -> bool:
        """
        兼容方法：根据消息键删除消息
        """
        try:
            # 解析消息键获取channel_id和message_id
            if message_key.startswith('msg:'):
                parts = message_key.split(':', 2)
                if len(parts) >= 3:
                    channel_id, message_id = parts[1], parts[2]
                else:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return False
            elif ':' in message_key:
                try:
                    channel_id, message_id = message_key.rsplit(':', 1)
                except ValueError:
                    logger.warning(f"消息键格式错误: {message_key}")
                    return False
            else:
                logger.warning(f"不支持的消息键格式: {message_key}")
                return False
            
            # 转换message_id为整数
            try:
                message_id = int(message_id)
            except (ValueError, TypeError):
                logger.warning(f"无效的消息ID: {message_id}")
                return False
            
            # 使用内部的delete_message方法
            return self._delete_message_core(channel_id, message_id)
            
        except Exception as e:
            logger.error(f"删除消息失败 {message_key}: {e}")
            return False
    
    # 添加兼容别名方法，保持API一致性
    def update_message_status(self, message_key_or_channel: str, message_id_or_status=None, new_status_or_reviewer=None, reviewer_id_or_reason=None, reason=None):
        """
        兼容的update_message_status方法
        支持两种调用方式：
        1. update_message_status(channel_id, message_id, new_status, reviewer_id, reason)  # 原始方式
        2. update_message_status(message_key, new_status, reviewer_id, reason)  # 新方式
        """
        if isinstance(message_id_or_status, int):
            # 原始方式：update_message_status(channel_id, message_id, new_status, reviewer_id, reason)
            channel_id = message_key_or_channel
            message_id = message_id_or_status
            new_status = new_status_or_reviewer
            reviewer_id = reviewer_id_or_reason
            return self._update_message_status_core(channel_id, message_id, new_status, reviewer_id)
        else:
            # 新方式：update_message_status(message_key, new_status, reviewer_id, reason)
            message_key = message_key_or_channel
            new_status = message_id_or_status
            reviewer_id = new_status_or_reviewer
            reason = reviewer_id_or_reason
            return self.update_message_status_by_key(message_key, new_status, reviewer_id, reason)
    
    def delete_message(self, message_key_or_channel: str, message_id=None):
        """
        兼容的delete_message方法
        支持两种调用方式：
        1. delete_message(channel_id, message_id)  # 原始方式
        2. delete_message(message_key)  # 新方式
        """
        if message_id is not None:
            # 原始方式：delete_message(channel_id, message_id)
            channel_id = message_key_or_channel
            return self._delete_message_core(channel_id, message_id)
        else:
            # 新方式：delete_message(message_key)
            message_key = message_key_or_channel
            return self.delete_message_by_key(message_key)
    
    # 为了向后兼容，添加原始方法的别名
    def _update_message_status_old(self, channel_id: str, message_id: int, new_status: str, reviewed_by: str = None) -> bool:
        """原始的更新消息状态方法（兼容别名）"""
        return self._update_message_status_core(channel_id, message_id, new_status, reviewed_by)
    
    def _delete_message_old(self, channel_id: str, message_id: int) -> bool:
        """原始的删除消息方法（兼容别名）"""
        return self._delete_message_core(channel_id, message_id)