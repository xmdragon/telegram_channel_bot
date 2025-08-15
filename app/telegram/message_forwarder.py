"""
Telegram消息转发器
专门负责消息转发相关的所有功能
"""
import logging
import os
from typing import Optional
from datetime import datetime
from telethon import TelegramClient

from app.storage.redis_store import get_redis_message_store
from app.storage.json_store import get_json_channel_store
from app.services.telegram_link_resolver import link_resolver
from app.services.content_filter import ContentFilter
from app.services.media_handler import media_handler

logger = logging.getLogger(__name__)

class MessageForwarder:
    """消息转发器 - 专门处理消息转发逻辑"""
    
    def __init__(self):
        self.content_filter = ContentFilter()
        
    async def forward_to_review(self, client: TelegramClient, message_data: dict):
        """转发消息到审核群（包含媒体）"""
        try:
            # 获取有效的审核群ID
            review_group_id = await link_resolver.get_effective_group_id()
            
            if not review_group_id:
                logger.error("❌ 审核群未配置！为了安全起见，消息不会被转发")
                # 更新消息状态为错误，防止自动转发
                message_store = get_redis_message_store()
                await message_store.update_message_status(
                    message_data['channel_id'], message_data['message_id'], 
                    'error', reject_reason='审核群未配置，消息被阻止'
                )
                raise ValueError("审核群未配置，消息转发被阻止。请先配置审核群！")
                return
            
            sent_message = None
            
            # 准备消息内容（使用过滤后的内容）
            message_text = message_data.get('filtered_content') or message_data.get('content')
            
            # 记录智能去尾部效果
            if message_data.get('filtered_content') and len(message_data.get('filtered_content', '')) < len(message_data.get('content', '')):
                removed_chars = len(message_data.get('content', '')) - len(message_data.get('filtered_content', ''))
                logger.info(f"📤 转发到审核群，智能去尾部已生效，减少 {removed_chars} 字符")
            
            # 在转发时添加频道落款
            # 获取频道名称
            channel_name = "未知频道"
            try:
                channel_store = get_json_channel_store()
                channels = channel_store.get_all_channels()
                source_channel = str(message_data.get('source_channel', ''))
                
                for channel_data in channels:
                    if str(channel_data.get('channel_id', '')) == source_channel:
                        channel_name = channel_data.get('channel_name') or channel_data.get('channel_title') or "未知频道"
                        break
            except Exception as e:
                logger.debug(f"获取频道名称失败: {e}")
            
            message_text = self.content_filter.add_channel_signature(message_text, channel_name)
            
            # 如果消息被判定为广告且文本被完全过滤，不发送媒体
            if message_data.get('is_ad') and (not message_text or message_text.strip() == ""):
                message_text = "[🚫 广告内容已过滤，媒体文件不予显示]"
                # 发送纯文本消息，不包含媒体
                sent_message = await client.send_message(
                    entity=int(review_group_id),
                    message=message_text
                )
            elif message_data.get('is_ad') and message_text:
                # 如果是广告但有文本内容，添加标记但仍发送媒体（供审核）
                message_text = f"[⚠️ 疑似广告内容]\n{message_text}"
            
            # 如果消息已经在上面处理过（广告内容被完全过滤），跳过这里
            if not sent_message:
                # 检查是否为组合消息
                if message_data.get('is_combined') and message_data.get('media_group'):
                    # 发送组合消息到审核群
                    sent_message = await self._send_combined_message_to_review(client, review_group_id, message_data, message_text)
                elif message_data.get('media_type'):
                    # 检查媒体文件是否存在
                    if message_data.get('media_url') and os.path.exists(message_data.get('media_url')):
                        # 发送单个媒体消息到审核群
                        sent_message = await self._send_single_media_to_review(client, review_group_id, message_data, message_text)
                    else:
                        # 媒体文件不存在（下载失败或超时），添加占位符
                        media_type_name = {
                            'photo': '图片',
                            'video': '视频',
                            'document': '文件',
                            'animation': '动图',
                            'audio': '音频'
                        }.get(message_data.get('media_type'), '媒体')
                        
                        placeholder = f"📎 [{media_type_name}下载超时，未能显示]"
                        
                        if message_text:
                            message_text = f"{placeholder}\n\n{message_text}"
                        else:
                            message_text = placeholder
                        
                        sent_message = await client.send_message(
                            entity=int(review_group_id),
                            message=message_text
                        )
                else:
                    # 发送纯文本消息到审核群
                    sent_message = await client.send_message(
                        entity=int(review_group_id),
                        message=message_text
                    )
            
            # 更新Redis记录
            if sent_message:
                try:
                    message_store = get_redis_message_store()
                    review_message_id = None
                    if isinstance(sent_message, list):
                        # 组合消息返回列表，保存第一个消息的ID
                        review_message_id = sent_message[0].id
                    else:
                        review_message_id = sent_message.id
                    
                    # 更新消息的review_message_id
                    await message_store.update_message_review_id(
                        message_data['channel_id'], 
                        message_data['message_id'], 
                        review_message_id
                    )
                    
                    logger.info(f"消息已转发到审核群: {message_data['message_id']} -> {review_message_id}")
                except Exception as e:
                    logger.error(f"更新消息审核ID失败: {e}")
                
        except Exception as e:
            logger.error(f"转发到审核群时出错: {e}")
    
    async def forward_to_target(self, client: TelegramClient, message):
        """重新发布到目标频道"""
        try:
            # 获取目标频道配置 - 使用解析后的数字ID
            from app.core.config import settings
            target_channel_id = await settings.get_target_channel_resolved_id()
            
            if not target_channel_id:
                logger.error("未配置目标频道ID")
                return
            
            # 移除隐藏链接（系统默认策略：始终移除）
            clean_entities = None
            
            # 记录被移除的隐藏链接
            if message.removed_hidden_links:
                logger.info(f"转发时移除 {len(message.removed_hidden_links)} 个隐藏链接")
                for link in message.removed_hidden_links:
                    logger.debug(f"  移除: {link.get('text', '')} -> {link.get('url', '')}")
            # 转发时不包含任何MessageEntityTextUrl类型的实体
            clean_entities = []  # 空实体列表，确保不包含隐藏链接
            
            sent_message = None
            
            # 检查是否为组合消息
            if message.is_combined and message.media_group:
                # 发送组合消息（媒体组）
                sent_message = await self._send_combined_message(client, target_channel_id, message)
            elif message.media_type and message.media_url and os.path.exists(message.media_url):
                # 发送单个媒体消息
                sent_message = await self._send_single_media_message(client, target_channel_id, message)
            else:
                # 发送纯文本消息（不包含隐藏链接实体）
                content_with_footer = await self._add_channel_footer(message.filtered_content or message.content)
                sent_message = await client.send_message(
                    entity=int(target_channel_id),
                    message=content_with_footer,
                    formatting_entities=clean_entities  # 传递空实体列表，移除隐藏链接
                )
            
            # 更新数据库
            if sent_message:
                if isinstance(sent_message, list):
                    message.target_message_id = sent_message[0].id
                else:
                    message.target_message_id = sent_message.id
            message.forwarded_time = datetime.now()
            
            logger.info(f"消息重新发布成功: {message.id} -> {message.target_message_id}")
            
            # 清理本地文件
            await self._cleanup_message_files(message)
            
        except Exception as e:
            logger.error(f"重新发布到目标频道时出错: {e}")
            await self._cleanup_message_files(message)
    
    async def update_review_message(self, client: TelegramClient, message):
        """更新审核群中的消息内容"""
        try:
            if not message.review_message_id:
                logger.warning("消息没有审核群消息ID，无法更新")
                return
            
            # 获取审核群ID
            review_group_id = await link_resolver.get_effective_group_id()
            
            if not review_group_id:
                logger.error("未配置审核群ID或无法解析审核群链接")
                return
            
            # 准备更新后的消息内容
            updated_content = message.filtered_content or message.content
            
            # 检查消息是否包含媒体
            has_media = (message.media_type and message.media_url) or (message.is_combined and message.media_group)
            
            # 尝试直接编辑消息（适用于纯文本或带caption的媒体）
            try:
                # 尝试编辑消息
                edited = await client.edit_message(
                    entity=int(review_group_id),
                    message=message.review_message_id,
                    text=updated_content
                )
                
                if edited:
                    logger.info(f"成功编辑审核群消息 {message.review_message_id}")
                    return
            except Exception as edit_error:
                logger.debug(f"无法直接编辑消息（可能是媒体组合消息）: {edit_error}")
            
            if has_media:
                # 对于无法编辑的媒体消息，需要删除旧消息并重新发送
                logger.info(f"消息包含媒体且无法编辑，需要重新发送到审核群")
                
                # 1. 删除旧的审核群消息
                await self.delete_review_message(client, message.review_message_id)
                
                # 2. 重新发送到审核群
                sent_message = None
                
                # 检查是否为组合消息
                if message.is_combined and message.media_group:
                    # 发送组合消息到审核群
                    sent_message = await self._send_combined_message_to_review(client, review_group_id, message, updated_content)
                elif message.media_type and message.media_url and os.path.exists(message.media_url):
                    # 发送单个媒体消息到审核群
                    sent_message = await self._send_single_media_to_review(client, review_group_id, message, updated_content)
                else:
                    # 媒体文件不存在，只发送文本
                    logger.warning(f"媒体文件不存在: {message.media_url}")
                    sent_message = await client.send_message(
                        entity=int(review_group_id),
                        message=updated_content
                    )
                
                # 3. 更新Redis中的review_message_id和filtered_content
                if sent_message:
                    try:
                        message_store = get_redis_message_store()
                        review_message_id = None
                        if isinstance(sent_message, list):
                            # 组合消息返回列表，保存第一个消息的ID
                            review_message_id = sent_message[0].id
                        else:
                            review_message_id = sent_message.id
                        
                        # 更新消息的review_message_id和filtered_content
                        await message_store.update_message_review_id(
                            message.get('channel_id') or message.source_channel, 
                            message.get('message_id') or message.message_id, 
                            review_message_id
                        )
                        
                        # 更新filtered_content
                        await message_store.update_message_field(
                            message.get('channel_id') or message.source_channel,
                            message.get('message_id') or message.message_id,
                            'filtered_content',
                            updated_content
                        )
                        
                        logger.info(f"已更新审核群消息ID和内容: {message.get('id') or message.message_id} -> {review_message_id}")
                    except Exception as e:
                        logger.error(f"更新Redis记录失败: {e}")
            else:
                # 纯文本消息，直接编辑
                await client.edit_message(
                    entity=int(review_group_id),
                    message=message.review_message_id,
                    text=updated_content
                )
                logger.info(f"已更新审核群消息: {message.review_message_id}")
            
        except Exception as e:
            logger.error(f"更新审核群消息失败: {e}")
    
    async def delete_review_message(self, client: TelegramClient, review_message_id: int):
        """删除审核群的消息"""
        try:
            # 获取审核群ID
            review_group_id = await link_resolver.get_effective_group_id()
            
            if not review_group_id:
                return
            
            # 删除消息
            await client.delete_messages(
                entity=int(review_group_id),
                message_ids=[review_message_id]
            )
            
            logger.info(f"已删除审核群消息: {review_message_id}")
            
        except Exception as e:
            logger.error(f"删除审核群消息失败: {e}")
    
    async def _send_combined_message_to_review(self, client: TelegramClient, review_group_id: str, message, caption: str):
        """发送组合消息到审核群"""
        try:
            # 如果是广告消息且文本被过滤，不发送媒体
            if message.is_ad and (not caption or caption.strip() == "" or "[🚫 广告内容已过滤" in caption):
                # 只发送文本提示
                return await client.send_message(
                    entity=int(review_group_id),
                    message=caption if caption else "[🚫 广告内容已过滤，媒体文件不予显示]"
                )
            
            media_files = []
            missing_items = []
            
            # 准备媒体文件列表
            for media_item in message.media_group:
                file_path = media_item.get('file_path')
                if file_path and os.path.exists(file_path):
                    media_files.append(file_path)
                else:
                    media_type_name = {
                        'photo': '图片',
                        'video': '视频',
                        'document': '文件',
                        'animation': '动图',
                        'audio': '音频'
                    }.get(media_item.get('media_type', 'unknown'), '媒体')
                    missing_items.append(media_type_name)
            
            # 如果有媒体文件缺失，添加占位符
            if missing_items:
                missing_text = f"📎 [{len(missing_items)}个{'/'.join(set(missing_items))}下载超时，未能显示]"
                caption = f"{missing_text}\n\n{caption}" if caption else missing_text
            
            if not media_files:
                # 没有媒体文件，发送纯文本
                return await client.send_message(
                    entity=int(review_group_id),
                    message=caption
                )
            
            # 发送媒体组
            if len(media_files) == 1:
                # 只有一个文件
                return await client.send_file(
                    entity=int(review_group_id),
                    file=media_files[0],
                    caption=caption
                )
            else:
                # 多个文件
                return await client.send_file(
                    entity=int(review_group_id),
                    file=media_files,
                    caption=caption
                )
                
        except Exception as e:
            logger.error(f"发送组合消息到审核群失败: {e}")
            # 失败时尝试发送纯文本
            return await client.send_message(
                entity=int(review_group_id),
                message=caption
            )
    
    async def _send_single_media_to_review(self, client: TelegramClient, review_group_id: str, message, caption: str):
        """发送单个媒体消息到审核群"""
        try:
            # 如果是广告消息且文本被过滤，不发送媒体
            if message.is_ad and (not caption or caption.strip() == "" or "[🚫 广告内容已过滤" in caption):
                # 只发送文本提示
                return await client.send_message(
                    entity=int(review_group_id),
                    message=caption if caption else "[🚫 广告内容已过滤，媒体文件不予显示]"
                )
            
            return await client.send_file(
                entity=int(review_group_id),
                file=message.media_url,
                caption=caption
            )
        except Exception as e:
            logger.error(f"发送媒体消息到审核群失败: {e}")
            # 失败时尝试发送纯文本
            return await client.send_message(
                entity=int(review_group_id),
                message=caption
            )
    
    async def _add_channel_footer(self, content: str) -> str:
        """
        添加频道落款到消息内容
        """
        try:
            # 使用ConfigManager从数据库获取配置
            from app.services.config_manager import ConfigManager
            config_manager = ConfigManager()
            footer = await config_manager.get_config("channels.signature", "")
            
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
    
    async def _send_combined_message(self, client: TelegramClient, target_channel_id: str, message):
        """发送组合消息（媒体组）"""
        try:
            media_files = []
            caption_text = message.filtered_content or message.content
            # 添加频道落款
            caption_text = await self._add_channel_footer(caption_text)
            
            # 准备媒体文件列表
            for media_item in message.media_group:
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
            # 发送失败时也要添加落款
            content_with_footer = await self._add_channel_footer(message.filtered_content or message.content)
            return await client.send_message(
                entity=int(target_channel_id),
                message=content_with_footer
            )
    
    async def _send_single_media_message(self, client: TelegramClient, target_channel_id: str, message):
        """发送单个媒体消息"""
        try:
            # 添加频道落款到caption
            caption_with_footer = await self._add_channel_footer(message.filtered_content or message.content)
            return await client.send_file(
                entity=int(target_channel_id),
                file=message.media_url,
                caption=caption_with_footer
            )
        except Exception as e:
            logger.error(f"发送媒体消息失败: {e}")
            # 发送失败时也要添加落款
            content_with_footer = await self._add_channel_footer(message.filtered_content or message.content)
            return await client.send_message(
                entity=int(target_channel_id),
                message=content_with_footer
            )
    
    async def _cleanup_message_files(self, message):
        """清理消息相关的媒体文件"""
        try:
            if message.is_combined and message.media_group:
                # 清理组合消息的所有媒体文件
                for media_item in message.media_group:
                    file_path = media_item['file_path']
                    if os.path.exists(file_path):
                        await media_handler.cleanup_file(file_path)
            elif message.media_url and os.path.exists(message.media_url):
                # 清理单个媒体文件
                await media_handler.cleanup_file(message.media_url)
        except Exception as e:
            logger.error(f"清理消息文件时出错: {e}")

# 全局转发器实例
message_forwarder = MessageForwarder()