"""
消息处理管道基础架构
定义处理器接口和上下文对象
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from telethon.tl.types import Message as TLMessage

logger = logging.getLogger(__name__)

@dataclass
class MessageContext:
    """消息处理上下文 - 在整个处理管道中传递"""
    
    # 原始消息信息
    telegram_message: TLMessage
    channel_id: str
    # is_history已移除：统一处理所有消息，不区分历史/实时
    
    # 组消息ID - Linus式修复：显式保存，消除特殊情况
    grouped_id: Optional[str] = None
    
    # 处理结果数据
    original_content: str = ""
    processed_content: str = ""
    filtered_content: str = ""
    is_ad: bool = False
    filter_reason: str = ""
    
    # 媒体信息
    media_info: Optional[Dict] = None
    media_type_info: Optional[Dict] = None
    ocr_result: Optional[Dict] = None
    
    # 实体和链接信息
    entities: list = field(default_factory=list)
    removed_hidden_links: list = field(default_factory=list)
    
    # 存储相关
    save_data: Optional[Dict] = None
    duplicate_info: Optional[Dict] = None
    
    # 状态标记
    should_reject: bool = False
    reject_reason: str = ""
    auto_rejected: bool = False
    
    # 转发标记
    should_forward: bool = True
    broadcast_enabled: bool = True
    
    # 时间戳
    created_at: Optional[datetime] = None
    
    # 元数据（用于扩展）
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_metadata(self, key: str, value: Any):
        """添加元数据"""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default=None):
        """获取元数据"""
        return self.metadata.get(key, default)


class ProcessorResult:
    """处理器执行结果"""
    
    def __init__(self, success: bool, context: MessageContext, error: str = ""):
        self.success = success
        self.context = context
        self.error = error
        
    @property
    def failed(self) -> bool:
        return not self.success


class MessageProcessor(ABC):
    """消息处理器基类"""
    
    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__
        self.logger = logging.getLogger(f"{__name__}.{self.name}")
    
    @abstractmethod
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理消息
        
        Args:
            context: 消息上下文
            
        Returns:
            ProcessorResult: 处理结果
        """
        pass
    
    async def _handle_error(self, context: MessageContext, error: Exception) -> ProcessorResult:
        """处理错误的通用方法"""
        error_msg = f"{self.name} 处理失败: {error}"
        self.logger.error(error_msg)
        return ProcessorResult(False, context, error_msg)


class MessagePipeline:
    """消息处理管道"""
    
    def __init__(self, processors: list[MessageProcessor] = None):
        self.processors = processors or []
        self.logger = logging.getLogger(__name__)
    
    def add_processor(self, processor: MessageProcessor):
        """添加处理器到管道"""
        self.processors.append(processor)
        self.logger.info(f"添加处理器: {processor.name}")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        执行完整的处理管道
        
        Args:
            context: 消息上下文
            
        Returns:
            ProcessorResult: 最终处理结果
        """
        self.logger.info(f"开始处理消息 #{context.telegram_message.id} 通过 {len(self.processors)} 个处理器")
        
        try:
            for i, processor in enumerate(self.processors):
                self.logger.debug(f"执行处理器 {i+1}/{len(self.processors)}: {processor.name}")
                
                # 添加超时保护，防止处理器阻塞
                try:
                    start_time = asyncio.get_event_loop().time()
                    result = await asyncio.wait_for(processor.process(context), timeout=30.0)
                    elapsed = asyncio.get_event_loop().time() - start_time
                    self.logger.debug(f"处理器 {processor.name} 执行完成，耗时: {elapsed:.2f}秒")
                except asyncio.TimeoutError:
                    error_msg = (
                        f"🚨 处理器 {processor.name} 执行超时 (30秒)\n"
                        f"  消息ID: {context.telegram_message.id}\n"
                        f"  频道ID: {context.channel_id}\n"
                        f"  这可能表明处理器中存在阻塞操作"
                    )
                    self.logger.error(error_msg)
                    return ProcessorResult(False, context, error_msg)
                
                if result.failed:
                    self.logger.error(f"处理器 {processor.name} 失败: {result.error}")
                    return result
                
                # 记录拒绝状态但继续处理（确保消息被保存）
                if context.should_reject:
                    self.logger.info(f"消息被 {processor.name} 标记为拒绝: {context.reject_reason}")
                    # 继续执行，确保消息被保存到存储
                
                self.logger.debug(f"处理器 {processor.name} 执行成功")
            
            self.logger.info(f"消息 #{context.telegram_message.id} 处理完成")
            return ProcessorResult(True, context)
            
        except Exception as e:
            error_msg = f"管道处理失败: {e}"
            self.logger.error(error_msg)
            return ProcessorResult(False, context, error_msg)