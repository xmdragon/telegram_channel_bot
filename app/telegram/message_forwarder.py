"""
Telegram消息转发器
专门负责消息转发相关的所有功能
"""
import logging
import os
import asyncio
from typing import Optional, Union, Dict, Any
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import FloodWaitError

from app.storage.redis_manager import redis_manager
from app.storage.json_store import get_json_channel_store
from app.services.media_handler import media_handler
from app.utils.rate_limiter import rate_limiter, MessageType

logger = logging.getLogger(__name__)


class StandardMessage:
    """统一消息类 - 消除MessageWrapper灾难"""
    
    def __init__(self, data: Union[Dict, Any]):
        """接受字典或对象，提供统一接口"""
        if isinstance(data, dict):
            self._data = data
            self._is_dict = True
        else:
            self._data = data
            self._is_dict = False
    
    def __getattr__(self, name: str) -> Any:
        """统一属性访问"""
        if self._is_dict:
            if name in self._data:
                return self._data[name]
            # 提供标准默认值
            defaults = {
                'removed_hidden_links': [],
                'is_combined': False,
                'media_group_display': None,
                'media_url': None,
                'media_type': None,
                'media_path': None,
                'target_message_id': None,
                'forwarded_time': None,
                'id': f"{self._data.get('source_channel')}:{self._data.get('message_id')}"
            }
            return defaults.get(name)
        else:
            return getattr(self._data, name, None)
    
    def get(self, key: str, default: Any = None) -> Any:
        """字典式访问"""
        if self._is_dict:
            return self._data.get(key, default)
        else:
            return getattr(self._data, key, default)

