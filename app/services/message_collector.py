"""
消息采集处理架构
"""
import logging
import asyncio
import json
import time
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import Message as TLMessage

from app.core.path_config import PathConfig
from app.storage.redis_manager import redis_manager
from app.utils.timezone import get_current_time
from app.services.simple_tail_filter import filter_tail_content
from app.services.filters.markdown_filter import MarkdownFilter
from app.services.filters.separator_filter import SeparatorFilter
from app.services.filters.base import FilterContext

logger = logging.getLogger(__name__)

@dataclass
class LocalMessage:
    """完整的消息结构 - 包含前端所需的全部字段"""
    # 基础标识
    channel_id: str
    message_id: int
    grouped_id: Optional[str] = None
    
    # 内容字段
    content: str = ""
    filtered_content: str = ""
    
    # 媒体字段
    media_info: Optional[Dict] = None
    media_type: Optional[str] = None
    media_display_url: Optional[str] = None
    media_path: Optional[str] = None
    media_url: Optional[str] = None
    
    # 组合消息字段
    is_combined: bool = False
    media_group_display: Optional[List] = None
    media_group_info: Optional[Dict] = None
    
    # 时间字段
    timestamp: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    # 状态和过滤字段
    status: str = "pending"
    filter_reason: Optional[str] = None
    removed_hidden_links: Optional[List] = None
    
    # 频道字段
    source_channel: Optional[str] = None
    source_channel_link_prefix: Optional[str] = None
    source_channel_title: Optional[str] = None
    source_channel_username: Optional[str] = None
    
    # 扩展字段
    details: Optional[Dict] = None
    entities: Optional[List] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = get_current_time()
        if self.filtered_content == "":
            self.filtered_content = self.content
        if self.source_channel is None:
            self.source_channel = self.channel_id

class ConfigManager:
    """系统配置管理器"""
    
    def __init__(self):
        self.target_channel_id: Optional[str] = None
        self.review_group_id: Optional[str] = None  
        self.history_limit: int = 10
        self.collection_enabled: bool = False
        self._system_mtime = 0
    
    async def load_config(self):
        """检测系统配置文件变化并动态加载"""
        system_mtime = PathConfig.SYSTEM_CONFIG_FILE.stat().st_mtime
        
        if system_mtime != self._system_mtime:
            with open(PathConfig.SYSTEM_CONFIG_FILE, 'r', encoding='utf-8') as f:
                system_config = json.load(f)
            self.target_channel_id = system_config["target.channel_id"]["value"]
            self.review_group_id = system_config["review.group_id"]["value"]
            self.history_limit = int(system_config["source.history_limit"]["value"])
            self.collection_enabled = system_config.get("collection.enabled", {}).get("value", False)
            self._system_mtime = system_mtime
            logger.info(f"系统配置已更新: 目标频道={self.target_channel_id}, 审核群={self.review_group_id}, 历史消息数={self.history_limit}, 采集开关={self.collection_enabled}")
    
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
    
    async def get_collection_enabled(self) -> bool:
        """获取采集开关配置"""
        await self.load_config()
        return self.collection_enabled

