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

                    # 检查重试次数
                    retry_count = message.get('auto_forward_retry_count', 0)
                    if retry_count >= 3:
                        logger.warning(f"消息 {message_id} 已重试 {retry_count} 次，永久跳过")
                        await self.mark_forward_failed(message_id, f"超过最大重试次数({retry_count}次)")
                        continue

                    logger.info(f"准备自动转发消息: {message_id} (第{retry_count + 1}次尝试)")

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
                        # 增加重试计数
                        await self.increment_retry_count(message_id)
                        await self.mark_forward_failed(message_id, f"发送超时({timeout}秒)")
                        logger.error(f"自动转发超时: {message_id} (超时时间: {timeout}秒)")

                    except Exception as e:
                        # 增加重试计数
                        await self.increment_retry_count(message_id)
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

    async def increment_retry_count(self, message_id: str):
        """
        增加消息的重试计数

        Args:
            message_id: 消息ID (格式: "channel_id:message_id")
        """
        try:
            # 获取当前重试次数并增加
            message = redis_manager.get_message_by_id(message_id)
            if message:
                current_count = message.get('auto_forward_retry_count', 0)
                redis_manager.update_message_atomic(message_id, {
                    'auto_forward_retry_count': current_count + 1,
                    'auto_forward_last_retry': get_current_time().isoformat()
                })
                logger.debug(f"消息 {message_id} 重试次数增加到 {current_count + 1}")
        except Exception as e:
            logger.error(f"增加重试计数时出错: {e}")

    async def mark_forward_failed(self, message_id: str, reason: str):
        """
        标记消息自动转发失败

        Args:
            message_id: 消息ID (格式: "channel_id:message_id")
            reason: 失败原因
        """
        try:
            # 使用原子更新方法，直接更新字段
            update_data = {
                'auto_forward_failed': True,
                'auto_forward_error': reason,
                'auto_forward_failed_at': get_current_time().isoformat()
            }

            # 使用 update_message_atomic 方法（接受完整的 message_id）
            redis_manager.update_message_atomic(message_id, update_data)
            logger.debug(f"已标记消息转发失败: {message_id} - {reason}")
        except Exception as e:
            logger.error(f"标记消息失败状态时出错: {e}")

    async def mark_message_processed(self, message_id: str, reason: str):
        """
        标记消息已处理（不需要重试的情况）

        Args:
            message_id: 消息ID (格式: "channel_id:message_id")
            reason: 处理原因（如 ad_detected, content_too_long, empty_content）
        """
        try:
            # 使用原子更新方法，直接更新字段
            update_data = {
                'auto_forward_processed': True,
                'auto_forward_process_reason': reason,
                'auto_forward_processed_at': get_current_time().isoformat()
            }

            # 如果是空内容，同时更新状态为rejected
            if reason == 'empty_content':
                update_data['status'] = 'rejected'
                update_data['reject_reason'] = '消息内容为空'

            # 使用 update_message_atomic 方法（接受完整的 message_id）
            redis_manager.update_message_atomic(message_id, update_data)
            logger.debug(f"已标记消息为已处理: {message_id} - {reason}")
        except Exception as e:
            logger.error(f"标记消息处理状态时出错: {e}")

    def stop(self):
        """停止自动转发服务"""
        self.is_running = False
        logger.info("正在停止自动转发服务...")

# 全局实例
auto_forwarder = AutoForwarder()