class MessageForwarder:
    """消息转发器 - 专门处理消息转发逻辑"""
    
    def __init__(self):
        # 简化：不需要复杂的过滤引擎依赖
        self._last_wait_time = 0

    def add_channel_signature(self, text: str, channel_name: str) -> str:
        """添加频道签名 - 简单直接，无复杂依赖"""
        if not text or not text.strip():
            return f"📡 来自：{channel_name}"
        return f"{text}\n\n📡 来自：{channel_name}"
        
    
    async def forward_to_target(self, client: TelegramClient, message):
        """重新发布到目标频道，返回目标消息链接"""
        try:
            # ✅ 优化：使用统一消息类，消除运行时类定义
            message = StandardMessage(message)

            # 获取目标频道ID（从配置）
            from app.services.config_manager import config_manager
            target_channel_id = await config_manager.get_config('target.channel_id')

            if not target_channel_id:
                logger.error("未配置目标频道ID")
                return None

            # 解析目标频道实体（避免PeerChannel找不到的错误）
            try:
                from telethon.tl.types import PeerChannel
                target_entity = await client.get_entity(PeerChannel(int(target_channel_id)))
            except Exception as e:
                logger.warning(f"通过PeerChannel解析失败: {e}，尝试直接解析ID")
                target_entity = await client.get_entity(int(target_channel_id))

            # 🚀 智能限流控制 - 根据消息类型等待
            message_type = self._get_message_type(message)
            wait_time = await rate_limiter.wait_if_needed(message_type, target_channel_id)
            # 存储等待时间供后续调用使用
            self._last_wait_time = wait_time
            if wait_time > 0:
                # 删除转发前限流等待的日志，会在最终结果中包含
                pass

            # 记录发送尝试的标记
            send_attempted = False

            # 移除隐藏链接（系统默认策略：始终移除）
            clean_entities = None

            # 记录被移除的隐藏链接
            removed_links = getattr(message, 'removed_hidden_links', []) or []
            if removed_links:
                logger.info(f"转发时移除 {len(removed_links)} 个隐藏链接")
                for link in removed_links:
                    logger.debug(f"  移除: {link.get('text', '')} -> {link.get('url', '')}")
            # 转发时不包含任何MessageEntityTextUrl类型的实体
            clean_entities = []  # 空实体列表，确保不包含隐藏链接

            sent_message = None

            # 🔧 检查是否为组合消息，支持动态组合检测
            is_combined = getattr(message, 'is_combined', False) or message.get('is_combined', False)
            media_group = getattr(message, 'media_group_display', None) or message.get('media_group_display', None)
            media_type = getattr(message, 'media_type', None) or message.get('media_type', None)
            media_url = getattr(message, 'media_url', None) or message.get('media_url', None)
            grouped_id = getattr(message, 'grouped_id', None) or message.get('grouped_id', None)
            
            # 🚀 优化：消除特殊情况，消息在采集时就应该正确组合

            # 处理媒体路径 - 转换相对路径为绝对路径
            actual_media_path = media_url
            if media_url and media_url.startswith('/temp_media/'):
                from app.core.path_config import PathConfig
                actual_media_path = str(PathConfig.ROOT_DIR / media_url.lstrip('/'))
                logger.debug(f"媒体路径转换: {media_url} -> {actual_media_path}")

            # 🚀 发送消息并处理FloodWait
            if is_combined and media_group:
                # 发送组合消息（媒体组）
                sent_message = await self._send_combined_message_with_retry(client, target_entity, message, message_type)
                send_attempted = True
            elif media_type and (
                (actual_media_path and os.path.exists(actual_media_path)) or
                (not (actual_media_path and os.path.exists(actual_media_path))
                 and message.get('source_channel') and message.get('message_id'))
            ):
                # 发送单个媒体消息（本地文件或远程引用）
                sent_message = await self._send_single_media_message_with_retry(client, target_entity, message, message_type)
                send_attempted = True
            else:
                # 发送纯文本消息（不包含隐藏链接实体）
                filtered_content = getattr(message, 'filtered_content', None) or message.get('filtered_content', None)
                content = getattr(message, 'content', None) or message.get('content', '')

                # 🗑️ 不再需要清理媒体组标记 - 现在单独存储
                text_content = filtered_content or content

                content_with_footer = await self._add_channel_footer(text_content)

                # 发送文本消息（带FloodWait处理）
                sent_message = await self._send_text_message_with_retry(
                    client, target_entity, content_with_footer, clean_entities, message_type
                )
                send_attempted = True
            
            # 更新数据库（如果是字典类型，需要更新Redis存储）
            if sent_message:
                # 🚀 修复：记录所有目标消息ID（支持媒体组批量删除）
                if isinstance(sent_message, list):
                    # 媒体组：记录所有消息ID
                    target_msg_ids = [msg.id for msg in sent_message]
                    target_msg_id = sent_message[0].id  # 保持兼容性
                else:
                    # 单个消息：记录一个ID
                    target_msg_ids = [sent_message.id]
                    target_msg_id = sent_message.id

                # 如果是字典类型，更新Redis中的记录
                if isinstance(message.data if hasattr(message, 'data') else message, dict):
                    try:
                        from app.storage.redis_manager import redis_manager
                        redis_store = redis_manager
                        if redis_store:
                            channel_id = message.get('source_channel')
                            message_id = message.get('message_id')
                            grouped_id = message.get('grouped_id')

                            # 🚀 优化：只更新主消息，子消息已删除无需更新
                            if channel_id and message_id:
                                # 更新目标消息ID（保持兼容）
                                redis_manager.update_message_field(
                                    channel_id, int(message_id), 'target_message_id', str(target_msg_id)
                                )
                                # 🚀 新增：记录所有目标消息ID供批量删除使用
                                redis_manager.update_message_field(
                                    channel_id, int(message_id), 'target_message_ids', target_msg_ids
                                )
                                redis_manager.update_message_field(
                                    channel_id, int(message_id), 'forwarded_time', datetime.now().isoformat()
                                )
                                logger.info(f"已更新Redis记录: {channel_id}:{message_id} -> 目标消息IDs: {target_msg_ids}")
                    except Exception as e:
                        logger.error(f"更新Redis记录失败: {e}")
                else:
                    # 对象类型，直接设置属性
                    message.target_message_id = target_msg_id
                    message.target_message_ids = target_msg_ids  # 新增批量删除字段
                    message.forwarded_time = datetime.now()
            
            # 构建目标消息链接
            target_message_link = None
            if sent_message:
                target_msg_id = sent_message[0].id if isinstance(sent_message, list) else sent_message.id

                # 获取目标频道用户名
                target_channel_username = await config_manager.get_config('target.channel_link')

                if target_channel_username:
                    # 去掉@符号（如果有的话）
                    channel_username = target_channel_username.lstrip('@')
                    target_message_link = f"https://t.me/{channel_username}/{target_msg_id}"
                else:
                    # 如果没有用户名，使用私有频道格式
                    # 需要转换频道ID格式：-100开头的ID需要去掉-100
                    channel_id_str = str(target_channel_id)
                    if channel_id_str.startswith('-100'):
                        channel_numeric_id = channel_id_str[4:]  # 去掉-100前缀
                    else:
                        channel_numeric_id = channel_id_str.lstrip('-')
                    target_message_link = f"https://t.me/c/{channel_numeric_id}/{target_msg_id}"

                # 删除消息重新发布成功的日志
            else:
                logger.warning(f"消息发布但未获取到消息ID: {getattr(message, 'id', 'unknown')}")

            # 记录成功发送（仅在真正发送成功时记录）
            if send_attempted and sent_message:
                rate_limiter.record_send_attempt(message_type, target_channel_id, True)
                logger.debug(f"已记录发送成功: {message_type.value} -> {target_channel_id}")

            # 返回完整的目标消息信息
            return {
                'link': target_message_link,
                'target_message_id': target_msg_id if sent_message else None,
                'target_message_ids': target_msg_ids if sent_message else []
            }

        except FloodWaitError as e:
            # FloodWait专门处理 - 不立即等待，让上层处理
            logger.warning(f"转发触发FloodWait，需等待{e.seconds if hasattr(e, 'seconds') else '未知'}秒: {getattr(message, 'id', 'unknown')}")

            # 记录失败发送（仅在真正尝试发送后）
            if send_attempted:
                rate_limiter.record_send_attempt(message_type, target_channel_id, False)
                logger.debug(f"已记录FloodWait失败: {message_type.value} -> {target_channel_id}")

            # 重新抛出异常，让上层决定是否重试
            raise

        except Exception as e:
            logger.error(f"重新发布到目标频道时出错: {e}")

            # 检查是否是FloodWait错误的其他形式
            error_str = str(e).lower()
            if 'flood' in error_str or 'wait' in error_str:
                logger.warning(f"检测到FloodWait错误形式: {getattr(message, 'id', 'unknown')}")

                # 尝试提取等待时间
                import re
                match = re.search(r'(\d+)\s*seconds?', error_str)
                wait_seconds = int(match.group(1)) if match else 60

                # 创建一个真正的FloodWaitError实例
                # FloodWaitError已经在文件顶部导入，不需要重新导入
                # FloodWaitError需要request参数，这里传None
                flood_error = FloodWaitError(request=None, message=f"A wait of {wait_seconds} seconds is required")
                flood_error.seconds = wait_seconds

                # 抛出真正的FloodWaitError
                raise flood_error

            # 记录失败发送（仅在真正尝试发送后）
            if send_attempted:
                rate_limiter.record_send_attempt(message_type, target_channel_id, False)
                logger.debug(f"已记录发送失败: {message_type.value} -> {target_channel_id}")

            # 不清理媒体文件 - 交给scheduler定期清理，保留文件用于重试
            raise  # 重新抛出异常，让队列处理器知道失败
    
    async def _add_channel_footer(self, content: str) -> str:
        """
        添加频道落款到消息内容
        """
        try:
            # 使用ConfigManager从数据库获取配置
            from app.services.config_manager import config_manager
            footer = await config_manager.get_config("target.signature", "")
            
            if footer:
                # 使用配置的落款，处理换行符
                footer = "\n\n" + footer.replace("\\n", "\n")
                # 删除添加频道落款的日志
                return (content or "") + footer
            
            # 如果没有配置落款，直接返回原内容
            return content
            
        except Exception as e:
            logger.error(f"添加频道落款失败: {e}")
            return content
    
    async def _check_caption_length(self, content: str, with_footer: bool = True) -> tuple[bool, int]:
        """检查caption长度是否超限

        Args:
            content: 消息内容
            with_footer: 是否计算加上落款的长度

        Returns:
            (是否合法, 超出字符数)
        """
        try:
            from app.services.config_manager import config_manager

            if with_footer:
                # 获取落款配置
                footer = await config_manager.get_config("target.signature", "")
                if footer:
                    footer = "\n\n" + footer.replace("\\n", "\n")
                    content = (content or "") + footer

            # 检查是否为Premium账号
            is_premium = await config_manager.get_config('telegram.is_premium', False)

            # 根据Premium状态选择字符限制
            if is_premium:
                max_length = await config_manager.get_config('telegram.max_message_length_vip', 2048)
                logger.debug(f"使用Premium字符限制: {max_length}字")
            else:
                max_length = await config_manager.get_config('telegram.max_message_length', 1024)
                logger.debug(f"使用普通用户字符限制: {max_length}字")

            content_length = len(content)

            if content_length <= max_length:
                return True, 0
            else:
                excess = content_length - max_length
                logger.warning(f"Caption长度超限: {content_length} > {max_length} (超出{excess}字符)")
                return False, excess

        except Exception as e:
            logger.error(f"检查caption长度失败: {e}")
            # 出错时保守处理，假设超限
            return False, 0
    
    async def _send_combined_message(self, client: TelegramClient, target_channel_id: str, message):
        """发送组合消息（媒体组）"""
        try:
            media_files = []
            caption_text = message.filtered_content or message.content
            
            # 🗑️ 不再需要清理媒体组标记 - 现在单独存储
            
            # 🔍 检查加上落款后的caption长度
            is_valid, excess = await self._check_caption_length(caption_text, with_footer=True)
            if not is_valid:
                error_msg = f"组合消息发布失败：内容加落款后超过1024字符限制（超出{excess}字符）"
                logger.warning(error_msg)
                # 不直接抛出异常，而是让上层处理
                raise ValueError(error_msg)
            
            # 添加频道落款
            caption_text = await self._add_channel_footer(caption_text)
            
            # 准备媒体文件列表（支持本地文件和远程引用混合）
            source_channel = message.get('source_channel')
            for media_item in message.media_group_display:
                file_path = media_item.get('file_path')
                # 处理媒体文件路径
                if file_path and file_path.startswith('/temp_media/'):
                    from app.core.path_config import PathConfig
                    file_path = str(PathConfig.ROOT_DIR / file_path.lstrip('/'))

                if file_path and os.path.exists(file_path):
                    media_files.append(file_path)
                elif source_channel and media_item.get('message_id'):
                    # 本地文件不存在，从源频道获取媒体引用（视频等）
                    media_obj = await self._fetch_source_media(
                        source_channel, media_item['message_id']
                    )
                    media_files.append(media_obj)
                    logger.info(f"组媒体使用远程引用: {source_channel}:{media_item['message_id']}")
                else:
                    logger.warning(f"媒体文件不可用: {file_path}")
            
            if not media_files:
                logger.warning("组合消息中没有可用的媒体文件，发送纯文本")
                # 获取超时配置
                timeout = await self._get_file_timeout()
                return await asyncio.wait_for(
                    client.send_message(
                        entity=target_channel_id,
                        message=caption_text
                    ),
                    timeout=timeout
                )
            
            # 发送媒体组
            if len(media_files) == 1:
                # 获取超时配置
                timeout = await self._get_file_timeout(media_files[0])
                return await asyncio.wait_for(
                    client.send_file(
                        entity=target_channel_id,
                        file=media_files[0],
                        caption=caption_text
                    ),
                    timeout=timeout
                )
            else:
                # 获取超时配置
                timeout = await self._get_file_timeout()
                return await asyncio.wait_for(
                    client.send_file(
                        entity=target_channel_id,
                        file=media_files,
                        caption=caption_text
                    ),
                    timeout=timeout
                )
                
        except Exception as e:
            logger.error(f"发送组合消息失败: {e}")
            # 不降级，直接抛出异常让上层处理
            raise
    
    async def _send_single_media_message(self, client: TelegramClient, target_channel_id: str, message):
        """发送单个媒体消息（支持本地文件和远程引用）"""
        try:
            caption_text = message.filtered_content or message.content

            is_valid, excess = await self._check_caption_length(caption_text, with_footer=True)
            if not is_valid:
                error_msg = f"媒体消息发布失败：内容加落款后超过1024字符限制（超出{excess}字符）"
                logger.warning(error_msg)
                raise ValueError(error_msg)

            caption_with_footer = await self._add_channel_footer(caption_text)

            # 处理媒体文件路径
            file_path = message.media_url
            if file_path and file_path.startswith('/temp_media/'):
                from app.core.path_config import PathConfig
                file_path = str(PathConfig.ROOT_DIR / file_path.lstrip('/'))

            # 判断是否需要从源频道获取媒体引用
            use_local_file = file_path and os.path.exists(file_path)

            if use_local_file:
                file_to_send = file_path
            else:
                # 从源频道获取原消息媒体（视频等未下载的文件）
                source_channel = message.get('source_channel')
                msg_id = message.get('message_id')
                file_to_send = await self._fetch_source_media(source_channel, msg_id)
                logger.info(f"使用远程媒体引用: {source_channel}:{msg_id}")

            timeout = await self._get_file_timeout()
            return await asyncio.wait_for(
                client.send_file(
                    entity=target_channel_id,
                    file=file_to_send,
                    caption=caption_with_footer
                ),
                timeout=timeout
            )
        except Exception as e:
            logger.error(f"发送媒体消息失败: {e}")
            raise

    async def _fetch_source_media(self, source_channel_id, message_id):
        """从源频道获取原消息的媒体对象（用于视频等未下载的文件转发）"""
        from app.telegram.dual_session_manager import dual_session_manager
        listener_client = await dual_session_manager.get_listener_client()
        if not listener_client:
            raise RuntimeError("采集客户端不可用")

        from telethon.tl.types import PeerChannel
        try:
            entity = await listener_client.get_entity(PeerChannel(int(source_channel_id)))
        except Exception:
            entity = await listener_client.get_entity(int(source_channel_id))

        messages = await listener_client.get_messages(entity, ids=[int(message_id)])
        if not messages or not messages[0]:
            raise RuntimeError(f"原消息不存在: {source_channel_id}:{message_id}")

        original_msg = messages[0]
        if not original_msg.media:
            raise RuntimeError(f"原消息无媒体: {source_channel_id}:{message_id}")

        return original_msg.media

    async def _get_file_timeout(self, file_path: str = None) -> int:
        """
        获取发送消息超时配置

        Args:
            file_path: 文件路径（保留参数以兼容）

        Returns:
            超时时间（秒）
        """
        try:
            from app.services.config_manager import ConfigManager
            config_manager = ConfigManager()
            timeout = await config_manager.get_config('processor.send_message_timeout', 120)
            return int(timeout)
        except Exception as e:
            logger.warning(f"获取发送超时配置失败，使用默认值120秒: {e}")
            return 120

    def _get_message_type(self, message) -> MessageType:
        """
        根据消息内容判断消息类型

        Args:
            message: 消息对象

        Returns:
            消息类型枚举
        """
        # 检查是否为组合消息
        if getattr(message, 'is_combined', False) or message.get('is_combined', False) or \
           getattr(message, 'media_group_display', None) or message.get('media_group_display', None):
            return MessageType.COMBINED

        # 检查是否有媒体
        if getattr(message, 'media_url', None) or message.get('media_url', None) or \
           getattr(message, 'media_type', None) or message.get('media_type', None):
            return MessageType.MEDIA

        # 默认为文本消息
        return MessageType.TEXT

    async def _send_text_message_with_retry(self, client: TelegramClient, target_channel_id: str,
                                           content: str, entities, message_type: MessageType) -> any:
        """发送文本消息（带FloodWait重试）"""
        try:
            # 获取超时配置
            timeout = await self._get_file_timeout()
            return await asyncio.wait_for(
                client.send_message(
                    entity=target_channel_id,
                    message=content,
                    formatting_entities=entities
                ),
                timeout=timeout
            )
        except FloodWaitError as e:
            # FloodWait处理并重新抛出，让上层处理
            wait_seconds = await rate_limiter.handle_flood_wait_error(str(e))
            await rate_limiter.wait_for_flood_wait(wait_seconds)
            raise

    async def _send_combined_message_with_retry(self, client: TelegramClient, target_channel_id: str,
                                               message, message_type: MessageType) -> any:
        """发送组合消息（带FloodWait重试）"""
        try:
            return await self._send_combined_message(client, target_channel_id, message)
        except FloodWaitError as e:
            # FloodWait处理并重新抛出，让上层处理
            wait_seconds = await rate_limiter.handle_flood_wait_error(str(e))
            await rate_limiter.wait_for_flood_wait(wait_seconds)
            raise

    async def _send_single_media_message_with_retry(self, client: TelegramClient, target_channel_id: str,
                                                   message, message_type: MessageType) -> any:
        """发送单个媒体消息（带FloodWait重试）"""
        try:
            return await self._send_single_media_message(client, target_channel_id, message)
        except FloodWaitError as e:
            # FloodWait处理并重新抛出，让上层处理
            wait_seconds = await rate_limiter.handle_flood_wait_error(str(e))
            await rate_limiter.wait_for_flood_wait(wait_seconds)
            raise

    async def forward_to_target_with_sender_session(self, message):
        """使用发送Session转发到目标频道（无锁设计），返回包含目标消息ID的完整信息"""
        from app.telegram.dual_session_manager import dual_session_manager

        try:
            # 确保发送Session已连接
            if await dual_session_manager.ensure_sender_connected():
                sender_client = await dual_session_manager.get_sender_client()
                if sender_client:
                    # 执行转发，返回完整信息（包含link, target_message_id, target_message_ids）
                    target_info = await self.forward_to_target(sender_client, message)
                    return target_info
                else:
                    raise RuntimeError("发送Session客户端未可用")
            else:
                raise RuntimeError("无法连接发送Session")

        except Exception as e:
            logger.error(f"使用发送Session转发失败: {e}")
            raise

# 全局转发器实例
message_forwarder = MessageForwarder()