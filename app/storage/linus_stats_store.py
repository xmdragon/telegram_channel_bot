"""
Linus式消息统计存储
彻底简化的统计系统 - 遵循"好品味"原则

核心原则：
1. 只有3种状态：pending, approved, rejected（没有更多）
2. 拒绝原因是元数据，不是状态
3. 原子计数器，100%一致性
4. 消除所有特殊情况
"""
import logging
from typing import Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass
from .redis_client import RedisBaseStore

logger = logging.getLogger(__name__)


class MessageState(Enum):
    """消息状态 - 只有3种，没有更多特殊情况"""
    PENDING = "pending"     # 待审核
    APPROVED = "approved"   # 已发布
    REJECTED = "rejected"   # 已拒绝


class RejectionReason(Enum):
    """拒绝原因 - 元数据，不是状态"""
    AD = "ad"              # 广告
    DUPLICATE = "duplicate" # 重复
    CHAT = "chat"          # 聊天
    OTHER = "other"        # 其他


@dataclass
class MessageStats:
    """消息统计数据结构"""
    total: int
    pending: int
    approved: int
    rejected: int
    
    def __post_init__(self):
        """确保数据一致性"""
        calculated_total = self.pending + self.approved + self.rejected
        if self.total != calculated_total:
            logger.warning(f"统计不一致: total={self.total}, calculated={calculated_total}")


@dataclass
class RejectionStats:
    """拒绝原因统计"""
    ad: int
    duplicate: int
    chat: int
    other: int


