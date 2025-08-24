"""
Linus式消息状态定义
消除所有特殊情况，只保留本质的3种状态

核心哲学：
- 消息要么在处理中 (PENDING)
- 要么被批准了 (APPROVED) 
- 要么被拒绝了 (REJECTED)
- 没有其他状态！
"""
from enum import Enum
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class MessageStatus(Enum):
    """
    Linus式消息状态 - 只有3种，消除所有特殊情况
    
    这是消息的本质状态，任何复杂的业务逻辑都不应该增加新状态
    """
    PENDING = "pending"      # 待审核 - 消息刚到达，等待审核
    APPROVED = "approved"    # 已发布 - 消息通过所有过滤器，可以发布
    REJECTED = "rejected"    # 已拒绝 - 消息被过滤器拒绝


class RejectionReason(Enum):
    """
    拒绝原因 - 这是元数据，不是状态
    
    只有当状态为REJECTED时，这个字段才有意义
    """
    AD = "ad"                # 广告内容
    DUPLICATE = "duplicate"   # 重复消息  
    CHAT = "chat"            # 聊天消息（非频道内容）
    LOW_QUALITY = "low_quality"  # 低质量内容
    INAPPROPRIATE = "inappropriate"  # 不当内容
    OTHER = "other"          # 其他原因


class StatusMapper:
    """
    状态映射器 - 将遗留的复杂状态映射到Linus式3状态
    
    这是过渡期间的工具，最终应该移除所有遗留状态
    """
    
    # 遗留状态到Linus状态的映射
    LEGACY_TO_LINUS_STATUS = {
        # 处理中的状态 -> PENDING
        'pending': MessageStatus.PENDING,
        'processing': MessageStatus.PENDING,
        'received': MessageStatus.PENDING,
        'queued': MessageStatus.PENDING,
        
        # 已发布的状态 -> APPROVED  
        'approved': MessageStatus.APPROVED,
        'published': MessageStatus.APPROVED,
        'auto_forwarded': MessageStatus.APPROVED,
        'forwarded': MessageStatus.APPROVED,
        
        # 已拒绝的状态 -> REJECTED
        'rejected': MessageStatus.REJECTED,
        'filtered': MessageStatus.REJECTED,
        'blocked': MessageStatus.REJECTED,
        'spam': MessageStatus.REJECTED,
    }
    
    # 遗留过滤原因到拒绝原因的映射
    LEGACY_TO_REJECTION_REASON = {
        'ad': RejectionReason.AD,
        'advertisement': RejectionReason.AD,
        'duplicate': RejectionReason.DUPLICATE,
        'dup': RejectionReason.DUPLICATE,
        'chat': RejectionReason.CHAT,
        'private_chat': RejectionReason.CHAT,
        'low_quality': RejectionReason.LOW_QUALITY,
        'short': RejectionReason.LOW_QUALITY,
        'inappropriate': RejectionReason.INAPPROPRIATE,
        'spam': RejectionReason.INAPPROPRIATE,
    }
    
    @classmethod
    def map_legacy_status(cls, legacy_status: str) -> MessageStatus:
        """将遗留状态映射到Linus状态"""
        if not legacy_status:
            return MessageStatus.PENDING
        
        status = cls.LEGACY_TO_LINUS_STATUS.get(legacy_status.lower())
        if status is None:
            logger.warning(f"未知的遗留状态: {legacy_status}, 默认为PENDING")
            return MessageStatus.PENDING
        
        return status
    
    @classmethod 
    def map_legacy_reason(cls, legacy_reason: str) -> Optional[RejectionReason]:
        """将遗留过滤原因映射到拒绝原因"""
        if not legacy_reason:
            return None
            
        reason = cls.LEGACY_TO_REJECTION_REASON.get(legacy_reason.lower())
        if reason is None:
            logger.warning(f"未知的遗留拒绝原因: {legacy_reason}, 默认为OTHER")
            return RejectionReason.OTHER
        
        return reason
    
    @classmethod
    def extract_rejection_info(cls, message_data: Dict[str, Any]) -> Optional[RejectionReason]:
        """从消息数据中提取拒绝原因信息"""
        # 检查直接的拒绝原因字段
        if 'rejection_reason' in message_data:
            return cls.map_legacy_reason(message_data['rejection_reason'])
        
        # 检查filter_reason字段（遗留）
        if 'filter_reason' in message_data:
            return cls.map_legacy_reason(message_data['filter_reason'])
        
        # 检查is_ad标志
        if message_data.get('is_ad', False):
            return RejectionReason.AD
        
        # 检查其他布尔标志
        if message_data.get('is_duplicate', False):
            return RejectionReason.DUPLICATE
        
        if message_data.get('is_chat', False):
            return RejectionReason.CHAT
        
        return RejectionReason.OTHER


def normalize_message_data(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    规范化消息数据，将其转换为Linus式格式
    
    Args:
        message_data: 原始消息数据
        
    Returns:
        规范化后的消息数据
    """
    normalized = message_data.copy()
    
    # 映射状态
    old_status = message_data.get('status', 'pending')
    new_status = StatusMapper.map_legacy_status(old_status)
    normalized['status'] = new_status.value
    
    # 处理拒绝原因
    if new_status == MessageStatus.REJECTED:
        rejection_reason = StatusMapper.extract_rejection_info(message_data)
        if rejection_reason:
            normalized['rejection_reason'] = rejection_reason.value
        
        # 清理遗留的布尔字段
        legacy_flags = ['is_ad', 'is_duplicate', 'is_chat', 'is_spam']
        for flag in legacy_flags:
            normalized.pop(flag, None)
    
    # 记录映射
    if old_status != new_status.value:
        logger.debug(f"状态映射: {old_status} -> {new_status.value}")
    
    return normalized


def is_valid_status(status: str) -> bool:
    """检查状态是否为有效的Linus状态"""
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
        RejectionReason.DUPLICATE: "重复消息",
        RejectionReason.CHAT: "聊天消息",
        RejectionReason.LOW_QUALITY: "低质量内容", 
        RejectionReason.INAPPROPRIATE: "不当内容",
        RejectionReason.OTHER: "其他原因"
    }
    return display_names.get(reason, reason.value)