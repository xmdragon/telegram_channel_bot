"""
极简Telegram实体解析器
只负责解析，不管缓存、配置更新等业务逻辑
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramResolver:
    """统一的Telegram实体（频道/群组）解析器"""

    def __init__(self):
        # 编译正则表达式以提高性能
        self.patterns = {
            'username': re.compile(r'^@?([A-Za-z0-9_]{5,32})$'),
            'public_link': re.compile(r'^https?://t\.me/([A-Za-z0-9_]{5,32})$'),
            'private_link': re.compile(r'^https?://t\.me/\+([A-Za-z0-9_-]+)$'),
            'joinchat_link': re.compile(r'^https?://t\.me/joinchat/([A-Za-z0-9_-]+)$'),
            'numeric_id': re.compile(r'^-?\d+$')
        }

    async def resolve(self, input_str: str) -> Optional[str]:
        """
        解析任何Telegram输入，返回ID

        Args:
            input_str: 可能的输入格式：
                - @username
                - username
                - https://t.me/username
                - https://t.me/+xxxxx (私有链接)
                - https://t.me/joinchat/xxxxx
                - -1001234567890 (已经是ID)

        Returns:
            解析后的ID字符串（如"-1001234567890"），失败返回None
        """
        if not input_str:
            return None

        input_str = input_str.strip()

        # 1. 如果已经是数字ID格式，直接返回
        if self.patterns['numeric_id'].match(input_str):
            # 确保频道/超级群组ID格式正确
            if input_str.startswith('-100'):
                return input_str
            # 如果是纯数字，加上-100前缀（Telegram频道ID格式）
            if input_str.isdigit():
                return f"-100{input_str}"
            return input_str

        # 2. 解析不同格式的输入
        username = None
        invite_hash = None

        # 检查是否为用户名（带或不带@）
        match = self.patterns['username'].match(input_str)
        if match:
            username = match.group(1)

        # 检查是否为公开链接
        if not username:
            match = self.patterns['public_link'].match(input_str)
            if match:
                username = match.group(1)

        # 检查是否为私有链接
        if not username:
            match = self.patterns['private_link'].match(input_str)
            if match:
                invite_hash = match.group(1)
            else:
                # 检查旧格式的joinchat链接
                match = self.patterns['joinchat_link'].match(input_str)
                if match:
                    invite_hash = match.group(1)

        # 3. 通过Telegram API解析实际ID
        try:
            from app.telegram.dual_session_manager import dual_session_manager

            client = await dual_session_manager.get_sender_client() # 使用发布认证
            if not client:
                logger.error("Telegram客户端未连接")
                return None

            # 解析用户名
            if username:
                try:
                    entity = await client.get_entity(username)
                    if hasattr(entity, 'id'):
                        channel_id = entity.id
                        # 确保返回正确格式的ID
                        if hasattr(entity, 'broadcast') and entity.broadcast:
                            # 频道
                            return str(channel_id) if str(channel_id).startswith('-100') else f"-100{channel_id}"
                        elif hasattr(entity, 'megagroup') and entity.megagroup:
                            # 超级群组
                            return str(channel_id) if str(channel_id).startswith('-100') else f"-100{channel_id}"
                        else:
                            # 普通群组或用户
                            return str(-channel_id if channel_id > 0 else channel_id)
                except Exception as e:
                    logger.debug(f"解析用户名 {username} 失败: {e}")

            # 解析邀请链接
            if invite_hash:
                try:
                    # 对于私有链接，需要先检查是否已加入
                    from telethon.tl.functions.messages import CheckChatInviteRequest

                    result = await client(CheckChatInviteRequest(invite_hash))
                    if hasattr(result, 'chat'):
                        chat = result.chat
                        if hasattr(chat, 'id'):
                            chat_id = chat.id
                            # 确保返回正确格式的ID
                            if hasattr(chat, 'broadcast') and chat.broadcast:
                                return str(chat_id) if str(chat_id).startswith('-100') else f"-100{chat_id}"
                            elif hasattr(chat, 'megagroup') and chat.megagroup:
                                return str(chat_id) if str(chat_id).startswith('-100') else f"-100{chat_id}"
                            else:
                                return str(-chat_id if chat_id > 0 else chat_id)
                except Exception as e:
                    logger.debug(f"解析邀请链接失败: {e}")

            return None

        except ImportError as e:
            logger.error(f"导入Telegram客户端失败: {e}")
            return None
        except Exception as e:
            logger.error(f"解析Telegram实体时出错: {e}")
            return None


# 全局实例
telegram_resolver = TelegramResolver()