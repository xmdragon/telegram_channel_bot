"""
消息数据存储操作模块 - 重构版本
处理Telegram消息的存储、检索、更新、删除和统计

重构说明：
- 原804行的庞大类已按单一职责原则拆分为Mixin模块
- 使用组合模式而非继承，保持向后兼容性
- 所有公共API保持不变，现有代码无需修改
"""
import logging
from .redis_client import RedisBaseStore
from .mixins import (
    MessageCrudMixin,
    MessageQueryMixin,
    MessageStatusMixin,
    MessageStatsMixin,
    MessageMaintenanceMixin,
    MessageCompatibilityMixin
)

logger = logging.getLogger(__name__)


class RedisMessageStore(
    MessageCrudMixin,
    MessageQueryMixin,
    MessageStatusMixin,
    MessageStatsMixin,
    MessageMaintenanceMixin,
    MessageCompatibilityMixin,
    RedisBaseStore
):
    """消息存储管理 - 重构版本
    
    通过继承多个Mixin类实现功能拆分：
    - MessageCrudMixin: 基础CRUD操作
    - MessageQueryMixin: 查询和检索功能
    - MessageStatusMixin: 状态管理
    - MessageStatsMixin: 统计和计数
    - MessageMaintenanceMixin: 维护和清理
    - MessageCompatibilityMixin: 向后兼容方法
    
    优势：
    1. 单一职责：每个Mixin专注一个功能领域
    2. 可测试性：功能独立便于单元测试
    3. 可维护性：修改单个功能不影响其他模块
    4. 向后兼容：保持所有现有API不变
    """
    
    pass  # 所有功能已通过Mixin继承实现