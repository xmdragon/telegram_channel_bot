"""
Telegram链接解析服务
解析Telegram群组/频道链接并获取真实ID
"""
import re
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs

from app.telegram.auth import auth_manager
from app.services.config_manager import config_manager

logger = logging.getLogger(__name__)

class TelegramLinkResolver:
    """Telegram链接解析器"""
    
    def __init__(self):
        self.link_patterns = {
            'invite_link': re.compile(r'https://t\.me/\+([A-Za-z0-9_-]+)'),
            'username_link': re.compile(r'https://t\.me/([A-Za-z0-9_]+)'),
            'joinchat_link': re.compile(r'https://t\.me/joinchat/([A-Za-z0-9_-]+)')
        }
    
    def is_telegram_link(self, text: str) -> bool:
        """检查是否为Telegram链接"""
        if not text:
            return False
        return any(pattern.match(text.strip()) for pattern in self.link_patterns.values())
    
    def parse_link(self, link: str) -> Dict[str, Any]:
        """解析Telegram链接"""
        link = link.strip()
        
        # 邀请链接 (https://t.me/+xxx)
        match = self.link_patterns['invite_link'].match(link)
        if match:
            return {
                'type': 'invite_link',
                'hash': match.group(1),
                'original_link': link
            }
        
        # 用户名链接 (https://t.me/username)
        match = self.link_patterns['username_link'].match(link)
        if match:
            return {
                'type': 'username_link',
                'username': match.group(1),
                'original_link': link
            }
        
        # 旧版加入链接 (https://t.me/joinchat/xxx)
        match = self.link_patterns['joinchat_link'].match(link)
        if match:
            return {
                'type': 'joinchat_link',
                'hash': match.group(1),
                'original_link': link
            }
        
        return {'type': 'unknown', 'original_link': link}
    
    async def resolve_group_id(self, link: str) -> Optional[int]:
        """解析群组链接获取真实ID"""
        try:
            if not auth_manager.client:
                logger.error("Telegram客户端未连接")
                return None
            
            parsed = self.parse_link(link)
            
            if parsed['type'] == 'invite_link':
                return await self._resolve_invite_link(parsed['hash'])
            elif parsed['type'] == 'username_link':
                return await self._resolve_username_link(parsed['username'])
            elif parsed['type'] == 'joinchat_link':
                return await self._resolve_joinchat_link(parsed['hash'])
            else:
                logger.error(f"不支持的链接格式: {link}")
                return None
                
        except Exception as e:
            logger.error(f"解析群组链接失败: {e}")
            return None
    
    async def _resolve_invite_link(self, invite_hash: str) -> Optional[int]:
        """解析邀请链接获取群组ID"""
        try:
            # 使用Telethon的方法解析邀请链接
            from telethon.tl.functions.messages import CheckChatInviteRequest
            from telethon.tl.functions.messages import ImportChatInviteRequest
            
            # 首先检查邀请链接信息
            result = await auth_manager.client(CheckChatInviteRequest(invite_hash))
            
            if hasattr(result, 'chat'):
                # 如果已经加入了群组，直接返回ID
                chat_id = result.chat.id
                if hasattr(result.chat, 'megagroup') and result.chat.megagroup:
                    # 超级群组需要添加-100前缀
                    return int(f"-100{chat_id}")
                else:
                    return -chat_id if chat_id > 0 else chat_id
            
            elif hasattr(result, 'title'):
                # 如果还没加入，需要先加入才能获取ID
                logger.info(f"需要加入群组: {result.title}")
                import_result = await auth_manager.client(ImportChatInviteRequest(invite_hash))
                
                if hasattr(import_result, 'chats') and import_result.chats:
                    chat = import_result.chats[0]
                    chat_id = chat.id
                    if hasattr(chat, 'megagroup') and chat.megagroup:
                        return int(f"-100{chat_id}")
                    else:
                        return -chat_id if chat_id > 0 else chat_id
            
            return None
            
        except Exception as e:
            logger.error(f"解析邀请链接失败: {e}")
            return None
    
    async def _resolve_username_link(self, username: str) -> Optional[int]:
        """解析用户名链接获取群组ID"""
        try:
            entity = await auth_manager.client.get_entity(username)
            
            if hasattr(entity, 'id'):
                chat_id = entity.id
                # 根据实体类型确定ID格式
                if hasattr(entity, 'megagroup') and entity.megagroup:
                    return int(f"-100{chat_id}")
                elif hasattr(entity, 'broadcast') and entity.broadcast:
                    return int(f"-100{chat_id}")
                else:
                    return -chat_id if chat_id > 0 else chat_id
            
            return None
            
        except Exception as e:
            logger.error(f"解析用户名链接失败: {e}")
            return None
    
    async def _resolve_joinchat_link(self, chat_hash: str) -> Optional[int]:
        """解析旧版加入链接获取群组ID"""
        # 旧版joinchat链接的处理方式与invite链接类似
        return await self._resolve_invite_link(chat_hash)
    
    async def resolve_and_cache_group_id(self, review_group_config: str) -> Optional[int]:
        """
        解析并缓存群组ID
        如果是链接，解析获取ID并缓存；如果已经是ID，直接返回
        """
        try:
            # 检查是否已经是数字ID
            if review_group_config.lstrip('-').isdigit():
                return int(review_group_config)
            
            # 检查是否是用户名格式
            if review_group_config.startswith('@') and not self.is_telegram_link(review_group_config):
                entity = await auth_manager.client.get_entity(review_group_config)
                if hasattr(entity, 'id'):
                    chat_id = entity.id
                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        resolved_id = int(f"-100{chat_id}")
                    elif hasattr(entity, 'broadcast') and entity.broadcast:
                        resolved_id = int(f"-100{chat_id}")
                    else:
                        resolved_id = -chat_id if chat_id > 0 else chat_id
                    
                    # 缓存解析结果
                    await self._cache_resolved_id(review_group_config, resolved_id)
                    return resolved_id
            
            # 如果是Telegram链接，解析获取ID
            if self.is_telegram_link(review_group_config):
                resolved_id = await self.resolve_group_id(review_group_config)
                if resolved_id:
                    # 缓存解析结果
                    await self._cache_resolved_id(review_group_config, resolved_id)
                    return resolved_id
            
            return None
            
        except Exception as e:
            logger.error(f"解析并缓存群组ID失败: {e}")
            return None
    
    async def _cache_resolved_id(self, original_config: str, resolved_id: int):
        """缓存解析的群组ID"""
        try:
            # 将解析的ID缓存到配置中
            await config_manager.set_config('channels.review_group_id_cached', str(resolved_id))
            logger.info(f"已缓存审核群ID: {original_config} -> {resolved_id}")
        except Exception as e:
            logger.error(f"缓存群组ID失败: {e}")
    
    async def get_cached_group_id(self) -> Optional[int]:
        """获取缓存的群组ID"""
        try:
            cached_id = await config_manager.get_config('channels.review_group_id_cached')
            if cached_id and cached_id.lstrip('-').isdigit():
                return int(cached_id)
            return None
        except Exception as e:
            logger.error(f"获取缓存群组ID失败: {e}")
            return None
    
    async def get_effective_group_id(self) -> Optional[int]:
        """
        获取有效的群组ID
        优先使用缓存的ID，如果没有则解析配置的链接/用户名
        """
        try:
            # 首先尝试获取缓存的ID
            cached_id = await self.get_cached_group_id()
            if cached_id:
                return cached_id
            
            # 如果没有缓存，获取配置的审核群设置
            review_group_config = await config_manager.get_config('channels.review_group_id', '')
            if not review_group_config:
                return None
            
            # 解析并缓存
            return await self.resolve_and_cache_group_id(review_group_config)
            
        except Exception as e:
            logger.error(f"获取有效群组ID失败: {e}")
            return None

# 全局链接解析器实例
link_resolver = TelegramLinkResolver()