"""
Telegram限流管理器 - 严格遵循官方限流规则
基于官方限制：群组20条/分钟，媒体5条/分钟/聊天室，个人1条/秒
智能处理FloodWait错误，动态调整发送间隔
"""
import logging
import asyncio
import time
import re
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)

class MessageType(Enum):
    """消息类型枚举"""
    TEXT = "text"
    MEDIA = "media"
    COMBINED = "combined"

class TelegramRateLimiter:
    """Telegram限流管理器 - 基于官方限流规则的智能控制"""

    def __init__(self):
        # 官方限流规则（严格遵循）
        self.CHANNEL_TEXT_LIMIT = 20  # 群组：20条消息/分钟
        self.CHANNEL_MEDIA_LIMIT = 5  # 媒体：5条媒体/分钟/聊天室
        self.PERSONAL_LIMIT = 1       # 个人：1条消息/秒

        # 默认配置（可通过配置文件覆盖）
        self.SAFETY_FACTOR = 0.8
        self.TEXT_INTERVAL = 3.75     # 默认文本间隔
        self.MEDIA_INTERVAL = 12.0    # 默认媒体间隔（从15秒降低到12秒）
        self.PERSONAL_INTERVAL = 1.25 # 默认个人间隔

        # 配置是否已加载
        self._config_loaded = False

        # 限流状态跟踪
        self._flood_wait_until: Optional[datetime] = None
        self._last_send_time: Dict[str, datetime] = {}
        self._send_count: Dict[str, int] = {}
        self._window_start: Dict[str, datetime] = {}

        # 错误统计
        self._flood_wait_count = 0
        self._total_sends = 0
        self._success_sends = 0

        # FloodWait错误解析正则
        self._flood_wait_pattern = re.compile(r'wait of (\d+) seconds is required|(\d+) seconds')

        logger.info(f"限流管理器初始化 - 文本间隔:{self.TEXT_INTERVAL:.1f}s, 媒体间隔:{self.MEDIA_INTERVAL:.1f}s")

    async def _load_config(self):
        """从配置文件加载限流参数"""
        if self._config_loaded:
            return

        try:
            from app.services.config_manager import config_manager

            # 加载配置参数
            self.SAFETY_FACTOR = float(await config_manager.get_config('telegram.rate_limit_safety_factor', 0.8))
            self.TEXT_INTERVAL = float(await config_manager.get_config('telegram.rate_limit_text_interval', 3.75))
            self.MEDIA_INTERVAL = float(await config_manager.get_config('telegram.rate_limit_media_interval', 12.0))

            # 标记配置已加载
            self._config_loaded = True

            logger.info(f"限流配置已加载 - 安全系数:{self.SAFETY_FACTOR}, 文本间隔:{self.TEXT_INTERVAL:.1f}s, 媒体间隔:{self.MEDIA_INTERVAL:.1f}s")

        except Exception as e:
            logger.warning(f"加载限流配置失败，使用默认值: {e}")
            self._config_loaded = True  # 标记为已尝试加载，避免重复尝试

    async def can_send_now(self, message_type: MessageType, channel_id: str) -> tuple[bool, float]:
        """
        检查当前是否可以发送消息

        Args:
            message_type: 消息类型
            channel_id: 频道ID

        Returns:
            (可否发送, 需要等待的秒数)
        """
        # 确保配置已加载
        await self._load_config()

        current_time = datetime.now()

        # 1. 检查全局FloodWait状态
        if self._flood_wait_until and current_time < self._flood_wait_until:
            wait_seconds = (self._flood_wait_until - current_time).total_seconds()
            logger.debug(f"全局FloodWait激活，需等待 {wait_seconds:.1f}秒")
            return False, wait_seconds

        # 2. 检查频道级别的发送间隔
        interval = self._get_send_interval(message_type)
        last_send = self._last_send_time.get(channel_id)

        if last_send:
            elapsed = (current_time - last_send).total_seconds()
            if elapsed < interval:
                wait_seconds = interval - elapsed
                logger.debug(f"频道 {channel_id} 发送间隔未满足，需等待 {wait_seconds:.1f}秒")
                return False, wait_seconds

        # 3. 检查频道级别的流量限制（按分钟计算）
        if not self._check_channel_rate_limit(message_type, channel_id):
            wait_seconds = self._get_window_reset_time(channel_id)
            logger.debug(f"频道 {channel_id} 流量限制，需等待 {wait_seconds:.1f}秒")
            return False, wait_seconds

        return True, 0.0

    def _get_send_interval(self, message_type: MessageType) -> float:
        """获取发送间隔"""
        if message_type == MessageType.MEDIA or message_type == MessageType.COMBINED:
            return self.MEDIA_INTERVAL
        else:
            return self.TEXT_INTERVAL

    def _check_channel_rate_limit(self, message_type: MessageType, channel_id: str) -> bool:
        """检查频道级别的流量限制"""
        current_time = datetime.now()
        window_key = f"{channel_id}_{message_type.value}"

        # 重置时间窗口（每分钟重置）
        if window_key not in self._window_start or \
           (current_time - self._window_start[window_key]).total_seconds() >= 60:
            self._window_start[window_key] = current_time
            self._send_count[window_key] = 0

        # 检查当前窗口内的发送次数
        current_count = self._send_count.get(window_key, 0)

        if message_type == MessageType.MEDIA or message_type == MessageType.COMBINED:
            return current_count < (self.CHANNEL_MEDIA_LIMIT * self.SAFETY_FACTOR)
        else:
            return current_count < (self.CHANNEL_TEXT_LIMIT * self.SAFETY_FACTOR)

    def _get_window_reset_time(self, channel_id: str) -> float:
        """获取时间窗口重置剩余时间"""
        current_time = datetime.now()

        # 找到最早的窗口开始时间
        earliest_window = None
        for key, start_time in self._window_start.items():
            if key.startswith(channel_id):
                if earliest_window is None or start_time < earliest_window:
                    earliest_window = start_time

        if earliest_window:
            next_reset = earliest_window + timedelta(minutes=1)
            return max(0, (next_reset - current_time).total_seconds())

        return 0.0

    async def wait_if_needed(self, message_type: MessageType, channel_id: str) -> float:
        """
        如果需要等待，则自动等待

        Returns:
            实际等待的秒数
        """
        can_send, wait_seconds = await self.can_send_now(message_type, channel_id)

        if not can_send and wait_seconds > 0:
            # 添加随机缓冲时间（1-3秒），避免边界竞争
            buffer_time = random.uniform(1.0, 3.0)
            total_wait = wait_seconds + buffer_time

            # 删除限流等待的详细日志，会在最终转发结果中包含
            await asyncio.sleep(total_wait)
            return total_wait

        return 0.0

    def record_send_attempt(self, message_type: MessageType, channel_id: str, success: bool):
        """
        记录发送尝试

        Args:
            message_type: 消息类型
            channel_id: 频道ID
            success: 是否成功
        """
        current_time = datetime.now()

        # 更新发送时间
        self._last_send_time[channel_id] = current_time

        # 更新发送计数
        window_key = f"{channel_id}_{message_type.value}"
        if window_key not in self._send_count:
            self._send_count[window_key] = 0
        self._send_count[window_key] += 1

        # 更新统计
        self._total_sends += 1
        if success:
            self._success_sends += 1

        logger.debug(f"记录发送: {message_type.value} -> {channel_id}, 成功:{success}")

    async def handle_flood_wait_error(self, error_message: str) -> int:
        """
        处理FloodWait错误，解析等待时间

        Args:
            error_message: 错误信息

        Returns:
            需要等待的秒数
        """
        # 确保配置已加载
        await self._load_config()

        # 解析FloodWait错误中的等待时间
        match = self._flood_wait_pattern.search(error_message)
        if match:
            wait_seconds = int(match.group(1) or match.group(2))
        else:
            # 如果无法解析，使用默认等待时间
            wait_seconds = 60
            logger.warning(f"无法解析FloodWait等待时间，使用默认60秒: {error_message}")

        # 设置全局FloodWait状态
        self._flood_wait_until = datetime.now() + timedelta(seconds=wait_seconds)
        self._flood_wait_count += 1

        logger.warning(f"触发FloodWait限流，等待 {wait_seconds}秒 (累计 {self._flood_wait_count} 次)")
        return wait_seconds

    async def wait_for_flood_wait(self, wait_seconds: int):
        """
        等待FloodWait结束

        Args:
            wait_seconds: 需要等待的基础秒数
        """
        # 确保配置已加载
        await self._load_config()

        try:
            from app.services.config_manager import config_manager

            # 获取缓冲时间配置
            buffer_min = float(await config_manager.get_config('telegram.flood_wait_buffer_min', 1.0))
            buffer_max = float(await config_manager.get_config('telegram.flood_wait_buffer_max', 5.0))

            # 添加随机缓冲时间，避免多个实例同时重试
            buffer_time = random.uniform(buffer_min, buffer_max)

        except Exception as e:
            logger.warning(f"获取缓冲时间配置失败，使用默认值: {e}")
            buffer_time = random.uniform(1.0, 5.0)

        total_wait = wait_seconds + buffer_time

        logger.info(f"FloodWait等待 {total_wait:.1f}秒 (基础:{wait_seconds}s + 缓冲:{buffer_time:.1f}s)")
        await asyncio.sleep(total_wait)

    def is_in_flood_wait(self) -> tuple[bool, float]:
        """
        检查是否处于FloodWait状态

        Returns:
            (是否在FloodWait, 剩余等待秒数)
        """
        if not self._flood_wait_until:
            return False, 0.0

        current_time = datetime.now()
        if current_time >= self._flood_wait_until:
            # FloodWait已结束
            self._flood_wait_until = None
            return False, 0.0

        remaining_seconds = (self._flood_wait_until - current_time).total_seconds()
        return True, remaining_seconds

    def get_stats(self) -> Dict[str, Any]:
        """获取限流统计信息"""
        success_rate = (self._success_sends / self._total_sends * 100) if self._total_sends > 0 else 0

        return {
            "total_sends": self._total_sends,
            "success_sends": self._success_sends,
            "failed_sends": self._total_sends - self._success_sends,
            "success_rate": f"{success_rate:.1f}%",
            "flood_wait_count": self._flood_wait_count,
            "current_flood_wait": self.is_in_flood_wait()[0],
            "text_interval": f"{self.TEXT_INTERVAL:.1f}s",
            "media_interval": f"{self.MEDIA_INTERVAL:.1f}s",
            "safety_factor": self.SAFETY_FACTOR
        }

    def reset_stats(self):
        """重置统计信息"""
        self._flood_wait_count = 0
        self._total_sends = 0
        self._success_sends = 0
        logger.info("限流统计信息已重置")

# 全局限流管理器实例
rate_limiter = TelegramRateLimiter()