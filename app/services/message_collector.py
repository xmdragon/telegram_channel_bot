"""
消息采集处理架构
"""
import logging
import asyncio
import json
import time
from typing import Optional, Dict, List, Any, Tuple, Union
from dataclasses import dataclass
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import Message as TLMessage

from app.core.path_config import PathConfig
from app.storage.redis_manager import redis_manager
from app.utils.timezone import get_current_time
from app.services.content_processor import ContentProcessor, LocalMessage as ProcessorLocalMessage
from app.utils.error_formatter import TelethonErrorHandler

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
    thumbnail_url: Optional[str] = None
    
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
    reject_reason: Optional[str] = None
    
    # 广告检测字段
    is_ad: bool = False
    ad_weight: float = 0.0
    hit_keywords: Optional[List[Dict[str, Union[str, float]]]] = None  # 命中的关键词及权重

    # 去重检测字段
    duplicate_status: str = "none"  # "none", "suspected", "confirmed", "not_duplicate"
    original_message_id: Optional[str] = None  # 格式："channel_id:message_id"
    similarity_score: float = 0.0
    duplicate_reason: Optional[str] = None  # "content_similar", "media_similar", "combined"

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

class CollectorConfigManager:
    """系统配置管理器"""
    
    def __init__(self):
        self.target_channel_id: Optional[str] = None
        self.history_limit: int = 10
        self.collection_enabled: bool = False
        self.auto_reject_ads: bool = True  # 是否自动拒绝广告
        self.max_media_size_mb: int = 200  # 媒体文件大小限制(MB)
        self.video_only: bool = False  # 仅采集视频消息
        self.comment_keywords: List[str] = []  # 评论区视频关键词
        self._system_mtime = 0
    
    async def load_config(self):
        """检测系统配置文件变化并动态加载"""
        system_mtime = PathConfig.SYSTEM_CONFIG_FILE.stat().st_mtime
        
        if system_mtime != self._system_mtime:
            with open(PathConfig.SYSTEM_CONFIG_FILE, 'r', encoding='utf-8') as f:
                system_config = json.load(f)
            self.target_channel_id = system_config["target.channel_id"]["value"]
            self.history_limit = int(system_config["source.history_limit"]["value"])
            collection_value = system_config.get("collection.enabled", {}).get("value", "false")
            self.collection_enabled = collection_value.lower() == "true" if isinstance(collection_value, str) else bool(collection_value)
            
            # 加载自动拒绝广告配置
            auto_reject_value = system_config.get("target.auto_reject_ads", {}).get("value", "true")
            self.auto_reject_ads = auto_reject_value.lower() == "true" if isinstance(auto_reject_value, str) else bool(auto_reject_value)

            # 加载媒体大小限制配置
            max_media_size_value = system_config.get("collection.max_media_size_mb", {}).get("value", "200")
            self.max_media_size_mb = int(max_media_size_value)

            # 加载仅采集视频配置
            self.video_only = self._parse_bool_config(system_config.get("collection.video_only", {}).get("value", "false"))

            # 加载评论区视频关键词
            kw_raw = system_config.get("collection.comment_keywords", {}).get("value", "[]")
            if isinstance(kw_raw, str):
                try:
                    kw_raw = json.loads(kw_raw)
                except (json.JSONDecodeError, TypeError):
                    kw_raw = []
            self.comment_keywords = [k.strip() for k in kw_raw if isinstance(k, str) and k.strip()] if isinstance(kw_raw, list) else []

            # 加载过滤器配置
            self.filter_enabled = self._parse_bool_config(system_config.get("filter.enabled", {}).get("value", "false"))
            self.tail_filter = self._parse_bool_config(system_config.get("filter.tail_filter", {}).get("value", "true"))
            self.separator_filter = self._parse_bool_config(system_config.get("filter.separator", {}).get("value", "true"))
            self.markdown_filter = self._parse_bool_config(system_config.get("filter.markdown", {}).get("value", "true"))
            self.ad_detector = self._parse_bool_config(system_config.get("filter.ad_detector", {}).get("value", "false"))

            self._system_mtime = system_mtime
            logger.debug(f"系统配置已更新: 目标频道={self.target_channel_id}, 历史消息数={self.history_limit}, 采集开关={self.collection_enabled}, 自动拒绝广告={self.auto_reject_ads}, 媒体大小限制={self.max_media_size_mb}MB")
            logger.debug(f"过滤器配置: 主开关={self.filter_enabled}, 尾部={self.tail_filter}, 分隔符={self.separator_filter}, Markdown={self.markdown_filter}, 广告检测={self.ad_detector}")
    
    async def get_target_channel_id(self) -> Optional[str]:
        """获取目标频道ID"""
        await self.load_config()
        return self.target_channel_id
    
    
    async def get_history_limit(self) -> int:
        """获取历史消息采集数配置"""
        await self.load_config()
        return self.history_limit
    
    async def get_collection_enabled(self) -> bool:
        """获取采集开关配置"""
        await self.load_config()
        return self.collection_enabled

    async def get_max_media_size_mb(self) -> int:
        """获取媒体文件大小限制(MB)"""
        await self.load_config()
        return self.max_media_size_mb
    
    async def get_auto_reject_ads(self) -> bool:
        """获取是否自动拒绝广告配置"""
        await self.load_config()
        return self.auto_reject_ads

    async def get_video_only(self) -> bool:
        """获取是否仅采集视频消息"""
        await self.load_config()
        return self.video_only

    async def get_comment_keywords(self) -> List[str]:
        """获取评论区视频关键词列表"""
        await self.load_config()
        return self.comment_keywords

    def _parse_bool_config(self, value) -> bool:
        """解析布尔配置值"""
        if isinstance(value, str):
            return value.lower() == "true"
        return bool(value)

    def get_filter_config(self) -> dict:
        """获取过滤器配置"""
        return {
            'enabled': self.filter_enabled,
            'tail_filter': self.tail_filter,
            'separator_filter': self.separator_filter,
            'markdown_filter': self.markdown_filter,
            'ad_detector': self.ad_detector
        }

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
            logger.debug(f"频道配置已更新: {len(self.source_channels)}个源频道")

    async def get_all_source_channels(self) -> List[Dict]:
        """获取所有源频道列表"""
        await self.load_config()
        return self.source_channels
    
    async def get_channel_entity(self, channel: dict, client: TelegramClient):
        """获取频道Telethon实体（带缓存）"""
        channel_id = channel.get('channel_id')
        channel_name = channel.get('channel_name')
        
        # 使用channel_id作为缓存key
        if channel_id and channel_id in self.entities:
            return self.entities[channel_id]
        
        # 优先尝试用户名（对公有频道更可靠）
        if channel_name:
            try:
                username = channel_name.lstrip('@')  # 去掉@前缀
                entity = await client.get_entity(username)
                if channel_id:
                    self.entities[channel_id] = entity
                logger.info(f"使用用户名 {channel_name} 成功获取频道实体")
                return entity
            except Exception as e:
                logger.debug(f"使用用户名 {channel_name} 获取失败: {e}")
        
        # 回退到ID方式
        if channel_id:
            try:
                entity = await client.get_entity(int(channel_id))
                self.entities[channel_id] = entity
                logger.info(f"使用ID {channel_id} 成功获取频道实体")
                return entity
            except Exception as e:
                logger.error(f"获取频道实体失败 {channel_name or channel_id}: {e}")
        
        return None

