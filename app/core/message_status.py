"""
消息状态定义
扩展为7种细分状态，提供更精确的状态管理

"""
from enum import Enum
from typing import List


class MessageStatus(Enum):
    """
    消息状态 - 7种细分状态
    """
    # 待处理状态
    PENDING = "pending"              # 待审核 - 未发送失败过的消息
    SEND_FAILED = "send_failed"      # 发送失败 - 发送失败的消息

    # 已发布状态
    AUTO_APPROVED = "auto_approved"    # 自动发布 - 系统自动发布的消息
    MANUAL_APPROVED = "manual_approved" # 手动发布 - 人工发布的消息

    # 已拒绝状态
    AD_REJECTED = "ad_rejected"         # 广告拒绝 - 检测为广告被拒绝
    DUP_REJECTED = "dup_rejected"       # 重复拒绝 - 检测为重复被拒绝
    MANUAL_REJECTED = "manual_rejected" # 手动拒绝 - 人工拒绝

    @classmethod
    def get_approved_statuses(cls) -> List[str]:
        """获取所有已发布状态"""
        return [cls.AUTO_APPROVED.value, cls.MANUAL_APPROVED.value]

    @classmethod
    def get_rejected_statuses(cls) -> List[str]:
        """获取所有已拒绝状态"""
        return [cls.AD_REJECTED.value, cls.DUP_REJECTED.value, cls.MANUAL_REJECTED.value]

    @classmethod
    def get_pending_like_statuses(cls) -> List[str]:
        """获取所有待处理状态（包括待审核和发送失败）"""
        return [cls.PENDING.value, cls.SEND_FAILED.value]


# 向后兼容：旧的3状态系统
LEGACY_PENDING = "pending"
LEGACY_APPROVED = "approved"
LEGACY_REJECTED = "rejected"


class RejectionReason(Enum):
    """
    拒绝原因 - 保留用于向后兼容
    """
    AD = "ad"                # 广告内容
    DUP = "dup"              # 重复内容
    MANUAL = "manual"        # 手动拒绝

def is_valid_status(status: str) -> bool:
    """检查状态是否有效（支持新7状态和旧3状态）"""
    # 检查新的7状态
    try:
        MessageStatus(status)
        return True
    except ValueError:
        # 兼容旧的3状态
        return status in [LEGACY_PENDING, LEGACY_APPROVED, LEGACY_REJECTED]

def is_valid_rejection_reason(reason: str) -> bool:
    """检查拒绝原因是否有效"""
    try:
        RejectionReason(reason)
        return True
    except ValueError:
        return False


def get_status_display_name(status: str) -> str:
    """获取状态的显示名称"""
    display_names = {
        MessageStatus.PENDING.value: "待审核",
        MessageStatus.SEND_FAILED.value: "发送失败",
        MessageStatus.AUTO_APPROVED.value: "自动发布",
        MessageStatus.MANUAL_APPROVED.value: "手动发布",
        MessageStatus.AD_REJECTED.value: "广告拒绝",
        MessageStatus.DUP_REJECTED.value: "重复拒绝",
        MessageStatus.MANUAL_REJECTED.value: "手动拒绝",
        # 向后兼容
        LEGACY_APPROVED: "已发布",
        LEGACY_REJECTED: "已拒绝"
    }
    return display_names.get(status, status)


def get_rejection_reason_display_name(reason: RejectionReason) -> str:
    """获取拒绝原因的显示名称"""
    display_names = {
        RejectionReason.AD: "广告内容",
        RejectionReason.DUP: "重复内容",
        RejectionReason.MANUAL: "手动拒绝"
    }
    return display_names.get(reason, reason.value)


def map_legacy_status(status: str, reject_reason: str = None) -> str:
    """
    将旧的3状态系统映射到新的7状态系统

    Args:
        status: 旧状态值 (pending/approved/rejected)
        reject_reason: 拒绝原因（用于细分rejected状态）

    Returns:
        新状态值
    """
    if status == LEGACY_PENDING:
        return MessageStatus.PENDING.value
    elif status == LEGACY_APPROVED:
        return MessageStatus.MANUAL_APPROVED.value
    elif status == LEGACY_REJECTED:
        if reject_reason:
            if "广告" in reject_reason or "ad" in reject_reason.lower():
                return MessageStatus.AD_REJECTED.value
            elif "重复" in reject_reason or "dup" in reject_reason.lower():
                return MessageStatus.DUP_REJECTED.value
        return MessageStatus.MANUAL_REJECTED.value
    else:
        # 已经是新状态，直接返回
        return status


def get_legacy_status(status: str) -> str:
    """
    将新的7状态映射回旧的3状态（向后兼容）

    Args:
        status: 新状态值

    Returns:
        旧状态值 (pending/approved/rejected)
    """
    if status in MessageStatus.get_pending_like_statuses():
        return LEGACY_PENDING
    elif status in MessageStatus.get_approved_statuses():
        return LEGACY_APPROVED
    elif status in MessageStatus.get_rejected_statuses():
        return LEGACY_REJECTED
    else:
        # 未知状态，返回原值
        return status