class ChannelManager:
    """频道管理器 - 专注频道相关功能"""
    
    def __init__(self):
        self.source_channels: List[Dict] = []    # 源频道列表缓存
        self.entities: Dict[str, Any] = {}       # Telethon实体缓存
        
        # 频道配置文件修改时间缓存
        self._channels_mtime = 0
    
    async def load_config(self):
        """检测频道配置文件变化并动态加载"""
        channels_mtime = PathConfig.CHANNELS_CONFIG_FILE.stat().st_mtime
        
        # 只有频道配置文件变化时才重新加载
        if channels_mtime != self._channels_mtime:
            with open(PathConfig.CHANNELS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.source_channels = json.load(f)
            self._channels_mtime = channels_mtime
            logger.info(f"频道配置已更新: {len(self.source_channels)}个源频道")

    async def get_all_source_channels(self) -> List[Dict]:
        """获取所有源频道列表"""
        await self.load_config()
        return self.source_channels
    
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

class ContentProcessingPipeline:
    """内容处理管道 - 尾部过滤 + markdown过滤 + 分隔符过滤处理"""
    
    def __init__(self):
        """初始化处理管道"""
        self.markdown_filter = MarkdownFilter()
        self.separator_filter = SeparatorFilter()
    
    async def process(self, message: LocalMessage) -> LocalMessage:
        """执行内容过滤处理 - 尾部过滤 → markdown过滤 → 分隔符过滤"""
        try:
            if not message.content:
                return message
            
            current_content = message.content
            filter_reasons = []
            
            # 1. 尾部过滤处理（先处理，删除尾部推广内容）
            filtered_content, is_filtered, removed_content, analysis = filter_tail_content(current_content)
            if is_filtered:
                current_content = filtered_content
                filter_reasons.append(f"尾部过滤: {analysis.get('reason', '检测到推广内容')}")
                logger.info(f"消息 {message.message_id} 尾部过滤: {len(message.content)} -> {len(current_content)} 字符")
            else:
                logger.debug(f"消息 {message.message_id} 无尾部内容需要过滤")
            
            # 2. markdown过滤处理（后处理，使用原始entities，位置仍准确）
            if message.entities:
                # 创建FilterContext
                context = FilterContext(
                    message_id=message.message_id,
                    channel_id=message.channel_id
                )
                context.add_metadata('entities', message.entities)
                
                # 执行markdown过滤
                markdown_result = await self.markdown_filter.filter(current_content, context)
                if markdown_result.passed and markdown_result.filtered_content != current_content:
                    current_content = markdown_result.filtered_content
                    filter_reasons.append(f"markdown过滤: {markdown_result.reason}")
                    logger.info(f"消息 {message.message_id} markdown过滤完成，最终: {len(current_content)} 字符")
                else:
                    logger.debug(f"消息 {message.message_id} 无markdown链接需要处理")
            
            # 3. 分隔符过滤处理（在markdown过滤后执行）
            separator_result, separator_stats = self.separator_filter.filter_content(current_content)
            if separator_stats.get('removed_lines_count', 0) > 0:
                current_content = separator_result
                filter_reasons.append(f"分隔符过滤: 移除{separator_stats['removed_lines_count']}行分隔符")
                logger.info(f"消息 {message.message_id} 分隔符过滤: 移除了{separator_stats['removed_lines_count']}行")
            else:
                logger.debug(f"消息 {message.message_id} 无分隔符需要过滤")
            
            # 更新消息内容
            message.filtered_content = current_content
            if filter_reasons:
                message.filter_reason = "; ".join(filter_reasons)
            
            return message
            
        except Exception as e:
            logger.error(f"内容处理失败 {message.message_id}: {e}")
            # 处理失败时返回原消息
            return message

class TelegramMessageCollector:
    """消息采集器 - 统一入口"""
    
    def __init__(self):
        # Telegram核心组件 - 延迟导入避免启动问题
        from app.telegram.dual_session_manager import dual_session_manager
        self.session_manager = dual_session_manager
        
        self.telethon_client: Optional[TelegramClient] = None
        
        # 配置和频道管理
        self.config_manager = ConfigManager()
        self.channel_manager = ChannelManager()
        
        # 业务组件
        self.checkpoint_manager = CheckpointManager()
        self.content_pipeline = ContentProcessingPipeline()
        
        # 初始化标志
        self._initialized = False
        
        # 信号控制标志
        self.running = True
    
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
            
            # 4. 初始化配置
            await self.config_manager.load_config()
            await self.channel_manager.load_config()
            
            source_channels = await self.channel_manager.get_all_source_channels()
            target_channel = await self.config_manager.get_target_channel_id()
            review_group = await self.config_manager.get_review_group_id()
            
            logger.info(f"配置初始化完成: {len(source_channels)}个源频道, 目标频道={target_channel}, 审核群={review_group}")
            
            self._initialized = True
            logger.info("TelegramMessageCollector初始化完成")
            
        except Exception as e:
            logger.error(f"TelegramMessageCollector初始化失败: {e}")
            raise
    
    async def start_collecting(self):
        """开始连续消息采集循环"""
        logger.info("开始连续消息采集循环")
        
        while True:
            loop_start_time = time.time()
            
            try:
                # 检查是否应该继续采集
                if not await self._should_continue():
                    logger.info("采集已停止")
                    break
                
                # 执行单轮采集
                await self._do_single_collection_round()
                
                # 再次检查，确保及时退出
                if not await self._should_continue():
                    logger.info("单轮采集完成后检测到停止信号")
                    break
                
            except Exception as e:
                logger.error(f"采集轮次失败: {e}")
                # 继续下一轮，不中断整个循环
            
            # 智能间隔等待
            await self._smart_wait(loop_start_time)
        
        logger.info("连续采集循环已结束")
    
    async def _do_single_collection_round(self):
        """执行单轮完整采集"""
        # 1. 加载频道列表
        channels = await self.channel_manager.get_all_source_channels()
        
        if not channels:
            logger.debug("没有配置源频道，跳过本轮采集")
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
        
        logger.info("单轮采集完成")
    
    async def _smart_wait(self, start_time: float):
        """智能间隔等待，确保不会过频采集"""
        runtime = time.time() - start_time
        min_interval = 30  # 最小间隔30秒
        
        if runtime < min_interval:
            wait_time = min_interval - runtime
            logger.info(f"本轮采集耗时 {runtime:.1f}s，等待 {wait_time:.1f}s 后继续下轮")
            await asyncio.sleep(wait_time)
        else:
            logger.info(f"本轮采集耗时 {runtime:.1f}s，立即开始下轮")
    
    async def _get_message_ids_to_collect(self, entity, channel_id: str, checkpoint: int) -> List[List[int]]:
        """根据channel和checkpoint返回要采集的消息ID组列表"""
        try:
            if checkpoint == 0:
                # 首次采集：获取历史消息ID
                history_limit = await self.config_manager.get_history_limit()
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
                # 过滤空消息（无文本且无媒体）
                if not msg.message and not msg.media:
                    logger.info(f"过滤空消息 {msg.id}：无文本内容且无媒体")
                    continue
                
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
                history_limit = await self.config_manager.get_history_limit()
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
    
    async def _fetch_telegram_messages(self, entity, message_groups: List[int], channel: dict) -> Optional[LocalMessage]:
        """从Telegram获取消息并处理媒体下载和组消息合并"""
        try:
            if not message_groups:
                return None
            
            # 1. 直接获取消息
            messages = await self.telethon_client.get_messages(entity, ids=message_groups)
            if not messages:
                return None
            
            # 2. 处理消息
            channel_id = str(entity.id) if hasattr(entity, 'id') else "unknown"
            
            if len(message_groups) == 1:
                # 单条消息
                if messages[0]:
                    msg = await self._process_single_message(messages[0], channel_id, channel)
                    if msg:
                        logger.info(f"成功处理1个消息")
                        return msg
            else:
                # 组消息 - 过滤掉None并合并处理
                valid_messages = [msg for msg in messages if msg is not None]
                if valid_messages:
                    merged_msg = await self._process_group_messages(valid_messages, channel_id, channel)
                    if merged_msg:
                        logger.info(f"成功处理消息组(共{len(message_groups)}个子消息)")
                        return merged_msg
            
            return None
            
        except Exception as e:
            logger.error(f"获取和处理Telegram消息失败: {e}")
            return None
    
    async def _process_channel_messages(self, channel: dict, checkpoint: int):
        """处理单个频道的消息"""
        channel_id = channel['channel_id']
        channel_name = channel.get('channel_name', channel.get('channel_title', 'Untitled'))
        
        logger.info(f"处理频道 {channel_name}, checkpoint: {checkpoint}")
        
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
        
        # 2. 循环处理每个消息组
        processed_count = 0
        
        for message_group in message_groups:
            collected_message = await self._fetch_telegram_messages(entity, message_group, channel)
            
            # 检查是否获取到消息
            if not collected_message:
                logger.warning(f"消息组 {message_group} 获取失败，跳过")
                continue
            
            # 3. 处理这个组的消息 - 内容过滤
            collected_message = await self.content_pipeline.process(collected_message)

            # 4. 保存消息到Redis,更新状态索引和频道索引
            try:
                # 直接使用LocalMessage对象属性构建存储数据
                message_data = {
                    'channel_id': channel_id,
                    'message_id': collected_message.message_id,
                    'grouped_id': collected_message.grouped_id,
                    'content': collected_message.content,
                    'filtered_content': collected_message.filtered_content,
                    'media_info': collected_message.media_info,
                    'media_type': collected_message.media_type,
                    'media_display_url': collected_message.media_display_url,
                    'media_path': collected_message.media_path,
                    'media_url': collected_message.media_url,
                    'is_combined': collected_message.is_combined,
                    'media_group_display': collected_message.media_group_display,
                    'media_group_info': collected_message.media_group_info,
                    'timestamp': collected_message.timestamp.isoformat() if collected_message.timestamp else None,
                    'created_at': collected_message.created_at.isoformat() if collected_message.created_at else None,
                    'status': collected_message.status,
                    'filter_reason': collected_message.filter_reason,
                    'removed_hidden_links': collected_message.removed_hidden_links,
                    'source_channel': collected_message.source_channel,
                    'source_channel_link_prefix': f"https://t.me/{channel.get('channel_name', '').lstrip('@')}",
                    'source_channel_title': channel.get('channel_title'),
                    'source_channel_username': channel.get('channel_name'),
                    'details': collected_message.details,
                    'entities': collected_message.entities
                }
                
                # 保存到Redis
                success = redis_manager.save_message(
                    channel_id, 
                    collected_message.message_id, 
                    message_data
                )
                
                if success:
                    processed_count += 1
                    
                    # 5. 立即更新checkpoint
                    checkpoint_id = collected_message.message_id
                    
                    # 如果是组消息，使用组内最大的message_id
                    if hasattr(collected_message, 'grouped_id') and collected_message.grouped_id:
                        if isinstance(message_group, list):
                            # 获取组内所有消息的最大ID
                            checkpoint_id = max([msg for msg in message_group])
                        
                    try:
                        await self.checkpoint_manager.update_checkpoint(channel_id, checkpoint_id)
                        logger.debug(f"消息 {collected_message.message_id} 存储成功，checkpoint更新为: {checkpoint_id}")
                        
                        # 🎯 数据安全检查点 - checkpoint更新完成后检查退出条件
                        if not await self._should_continue():
                            logger.info(f"频道 {channel_name} 检测到停止信号，已安全保存进度至消息 {checkpoint_id}")
                            return  # 优雅退出，数据已安全保存
                            
                    except Exception as checkpoint_e:
                        logger.error(f"更新checkpoint {checkpoint_id} 失败: {checkpoint_e}")
                else:
                    logger.error(f"消息 {collected_message.message_id} 存储失败")
                    
            except Exception as e:
                logger.error(f"处理消息组 {message_group} 时发生错误: {e}")
                continue
        
        logger.info(f"频道 {channel_name} 采集完成，成功处理 {processed_count} 条消息（共 {len(message_groups)} 个消息组）")
    
    async def _process_single_message(self, message: TLMessage, channel_id: str, channel: dict) -> Optional[LocalMessage]:
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
            
            # 创建LocalMessage
            return LocalMessage(
                channel_id=channel_id,
                message_id=message.id,
                grouped_id=getattr(message, 'grouped_id', None),
                content=message.message or "",
                filtered_content=message.message or "",  # 暂时与content相同
                media_info=media_info,
                media_type=media_info.get('media_type') if media_info else None,
                media_path=media_info.get('file_path') if media_info else None,
                media_url=media_info.get('file_path') if media_info else None,
                is_combined=False,  # 单条消息不是组合消息
                timestamp=message.date,
                status="pending",
                source_channel=channel_id,
                source_channel_title=channel.get('channel_name', channel.get('channel_title')),
                source_channel_username=channel.get('channel_username'),
                entities=message.entities
            )
            
        except Exception as e:
            logger.error(f"处理单个消息失败 {message.id}: {e}")
            return None
    
    async def _process_group_messages(self, group_messages: List[TLMessage], channel_id: str, channel: dict) -> Optional[LocalMessage]:
        """处理组消息，合并内容和媒体"""
        try:
            if not group_messages:
                return None
            
            # 确定主消息（第一条有文本的，或第一条）
            primary_msg = next((msg for msg in group_messages if msg.message), group_messages[0])
            
            # 收集所有文本内容
            all_texts = [msg.message for msg in group_messages if msg.message]
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
            
            # 组合媒体信息 - 使用简化逻辑
            
            # 创建LocalMessage
            return LocalMessage(
                channel_id=channel_id,
                message_id=primary_msg.id,
                grouped_id=getattr(primary_msg, 'grouped_id', None),
                content=merged_content,
                filtered_content=merged_content,  # 暂时与content相同
                media_info=None,  # 组消息不需要单独的 media_info
                media_type="group",  # 组合消息统一使用 "group" 类型
                is_combined=True,  # 组合消息
                media_group_display=media_files,  # 媒体组显示数据
                media_group_info={
                    'total_count': len(media_files),
                    'display_text': f"{len(media_files)}个媒体文件"
                } if media_files else None,
                timestamp=primary_msg.date,
                status="pending",
                source_channel=channel_id,
                source_channel_title=channel.get('channel_name', channel.get('channel_title')),
                source_channel_username=channel.get('channel_username'),
                entities=primary_msg.entities
            )
            
        except Exception as e:
            logger.error(f"处理组消息失败: {e}")
            return None
    
    async def _should_continue(self) -> bool:
        """检查是否应该继续采集 - 基于信号控制 + collection.enabled配置"""
        # 首先检查信号控制
        if not self.running:
            logger.info("检测到停止信号，准备停止采集")
            return False
        
        try:
            # 检查collection.enabled配置项
            collection_enabled = await self.config_manager.get_collection_enabled()
            
            if not collection_enabled:
                logger.info("检测到collection.enabled=False，准备停止采集")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查采集继续条件失败: {e}")
            # 出错时停止采集，确保安全
            return False

# 全局实例
message_collector = TelegramMessageCollector()