class CheckpointManager:
    """Checkpoint管理器"""

    def __init__(self):
        from app.storage.channel_store import RedisChannelStore
        self._store = RedisChannelStore()

    def get_checkpoint(self, channel_id: str) -> int:
        """获取checkpoint，默认返回0"""
        try:
            result = self._store.get_checkpoint(channel_id)
            return result if result is not None else 0
        except Exception as e:
            logger.error(f"获取checkpoint失败 {channel_id}: {e}")
            return 0

    async def update_checkpoint(self, channel_id: str, message_id: int):
        """异步更新checkpoint（保持单调递增）"""
        try:
            current = self.get_checkpoint(channel_id)
            if message_id <= current:
                return
            await asyncio.get_event_loop().run_in_executor(
                None, self._store.set_checkpoint, channel_id, message_id)
        except Exception as e:
            logger.error(f"更新checkpoint失败 {channel_id}: {e}")

class TelegramMessageCollector:
    """消息采集器 - 统一入口"""
    
    def __init__(self):
        # Telegram核心组件 - 延迟导入避免启动问题
        from app.telegram.dual_session_manager import dual_session_manager
        self.session_manager = dual_session_manager
        
        self.telethon_client: Optional[TelegramClient] = None
        
        # 配置和频道管理
        self.config_manager = CollectorConfigManager()
        self.channel_manager = ChannelManager()
        
        # 业务组件
        self.checkpoint_manager = CheckpointManager()
        self.content_processor = ContentProcessor()
        
        # 初始化标志
        self._initialized = False

        # 错误处理器
        self._error_handler = TelethonErrorHandler(logger)
        
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

            logger.info(f"配置初始化完成: {len(source_channels)}个源频道, 目标频道={target_channel}")
            
            self._initialized = True
            logger.info("TelegramMessageCollector初始化完成")
            
        except Exception as e:
            logger.error(f"TelegramMessageCollector初始化失败: {e}")
            raise
    
    async def start_collecting(self):
        """开始连续消息采集循环"""
        logger.info("消息采集服务已启动，等待配置...")
        
        while True:
            try:
                # 首先检查停止信号（服务退出）
                if not self.running:
                    logger.info("检测到停止信号，服务将退出")
                    break
                
                # 直接执行采集（配置检测在消息组级别进行）
                loop_start_time = time.time()
                
                # 执行单轮采集
                await self._do_single_collection_round()
                
                # 再次检查退出信号
                if not self.running:
                    logger.info("单轮采集完成后检测到停止信号")
                    break
                
                # 智能间隔等待
                await self._smart_wait(loop_start_time)
                
            except Exception as e:
                logger.error(f"采集轮次失败: {e}")
                await asyncio.sleep(30)  # 错误时等待30秒再重试
        
        logger.info("连续采集循环已结束")
    
    async def _do_single_collection_round(self):
        """执行单轮完整采集（支持断点续传）"""
        # 1. 加载频道列表
        channels = await self.channel_manager.get_all_source_channels()

        if not channels:
            logger.debug("没有配置源频道，跳过本轮采集")
            return

        # 2. 获取上次中断的位置（断点续传）
        try:
            last_index = redis_manager.cache_get("collector:current_channel_index")
            start_index = int(last_index) if last_index else 0

            if start_index > 0 and start_index < len(channels):
                logger.info(f"检测到上次中断位置，从第 {start_index + 1} 个频道继续采集")
            else:
                start_index = 0
        except Exception as e:
            logger.warning(f"获取采集进度失败: {e}，从头开始")
            start_index = 0

        logger.info(f"开始处理 {len(channels)} 个源频道，从位置 {start_index + 1} 开始")

        # 3. 遍历处理每个频道（支持断点续传）
        for i in range(start_index, len(channels)):
            channel = channels[i]
            channel_id = channel['channel_id']
            channel_name = channel.get('channel_name', channel.get('channel_title', 'Untitled'))

            # 删除处理频道的进度日志 - 将在最后汇总

            # 检查checkpoint并处理消息
            checkpoint = self.checkpoint_manager.get_checkpoint(channel_id)
            await self._process_channel_messages(channel, checkpoint)

            # 4. 更新当前处理位置到Redis（每个频道完成后保存进度）
            try:
                # 保存下一个要处理的频道索引
                next_index = i + 1
                if next_index < len(channels):
                    redis_manager.cache_set("collector:current_channel_index", str(next_index), expire=3600)
                    logger.debug(f"已保存采集进度: 下次从第 {next_index + 1} 个频道开始")
                else:
                    # 所有频道处理完成，清除进度记录
                    redis_manager.cache_delete("collector:current_channel_index")
                    logger.debug("本轮所有频道处理完成，清除进度记录")
            except Exception as e:
                logger.error(f"保存采集进度失败: {e}")

        # 5. 确保一轮完成后清除进度（防止遗留）
        try:
            redis_manager.cache_delete("collector:current_channel_index")
        except:
            pass

        # 删除单轮采集完成的日志
    
    async def _smart_wait(self, start_time: float):
        """智能间隔等待，确保不会过频采集，并支持配置热更新"""
        runtime = time.time() - start_time
        min_interval = 30  # 最小间隔30秒
        
        if runtime < min_interval:
            wait_time = min_interval - runtime
            logger.info(f"本轮采集耗时 {runtime:.1f}s，等待 {wait_time:.1f}s 后继续下轮")
            
            # 分段等待，每2秒检查一次配置
            check_interval = 2
            elapsed = 0
            
            while elapsed < wait_time:
                sleep_time = min(check_interval, wait_time - elapsed)
                await asyncio.sleep(sleep_time)
                elapsed += sleep_time
                
                # 检查配置变更
                if not await self._should_continue():
                    logger.info("等待期间检测到停止信号")
                    return
        else:
            logger.info(f"本轮采集耗时 {runtime:.1f}s，立即开始下轮")
    
    async def _get_message_ids_to_collect(self, entity, channel_id: str, checkpoint: int) -> List[List[int]]:
        """根据channel和checkpoint返回要采集的消息ID组列表 - 修复组消息完整性问题"""
        try:
            if checkpoint == 0:
                # 首次采集：获取历史消息ID
                history_limit = await self.config_manager.get_history_limit()
                # 🔧 修复：增加安全系数，确保组消息不被截断
                actual_limit = history_limit * 8  # 从5倍增加到8倍，更安全
                # 获取最新的actual_limit条消息ID
                messages = await self.telethon_client.get_messages(entity, limit=actual_limit)
            else:
                # 🔧 修复：增量采集时扩展范围，避免组消息边界问题
                # 先获取checkpoint之后的消息
                messages = await self.telethon_client.get_messages(entity, min_id=checkpoint, limit=None)
                messages = [msg for msg in messages if msg and msg.id > checkpoint]

                # 🆕 新增：检查是否有不完整的组消息，向前扩展
                if messages:
                    earliest_msg = min(messages, key=lambda m: m.id)
                    if hasattr(earliest_msg, 'grouped_id') and earliest_msg.grouped_id:
                        # 如果最早的消息是组消息，向前扩展获取完整组
                        logger.debug(f"检测到增量采集边界有组消息，向前扩展获取完整组")
                        try:
                            # 向前扩展10条消息，确保获取完整组
                            extended_messages = await self.telethon_client.get_messages(
                                entity,
                                max_id=earliest_msg.id,
                                limit=10
                            )
                            # 过滤出属于同一组的消息
                            group_messages = [
                                msg for msg in extended_messages
                                if msg and hasattr(msg, 'grouped_id') and msg.grouped_id == earliest_msg.grouped_id
                            ]
                            # 添加到消息列表中
                            messages.extend(group_messages)
                            logger.debug(f"向前扩展获取到 {len(group_messages)} 条组消息")
                        except Exception as e:
                            logger.warning(f"向前扩展组消息失败: {e}")

            if not messages:
                return []

            # 🔧 修复：改进分组逻辑，确保组消息完整性
            message_groups = {}  # {grouped_id: [msg_ids]}
            single_messages = []  # 单独消息
            incomplete_groups = set()  # 记录可能不完整的组

            for msg in messages:
                # 🔧 修复：放宽空消息判断，避免过度过滤组消息
                if not msg:
                    continue

                # 只过滤明确的空消息，对组消息更宽松
                if msg.grouped_id:
                    # 组消息：即使看起来是"空"的也要保留，可能是纯媒体
                    if msg.grouped_id not in message_groups:
                        message_groups[msg.grouped_id] = []
                    message_groups[msg.grouped_id].append(msg.id)
                else:
                    # 单独消息：应用空消息判断
                    is_empty, reason = self._is_empty_message(msg)
                    if not is_empty:
                        single_messages.append([msg.id])

            # 🆕 新增：检查组消息完整性
            for grouped_id, msg_ids in message_groups.items():
                if len(msg_ids) < 2:
                    # 组消息数量异常少，可能不完整
                    incomplete_groups.add(grouped_id)
                    logger.debug(f"检测到可能不完整的组: {grouped_id}, 消息数: {len(msg_ids)}")

            # 🆕 新增：对可能不完整的组进行扩展查找
            if incomplete_groups and checkpoint != 0:  # 只在增量采集时处理
                logger.debug(f"尝试修复 {len(incomplete_groups)} 个可能不完整的组")
                await self._extend_incomplete_groups(entity, message_groups, incomplete_groups)

            # 合并结果：组消息 + 单独消息
            all_groups = list(message_groups.values()) + single_messages

            # 🔧 按每组的最小ID升序排序，确保从旧到新处理，防止checkpoint倒退
            all_groups.sort(key=lambda group: min(group) if group else 0)

            # 🆕 新增：记录组消息统计
            group_count = len(message_groups)
            single_count = len(single_messages)
            total_msgs = sum(len(group) for group in message_groups.values()) + single_count
            logger.debug(f"消息分组完成: {group_count}个组消息({sum(len(g) for g in message_groups.values())}条), {single_count}个单消息, 总计{total_msgs}条")

            # 🎯 重要：只返回最近的history_limit个消息组
            if checkpoint == 0:  # 只在首次采集时限制
                history_limit = await self.config_manager.get_history_limit()
                if len(all_groups) > history_limit:
                    # 排序后取后面的history_limit个（ID较大的，即较新的消息）
                    result = all_groups[-history_limit:]
                    logger.debug(f"首次采集限制: 从{len(all_groups)}个组中取最新{len(result)}个")
                else:
                    result = all_groups
            else:
                result = all_groups  # 增量采集不限制

            return result

        except Exception as e:
            logger.error(f"获取消息ID失败: {e}")
            return []
    
    async def _extend_incomplete_groups(self, entity, message_groups: dict, incomplete_groups: set):
        """扩展不完整的组消息 - 尝试获取完整的组"""
        try:
            for grouped_id in incomplete_groups:
                current_msg_ids = message_groups[grouped_id]
                if not current_msg_ids:
                    continue

                logger.debug(f"尝试扩展不完整组 {grouped_id}, 当前消息: {current_msg_ids}")

                # 以当前组的消息ID为中心，向前后扩展查找
                center_id = min(current_msg_ids)
                extend_range = 15  # 向前后各扩展15条

                try:
                    # 向前扩展
                    before_messages = await self.telethon_client.get_messages(
                        entity,
                        max_id=center_id,
                        limit=extend_range
                    )

                    # 向后扩展
                    after_messages = await self.telethon_client.get_messages(
                        entity,
                        min_id=max(current_msg_ids),
                        limit=extend_range
                    )

                    # 合并所有消息
                    all_messages = before_messages + after_messages

                    # 过滤出属于同一组的消息
                    group_messages = [
                        msg for msg in all_messages
                        if msg and hasattr(msg, 'grouped_id') and msg.grouped_id == grouped_id
                    ]

                    # 提取新的消息ID
                    new_msg_ids = [msg.id for msg in group_messages if msg.id not in current_msg_ids]

                    if new_msg_ids:
                        # 更新组消息列表
                        message_groups[grouped_id].extend(new_msg_ids)
                        message_groups[grouped_id].sort()  # 保持ID顺序
                        logger.debug(f"组 {grouped_id} 扩展成功: 新增 {len(new_msg_ids)} 条消息，总计 {len(message_groups[grouped_id])} 条")
                    else:
                        logger.debug(f"组 {grouped_id} 无法扩展，保持原状")

                except Exception as e:
                    logger.warning(f"扩展组 {grouped_id} 失败: {e}")

        except Exception as e:
            logger.error(f"扩展不完整组消息失败: {e}")

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
            # Telegram超级群组/频道ID需要加上-100前缀
            if not channel_id.startswith('-') and channel_id != "unknown":
                channel_id = f'-100{channel_id}'
            
            if len(message_groups) == 1:
                # 单条消息
                if messages[0]:
                    msg = await self._process_single_message(messages[0], channel_id, channel)
                    if msg:
                        # 删除单个消息处理成功的日志
                        return msg
            else:
                # 组消息 - 过滤掉None并合并处理
                valid_messages = [msg for msg in messages if msg is not None]
                if valid_messages:
                    merged_msg = await self._process_group_messages(valid_messages, channel_id, channel)
                    if merged_msg:
                        # 删除消息组处理成功的日志
                        return merged_msg
            
            return None
            
        except Exception as e:
            self._error_handler.handle_error(e, "获取和处理Telegram消息失败")
            return None
    
    async def _process_channel_messages(self, channel: dict, checkpoint: int):
        """处理单个频道的消息"""
        channel_id = channel['channel_id']
        channel_name = channel.get('channel_name', channel.get('channel_title', 'Untitled'))
        
        # 删除处理频道checkpoint的日志
        
        # 获取频道实体
        entity = await self.channel_manager.get_channel_entity(channel, self.telethon_client)
        if not entity:
            logger.error(f"无法获取频道 {channel_name} 的实体，跳过")
            return

        # 同步更新频道信息
        await self._update_channel_info(channel, entity)

        # 1. 获取要采集的ID组列表
        message_groups = await self._get_message_ids_to_collect(entity, channel_id, checkpoint)
        if not message_groups:
            # 无新消息时不记录日志
            return
        
        # 统计总消息数（不记录日志，将在完成时汇总）
        total_message_count = sum(len(group) for group in message_groups)
        
        # 2. 循环处理每个消息组
        processed_count = 0
        
        for message_group in message_groups:
            # 检查采集是否仍然启用（消息级别的最细粒度检查）
            collection_enabled = await self.config_manager.get_collection_enabled()
            if not collection_enabled:
                logger.info(f"检测到采集已禁用，停止处理频道 {channel_name} 的剩余消息")
                break
            
            collected_message = await self._fetch_telegram_messages(entity, message_group, channel)

            # 检查是否获取到消息
            if not collected_message:
                # 可能是因为媒体文件太大被跳过，需要更新checkpoint
                checkpoint_id = message_group if isinstance(message_group, int) else max(message_group)
                logger.warning(f"消息组 {message_group} 获取失败或被跳过，直接更新checkpoint到 {checkpoint_id}")
                try:
                    await self.checkpoint_manager.update_checkpoint(channel_id, checkpoint_id)
                    logger.debug(f"checkpoint已更新为: {checkpoint_id} (跳过的消息)")
                except Exception as e:
                    logger.error(f"更新checkpoint {checkpoint_id} 失败: {e}")
                continue
            
            # 3. 处理这个组的消息 - 内容过滤（包含广告检测）
            # 获取最新的过滤器配置
            await self.config_manager.load_config()
            filter_config = self.config_manager.get_filter_config()
            collected_message = await self.content_processor.process(collected_message, self.config_manager, filter_config=filter_config)

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
                    'thumbnail_url': collected_message.thumbnail_url,
                    'is_combined': collected_message.is_combined,
                    'media_group_display': collected_message.media_group_display,
                    'media_group_info': collected_message.media_group_info,
                    'timestamp': collected_message.timestamp.isoformat() if collected_message.timestamp else None,
                    'created_at': collected_message.created_at.isoformat() if collected_message.created_at else None,
                    'status': collected_message.status,
                    'filter_reason': collected_message.filter_reason,
                    'removed_hidden_links': collected_message.removed_hidden_links,
                    'reject_reason': collected_message.reject_reason,
                    'is_ad': 'True' if collected_message.is_ad else 'False',
                    'ad_weight': collected_message.ad_weight,
                    'hit_keywords': collected_message.hit_keywords,  # 命中的关键词详情
                    # 去重检测字段
                    'duplicate_status': collected_message.duplicate_status,
                    'original_message_id': collected_message.original_message_id,
                    'similarity_score': collected_message.similarity_score,
                    'duplicate_reason': collected_message.duplicate_reason,
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
        
        # 计算媒体消息数量
        media_count = 0
        for message_group in message_groups:
            try:
                messages = await self.telethon_client.get_messages(entity, ids=message_group)
                for msg in messages:
                    if msg and msg.media:
                        media_count += 1
            except:
                continue

        # 只记录有处理消息的频道
        if processed_count > 0:
            logger.info(f"频道{channel_name}/{channel_id}采集成功（包含{media_count}个媒体）")
    
    async def _fetch_comment_video(self, message: TLMessage, channel_id: str, channel: dict) -> Optional[TLMessage]:
        """从评论区抓取第一条带视频的评论，替换原消息"""
        try:
            from telethon.tl.types import MessageMediaDocument
            entity = await self.channel_manager.get_channel_entity(
                channel, self.telethon_client
            )
            if not entity:
                logger.warning(f"获取评论区失败: 无法获取频道实体 {channel_id}")
                return None
            replies = await self.telethon_client.get_messages(
                entity, reply_to=message.id, limit=10
            )
            for r in replies:
                if not r or not r.media:
                    continue
                if isinstance(r.media, MessageMediaDocument):
                    doc = r.media.document
                    if doc and (doc.mime_type or '').startswith('video/'):
                        logger.info(
                            f"评论区视频命中: 原帖 {message.id} -> 评论 {r.id}"
                        )
                        return r
            logger.debug(f"评论区无视频，跳过消息 {message.id}")
            return None
        except Exception as e:
            logger.warning(f"获取评论区失败 {message.id}: {e}")
            return None

    async def _process_single_message(self, message: TLMessage, channel_id: str, channel: dict) -> Optional[LocalMessage]:
        """处理单个消息，包括媒体下载"""
        try:
            # 检查媒体大小限制
            if message.media:
                # 获取媒体大小限制配置
                max_media_size_mb = await self.config_manager.get_max_media_size_mb()
                max_media_size_bytes = max_media_size_mb * 1024 * 1024

                # 检查媒体大小
                from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
                if isinstance(message.media, MessageMediaDocument):
                    document = message.media.document
                    if document and hasattr(document, 'size'):
                        if document.size > max_media_size_bytes:
                            logger.warning(f"消息 {message.id} 媒体文件 {document.size/(1024*1024):.1f}MB 超过限制 {max_media_size_mb}MB，跳过该消息")
                            return None  # 返回None表示跳过该消息
                elif isinstance(message.media, MessageMediaPhoto):
                    # 图片通常不会太大，但也可以检查
                    photo = message.media.photo
                    if photo and hasattr(photo, 'sizes') and photo.sizes:
                        # 获取最大尺寸的图片大小（估算）
                        largest_size = max(photo.sizes, key=lambda s: getattr(s, 'size', 0) if hasattr(s, 'size') else 0)
                        if hasattr(largest_size, 'size') and largest_size.size > max_media_size_bytes:
                            logger.warning(f"消息 {message.id} 图片文件超过限制 {max_media_size_mb}MB，跳过该消息")
                            return None

            # 仅采集视频消息过滤
            if await self.config_manager.get_video_only():
                has_video = False
                if message.media:
                    from telethon.tl.types import MessageMediaDocument as MMD
                    if isinstance(message.media, MMD):
                        doc = message.media.document
                        if doc and (doc.mime_type or '').startswith('video/'):
                            has_video = True
                if not has_video:
                    return None

            # 评论区视频关键词检查
            comment_keywords = await self.config_manager.get_comment_keywords()
            if comment_keywords:
                text = (message.message or "").strip()
                if text and any(kw in text for kw in comment_keywords):
                    original_msg_id = message.id
                    comment_msg = await self._fetch_comment_video(
                        message, channel_id, channel
                    )
                    if comment_msg is None:
                        return None
                    message = comment_msg
                    # 保留原帖的message_id用于checkpoint和去重
                    message._original_msg_id = original_msg_id

            # 下载媒体（如果有）
            media_info = None
            if message.media:
                from app.services.media_handler import MediaHandler
                media_handler = MediaHandler()
                media_info = await media_handler.download_media_with_retry(
                    self.telethon_client, message, message.id
                )
            
            # 创建LocalMessage（评论替换时保留原帖ID）
            effective_msg_id = getattr(message, '_original_msg_id', message.id)
            return LocalMessage(
                channel_id=channel_id,
                message_id=effective_msg_id,
                grouped_id=getattr(message, 'grouped_id', None),
                content=message.message or "",
                filtered_content=message.message or "",  # 暂时与content相同
                media_info=media_info,
                media_type=media_info.get('media_type') if media_info else None,
                media_path=media_info.get('file_path') if media_info else None,
                media_url=media_info.get('file_path') if media_info else None,
                thumbnail_url=media_info.get('thumbnail_url') if media_info else None,
                is_combined=False,  # 单条消息不是组合消息
                timestamp=message.date,
                # status="pending" - 移除硬编码，使用LocalMessage的默认值
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

            # 获取媒体大小限制配置
            max_media_size_mb = await self.config_manager.get_max_media_size_mb()
            max_media_size_bytes = max_media_size_mb * 1024 * 1024

            # 🔧 修复：检查组内媒体大小，但不因单个文件过大就跳过整组
            from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
            valid_messages = []  # 保存通过大小检查的消息
            skipped_count = 0    # 跳过的消息数量

            for msg in group_messages:
                should_include = True

                if msg.media:
                    if isinstance(msg.media, MessageMediaDocument):
                        document = msg.media.document
                        if document and hasattr(document, 'size'):
                            if document.size > max_media_size_bytes:
                                logger.warning(f"消息组中消息 {msg.id} 媒体文件 {document.size/(1024*1024):.1f}MB 超过限制 {max_media_size_mb}MB，跳过该消息")
                                should_include = False
                                skipped_count += 1
                    elif isinstance(msg.media, MessageMediaPhoto):
                        photo = msg.media.photo
                        if photo and hasattr(photo, 'sizes') and photo.sizes:
                            largest_size = max(photo.sizes, key=lambda s: getattr(s, 'size', 0) if hasattr(s, 'size') else 0)
                            if hasattr(largest_size, 'size') and largest_size.size > max_media_size_bytes:
                                logger.warning(f"消息组中消息 {msg.id} 图片超过限制 {max_media_size_mb}MB，跳过该消息")
                                should_include = False
                                skipped_count += 1

                if should_include:
                    valid_messages.append(msg)

            # 🔧 修复：只有当所有消息都被跳过时才放弃整组
            if not valid_messages:
                logger.warning(f"消息组 {[m.id for m in group_messages]} 中所有消息都超过大小限制，跳过整组")
                return None

            if skipped_count > 0:
                logger.info(f"消息组处理：保留 {len(valid_messages)} 条消息，跳过 {skipped_count} 条超大媒体消息")

            # 使用通过检查的消息继续处理
            group_messages = valid_messages

            # 仅采集视频消息过滤（组消息中至少有一个视频才保留）
            if await self.config_manager.get_video_only():
                has_video = any(
                    isinstance(msg.media, MessageMediaDocument)
                    and msg.media.document
                    and (msg.media.document.mime_type or '').startswith('video/')
                    for msg in group_messages if msg.media
                )
                if not has_video:
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
            
            # 创建LocalMessage - 移除硬编码status，让内容处理器决定状态
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
                # status="pending" - 移除硬编码，使用LocalMessage的默认值
                source_channel=channel_id,
                source_channel_title=channel.get('channel_name', channel.get('channel_title')),
                source_channel_username=channel.get('channel_username'),
                entities=primary_msg.entities
            )
            
        except Exception as e:
            logger.error(f"处理组消息失败: {e}")
            return None
    
    async def _should_continue(self) -> bool:
        """检查是否应该继续采集 - 仅基于信号控制"""
        # 检查服务停止信号
        if not self.running:
            logger.info("检测到停止信号，准备停止采集")
            return False
        
        return True
    
    def _is_substantial_media(self, media) -> bool:
        """判断是否为有实质内容的媒体"""
        if not media:
            return False
        
        try:
            # 导入Telegram媒体类型
            from telethon.tl.types import (
                MessageMediaPhoto,      # 图片 - 实质内容
                MessageMediaDocument,   # 文档/视频/音频 - 实质内容  
                MessageMediaWebPage,    # 网页预览 - 可能有实质内容
                MessageMediaGiveaway,   # 抽奖 - 无实质内容
                MessageMediaPoll,       # 投票 - 无实质内容
                MessageMediaGame,       # 游戏 - 无实质内容
                MessageMediaContact,    # 联系人 - 无实质内容
                MessageMediaVenue,      # 地点 - 无实质内容
                MessageMediaGeo,        # 地理位置 - 无实质内容
                MessageMediaDice,       # 骰子 - 无实质内容
                MessageMediaUnsupported # 不支持 - 无实质内容
            )
            
            # 有实质内容的媒体类型
            substantial_types = (
                MessageMediaPhoto,
                MessageMediaDocument,
                MessageMediaWebPage  # 网页预览可能包含图片
            )
            
            return isinstance(media, substantial_types)
            
        except ImportError as e:
            logger.warning(f"导入媒体类型失败: {e}")
            # 导入失败时保守处理，认为有实质内容
            return True
        except Exception as e:
            logger.error(f"判断媒体类型失败: {e}")
            return True
    
    def _is_empty_message(self, msg) -> Tuple[bool, str]:
        """
        高级空消息判断
        
        Args:
            msg: Telegram消息对象
            
        Returns:
            (是否为空消息, 判断原因)
        """
        # 有文本内容，不是空消息
        if msg.message and msg.message.strip():
            return False, "有文本内容"
        
        # 无文本且无媒体
        if not msg.media:
            return True, "无文本内容且无媒体"
        
        # 无文本但有实质媒体内容
        if self._is_substantial_media(msg.media):
            media_type = type(msg.media).__name__
            return False, f"有实质媒体内容: {media_type}"
        
        # 无文本且只有非实质媒体
        media_type = type(msg.media).__name__
        return True, f"只有非实质媒体: {media_type}"

    async def _update_channel_info(self, channel: dict, entity):
        """在采集时顺便更新频道信息"""
        try:
            # 获取最新的用户名和标题
            current_username = f"@{entity.username}" if hasattr(entity, 'username') and entity.username else None
            current_title = entity.title if hasattr(entity, 'title') else None

            changes = []

            # 检查并更新变化
            if current_username and current_username != channel.get('channel_name'):
                logger.info(f"频道名称更新: {channel.get('channel_name')} -> {current_username}")
                channel['channel_name'] = current_username
                changes.append('name')

            if current_title and current_title != channel.get('channel_title'):
                logger.info(f"频道标题更新: {channel.get('channel_title')} -> {current_title}")
                channel['channel_title'] = current_title
                changes.append('title')

            # 如果有变化，保存到配置
            if changes:
                from app.storage.json_store import get_json_channel_store
                from app.utils.timezone import get_current_time
                channel_store = get_json_channel_store()
                channel['updated_at'] = get_current_time().isoformat()
                channel_store.update_channel(channel)
                logger.info(f"频道 {current_username or channel['channel_id']} 信息已更新")

        except Exception as e:
            # 静默处理，不影响主流程
            logger.debug(f"更新频道信息失败（不影响采集）: {e}")

# 全局实例
message_collector = TelegramMessageCollector()