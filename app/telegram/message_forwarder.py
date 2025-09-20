"""
Telegram消息转发器
专门负责消息转发相关的所有功能
"""
import logging
import os
from typing import Optional, Union, Dict, Any
from datetime import datetime
from telethon import TelegramClient

from app.storage.redis_manager import redis_manager
from app.storage.json_store import get_json_channel_store
from app.services.media_handler import media_handler

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
        pass

    def add_channel_signature(self, text: str, channel_name: str) -> str:
        """添加频道签名 - 简单直接，无复杂依赖"""
        if not text or not text.strip():
            return f"📡 来自：{channel_name}"
        return f"{text}\n\n📡 来自：{channel_name}"
        
    
    async def forward_to_target(self, client: TelegramClient, message):
        """重新发布到目标频道"""
        try:
            # ✅ 优化：使用统一消息类，消除运行时类定义
            message = StandardMessage(message)
            
            # 获取目标频道ID（从配置）
            from app.services.config_manager import config_manager
            target_channel_id = await config_manager.get_config('target.channel_id')
            
            if not target_channel_id:
                logger.error("未配置目标频道ID")
                return
            
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
            
            if is_combined and media_group:
                # 发送组合消息（媒体组）
                sent_message = await self._send_combined_message(client, target_channel_id, message)
            elif media_type and media_url and os.path.exists(media_url):
                # 发送单个媒体消息
                sent_message = await self._send_single_media_message(client, target_channel_id, message)
            else:
                # 发送纯文本消息（不包含隐藏链接实体）
                filtered_content = getattr(message, 'filtered_content', None) or message.get('filtered_content', None)
                content = getattr(message, 'content', None) or message.get('content', '')
                
                # 🗑️ 不再需要清理媒体组标记 - 现在单独存储
                text_content = filtered_content or content
                
                content_with_footer = await self._add_channel_footer(text_content)
                sent_message = await client.send_message(
                    entity=int(target_channel_id),
                    message=content_with_footer,
                    formatting_entities=clean_entities  # 传递空实体列表，移除隐藏链接
                )
            
            # 更新数据库（如果是字典类型，需要更新Redis存储）
            if sent_message:
                target_msg_id = sent_message[0].id if isinstance(sent_message, list) else sent_message.id
                
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
                                # 单个消息更新
                                redis_manager.update_message_field(
                                    channel_id, int(message_id), 'target_message_id', str(target_msg_id)
                                )
                                redis_manager.update_message_field(
                                    channel_id, int(message_id), 'forwarded_time', datetime.now().isoformat()
                                )
                                logger.info(f"已更新Redis记录: {channel_id}:{message_id} -> 目标消息ID: {target_msg_id}")
                    except Exception as e:
                        logger.error(f"更新Redis记录失败: {e}")
                else:
                    # 对象类型，直接设置属性
                    message.target_message_id = target_msg_id
                    message.forwarded_time = datetime.now()
            
            logger.info(f"消息重新发布成功: {getattr(message, 'id', 'unknown')} -> 目标频道: {target_channel_id}")
            
        except Exception as e:
            logger.error(f"重新发布到目标频道时出错: {e}")
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
                logger.info(f"添加频道落款到消息")
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
            if with_footer:
                # 获取落款配置
                from app.services.config_manager import config_manager
                footer = await config_manager.get_config("target.signature", "")
                if footer:
                    footer = "\n\n" + footer.replace("\\n", "\n")
                    content = (content or "") + footer
            
            max_length = 1024  # Telegram媒体caption限制
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
            
            # 准备媒体文件列表
            for media_item in message.media_group_display:
                file_path = media_item['file_path']
                if os.path.exists(file_path):
                    media_files.append(file_path)
            
            if not media_files:
                logger.warning("组合消息中没有可用的媒体文件，发送纯文本")
                return await client.send_message(
                    entity=int(target_channel_id),
                    message=caption_text
                )
            
            # 发送媒体组
            if len(media_files) == 1:
                return await client.send_file(
                    entity=int(target_channel_id),
                    file=media_files[0],
                    caption=caption_text
                )
            else:
                return await client.send_file(
                    entity=int(target_channel_id),
                    file=media_files,
                    caption=caption_text
                )
                
        except Exception as e:
            logger.error(f"发送组合消息失败: {e}")
            # 不降级，直接抛出异常让上层处理
            raise
    
    async def _send_single_media_message(self, client: TelegramClient, target_channel_id: str, message):
        """发送单个媒体消息"""
        try:
            # 🗑️ 不再需要清理媒体组标记 - 现在单独存储
            caption_text = message.filtered_content or message.content

            # 🔍 检查加上落款后的caption长度
            is_valid, excess = await self._check_caption_length(caption_text, with_footer=True)
            if not is_valid:
                error_msg = f"媒体消息发布失败：内容加落款后超过1024字符限制（超出{excess}字符）"
                logger.warning(error_msg)
                # 不直接抛出异常，而是让上层处理
                raise ValueError(error_msg)
            
            caption_with_footer = await self._add_channel_footer(caption_text)
            return await client.send_file(
                entity=int(target_channel_id),
                file=message.media_url,
                caption=caption_with_footer
            )
        except Exception as e:
            logger.error(f"发送媒体消息失败: {e}")
            # 不降级，直接抛出异常让上层处理
            raise

    async def forward_to_target_with_sender_session(self, message):
        """使用发送Session转发到目标频道（无锁设计）"""
        from app.telegram.dual_session_manager import dual_session_manager
        
        try:
            # 确保发送Session已连接
            if await dual_session_manager.ensure_sender_connected():
                sender_client = await dual_session_manager.get_sender_client()
                if sender_client:
                    # 执行转发
                    await self.forward_to_target(sender_client, message)
                else:
                    raise RuntimeError("发送Session客户端未可用")
            else:
                raise RuntimeError("无法连接发送Session")
                
        except Exception as e:
            logger.error(f"使用发送Session转发失败: {e}")
            raise

# 全局转发器实例
message_forwarder = MessageForwarder()