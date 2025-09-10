"""
TelegramMessageCollector - 全新的消息采集处理架构
基于流程图重新设计的干净架构，集成Telegram核心组件
"""
import logging
import asyncio
import json
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import Message as TLMessage

from app.core.path_config import PathConfig
from app.storage.redis_manager import redis_manager
from app.services.message_queue import CollectedMessage

logger = logging.getLogger(__name__)


@dataclass
class RawMessage:
    """解析后的原始消息数据"""
    channel_id: str
    message_id: int
    content: str
    media_info: Optional[Dict] = None
    grouped_id: Optional[str] = None
    timestamp: datetime = None
    raw_telegram_message: TLMessage = None

class ChannelManager:
    """频道管理器"""
    
    def __init__(self):
        self.source_channels: List[Dict] = []    # 源频道列表缓存
        self.target_channel_id: Optional[str] = None    # 目标频道ID
        self.review_group_id: Optional[str] = None      # 审核群ID
        self.history_limit: int = 10                    # 历史消息采集数配置
        self.entities: Dict[str, Any] = {}              # Telethon实体缓存
        
        # 文件修改时间缓存（用于检测配置变化）
        self._channels_mtime = 0
        self._system_mtime = 0
    
    async def load_config(self):
        """检测配置文件变化并动态加载"""
        # 获取当前文件修改时间
        channels_mtime = PathConfig.CHANNELS_CONFIG_FILE.stat().st_mtime
        system_mtime = PathConfig.SYSTEM_CONFIG_FILE.stat().st_mtime
        
        # 只有频道配置文件变化时才重新加载
        if channels_mtime != self._channels_mtime:
            with open(PathConfig.CHANNELS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.source_channels = json.load(f)
            self._channels_mtime = channels_mtime
            logger.info(f"频道配置已更新: {len(self.source_channels)}个源频道")
        
        # 只有系统配置文件变化时才重新加载
        if system_mtime != self._system_mtime:
            with open(PathConfig.SYSTEM_CONFIG_FILE, 'r', encoding='utf-8') as f:
                system_config = json.load(f)
            self.target_channel_id = system_config["target.channel_id"]["value"]
            self.review_group_id = system_config["review.group_id"]["value"]
            self.history_limit = int(system_config["source.history_limit"]["value"])
            self._system_mtime = system_mtime
            logger.info(f"系统配置已更新: 目标频道={self.target_channel_id}, 审核群={self.review_group_id}, 历史消息数={self.history_limit}")
    
    # 使用示例（在消息采集循环中）：
    # await channel_manager.load_config()  # 自动检测配置更新
    # channels = await channel_manager.get_all_source_channels()
    
    async def get_all_source_channels(self) -> List[Dict]:
        """获取所有源频道列表"""
        await self.load_config()
        return self.source_channels
    
    async def get_target_channel_id(self) -> Optional[str]:
        """获取目标频道ID"""
        await self.load_config()
        return self.target_channel_id
    
    async def get_review_group_id(self) -> Optional[str]:
        """获取审核群ID"""
        await self.load_config()
        return self.review_group_id
    
    async def get_history_limit(self) -> int:
        """获取历史消息采集数配置"""
        await self.load_config()
        return self.history_limit
    
    async def get_channel_entity(self, channel_id: str, client: TelegramClient):
        """获取频道Telethon实体（带缓存）"""
        if channel_id in self.entities:
            return self.entities[channel_id]
        
        try:
            entity = await client.get_entity(int(channel_id))
            self.entities[channel_id] = entity
            return entity
        except Exception as e:
            logger.error(f"获取频道实体失败 {channel_id}: {e}")
            return None


# 占位符组件 - 为后续实现预留接口
class CheckpointManager:
    """Checkpoint管理器"""
    
    def get_checkpoint(self, channel_id: str) -> int:
        """从Redis获取checkpoint，默认返回0"""
        try:
            checkpoint = redis_manager.client.hget("channel:checkpoint", channel_id)
            return int(checkpoint) if checkpoint else 0
        except Exception as e:
            logger.error(f"获取checkpoint失败 {channel_id}: {e}")
            return 0
    
    async def update_checkpoint(self, channel_id: str, message_id: int):
        """异步更新checkpoint到Redis"""
        try:
            # 异步更新，避免阻塞消息处理
            await asyncio.get_event_loop().run_in_executor(
                None, 
                redis_manager.client.hset, 
                "channel:checkpoint", 
                channel_id, 
                str(message_id)
            )
            logger.debug(f"checkpoint已更新: {channel_id} -> {message_id}")
        except Exception as e:
            logger.error(f"更新checkpoint失败 {channel_id}: {e}")


class MessageParser:
    """消息解析器 - 占位符"""
    
    def __init__(self):
        self.client: Optional[TelegramClient] = None
    
    def set_client(self, client: TelegramClient):
        """设置Telethon客户端"""
        self.client = client
    
    async def parse(self, telegram_message: TLMessage, channel_id: str) -> RawMessage:
        """解析消息，提取基础信息"""
        # TODO: 实现消息解析逻辑
        return RawMessage(
            channel_id=channel_id,
            message_id=telegram_message.id,
            content=getattr(telegram_message, 'text', '') or '',
            timestamp=telegram_message.date or datetime.now(),
            raw_telegram_message=telegram_message
        )


class ContentProcessingPipeline:
    """内容处理管道 - 占位符"""
    
    async def process(self, raw_message: RawMessage):
        """执行三步处理管道"""
        # TODO: 实现三步处理逻辑
        pass


class MessageStorage:
    """消息存储管理器 - 占位符"""
    
    async def save(self, processed_message):
        """保存处理后的消息"""
        # TODO: 实现存储逻辑
        pass


class TelegramMessageCollector:
    """消息采集器 - 统一入口"""
    
    def __init__(self):
        # Telegram核心组件 - 延迟导入避免启动问题
        from app.telegram.dual_session_manager import dual_session_manager
        self.session_manager = dual_session_manager
        
        self.telethon_client: Optional[TelegramClient] = None
        
        # 频道管理
        self.channel_manager = ChannelManager()
        
        # 业务组件
        self.checkpoint_manager = CheckpointManager()
        self.message_parser = MessageParser()
        self.content_pipeline = ContentProcessingPipeline()
        self.storage = MessageStorage()
        
        # 初始化标志
        self._initialized = False
    
    async def initialize(self):
        """初始化采集器"""
        logger.info("初始化TelegramMessageCollector")
        
        try:
            # 1. 检查session_manager是否成功导入
            if self.session_manager is None:
                raise RuntimeError("dual_session_manager导入失败，无法初始化")
            
            # 2. 获取Telethon客户端（使用监听客户端进行消息采集）
            self.telethon_client = await self.session_manager.get_listener_client()
            
            # 3. 确保客户端连接
            if self.telethon_client and not self.telethon_client.is_connected():
                await self.telethon_client.connect()
            
            # 4. 设置客户端到需要的组件
            if self.telethon_client:
                self.message_parser.set_client(self.telethon_client)
            
            # 5. 初始化频道配置
            await self.channel_manager.load_config()
            source_channels = await self.channel_manager.get_all_source_channels()
            target_channel = await self.channel_manager.get_target_channel_id()
            review_group = await self.channel_manager.get_review_group_id()
            
            logger.info(f"频道配置初始化完成: {len(source_channels)}个源频道, 目标频道={target_channel}, 审核群={review_group}")
            
            self._initialized = True
            logger.info("TelegramMessageCollector初始化完成")
            
        except Exception as e:
            logger.error(f"TelegramMessageCollector初始化失败: {e}")
            raise
    
    async def process_message(self, telegram_message: TLMessage, channel_id: str, source: str = "realtime"):
        """
        统一消息处理入口
        
        Args:
            telegram_message: Telegram原始消息对象
            channel_id: 频道ID
            source: 消息来源 ("realtime" 或 "history")
        """
        
        logger.debug(f"开始处理消息 #{telegram_message.id} from {channel_id} ({source})")
        
        try:
            # 1. 消息解析
            raw_message = await self.message_parser.parse(telegram_message, channel_id)
            
            # 2. Checkpoint检查（仅历史采集）
            if source == "history":
                current_checkpoint = self.checkpoint_manager.get_checkpoint(channel_id)
                if raw_message.message_id <= current_checkpoint:
                    logger.debug(f"消息 #{raw_message.message_id} 已处理过，跳过")
                    return "already_processed"
            
            # 3. 三步处理管道
            processed = await self.content_pipeline.process(raw_message)
            
            # 4. 存储并决定状态
            stored = await self.storage.save(processed)
            
            # 5. 更新Checkpoint（仅历史采集）
            if source == "history":
                await self.checkpoint_manager.update_checkpoint(channel_id, raw_message.message_id)
            
            logger.info(f"消息 #{telegram_message.id} 处理完成")
            return stored
            
        except Exception as e:
            logger.error(f"处理消息 #{telegram_message.id} 失败: {e}")
            raise
    
    async def start_collecting(self):
        """开始消息采集循环"""
        logger.info("开始消息采集循环")
        
        # 1. 初始加载频道列表
        channels = await self.channel_manager.get_all_source_channels()
        
        if not channels:
            logger.warning("没有配置源频道，跳过采集")
            return
        
        logger.info(f"开始处理 {len(channels)} 个源频道")
        
        # 2. 遍历处理每个频道
        for i, channel in enumerate(channels, 1):
            channel_id = channel['channel_id']
            channel_name = channel.get('channel_name', channel.get('channel_title', 'Untitled'))
            
            logger.info(f"处理频道 ({i}/{len(channels)}): {channel_name} ({channel_id})")
            
            # 检查checkpoint并处理消息
            checkpoint = self.checkpoint_manager.get_checkpoint(channel_id)
            await self._process_channel_messages(channel, checkpoint)
        
        # 3. 处理完成后检查配置更新（为下次调用准备）
        await self.channel_manager.get_all_source_channels()
        
        logger.info("采集循环完成")
    
    async def _get_message_ids_to_collect(self, entity, channel_id: str, checkpoint: int) -> List[List[int]]:
        """根据channel和checkpoint返回要采集的消息ID组列表"""
        try:
            if checkpoint == 0:
                # 首次采集：获取历史消息ID
                history_limit = await self.channel_manager.get_history_limit()
                # 实际获取数量 = 配置值 × 5，考虑组消息情况
                actual_limit = history_limit * 5
                # 获取最新的actual_limit条消息ID
                messages = await self.telethon_client.get_messages(entity, limit=actual_limit)
            else:
                # 增量采集：获取checkpoint之后的消息ID
                messages = await self.telethon_client.get_messages(entity, min_id=checkpoint, limit=None)
                messages = [msg for msg in messages if msg and msg.id > checkpoint]
            
            if not messages:
                return []
            
            # 按grouped_id分组
            message_groups = {}  # {grouped_id: [msg_ids]}
            single_messages = []  # 单独消息
            
            for msg in messages:
                if msg.grouped_id:
                    # 组消息
                    if msg.grouped_id not in message_groups:
                        message_groups[msg.grouped_id] = []
                    message_groups[msg.grouped_id].append(msg.id)
                else:
                    # 单独消息
                    single_messages.append([msg.id])
            
            # 合并结果：组消息 + 单独消息
            all_groups = list(message_groups.values()) + single_messages
            
            # 🎯 重要：只返回最近的history_limit个消息组
            if checkpoint == 0:  # 只在首次采集时限制
                history_limit = await self.channel_manager.get_history_limit()
                if len(all_groups) > history_limit:
                    result = all_groups[:history_limit]  # 取前history_limit个（最新的）
                else:
                    result = all_groups
            else:
                result = all_groups  # 增量采集不限制
            
            return result
            
        except Exception as e:
            logger.error(f"获取消息ID失败: {e}")
            return []
    
    async def _fetch_telegram_messages(self, entity, message_groups: List[List[int]]) -> List[CollectedMessage]:
        """根据ID组列表从Telegram获取消息并处理媒体下载和组消息合并"""
        try:
            if not message_groups:
                return []
            
            # 1. 批量获取原始消息
            raw_messages = await self._batch_get_raw_messages(entity, message_groups)
            if not raw_messages:
                return []
            
            # 2. 按组处理消息
            processed_messages = []
            channel_id = str(entity.id) if hasattr(entity, 'id') else "unknown"
            
            for group_ids in message_groups:
                if len(group_ids) == 1:
                    # 单独消息
                    message_id = group_ids[0]
                    if message_id in raw_messages:
                        msg = await self._process_single_message(
                            raw_messages[message_id], channel_id
                        )
                        if msg:
                            processed_messages.append(msg)
                else:
                    # 组消息 - 合并处理
                    group_raw_messages = [raw_messages[id] for id in group_ids if id in raw_messages]
                    if group_raw_messages:
                        merged_msg = await self._process_group_messages(
                            group_raw_messages, channel_id
                        )
                        if merged_msg:
                            processed_messages.append(merged_msg)
            
            logger.info(f"成功处理 {len(processed_messages)}/{len(message_groups)} 个消息组")
            return processed_messages
            
        except Exception as e:
            logger.error(f"获取和处理Telegram消息失败: {e}")
            return []
    
    async def _process_channel_messages(self, channel: dict, checkpoint: int):
        """处理单个频道的消息"""
        channel_id = channel['channel_id']
        channel_name = channel.get('channel_name', channel.get('channel_title', 'Untitled'))
        
        logger.info(f"处理频道 {channel_name}, checkpoint: {checkpoint}")
        
        try:
            # 获取频道实体
            entity = await self.channel_manager.get_channel_entity(channel_id, self.telethon_client)
            if not entity:
                logger.error(f"无法获取频道 {channel_name} 的实体，跳过")
                return
            
            # 1. 获取要采集的ID组列表
            message_groups = await self._get_message_ids_to_collect(entity, channel_id, checkpoint)
            if not message_groups:
                logger.info(f"频道 {channel_name} 没有新消息需要采集")
                return
            
            # 统计总消息数
            total_message_count = sum(len(group) for group in message_groups)
            logger.info(f"频道 {channel_name} 将采集 {total_message_count} 条消息（{len(message_groups)} 个消息组）")
            
            # 2. 从Telegram获取消息
            telegram_messages = await self._fetch_telegram_messages(entity, message_groups)
            if not telegram_messages:
                logger.warning(f"频道 {channel_name} 没有获取到有效消息")
                return
            
            # 3. 循环处理每条CollectedMessage消息
            processed_count = 0
            for collected_message in telegram_messages:
                try:
                    # CollectedMessage已经完成了媒体下载和内容解析
                    # 直接进入存储和处理管道
                    if collected_message:
                        # 更新checkpoint
                        await self.checkpoint_manager.update_checkpoint(channel_id, collected_message.message_id)
                        processed_count += 1
                        logger.debug(f"消息 #{collected_message.message_id} 处理完成")
                except Exception as e:
                    logger.error(f"处理消息 #{collected_message.message_id if collected_message else 'unknown'} 失败: {e}")
                    continue
            
            logger.info(f"频道 {channel_name} 采集完成，成功处理 {processed_count}/{len(telegram_messages)} 条消息（共 {len(message_groups)} 个消息组）")
            
        except Exception as e:
            logger.error(f"处理频道 {channel_name} 时出错: {e}")
    
    async def shutdown(self):
        """关闭采集器，清理资源"""
        logger.info("关闭TelegramMessageCollector")
        
        if self.telethon_client and self.telethon_client.is_connected():
            await self.telethon_client.disconnect()
        
        self._initialized = False
        logger.info("TelegramMessageCollector已关闭")
    
    async def _batch_get_raw_messages(self, entity, message_groups: List[List[int]]) -> Dict[int, TLMessage]:
        """批量获取原始Telegram消息"""
        try:
            # 将嵌套列表展平为单一ID列表
            all_message_ids = []
            for group in message_groups:
                all_message_ids.extend(group)
            
            if not all_message_ids:
                return {}
            
            # 批量获取所有消息
            messages = await self.telethon_client.get_messages(entity, ids=all_message_ids)
            
            # 构建ID到消息的映射
            message_map = {}
            for msg in messages:
                if msg is not None:
                    message_map[msg.id] = msg
            
            logger.debug(f"批量获取消息成功: {len(message_map)}/{len(all_message_ids)} 条")
            return message_map
            
        except Exception as e:
            logger.error(f"批量获取原始消息失败: {e}")
            return {}
    
    async def _process_single_message(self, message: TLMessage, channel_id: str) -> Optional[CollectedMessage]:
        """处理单个消息，包括媒体下载"""
        try:
            # 下载媒体（如果有）
            media_info = None
            if message.media:
                from app.services.media_handler import MediaHandler
                media_handler = MediaHandler()
                media_info = await media_handler.download_media_with_retry(
                    self.telethon_client, message, message.id
                )
            
            # 创建CollectedMessage
            return CollectedMessage(
                channel_id=channel_id,
                message_id=message.id,
                grouped_id=getattr(message, 'grouped_id', None),
                content=message.text or "",
                media_info=media_info,
                timestamp=message.date,
                raw_data={
                    'views': getattr(message, 'views', None),
                    'forwards': getattr(message, 'forwards', None),
                    'edit_date': getattr(message, 'edit_date', None)
                }
            )
            
        except Exception as e:
            logger.error(f"处理单个消息失败 {message.id}: {e}")
            return None
    
    async def _process_group_messages(self, group_messages: List[TLMessage], channel_id: str) -> Optional[CollectedMessage]:
        """处理组消息，合并内容和媒体"""
        try:
            if not group_messages:
                return None
            
            # 确定主消息（第一条有文本的，或第一条）
            primary_msg = next((msg for msg in group_messages if msg.text), group_messages[0])
            
            # 收集所有文本内容
            all_texts = [msg.text for msg in group_messages if msg.text]
            merged_content = '\n'.join(all_texts) if all_texts else ''
            
            # 批量下载所有媒体
            media_files = []
            from app.services.media_handler import MediaHandler
            media_handler = MediaHandler()
            
            for msg in group_messages:
                if msg.media:
                    media_info = await media_handler.download_media_with_retry(
                        self.telethon_client, msg, msg.id
                    )
                    if media_info:
                        media_files.append(media_info)
            
            # 构建组合媒体信息
            combined_media_info = None
            if media_files:
                combined_media_info = {
                    'is_group': True,
                    'media_files': media_files,
                    'total_count': len(media_files),
                    'media_types': list(set(m.get('media_type', 'unknown') for m in media_files))
                }
            
            # 创建CollectedMessage
            return CollectedMessage(
                channel_id=channel_id,
                message_id=primary_msg.id,
                grouped_id=getattr(primary_msg, 'grouped_id', None),
                content=merged_content,
                media_info=combined_media_info,
                timestamp=primary_msg.date,
                raw_data={
                    'group_size': len(group_messages),
                    'message_ids': [msg.id for msg in group_messages],
                    'views': getattr(primary_msg, 'views', None),
                    'forwards': getattr(primary_msg, 'forwards', None)
                }
            )
            
        except Exception as e:
            logger.error(f"处理组消息失败: {e}")
            return None


# 全局实例
message_collector = TelegramMessageCollector()