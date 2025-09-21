"""
自动转发服务 - 极简实现
负责定时检查并自动转发符合条件的消息
"""
import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import List

from app.storage.redis_manager import redis_manager
from app.services.config_manager import config_manager
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class AutoForwarder:
    """自动转发服务"""

    async def check_and_forward(self):
        """检查并转发符合条件的消息 - 30秒执行一次"""
        try:
            # 1. 检查是否启用自动转发
            enabled = await config_manager.get_config('target.auto_forward_enabled', False)
            if not enabled:
                logger.debug("自动转发未启用")
                return

            # 2. 获取延迟配置（默认1800秒 = 30分钟）
            delay_seconds = await config_manager.get_config('target.auto_forward_delay', 1800)
            delay_seconds = int(delay_seconds)
            cutoff_time = get_current_time() - timedelta(seconds=delay_seconds)

            logger.debug(f"自动转发检查: 延迟={delay_seconds}秒, 截止时间={cutoff_time}")

            # 3. 获取所有待审核消息
            pending_messages = redis_manager.get_messages_by_status('pending', limit=100)

            if not pending_messages:
                logger.debug("没有待审核消息")
                return

            # 4. 筛选符合时间条件的消息ID
            eligible_ids = []

            for msg in pending_messages:
                try:
                    # 检查是否有自动转发失败标记，如果有则跳过
                    if msg.get('auto_forwarder_status') is not None:
                        logger.debug(f"跳过已标记失败的消息: {msg.get('source_channel')}:{msg.get('message_id')}")
                        continue

                    # 检查创建时间
                    created_at_str = msg.get('created_at')
                    if not created_at_str:
                        continue

                    # 使用统一的时区处理
                    from app.utils.timezone import to_utc
                    created_at = to_utc(datetime.fromisoformat(created_at_str.replace('Z', '+00:00')))

                    # 时间符合条件就加入
                    if created_at <= cutoff_time:
                        # 使用rsplit确保正确解析包含冒号的channel_id
                        message_id = f"{msg.get('source_channel')}:{msg.get('message_id')}"
                        eligible_ids.append(message_id)

                except Exception as e:
                    logger.error(f"处理消息时间时出错: {e}")
                    continue

            if not eligible_ids:
                logger.debug(f"检查了 {len(pending_messages)} 条消息，没有符合时间条件的")
                return

            # 5. 限制每次处理的消息数量，避免超时
            MAX_BATCH_SIZE = 50  # 每次最多处理50条消息

            if len(eligible_ids) > MAX_BATCH_SIZE:
                logger.info(f"🔄 自动转发: 发现 {len(eligible_ids)} 条符合条件的消息，本次处理前 {MAX_BATCH_SIZE} 条")
                eligible_ids = eligible_ids[:MAX_BATCH_SIZE]
            else:
                logger.info(f"🔄 自动转发: 发现 {len(eligible_ids)} 条符合条件的消息")

            # 6. 直接调用核心发布方法处理每条消息
            from app.api.messages_crud import publish_single_message

            logger.info(f"开始处理 {len(eligible_ids)} 条消息的自动转发...")

            approved_count = 0
            failed_count = 0
            ad_count = 0
            length_exceeded_count = 0

            for message_id in eligible_ids:
                try:
                    # 直接调用核心发布方法
                    result = await publish_single_message(
                        message_id,
                        user_id="auto_forward",
                        is_auto_forward=True  # 标记为自动转发
                    )

                    if result['success']:
                        approved_count += 1
                        logger.debug(f"自动发布成功: {message_id}")
                    else:
                        failed_count += 1
                        # 统计失败原因
                        if result.get('error') == 'ad_detected':
                            ad_count += 1
                        elif result.get('error') == 'content_too_long':
                            length_exceeded_count += 1
                        logger.debug(f"自动发布失败: {message_id}, 原因: {result.get('message')}")

                except Exception as e:
                    failed_count += 1
                    logger.error(f"处理消息失败 {message_id}: {e}")

                # 短暂延迟避免过载
                await asyncio.sleep(0.1)

            # 7. 记录统计
            logger.info(f"✅ 自动转发完成: 成功 {approved_count} 条, 失败 {failed_count} 条")
            if ad_count > 0:
                logger.info(f"  - 广告消息: {ad_count} 条")
            if length_exceeded_count > 0:
                logger.info(f"  - 内容超长: {length_exceeded_count} 条")

        except asyncio.CancelledError:
            # 服务关闭时的正常中断，不记录错误
            logger.debug("自动转发任务被取消（服务关闭）")
            raise  # 重新抛出让调度器正确处理
        except Exception as e:
            logger.error(f"自动转发异常: {e}")

# 全局实例
auto_forwarder = AutoForwarder()