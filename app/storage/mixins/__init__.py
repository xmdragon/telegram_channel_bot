"""
消息存储Mixin模块
将RedisMessageStore的功能按职责拆分为独立的Mixin类
"""

from .crud_mixin import MessageCrudMixin
from .query_mixin import MessageQueryMixin
from .status_mixin import MessageStatusMixin
from .stats_mixin import MessageStatsMixin
from .maintenance_mixin import MessageMaintenanceMixin
from .compatibility_mixin import MessageCompatibilityMixin

__all__ = [
    'MessageCrudMixin',
    'MessageQueryMixin', 
    'MessageStatusMixin',
    'MessageStatsMixin',
    'MessageMaintenanceMixin',
    'MessageCompatibilityMixin'
]