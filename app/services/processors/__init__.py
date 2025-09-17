"""
消息处理器模块
提供模块化的消息处理管道和处理器
"""

# 基础架构
from .base import MessageContext, ProcessorResult, MessageProcessor, MessagePipeline

# 具体处理器
from .message_receiver import MessageReceiver
from .message_storage_processor import MessageStorageProcessor

__all__ = [
    # 基础架构
    'MessageContext',
    'ProcessorResult',
    'MessageProcessor',
    'MessagePipeline',

    # 核心处理器
    'MessageReceiver',
    'MessageStorageProcessor',
]