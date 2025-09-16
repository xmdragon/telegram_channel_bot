"""
消息状态定义
只保留本质的3种状态和2种拒绝原因

消息要么在处理中(PENDING)，要么被批准了(APPROVED)，要么被拒绝了(REJECTED)
拒绝原因只有广告(AD)和手动拒绝(MANUAL)两种
"""
from enum import Enum


class MessageStatus(Enum):
    """
    消息状态 - 只有3种
    """
    PENDING = "pending"      # 待审核 - 消息刚到达，等待审核
    APPROVED = "approved"    # 已发布 - 消息通过所有过滤器，可以发布
    REJECTED = "rejected"    # 已拒绝 - 消息被过滤器拒绝


class RejectionReason(Enum):
    """
    拒绝原因 - 只有2种
    """
    AD = "ad"                # 广告内容
    MANUAL = "manual"        # 手动拒绝


def is_valid_status(status: str) -> bool:
    """检查状态是否有效"""
    try:
        MessageStatus(status)
        return True
    except ValueError:
        return False


def is_valid_rejection_reason(reason: str) -> bool:
    """检查拒绝原因是否有效"""
    try:
        RejectionReason(reason)
        return True
    except ValueError:
        return False


def get_status_display_name(status: MessageStatus) -> str:
    """获取状态的显示名称"""
    display_names = {
        MessageStatus.PENDING: "待审核",
        MessageStatus.APPROVED: "已发布",
        MessageStatus.REJECTED: "已拒绝"
    }
    return display_names.get(status, status.value)


def get_rejection_reason_display_name(reason: RejectionReason) -> str:
    """获取拒绝原因的显示名称"""
    display_names = {
        RejectionReason.AD: "广告内容",
        RejectionReason.MANUAL: "手动拒绝"
    }
    return display_names.get(reason, reason.value)