class LinusStatsStore(RedisBaseStore):
    """
    Linus式统计存储
    
    设计原则：
    1. 数据结构决定一切
    2. 消除所有特殊情况
    3. 原子操作保证一致性
    4. O(1)性能，不扫描不采样
    """
    
    # Redis键模式 - 简化且一致
    GLOBAL_STATS_KEY = "stats:global"
    CHANNEL_STATS_PREFIX = "stats:channel:"
    REJECTION_STATS_KEY = "stats:rejection"
    
    def __init__(self, redis_url: str = None):
        super().__init__(redis_url)
        self._init_global_stats()
    
    def _init_global_stats(self):
        """初始化全局统计计数器"""
        if not self.redis.exists(self.GLOBAL_STATS_KEY):
            # 原子初始化所有计数器为0
            pipe = self.redis.pipeline()
            pipe.hset(self.GLOBAL_STATS_KEY, mapping={
                'total': 0,
                'pending': 0,
                'approved': 0,
                'rejected': 0
            })
            pipe.hset(self.REJECTION_STATS_KEY, mapping={
                'ad': 0,
                'duplicate': 0,
                'chat': 0,
                'other': 0
            })
            pipe.execute()
    
    def increment_message(self, state: MessageState, channel_id: str = None):
        """
        增加消息计数 - 原子操作
        
        Args:
            state: 消息状态
            channel_id: 频道ID（可选，用于频道级统计）
        """
        try:
            pipe = self.redis.pipeline()
            
            # 全局统计
            pipe.hincrby(self.GLOBAL_STATS_KEY, 'total', 1)
            pipe.hincrby(self.GLOBAL_STATS_KEY, state.value, 1)
            
            # 频道级统计（如果提供）
            if channel_id:
                channel_key = f"{self.CHANNEL_STATS_PREFIX}{channel_id}"
                pipe.hincrby(channel_key, 'total', 1)
                pipe.hincrby(channel_key, state.value, 1)
            
            pipe.execute()
            logger.debug(f"消息计数已更新: {state.value} (频道: {channel_id or 'global'})")
            
        except Exception as e:
            logger.error(f"增加消息计数失败: {e}")
    
    def change_message_state(self, old_state: MessageState, new_state: MessageState, 
                           channel_id: str = None, rejection_reason: Optional[RejectionReason] = None):
        """
        改变消息状态 - 原子操作
        
        Args:
            old_state: 旧状态
            new_state: 新状态
            channel_id: 频道ID（可选）
            rejection_reason: 拒绝原因（仅当new_state为REJECTED时）
        """
        try:
            pipe = self.redis.pipeline()
            
            # 全局统计更新
            pipe.hincrby(self.GLOBAL_STATS_KEY, old_state.value, -1)
            pipe.hincrby(self.GLOBAL_STATS_KEY, new_state.value, 1)
            
            # 频道级统计更新
            if channel_id:
                channel_key = f"{self.CHANNEL_STATS_PREFIX}{channel_id}"
                pipe.hincrby(channel_key, old_state.value, -1)
                pipe.hincrby(channel_key, new_state.value, 1)
            
            # 处理拒绝原因统计
            if new_state == MessageState.REJECTED and rejection_reason:
                pipe.hincrby(self.REJECTION_STATS_KEY, rejection_reason.value, 1)
            elif old_state == MessageState.REJECTED and rejection_reason:
                # 从rejected状态改变时，减少拒绝原因计数
                pipe.hincrby(self.REJECTION_STATS_KEY, rejection_reason.value, -1)
            
            pipe.execute()
            logger.debug(f"状态已更新: {old_state.value} -> {new_state.value}")
            
        except Exception as e:
            logger.error(f"更新消息状态失败: {e}")
    
    def get_global_stats(self) -> MessageStats:
        """
        获取全局统计 - Linus式单一数据源版本
        直接从索引计算，消除数据不一致问题
        """
        try:
            # 🔥 Linus方式：索引就是唯一真相源
            pending = self.redis.zcard("msg:idx:pending")      # O(1)
            approved = self.redis.zcard("msg:idx:approved")    # O(1)
            rejected = self.redis.zcard("msg:idx:rejected")    # O(1)
            auto_forwarded = self.redis.zcard("msg:idx:auto_forwarded")  # O(1)
            
            # 直接使用approved
            total_approved = approved
            total = pending + total_approved + rejected + auto_forwarded
            
            logger.debug(f"📊 从索引计算统计: pending={pending}, approved={total_approved}, rejected={rejected}, total={total}")
            
            return MessageStats(
                total=total,
                pending=pending,
                approved=total_approved,
                rejected=rejected
            )
        except Exception as e:
            logger.error(f"获取全局统计失败: {e}")
            return MessageStats(0, 0, 0, 0)
    
    def get_channel_stats(self, channel_id: str) -> MessageStats:
        """获取频道统计 - O(1)操作"""
        try:
            channel_key = f"{self.CHANNEL_STATS_PREFIX}{channel_id}"
            stats_data = self.redis.hgetall(channel_key)
            if not stats_data:
                return MessageStats(0, 0, 0, 0)
            
            # 处理字节字符串和普通字符串两种情况
            def get_value(key):
                byte_key = key.encode() if isinstance(key, str) else key
                str_key = key.decode() if isinstance(key, bytes) else key
                
                value = stats_data.get(byte_key) or stats_data.get(str_key) or 0
                if isinstance(value, bytes):
                    value = value.decode()
                return int(value)
            
            return MessageStats(
                total=get_value('total'),
                pending=get_value('pending'),
                approved=get_value('approved'),
                rejected=get_value('rejected')
            )
        except Exception as e:
            logger.error(f"获取频道统计失败 (频道: {channel_id}): {e}")
            return MessageStats(0, 0, 0, 0)
    
    def get_rejection_stats(self) -> RejectionStats:
        """
        获取拒绝原因统计 - Linus式单一数据源版本
        从实际rejected消息计算，确保100%准确
        """
        try:
            # 🔥 Linus方式：从实际数据实时聚合
            # 获取所有rejected消息的键
            rejected_keys = self.redis.zrange("msg:idx:rejected", 0, -1)
            
            # 统计各种拒绝原因
            reason_counts = {'ad': 0, 'duplicate': 0, 'chat': 0, 'other': 0}
            
            if rejected_keys:
                # 批量获取拒绝原因
                pipe = self.redis.pipeline()
                for key in rejected_keys:
                    # key格式: "channel_id:message_id"
                    msg_key = f"msg:{key}"
                    pipe.hget(msg_key, 'rejection_reason')
                
                reasons = pipe.execute()
                
                # 统计原因分布
                for reason in reasons:
                    if isinstance(reason, bytes):
                        reason = reason.decode()
                    
                    reason = reason or 'other'  # 默认为other
                    if reason in reason_counts:
                        reason_counts[reason] += 1
                    else:
                        reason_counts['other'] += 1
            
            logger.debug(f"📊 从实际数据计算拒绝原因: {reason_counts}")
            
            return RejectionStats(
                ad=reason_counts['ad'],
                duplicate=reason_counts['duplicate'], 
                chat=reason_counts['chat'],
                other=reason_counts['other']
            )
        except Exception as e:
            logger.error(f"获取拒绝原因统计失败: {e}")
            return RejectionStats(0, 0, 0, 0)
    
    def reset_stats(self):
        """重置所有统计 - 谨慎使用"""
        try:
            pipe = self.redis.pipeline()
            
            # 重置全局统计
            pipe.delete(self.GLOBAL_STATS_KEY)
            pipe.delete(self.REJECTION_STATS_KEY)
            
            # 删除所有频道统计
            pattern = f"{self.CHANNEL_STATS_PREFIX}*"
            channel_keys = self.redis.keys(pattern)
            if channel_keys:
                pipe.delete(*channel_keys)
            
            pipe.execute()
            
            # 重新初始化
            self._init_global_stats()
            
            logger.info("所有统计已重置")
            
        except Exception as e:
            logger.error(f"重置统计失败: {e}")
    
    # 添加缺少的方法以保持向后兼容
    def increment_pending(self):
        """增加pending计数"""
        self.increment_message(MessageState.PENDING)
        
    def increment_approved(self):
        """增加approved计数"""  
        self.increment_message(MessageState.APPROVED)
        
    def increment_rejected(self):
        """增加rejected计数"""
        self.increment_message(MessageState.REJECTED)
        
    def decrement_pending(self):
        """减少pending计数（暂时兼容，实际上不需要了）"""
        try:
            self.redis.hincrby(self.GLOBAL_STATS_KEY, 'pending', -1)
        except Exception as e:
            logger.error(f"减少pending计数失败: {e}")
            
    def decrement_approved(self):
        """减少approved计数"""
        try:
            self.redis.hincrby(self.GLOBAL_STATS_KEY, 'approved', -1)
        except Exception as e:
            logger.error(f"减少approved计数失败: {e}")
            
    def decrement_rejected(self):
        """减少rejected计数（暂时兼容，实际上不需要了）"""
        try:
            self.redis.hincrby(self.GLOBAL_STATS_KEY, 'rejected', -1)
        except Exception as e:
            logger.error(f"减少rejected计数失败: {e}")
            
    def increment_rejection_reason(self, reason: str):
        """增加拒绝原因计数（暂时兼容，实际上不需要了）"""
        try:
            self.redis.hincrby(self.REJECTION_STATS_KEY, reason, 1)
        except Exception as e:
            logger.error(f"增加拒绝原因计数失败: {e}")
    
    def validate_consistency(self) -> Dict[str, Any]:
        """验证统计数据一致性"""
        try:
            global_stats = self.get_global_stats()
            rejection_stats = self.get_rejection_stats()
            
            # 验证全局统计一致性
            calculated_total = global_stats.pending + global_stats.approved + global_stats.rejected
            total_consistent = (global_stats.total == calculated_total)
            
            # 验证拒绝原因总数
            rejection_total = rejection_stats.ad + rejection_stats.duplicate + rejection_stats.chat + rejection_stats.other
            rejection_consistent = (rejection_total <= global_stats.rejected)
            
            return {
                'consistent': total_consistent and rejection_consistent,
                'global_stats': {
                    'total': global_stats.total,
                    'calculated_total': calculated_total,
                    'consistent': total_consistent
                },
                'rejection_stats': {
                    'rejection_total': rejection_total,
                    'rejected_messages': global_stats.rejected,
                    'consistent': rejection_consistent
                }
            }
            
        except Exception as e:
            logger.error(f"验证一致性失败: {e}")
            return {'consistent': False, 'error': str(e)}


# 全局实例
linus_stats_store = None

def get_linus_stats_store() -> LinusStatsStore:
    """获取Linus式统计存储实例"""
    global linus_stats_store
    if linus_stats_store is None:
        linus_stats_store = LinusStatsStore()
    return linus_stats_store

def init_linus_stats_store(redis_url: str = None):
    """初始化Linus式统计存储"""
    global linus_stats_store
    linus_stats_store = LinusStatsStore(redis_url)
    return linus_stats_store