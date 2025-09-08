"""
消息处理器模块
提供模块化的消息处理管道和处理器
"""

# 基础架构
from .base import MessageContext, ProcessorResult, MessageProcessor, MessagePipeline

# 具体处理器
from .message_receiver import MessageReceiver, MediaMetadataProcessor
from .message_filter_processor import MessageFilterProcessor
from .message_ad_detector_processor import MessageAdDetectorProcessor
from .message_storage_processor import MessageStorageProcessor
from .message_forwarder_processor import MessageForwarderProcessor, ReviewForwarder, WebSocketBroadcaster

__all__ = [
    # 基础架构
    'MessageContext',
    'ProcessorResult', 
    'MessageProcessor',
    'MessagePipeline',
    
    # 接收处理器
    'MessageReceiver',
    'MediaMetadataProcessor',
    
    # 过滤处理器
    'MessageFilterProcessor',
    
    # 广告检测处理器
    'MessageAdDetectorProcessor',
    
    # 存储处理器
    'MessageStorageProcessor',
    
    # 转发处理器
    'MessageForwarderProcessor',
    'ReviewForwarder', 
    'WebSocketBroadcaster',
]