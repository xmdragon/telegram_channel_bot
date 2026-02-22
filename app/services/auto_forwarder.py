"""
自动转发服务 - 持续运行模式
负责持续检查并自动转发符合条件的消息，避免并发冲突
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from telethon.errors import FloodWaitError

from app.storage.redis_manager import redis_manager
from app.services.config_manager import config_manager
from app.utils.timezone import get_current_time
from app.utils.rate_limiter import rate_limiter, MessageType

logger = logging.getLogger(__name__)

class AutoForwarder:
    """自动转发服务 - 持续运行模式"""

    def __init__(self):
        self.is_running = False
        self.last_forward_time = None

    def is_system_error(self, error_msg: str) -> bool:
        """
        判断是否为系统级错误（不应写入消息结构）

        系统级错误包括：
        - Session连接问题
        - Telethon连接错误
        - 网络连接问题
        - 认证问题
        """
        if not error_msg:
            return False

        error_lower = str(error_msg).lower()

        # 系统级错误关键词
        system_keywords = [
            'session',
            '连接',
            'connect',
            'telethon',
            '网络',
            'network',
            '认证',
            'auth',
            'client',
            '无法连接',
            '客户端',
            'runtime',
            '配置验证失败',
            '格式无效'
        ]

        return any(keyword in error_lower for keyword in system_keywords)

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

                    # 5. 根据消息类型设置超时时间
                    timeout = await self.get_timeout_for_message(message)

                    # 6. 发送消息（带FloodWait处理）
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
                            # 获取转发后的链接信息
                            link = result.get('link', '')
                            # 获取限流信息（如果有的话）
                            rate_limit_info = result.get('rate_limit_time', 0)
                            if rate_limit_info > 0:
                                logger.info(f"🚀 转发成功: {message_id} -> {link} (限流{rate_limit_info:.1f}s)")
                            else:
                                logger.info(f"🚀 转发成功: {message_id} -> {link}")

                            self.last_forward_time = get_current_time()
                            # 清除重试标记
                            await self.clear_retry_flag(message_id)
                        else:
                            # 处理发送失败
                            error_type = result.get('error', 'unknown')
                            error_msg = result.get('message', 'unknown error')

                            if error_type in ['ad_detected', 'content_too_long', 'empty_content']:
                                # 这些错误不需要重试，标记为已处理
                                await self.mark_message_processed(message_id, error_type)
                                logger.info(f"消息被拒绝: {message_id} - {error_type}")
                            elif self.is_system_error(error_msg):
                                # 系统错误：不写入消息，只记录日志
                                logger.error(f"自动转发遇到系统错误: {message_id} - {error_msg}")
                                # 增加重试计数
                                await self.increment_retry_count(message_id)
                            else:
                                # 其他业务错误标记为失败
                                await self.mark_forward_failed(message_id, error_msg)
                                logger.error(f"自动转发失败(业务错误): {message_id} - {error_msg}")

                    except FloodWaitError as e:
                        # FloodWait专门处理 - 不标记为永久失败
                        wait_seconds = e.seconds if hasattr(e, 'seconds') else 60
                        logger.warning(f"自动转发触发FloodWait: {message_id} - 需等待{wait_seconds}秒")

                        # 增加重试计数但不标记为失败
                        await self.increment_retry_count(message_id)

                        # 设置全局FloodWait状态（重要：让其他协程感知）
                        await rate_limiter.handle_flood_wait_error(str(e))

                        # 等待指定时间
                        await rate_limiter.wait_for_flood_wait(wait_seconds)

                        # 继续下一轮循环，消息会在下次被重试
                        logger.info(f"FloodWait等待完成，消息 {message_id} 将在下一轮重试")

                    except asyncio.TimeoutError:
                        # 增加重试计数
                        await self.increment_retry_count(message_id)
                        await self.mark_forward_failed(message_id, f"发送超时({timeout}秒)")
                        logger.error(f"自动转发超时: {message_id} (超时时间: {timeout}秒)")

                    except Exception as e:
                        error_msg = str(e)
                        error_str = error_msg.lower()

                        # 检查是否是FloodWait错误的其他形式
                        if 'flood' in error_str or 'wait' in error_str:
                            # 设置全局FloodWait状态
                            wait_seconds = await rate_limiter.handle_flood_wait_error(str(e))
                            await rate_limiter.wait_for_flood_wait(wait_seconds)
                            logger.warning(f"检测到FloodWait错误: {message_id} - {e}")
                            # 增加重试计数但不标记为失败
                            await self.increment_retry_count(message_id)
                        elif self.is_system_error(error_msg):
                            # 系统级错误：只记录日志和重试计数，不写入消息
                            logger.error(f"自动转发遇到系统错误: {message_id} - {e}")
                            await self.increment_retry_count(message_id)
                            # 系统错误时短暂等待后继续
                            await asyncio.sleep(10)
                        else:
                            # 业务错误：标记失败，写入消息
                            await self.increment_retry_count(message_id)
                            await self.mark_forward_failed(message_id, error_msg)
                            logger.error(f"自动转发失败(业务错误): {message_id} - {e}")

                    # 8. 智能发送间隔
                    await asyncio.sleep(0.1)

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

            # 使用小批量获取最旧的待审核消息，避免加载全部
            # 每次取50条最旧的，逐批查找符合条件的
            batch_size = 50
            offset = 0
            max_batches = 20  # 最多检查1000条

            for _ in range(max_batches):
                pending_messages = redis_manager.get_messages_by_status(
                    'pending', limit=batch_size, offset=offset, reverse=False
                )

                if not pending_messages:
                    return None

                for msg in pending_messages:
                    # 跳过已标记失败的消息（除非需要重试）
                    if msg.get('auto_forward_failed') and not msg.get('needs_retry'):
                        continue

                    # 跳过已处理的消息（广告、超长等）
                    if msg.get('auto_forward_processed'):
                        continue

                    # 跳过疑似重复消息
                    duplicate_status = msg.get('duplicate_status', 'none')
                    if duplicate_status == 'suspected':
                        logger.debug(f"跳过疑似重复消息: {msg.get('source_channel')}:{msg.get('message_id')} "
                                    f"(原消息: {msg.get('original_message_id')}, 相似度: {msg.get('similarity_score', 0):.3f})")
                        continue

                    # 检查创建时间
                    created_at_str = msg.get('created_at')
                    if not created_at_str:
                        continue

                    try:
                        from app.utils.timezone import to_utc
                        created_at = to_utc(datetime.fromisoformat(created_at_str.replace('Z', '+00:00')))

                        if created_at <= cutoff_time:
                            return msg  # 已按时间排序，第一个符合条件的就是最旧的

                    except Exception as e:
                        logger.error(f"解析消息时间失败: {e}")
                        continue

                offset += batch_size

            return None

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
        # 从配置获取基础超时时间
        base_timeout = await config_manager.get_config('processor.send_message_timeout', 120)
        base_timeout = int(base_timeout)

        # 检查是否有媒体
        if not message.get('media_url'):
            return base_timeout  # 纯文本消息使用配置的超时时间

        media_url = message.get('media_url', '')

        # 根据文件扩展名判断类型，使用倍数关系
        if any(media_url.lower().endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv']):
            return base_timeout * 6  # 视频文件使用6倍超时（720秒）
        elif any(media_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return base_timeout  # 图片文件使用基础超时
        else:
            return int(base_timeout * 1.5)  # 其他文件使用1.5倍超时

    def _get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """
        根据消息内容判断消息类型

        Args:
            message: 消息对象

        Returns:
            消息类型枚举
        """
        # 检查是否为组合消息
        if message.get('is_combined') or message.get('media_group_display'):
            return MessageType.COMBINED

        # 检查是否有媒体
        if message.get('media_url') or message.get('media_type'):
            return MessageType.MEDIA

        # 默认为文本消息
        return MessageType.TEXT

    async def increment_retry_count(self, message_id: str):
        """
        增加消息的重试计数 - 使用Redis HINCRBY实现原子递增

        Args:
            message_id: 消息ID (格式: "channel_id:message_id")
        """
        try:
            if ':' not in message_id:
                return

            channel_id, msg_id = message_id.rsplit(':', 1)
            message_key = f"message:{channel_id}:{msg_id}"

            # 读取当前消息数据，原子更新retry_count
            message = redis_manager.get_message_by_id(message_id)
            if message:
                current_count = message.get('auto_forward_retry_count', 0)
                new_count = current_count + 1
                redis_manager.update_message_atomic(message_id, {
                    'auto_forward_retry_count': new_count,
                    'auto_forward_last_retry': get_current_time().isoformat()
                })
                logger.debug(f"消息 {message_id} 重试次数增加到 {new_count}")
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
            from app.core.message_status import MessageStatus

            # 更新状态为发送失败
            update_data = {
                'status': MessageStatus.SEND_FAILED.value,
                'auto_forward_failed': True,
                'auto_forward_error': reason,
                'auto_forward_failed_at': get_current_time().isoformat(),
                'needs_retry': False  # 永久失败不需要重试
            }

            # 使用 update_message_atomic 方法（接受完整的 message_id）
            redis_manager.update_message_atomic(message_id, update_data)
            logger.debug(f"已标记消息转发失败: {message_id} - {reason}")
        except Exception as e:
            logger.error(f"标记消息失败状态时出错: {e}")

    async def clear_retry_flag(self, message_id: str):
        """
        清除消息的重试标记（转发成功后调用）

        Args:
            message_id: 消息ID (格式: "channel_id:message_id")
        """
        try:
            update_data = {
                'auto_forward_failed': False,
                'auto_forward_error': None,
                'needs_retry': False,
                'flood_wait_seconds': None,
                'auto_forward_retry_count': 0  # 使用正确的字段名
            }

            redis_manager.update_message_atomic(message_id, update_data)
            logger.debug(f"已清除消息重试标记: {message_id}")
        except Exception as e:
            logger.error(f"清除重试标记时出错: {e}")

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

            # 根据原因设置不同的拒绝状态
            from app.core.message_status import MessageStatus

            if reason == 'empty_content':
                update_data['status'] = MessageStatus.MANUAL_REJECTED.value
                update_data['reject_reason'] = '消息内容为空'
            elif reason == 'ad_detected':
                update_data['status'] = MessageStatus.AD_REJECTED.value
                update_data['reject_reason'] = '检测为广告内容'

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