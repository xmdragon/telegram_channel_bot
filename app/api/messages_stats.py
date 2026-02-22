"""
消息统计和监控API模块
处理统计数据、性能监控、报告生成等功能
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.utils.timezone import get_current_time, format_for_api
import logging

from app.storage.redis_manager import redis_manager
from app.services.message_processor import MessageProcessor
from app.services.channel_manager import ChannelManager
from app.core.route_config import ROUTES
from app.api.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()

# 依赖注入辅助函数
def get_message_processor() -> MessageProcessor:
    return MessageProcessor()

def get_channel_manager() -> ChannelManager:
    return ChannelManager()


@router.get(ROUTES.messages.stats_overview)
async def get_message_stats(
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    获取消息统计概览 - 直接从数据库获取
    """
    try:
        from app.core.message_status import MessageStatus

        # 直接从数据库获取各状态的数量
        status_counts = {}
        for status_enum in MessageStatus:
            count = redis_manager.get_message_count_by_status(status_enum.value)
            status_counts[status_enum.value] = count

        # 计算兼容的旧状态统计
        approved_total = status_counts.get(MessageStatus.AUTO_APPROVED.value, 0) + status_counts.get(MessageStatus.MANUAL_APPROVED.value, 0)
        rejected_total = (status_counts.get(MessageStatus.AD_REJECTED.value, 0) +
                         status_counts.get(MessageStatus.DUP_REJECTED.value, 0) +
                         status_counts.get(MessageStatus.MANUAL_REJECTED.value, 0))

        return {
            "success": True,
            "data": {
                "message_status": {
                    # 新7种状态
                    "pending": status_counts.get(MessageStatus.PENDING.value, 0),
                    "send_failed": status_counts.get(MessageStatus.SEND_FAILED.value, 0),
                    "auto_approved": status_counts.get(MessageStatus.AUTO_APPROVED.value, 0),
                    "manual_approved": status_counts.get(MessageStatus.MANUAL_APPROVED.value, 0),
                    "ad_rejected": status_counts.get(MessageStatus.AD_REJECTED.value, 0),
                    "dup_rejected": status_counts.get(MessageStatus.DUP_REJECTED.value, 0),
                    "manual_rejected": status_counts.get(MessageStatus.MANUAL_REJECTED.value, 0),
                    # 兼容旧3状态
                    "approved": approved_total,
                    "rejected": rejected_total,
                    "labels": {
                        "pending": "待审核",
                        "send_failed": "发送失败",
                        "auto_approved": "自动发布",
                        "manual_approved": "手动发布",
                        "ad_rejected": "广告拒绝",
                        "dup_rejected": "重复拒绝",
                        "manual_rejected": "手动拒绝",
                        "approved": "已发布",
                        "rejected": "已拒绝"
                    }
                }
            },
            "timestamp": format_for_api(get_current_time())
        }

    except Exception as e:
        logger.error(f"获取消息统计失败: {e}")
        # 返回默认7种状态统计数据，确保前端不会出错
        return {
            "success": True,
            "data": {
                "message_status": {
                    # 新7种状态
                    "pending": 0,
                    "send_failed": 0,
                    "auto_approved": 0,
                    "manual_approved": 0,
                    "ad_rejected": 0,
                    "dup_rejected": 0,
                    "manual_rejected": 0,
                    # 兼容旧3状态
                    "approved": 0,
                    "rejected": 0,
                    "labels": {
                        "pending": "待审核",
                        "send_failed": "发送失败",
                        "auto_approved": "自动发布",
                        "manual_approved": "手动发布",
                        "ad_rejected": "广告拒绝",
                        "dup_rejected": "重复拒绝",
                        "manual_rejected": "手动拒绝",
                        "approved": "已发布",
                        "rejected": "已拒绝"
                    }
                }
            },
            "timestamp": format_for_api(get_current_time())
        }

