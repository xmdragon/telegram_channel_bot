"""
自动转发服务 - 持续运行模式
负责持续检查并自动转发符合条件的消息，避免并发冲突
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from app.storage.redis_manager import redis_manager
from app.services.config_manager import config_manager
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class AutoForwarder:
    """自动转发服务 - 持续运行模式"""

    def __init__(self):
        self.is_running = False
        self.last_forward_time = None

    async def run_continuous(self):
        """持续运行的自动转发主循环"""
        self.is_running = True
        logger.info("🔄 自动转发服务启动（持续运行模式）")

        try:
            while self.is_running:
                try:
                    # 1. 检查是否启用自动转发
                    enabled = await config_manager.get_config('target.auto_forward_enabled', False)
                    if not enabled:
                        logger.debug("自动转发未启用，等待10秒后重试")
                        await asyncio.sleep(10)
                        continue

                    # 2. 获取延迟配置
                    delay_seconds = await config_manager.get_config('target.auto_forward_delay', 1800)
                    delay_seconds = int(delay_seconds)

                    # 3. 获取最旧的一条符合条件的消息
                    message = await self.get_oldest_eligible_message(delay_seconds)

                    if not message:
                        # 没有符合条件的消息，休眠5秒
                        await asyncio.sleep(5)
                        continue

                    # 4. 处理单条消息
                    message_id = f"{message.get('source_channel')}:{message.get('message_id')}"
                    logger.info(f"准备自动转发消息: {message_id}")

                    # 5. 根据消息类型设置超时时间
                    timeout = await self.get_timeout_for_message(message)

                    # 6. 发送消息（带超时保护）
                    try:
                        from app.api.messages_crud import publish_single_message

                        result = await asyncio.wait_for(
                            publish_single_message(
                                message_id,
                                user_id="auto_forward",
                                is_auto_forward=True
                            ),
                            timeout=timeout
                        )

                        if result['success']:
                            logger.info(f"✅ 自动转发成功: {message_id}")
                            self.last_forward_time = get_current_time()
                        else:
                            # 处理发送失败
                            error_type = result.get('error', 'unknown')
                            if error_type in ['ad_detected', 'content_too_long']:
                                # 这些错误不需要重试，标记为已处理
                                await self.mark_message_processed(message_id, error_type)
                                logger.info(f"消息被拒绝: {message_id} - {error_type}")
                            else:
                                # 其他错误标记为失败，可能需要人工处理
                                await self.mark_forward_failed(message_id, result.get('message', 'unknown error'))
                                logger.error(f"自动转发失败: {message_id} - {result.get('message')}")

                    except asyncio.TimeoutError:
                        await self.mark_forward_failed(message_id, f"发送超时({timeout}秒)")
                        logger.error(f"自动转发超时: {message_id} (超时时间: {timeout}秒)")

                    except Exception as e:
                        await self.mark_forward_failed(message_id, str(e))
                        logger.error(f"自动转发异常: {message_id} - {e}")

                    # 7. 速率控制：每秒最多发送一条消息
                    await asyncio.sleep(1)

                except asyncio.CancelledError:
                    # 服务关闭信号
                    logger.info("收到关闭信号，停止自动转发")
                    break

                except Exception as e:
                    # 捕获所有其他异常，避免主循环退出
                    logger.error(f"自动转发循环异常: {e}")
                    await asyncio.sleep(5)  # 出错后等待5秒再继续

        finally:
            self.is_running = False
            logger.info("🛑 自动转发服务已停止")

    async def get_oldest_eligible_message(self, delay_seconds: int) -> Optional[Dict[str, Any]]:
        """
        获取最旧的符合条件的待审核消息

        Args:
            delay_seconds: 延迟时间（秒）

        Returns:
            符合条件的最旧消息，如果没有则返回None
        """
        try:
            cutoff_time = get_current_time() - timedelta(seconds=delay_seconds)

            # 获取所有待审核消息
            pending_messages = redis_manager.get_messages_by_status('pending', limit=1000)

            if not pending_messages:
                return None

            # 筛选符合条件的消息
            eligible_messages = []

            for msg in pending_messages:
                # 跳过已标记失败的消息
                if msg.get('auto_forward_failed'):
                    continue

                # 跳过已处理的消息（广告、超长等）
                if msg.get('auto_forward_processed'):
                    continue

                # 检查创建时间
                created_at_str = msg.get('created_at')
                if not created_at_str:
                    continue

                try:
                    from app.utils.timezone import to_utc
                    created_at = to_utc(datetime.fromisoformat(created_at_str.replace('Z', '+00:00')))

                    if created_at <= cutoff_time:
                        eligible_messages.append(msg)

                except Exception as e:
                    logger.error(f"解析消息时间失败: {e}")
                    continue

            if not eligible_messages:
                return None

            # 返回最旧的消息（按创建时间排序）
            eligible_messages.sort(key=lambda x: x.get('created_at', ''))
            return eligible_messages[0]

        except Exception as e:
            logger.error(f"获取符合条件的消息失败: {e}")
            return None

    async def get_timeout_for_message(self, message: Dict[str, Any]) -> int:
        """
        根据消息类型返回合适的超时时间

        Args:
            message: 消息对象

        Returns:
            超时时间（秒）
        """
        # 检查是否有媒体
        if not message.get('media_url'):
            return 30  # 纯文本消息30秒

        media_url = message.get('media_url', '')

        # 根据文件扩展名判断类型
        if any(media_url.lower().endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv']):
            return 180  # 视频文件180秒
        elif any(media_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return 60  # 图片文件60秒
        else:
            return 90  # 其他文件90秒

    async def mark_forward_failed(self, message_id: str, reason: str):
        """
        标记消息自动转发失败

        Args:
            message_id: 消息ID
            reason: 失败原因
        """
        try:
            message = redis_manager.get_message_by_id(message_id)
            if message:
                message['auto_forward_failed'] = True
                message['auto_forward_error'] = reason
                message['auto_forward_failed_at'] = get_current_time().isoformat()
                redis_manager.update_message(message_id, message)
                logger.debug(f"已标记消息转发失败: {message_id}")
        except Exception as e:
            logger.error(f"标记消息失败状态时出错: {e}")

    async def mark_message_processed(self, message_id: str, reason: str):
        """
        标记消息已处理（不需要重试的情况）

        Args:
            message_id: 消息ID
            reason: 处理原因（如 ad_detected, content_too_long）
        """
        try:
            message = redis_manager.get_message_by_id(message_id)
            if message:
                message['auto_forward_processed'] = True
                message['auto_forward_process_reason'] = reason
                message['auto_forward_processed_at'] = get_current_time().isoformat()
                redis_manager.update_message(message_id, message)
                logger.debug(f"已标记消息为已处理: {message_id} - {reason}")
        except Exception as e:
            logger.error(f"标记消息处理状态时出错: {e}")

    def stop(self):
        """停止自动转发服务"""
        self.is_running = False
        logger.info("正在停止自动转发服务...")

# 全局实例
auto_forwarder = AutoForwarder()