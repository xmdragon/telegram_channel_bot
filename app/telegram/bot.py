"""
Telegram客户端核心功能 - 重构版本
使用组件化架构，保持向后兼容
"""
import logging
import asyncio
import os
from typing import List, Optional
from datetime import datetime
from app.utils.timezone import format_for_api
from telethon.tl.types import Message as TLMessage
from app.storage.redis_store import get_redis_message_store
from app.services.message_processor import MessageProcessor
from app.services.content_filter import ContentFilter
from app.services.system_monitor import system_monitor
from app.services.media_handler import media_handler
from app.services.message_grouper import message_grouper
from app.services.config_manager import ConfigManager
from app.services.channel_manager import channel_manager
from app.services.unified_message_processor import unified_processor

# 新的组件化模块
from app.telegram.client_manager import client_manager
from app.telegram.message_event_handler import message_event_handler
from app.telegram.message_forwarder import message_forwarder
from app.telegram.history_collector import history_collector

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram机器人管理类 - 重构版本，保持向后兼容"""
    
    def __init__(self):
        # 保持原有属性以确保向后兼容
        self.client = None
        self.message_processor = MessageProcessor()
        self.content_filter = ContentFilter()
        self.is_running = False
        self.monitor_task = None
        self.auto_collection_done = False
        from app.services.config_manager import config_manager
        self.config_manager = config_manager
        self.event_loop_task = None
        
        # 设置组件间的回调关系
        self._setup_component_callbacks()
        
    def _setup_component_callbacks(self):
        """设置各组件间的回调关系"""
        # 设置事件处理器的消息处理器
        message_event_handler.set_message_processor(self._handle_message_from_event)
        message_event_handler.set_callback_processor(self._handle_callback)
        
        # 设置历史采集器的消息处理器
        history_collector.set_message_processor(self._process_and_save_message)
        
        # 设置客户端管理器的回调
        client_manager.add_connection_callback(self._on_client_connected)
        client_manager.add_disconnection_callback(self._on_client_disconnected)
    
    async def start(self):
        """启动Telegram客户端和监控"""
        # 启动系统监控
        await system_monitor.start()
        logger.info("系统监控已启动")
        
        # 启动客户端监控循环
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
    
    async def _monitoring_loop(self):
        """监控循环 - 持续检查系统状态并尝试连接"""
        while True:
            try:
                if not self.is_running:
                    # 尝试连接客户端
                    if await client_manager.connect():
                        self.client = await client_manager.get_client()  # 保持向后兼容
                        self.is_running = True
                        
                await asyncio.sleep(30)  # 30秒检查一次
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                await asyncio.sleep(10)
    
    async def _on_client_connected(self, client):
        """客户端连接成功时的回调"""
        try:
            # 保持向后兼容
            self.client = client
            
            # 启动媒体处理器
            await media_handler.start()
            
            # 注册事件处理器
            await message_event_handler.register_event_handlers(client)
            
            # 执行完整的启动检查（包括解析所有频道ID）
            await self._perform_startup_checks()
            
            # 首次连接时进行历史消息采集
            if not self.auto_collection_done:
                await self._auto_collect_history(client)
                self.auto_collection_done = True
            
            # 创建并启动事件循环任务
            logger.info("启动事件循环...")
            self.event_loop_task = asyncio.create_task(self._run_event_loop(client))
            
        except Exception as e:
            logger.error(f"客户端连接回调失败: {e}")
    
    async def _on_client_disconnected(self):
        """客户端断开连接时的回调"""
        self.is_running = False
        self.client = None
        
        if self.event_loop_task:
            self.event_loop_task.cancel()
    
    async def _run_event_loop(self, client):
        """运行客户端事件循环"""
        try:
            logger.info("开始监听消息...")
            await client.run_until_disconnected()
            logger.info("客户端事件循环已结束")
        except Exception as e:
            logger.error(f"客户端运行出错: {e}")
        finally:
            self.is_running = False
    
    async def _handle_message_from_event(self, message: TLMessage, chat, chat_info: dict, message_type: str):
        """处理来自事件处理器的消息"""
        try:
            if message_type == "source_channel":
                logger.info(f"消息来自监听的源频道: {chat_info['title']}")
                await self.process_source_message(message, chat)
            elif message_type == "review_group":
                logger.info(f"消息来自审核群: {chat_info['title']}")
                await self.process_review_message(message, chat)
            else:
                logger.debug(f"消息来自未监听的频道/群组: {chat_info['title']} (ID: {chat_info['formatted_id']})")
                
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    async def _common_message_processing(self, message: TLMessage, channel_id: str, is_history: bool = False):
        """
        通用消息处理逻辑
        
        Args:
            message: Telegram消息对象
            channel_id: 频道ID（已格式化）
            is_history: 是否为历史消息
            
        Returns:
            处理后的消息数据字典，如果消息被过滤则返回None
        """
        try:
            # 提取消息内容（包括带caption的媒体消息）
            content = message.text or message.raw_text or message.message or ""
            
            # 对于媒体消息，检查是否有caption
            if not content and message.media:
                # 尝试获取媒体的caption（适用于图片、视频等）
                if hasattr(message, 'caption'):
                    content = message.caption or ""
                elif hasattr(message, 'raw_text'):
                    content = message.raw_text or ""
            
            # 对于组合消息，某些情况下文本可能在message属性中
            if not content:
                # 再次尝试获取，某些组合消息的文本可能存储在不同字段
                if hasattr(message, 'message') and message.message:
                    content = message.message
                    logger.debug(f"📝 从message属性提取到内容")
            
            # 如果组合消息仍无文本，可能是纯图片组
            if not content and hasattr(message, 'grouped_id') and message.grouped_id:
                # 对于纯媒体组合消息，某些消息可能没有文本
                logger.debug(f"📝 组合消息 {message.grouped_id} 中的消息 {message.id} 无文本内容")
                    
            # 记录内容提取结果
            if content:
                logger.info(f"📝 提取到消息内容: {content[:100]}...")
            else:
                logger.debug(f"📝 消息无文本内容（纯媒体）")
            media_type = None
            media_url = None
            media_info = None
            
            # 处理媒体消息 - 同步下载到本地
            if message.media:
                if hasattr(message.media, 'photo'):
                    media_type = "photo"
                elif hasattr(message.media, 'document'):
                    media_type = "document"
                    
                # 下载媒体文件（视频120秒，图片30秒）
                try:
                    # 根据媒体类型设置超时时间
                    if media_type == "photo":
                        timeout = 30.0  # 图片30秒
                    elif media_type == "document" and hasattr(message.media, 'document'):
                        # 检查是否为视频
                        document = message.media.document
                        mime_type = document.mime_type or ""
                        if mime_type.startswith("video/"):
                            timeout = 120.0  # 视频120秒
                        else:
                            timeout = 60.0  # 其他文档60秒
                    else:
                        timeout = 60.0  # 默认60秒
                    
                    media_info = await media_handler.download_media(self.client, message, message.id, timeout=timeout)
                    
                    if media_info:
                        media_type = media_info['media_type']
                        media_url = media_info['file_path']
                        logger.info(f"✅ 媒体下载成功: {media_url}")
                    elif message.media and hasattr(message.media, 'document'):
                        # media_info 为 None 表示文件被拒绝（可能是危险文件）
                        document = message.media.document
                        mime_type = document.mime_type or "application/octet-stream"
                        # 检查是否为危险文件
                        dangerous_extensions = ['.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js', '.jar', '.msi', '.dll', '.bin']
                        is_dangerous = False
                        for attr in document.attributes:
                            if hasattr(attr, 'file_name') and attr.file_name:
                                if any(attr.file_name.lower().endswith(ext) for ext in dangerous_extensions):
                                    is_dangerous = True
                                    break
                        
                        if is_dangerous:
                            logger.warning(f"🚫 消息包含危险文件，自动过滤")
                            return None
                        else:
                            # 不是危险文件，只是下载超时，创建占位信息
                            logger.warning(f"⏳ 媒体下载超时（{timeout}秒），创建占位信息 (message_id={message.id})")
                            media_info = {
                                'message_id': message.id,
                                'media_type': media_type or "document",
                                'file_path': None,
                                'file_size': 0,
                                'download_failed': True,
                                'timeout': timeout
                            }
                    else:
                        # 其他下载失败情况，创建占位信息
                        logger.warning(f"⏳ 媒体下载失败（超时{timeout}秒） (message_id={message.id})")
                        media_info = {
                            'message_id': message.id,
                            'media_type': media_type,
                            'file_path': None,
                            'file_size': 0,
                            'download_failed': True,
                            'timeout': timeout
                        }
                except Exception as e:
                    logger.error(f"下载媒体异常 (message_id={message.id}): {e}")
                    # 创建占位信息
                    media_info = {
                        'message_id': message.id,
                        'media_type': media_type,
                        'file_path': None,
                        'file_size': 0,
                        'download_failed': True,
                        'error': str(e)
                    }
            
            # 内容过滤（包含智能去尾部）
            logger.info(f"📝 开始内容过滤，原始内容长度: {len(content)} 字符")
            is_ad, filtered_content, filter_reason = self.content_filter.filter_message_sync(content, channel_id=channel_id)
            
            # 记录过滤结果和原因
            if filter_reason == "tail_only":
                logger.info(f"📝 内容过滤完成：文本完全是尾部推广，已过滤")
            elif filter_reason == "ad_filtered":
                logger.info(f"📝 内容过滤完成：检测到广告内容")
            elif filter_reason == "normal":
                logger.info(f"📝 内容过滤完成，过滤后长度: {len(filtered_content)} 字符，减少: {len(content) - len(filtered_content)} 字符")
            else:
                logger.info(f"📝 内容过滤完成，长度无变化: {len(filtered_content)} 字符")
            
            # 检测高风险广告内容（色情、赌博等）
            high_risk_keywords = [
                # 色情相关
                '约炮', '一夜情', '包夜', '上门服务', '外围', '兼职模特',
                '性服务', '色情', '成人视频', '激情视频', '裸聊',
                # 赌博相关
                '网赌', '赌场', '百家乐', '德州扑克', '体育投注',
                '彩票代理', '博彩', '棋牌游戏', '时时彩',
                # 诈骗相关
                '刷单', '兼职刷单', '日赚千元', '躺赚', '零投资高回报'
            ]
            
            # 检查是否包含高风险关键词
            is_high_risk = False
            content_lower = content.lower() if content else ""
            for keyword in high_risk_keywords:
                if keyword in content_lower:
                    is_high_risk = True
                    logger.warning(f"🚨 检测到高风险广告关键词: {keyword}")
                    break
            
            # 如果是高风险广告，直接拒绝
            if is_high_risk:
                logger.warning(f"🚫 拒绝高风险广告消息: {content[:50]}...")
                if media_info and media_info.get('file_path'):
                    await media_handler.cleanup_file(media_info['file_path'])
                return None
            
            # 检查图片是否为已知广告（新增）
            if media_info and media_info.get('visual_hashes') and media_type and media_type.startswith('image'):
                try:
                    from app.services.ad_image_detector import ad_image_detector
                    is_ad_image, similarity, match_id = await ad_image_detector.is_known_ad(
                        media_info['visual_hashes']
                    )
                    if is_ad_image:
                        logger.warning(f"🚫 检测到广告图片（相似度{similarity:.1f}%），自动拒绝")
                        if media_info.get('file_path'):
                            await media_handler.cleanup_file(media_info['file_path'])
                        return None
                except Exception as e:
                    logger.error(f"广告图片检测失败: {e}")
            
            # 检查无意义内容+广告图片的组合
            if filtered_content and media_info and media_info.get('visual_hashes'):
                # 检查过滤后的内容是否无意义
                if self.content_filter.is_meaningless_content(filtered_content):
                    # 如果有图片且可能是广告图片
                    try:
                        from app.services.ad_image_detector import ad_image_detector
                        is_ad_image, similarity, match_id = await ad_image_detector.is_known_ad(
                            media_info['visual_hashes']
                        )
                        if is_ad_image or similarity > 50:  # 相似度超过50%也认为可疑
                            logger.warning(f"🚫 检测到无意义文本+广告图片组合，自动拒绝")
                            if media_info.get('file_path'):
                                await media_handler.cleanup_file(media_info['file_path'])
                            return None
                    except:
                        pass
            
            # 检查是否为纯广告（优先使用AI检测）
            try:
                # 获取是否启用AI广告检测
                use_ai_ad_detection = await config_manager.get_config('ai.use_ad_detection', True)
                
                if use_ai_ad_detection:
                    # 使用AI检测
                    is_pure_ad = await self.content_filter.is_pure_advertisement_ai(content)
                else:
                    # 使用传统规则检测
                    is_pure_ad = self.content_filter.is_pure_advertisement(content)
                
                if is_pure_ad:
                    logger.warning(f"🚫 检测到纯广告，自动拒绝: {content[:50]}...")
                    if media_info and media_info.get('file_path'):
                        await media_handler.cleanup_file(media_info['file_path'])
                    return None
            except Exception as e:
                logger.error(f"广告检测失败，使用传统方法: {e}")
                # 回退到传统检测
                if self.content_filter.is_pure_advertisement(content):
                    logger.warning(f"🚫 检测到纯广告（规则），自动拒绝: {content[:50]}...")
                    if media_info and media_info.get('file_path'):
                        await media_handler.cleanup_file(media_info['file_path'])
                    return None
            
            # 处理文本被完全过滤的情况
            if content and not filtered_content:
                if filter_reason == "tail_only":
                    # 文本完全是尾部推广
                    if media_info:
                        # 有媒体，保留媒体，文本为空
                        logger.info(f"ℹ️ 媒体消息的文本为纯尾部推广，已过滤，保留媒体")
                        filtered_content = ""  # 文本为空，但保留媒体
                        # 继续处理，不返回None
                    else:
                        # 纯文本且完全是尾部，可能是只发了推广信息
                        logger.info(f"ℹ️ 纯文本消息完全是尾部推广，已过滤")
                        # 这种情况通常不需要采集，但不是广告
                        return None
                else:
                    # 其他原因导致文本为空（如广告过滤）
                    logger.warning(f"🚫 文本被完全过滤（原因: {filter_reason}），拒绝消息")
                    if media_info and media_info.get('file_path'):
                        await media_handler.cleanup_file(media_info['file_path'])
                    return None
            
            # 不进行自动过滤，所有消息都发送到审核群
            # 注：根据配置要求，移除了自动过滤逻辑
            
            # 检查是否为空消息（没有内容也没有媒体）
            if not filtered_content and not media_info:
                logger.warning(f"🚫 消息无内容也无媒体，自动跳过")
                return None
            
            # 返回处理后的消息数据
            return {
                'message': message,
                'content': content,
                'filtered_content': filtered_content,
                'is_ad': is_ad,
                'media_info': media_info,
                'channel_id': channel_id
            }
            
        except Exception as e:
            logger.error(f"通用消息处理失败: {e}")
            # 清理可能已下载的媒体
            if 'media_info' in locals() and media_info and media_info.get('file_path'):
                await media_handler.cleanup_file(media_info['file_path'])
            return None
    
    async def process_source_message(self, message: TLMessage, chat):
        """处理源频道消息 - 使用统一处理器"""
        try:
            # 获取格式化的频道ID
            raw_chat_id = chat.id
            if raw_chat_id > 0:
                channel_id = f"-100{raw_chat_id}"
            else:
                channel_id = str(raw_chat_id)
            
            # 使用统一处理器
            db_message = await unified_processor.process_telegram_message(
                message, 
                channel_id, 
                is_history=False
            )
            
            if not db_message:
                logger.debug(f"消息 {message.id} 处理完成（被过滤或等待组合）")
                
        except Exception as e:
            logger.error(f"处理源频道消息时出错: {e}")
    
    async def process_review_message(self, message: TLMessage, chat):
        """处理审核群中的消息 - 保持原有接口"""
        try:
            text = message.text or ""
            
            # 处理命令
            if text.startswith('/approve_'):
                message_id = int(text.split('_')[1])
                await self.approve_message(message_id, message.sender.username)
            elif text.startswith('/reject_'):
                message_id = int(text.split('_')[1])
                await self.reject_message(message_id, message.sender.username)
            elif text.startswith('/edit_'):
                message_id = int(text.split('_')[1])
                await self.edit_message(message_id)
            elif text.startswith('/detail_'):
                message_id = int(text.split('_')[1])
                await self.show_message_detail(message_id)
                
        except Exception as e:
            logger.error(f"处理审核群消息时出错: {e}")
    
    async def _handle_callback(self, event):
        """处理回调按钮 - 保持原有接口"""
        try:
            data = event.data.decode()
            action, message_id = data.split('_', 1)
            message_id = int(message_id)
            
            if action == "approve":
                await self.approve_message(message_id, event.sender.username)
            elif action == "reject":
                await self.reject_message(message_id, event.sender.username)
            elif action == "edit":
                await self.edit_message(message_id)
            elif action == "detail":
                await self.show_message_detail(message_id)
                
        except Exception as e:
            logger.error(f"处理回调时出错: {e}")
    
    # 保持所有原有的公开方法接口不变
    async def forward_to_review(self, db_message):
        """转发消息到审核群 - 委托给转发器"""
        if self.client:
            await message_forwarder.forward_to_review(self.client, db_message)
        else:
            logger.error("客户端未连接，无法转发消息")
    
    async def forward_to_target(self, message):
        """重新发布到目标频道 - 委托给转发器"""
        if self.client:
            await message_forwarder.forward_to_target(self.client, message)
        else:
            logger.error("客户端未连接，无法转发消息")
    
    async def update_review_message(self, message):
        """更新审核群中的消息内容 - 委托给转发器"""
        if self.client:
            await message_forwarder.update_review_message(self.client, message)
        else:
            logger.error("客户端未连接，无法更新消息")
    
    async def delete_review_message(self, review_message_id: int):
        """删除审核群的消息 - 委托给转发器"""
        if self.client:
            await message_forwarder.delete_review_message(self.client, review_message_id)
        else:
            logger.error("客户端未连接，无法删除消息")
    
    async def approve_message(self, message_id: int, reviewer: str):
        """批准消息 - 兼容接口（已迁移到Redis）"""
        try:
            # 注意: 这个方法保持兼容性，但新系统使用unified_processor
            logger.warning(f"使用了旧的approve_message接口，消息ID: {message_id}")
            logger.info("建议使用新的统一消息处理器进行消息审核")
            # 这里可以添加兼容性代码，或者抛出弃用警告
            
        except Exception as e:
            logger.error(f"批准消息时出错: {e}")
    
    async def reject_message(self, message_id: int, reviewer: str):
        """拒绝消息 - 兼容接口（已迁移到Redis）"""
        try:
            # 注意: 这个方法保持兼容性，但新系统使用unified_processor
            logger.warning(f"使用了旧的reject_message接口，消息ID: {message_id}")
            logger.info("建议使用新的统一消息处理器进行消息审核")
            # 这里可以添加兼容性代码，或者抛出弃用警告
                
        except Exception as e:
            logger.error(f"拒绝消息时出错: {e}")
    
    async def edit_message(self, message_id: int):
        """编辑消息（预留功能）"""
        pass
    
    async def show_message_detail(self, message_id: int):
        """显示消息详情（预留功能）"""
        pass
    
    async def get_chat_info(self, chat_id: str):
        """获取聊天信息 - 委托给客户端管理器"""
        return await client_manager.get_chat_info(chat_id)
    
    async def stop(self):
        """停止客户端 - 保持原有接口"""
        self.is_running = False
        
        # 停止监控任务
        if self.monitor_task:
            self.monitor_task.cancel()
        
        # 停止事件循环任务
        if self.event_loop_task:
            self.event_loop_task.cancel()
            
        # 停止系统监控
        await system_monitor.stop()
        
        # 停止历史采集
        from app.services.history_collector import history_collector as old_history_collector
        await old_history_collector.stop_all_collections()
        
        # 停止媒体处理器
        await media_handler.stop()
        
        # 断开客户端连接
        await client_manager.disconnect()
        self.client = None
        
        logger.info("Telegram客户端已停止")
    
    # 以下为内部方法，保持原有逻辑
    async def _broadcast_new_message(self, db_message):
        """广播新消息到WebSocket客户端"""
        try:
            from app.api.websocket import websocket_manager
            
            # 准备消息数据（确保包含所有必要字段）
            message_data = {
                "id": db_message.id,
                "message_id": db_message.message_id,  # 添加message_id字段（前端需要）
                "source_channel": db_message.source_channel,
                "content": db_message.content,
                "filtered_content": db_message.filtered_content,
                "media_type": db_message.media_type,
                "media_url": db_message.media_url,
                "is_ad": db_message.is_ad,
                "status": db_message.status,
                "created_at": format_for_api(db_message.created_at),
                "is_combined": db_message.is_combined,
                "media_group_display": self._prepare_media_group_display(db_message),
                "media_group": db_message.media_group if db_message.is_combined else None,
                "combined_messages": db_message.combined_messages if db_message.is_combined else None
            }
            
            # 广播到所有WebSocket客户端
            await websocket_manager.broadcast_new_message(message_data)
            logger.info(f"✅ 成功广播新消息 ID:{db_message.id} 到 {len(websocket_manager.active_connections)} 个WebSocket连接")
            
        except ImportError as e:
            logger.error(f"导入WebSocket管理器失败: {e}")
        except Exception as e:
            logger.error(f"广播新消息到WebSocket时出错: {e}")
    
    def _prepare_media_group_display(self, db_message):
        """准备媒体组显示数据"""
        try:
            if not db_message.is_combined or not db_message.media_group:
                return None
                
            media_display = []
            for media_item in db_message.media_group:
                # 转换本地文件路径为web访问路径
                file_path = media_item.get('file_path', '')
                if file_path.startswith('./temp_media/'):
                    web_path = file_path.replace('./temp_media/', '/temp_media/')
                else:
                    web_path = file_path
                    
                media_display.append({
                    'media_type': media_item.get('media_type'),
                    'url': web_path,
                    'file_size': media_item.get('file_size'),
                    'mime_type': media_item.get('mime_type')
                })
            
            return media_display
            
        except Exception as e:
            logger.error(f"准备媒体组显示数据时出错: {e}")
            return None
    
    async def _perform_startup_checks(self):
        """执行启动时的完整配置检查"""
        try:
            from app.services.startup_checker import startup_checker
            
            # 执行完整检查，传递已连接的客户端
            check_results = await startup_checker.check_and_resolve_all_channels(self.client)
            
            # 如果有严重错误，记录但继续运行（让用户可以通过Web界面修复）
            if not check_results['success']:
                logger.error("启动检查发现配置问题，请通过Web界面修复配置")
                # 可以选择在这里停止启动，或继续运行让用户修复
                # raise Exception("启动检查失败，请修复配置后重试")
            
            # 更新内存中的频道列表
            if check_results['source_channels']:
                logger.info(f"已加载 {len(check_results['source_channels'])} 个源频道")
            
            if check_results['target_channel']:
                logger.info(f"目标频道已配置: {check_results['target_channel']}")
            else:
                logger.warning("⚠️ 目标频道未配置，消息将无法转发")
                
            if check_results['review_group']:
                logger.info(f"审核群已配置: {check_results['review_group']}")
            else:
                logger.error("❌ 审核群未配置！为了安全起见，消息不会被转发到目标频道")
                logger.error("请通过Web界面配置审核群，否则所有消息将被阻止！")
                
        except Exception as e:
            logger.error(f"启动检查失败: {e}")
            # 继续运行，让用户可以通过Web界面修复
    
    async def _auto_collect_history(self, client):
        """自动采集频道历史消息"""
        try:
            logger.info("开始采集频道历史消息...")
            await history_collector.collect_channel_history(client)
        except Exception as e:
            logger.error(f"自动采集历史消息失败: {e}")
    
    async def _process_and_save_message(self, message, channel_id: str, is_history: bool = False):
        """处理并保存消息（用于历史消息采集） - 使用统一处理器"""
        try:
            # 使用统一处理器
            db_message = await unified_processor.process_telegram_message(
                message, 
                channel_id, 
                is_history=True
            )
            
            if not db_message:
                logger.debug(f"历史消息 {message.id} 处理完成（被过滤或等待组合）")
                
        except Exception as e:
            logger.error(f"处理历史消息失败: {e}")
    
    async def _save_processed_message(self, message_data: dict, channel_id: str, is_history: bool = False, original_media_info: dict = None):
        """保存处理后的消息"""
        try:
            # 检查是否已经有过滤后的内容（从message_grouper传递过来的）
            if 'filtered_content' in message_data:
                # 已经过滤过了，直接使用
                filtered_content = message_data['filtered_content']
                is_ad = message_data.get('is_ad', False)
                logger.info(f"📝 使用预过滤内容，长度: {len(filtered_content)} 字符")
            else:
                # 未过滤，进行过滤（兼容旧的调用方式）
                logger.info(f"📝 开始内容过滤，原始内容长度: {len(message_data.get('content', ''))} 字符")
                if message_data.get('content'):
                    logger.info(f"📝 内容预览: {message_data['content'][:100]}...")
                
                # 内容过滤
                is_ad, filtered_content, filter_reason = self.content_filter.filter_message_sync(message_data['content'], channel_id=channel_id)
                
                # 对于组合消息，如果文本被判定为广告，保留原始内容供审核
                # 避免出现只有媒体没有文本的情况
                if message_data.get('is_combined') and is_ad and not filtered_content:
                    logger.info(f"📝 组合消息被判定为广告，保留原始文本供审核")
                    filtered_content = message_data['content']  # 保留原始内容
                
                # 添加过滤后的日志
                if message_data.get('content') != filtered_content:
                    logger.info(f"📝 内容过滤完成，长度变化: {len(message_data.get('content', ''))} -> {len(filtered_content)} 字符")
                else:
                    logger.info(f"📝 内容过滤完成，长度无变化: {len(filtered_content)} 字符")
            
            # 初始化媒体哈希变量
            media_hash = None
            combined_media_hash = None
            
            # 不进行自动过滤，所有消息都发送到审核群
            # 注：根据配置要求，移除了自动过滤逻辑
            
            # 计算媒体哈希（先计算，再检查重复）
            logger.info(f"📊 开始计算媒体哈希: is_combined={message_data.get('is_combined')}, media_type={message_data.get('media_type')}, media_url={message_data.get('media_url')}")
            
            # 初始化视觉哈希
            visual_hash = None
            combined_visual_hashes = []
            
            # 单个媒体哈希和视觉哈希
            if message_data.get('media_type') and message_data.get('media_url'):
                # 从文件计算哈希
                media_hash = await media_handler._calculate_file_hash(message_data['media_url'])
                logger.info(f"📊 单个媒体哈希计算完成: {media_hash}")
                
                # 优先使用已经计算好的视觉哈希
                if original_media_info and original_media_info.get('visual_hashes'):
                    visual_hash = str(original_media_info['visual_hashes'])
                    logger.info(f"📊 使用已计算的视觉哈希")
                # 如果没有，则重新计算视觉哈希（仅对图片）
                elif message_data.get('media_type') in ['photo', 'animation']:
                    try:
                        from app.services.visual_similarity import visual_detector
                        if visual_detector and os.path.exists(message_data['media_url']):
                            with open(message_data['media_url'], 'rb') as f:
                                image_data = f.read()
                            visual_hashes = visual_detector.calculate_perceptual_hashes(image_data)
                            visual_hash = str(visual_hashes)
                            logger.info(f"📊 重新计算单个媒体视觉哈希完成")
                    except Exception as e:
                        logger.debug(f"计算视觉哈希失败: {e}")
            
            # 组合媒体哈希
            if message_data.get('is_combined'):
                combined_media_list = []
                
                # 优先从media_group获取（新格式）
                if message_data.get('media_group'):
                    logger.info(f"📊 处理媒体组: {len(message_data['media_group'])} 个文件")
                    for i, media_item in enumerate(message_data['media_group']):
                        if media_item.get('file_path'):
                            # 计算每个媒体文件的哈希
                            file_hash = await media_handler._calculate_file_hash(media_item['file_path'])
                            logger.info(f"📊 媒体{i+1}哈希: {file_hash} (文件: {media_item.get('file_path')})")
                            if file_hash:
                                combined_media_list.append({
                                    'hash': file_hash,
                                    'message_id': media_item.get('message_id', 0)
                                })
                            
                            # 优先使用已计算的视觉哈希
                            if media_item.get('visual_hashes'):
                                combined_visual_hashes.append(media_item['visual_hashes'])
                                logger.info(f"📊 媒体{i+1}使用已计算的视觉哈希")
                            # 如果没有，则重新计算视觉哈希（仅对图片）
                            elif media_item.get('media_type') in ['photo', 'animation']:
                                try:
                                    from app.services.visual_similarity import visual_detector
                                    if visual_detector and os.path.exists(media_item['file_path']):
                                        with open(media_item['file_path'], 'rb') as f:
                                            image_data = f.read()
                                        item_visual_hash = visual_detector.calculate_perceptual_hashes(image_data)
                                        combined_visual_hashes.append(item_visual_hash)
                                        logger.info(f"📊 媒体{i+1}重新计算视觉哈希完成")
                                except Exception as e:
                                    logger.debug(f"计算媒体{i+1}视觉哈希失败: {e}")
                # 兼容旧格式combined_messages
                elif message_data.get('combined_messages'):
                    logger.info(f"📊 处理旧格式组合消息: {len(message_data['combined_messages'])} 个")
                    for msg in message_data['combined_messages']:
                        if msg.get('media_info') and msg['media_info'].get('file_path'):
                            # 计算每个媒体文件的哈希
                            file_hash = await media_handler._calculate_file_hash(msg['media_info']['file_path'])
                            if file_hash:
                                combined_media_list.append({
                                    'hash': file_hash,
                                    'message_id': msg.get('message_id', 0)
                                })
                
                if combined_media_list:
                    combined_media_hash = await media_handler.process_media_group(combined_media_list)
                    logger.info(f"📊 组合媒体哈希计算完成: {combined_media_hash}")
                else:
                    logger.warning("📊 没有有效的媒体文件用于计算组合哈希")
                
                # 组合视觉哈希列表为字符串
                if combined_visual_hashes:
                    visual_hash = str(combined_visual_hashes)
                    logger.info(f"📊 组合媒体包含 {len(combined_visual_hashes)} 个视觉哈希")
            
            # 使用整合的重复检测器（历史消息和实时消息都需要检测重复）
            from app.services.duplicate_detector import DuplicateDetector
            duplicate_detector = DuplicateDetector()
            
            # 执行整合的重复检测（包括视觉相似度）
            visual_hashes_dict = None
            if visual_hash:
                try:
                    # 尝试解析视觉哈希字符串
                    visual_hashes_dict = eval(visual_hash) if isinstance(visual_hash, str) else visual_hash
                    # 如果是列表（组合媒体），取第一个
                    if isinstance(visual_hashes_dict, list) and visual_hashes_dict:
                        visual_hashes_dict = visual_hashes_dict[0]
                except:
                    pass
            
            is_duplicate, original_msg_id, duplicate_type = await duplicate_detector.is_duplicate_message(
                source_channel=channel_id,
                media_hash=media_hash,
                combined_media_hash=combined_media_hash,
                content=message_data.get('content'),
                message_time=message_data.get('date') or datetime.now(),
                visual_hashes=visual_hashes_dict
            )
            
            if is_duplicate:
                logger.info(f"{'历史' if is_history else '实时'}消息：发现重复消息（{duplicate_type}），原始消息ID: {original_msg_id}，跳过处理")
                # 清理已下载的媒体文件
                if message_data.get('media_url') and os.path.exists(message_data['media_url']):
                    await media_handler.cleanup_file(message_data['media_url'])
                # 清理组合消息的媒体文件
                if message_data.get('media_group'):
                    for media_item in message_data['media_group']:
                        if media_item.get('file_path') and os.path.exists(media_item['file_path']):
                            await media_handler.cleanup_file(media_item['file_path'])
                return
            
            # 使用消息处理器进行处理（包含重复检测）
            process_message_data = {
                'source_channel': channel_id,
                'message_id': message_data['message_id'],
                'content': message_data['content'],
                'media_type': message_data.get('media_type'),
                'media_url': message_data.get('media_url'),
                'grouped_id': str(message_data.get('grouped_id')) if message_data.get('grouped_id') else None,
                'is_combined': message_data.get('is_combined', False),
                'combined_messages': message_data.get('combined_messages'),
                'media_hash': media_hash,
                'combined_media_hash': combined_media_hash,
                'visual_hash': visual_hash,
                'media_group': message_data.get('media_group'),
                'is_ad': is_ad,
                'filtered_content': filtered_content,
                'status': 'pending',  # 所有消息都需要审核
                'created_at': message_data.get('date').replace(tzinfo=None) if message_data.get('date') and hasattr(message_data.get('date'), 'tzinfo') else (message_data.get('date') or datetime.now())
            }
            
            db_message = await self.message_processor.process_new_message(process_message_data)
            
            # 如果消息被重复检测拒绝，则不进行后续处理
            if not db_message:
                logger.info(f"{'历史' if is_history else '实时'}消息 {message_data['message_id']} 被重复检测拒绝")
                return
                
            # 转发到审核群（历史消息和实时消息都需要审核）
            await self.forward_to_review(db_message)
                
            # 广播新消息到WebSocket客户端
            await self._broadcast_new_message(db_message)
                    
        except Exception as e:
            logger.error(f"保存处理后的消息失败: {e}")
            # 出错时清理媒体文件
            if message_data.get('media_url') and os.path.exists(message_data['media_url']):
                await media_handler.cleanup_file(message_data['media_url'])
    
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

# 全局bot实例，供其他模块使用
telegram_bot = None