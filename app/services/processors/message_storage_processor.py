"""
消息存储处理器
负责数据准备、去重检测、消息保存和组合消息处理
"""
import logging
import hashlib
import json
from typing import Optional, Dict

from app.services.processors.base import MessageProcessor, ProcessorResult, MessageContext

logger = logging.getLogger(__name__)


class MessageStorageProcessor(MessageProcessor):
    """消息存储处理器 - 准备数据并保存到存储系统"""
    
    def __init__(self):
        super().__init__("MessageStorageProcessor")
        # 延迟初始化依赖
        self._duplicate_detector = None
        self._message_processor = None
        self._message_grouper = None
    
    @property
    def duplicate_detector(self):
        """延迟加载去重检测器"""
        if self._duplicate_detector is None:
            from app.services.duplicate_detector import DuplicateDetector
            self._duplicate_detector = DuplicateDetector()
        return self._duplicate_detector
    
    @property
    def message_processor(self):
        """延迟加载消息处理器"""
        if self._message_processor is None:
            from app.services.message_processor import MessageProcessor
            self._message_processor = MessageProcessor()
        return self._message_processor
    
    @property
    def message_grouper(self):
        """延迟加载消息组合器"""
        if self._message_grouper is None:
            from app.services.message_grouper import message_grouper
            self._message_grouper = message_grouper
        return self._message_grouper
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理消息存储阶段
        - 准备保存数据
        - 去重检测
        - 保存单独消息
        - 处理组合消息（如果有）
        """
        try:
            message = context.telegram_message
            
            # 步骤1: 准备保存数据
            await self._prepare_save_data(context)
            
            # 步骤2: 去重检测
            await self._check_duplicate(context)
            
            # 步骤3: 处理拒绝状态
            if context.should_reject:
                context.save_data['status'] = 'rejected'
                context.save_data['reject_reason'] = context.reject_reason
                
                # 保存重复信息（如果有）
                if context.duplicate_info:
                    context.save_data['duplicate_original_id'] = context.duplicate_info.get('original_id')
                    context.save_data['duplicate_type'] = context.duplicate_info.get('type')
            
            # 检查是否为组消息
            grouped_id = str(getattr(message, 'grouped_id', None)) if getattr(message, 'grouped_id', None) else None
            
            if grouped_id:
                # 组消息交给组合器处理，不立即保存
                await self._handle_grouped_message(context, grouped_id)
                # 设置save_data为None，表示等待组合
                context.save_data = None
                self.logger.info(f"组消息 #{message.id} 已交给组合器处理，等待组合完成")
            else:
                # 步骤4: 非组消息立即保存到Redis
                saved_message = await self.message_processor.process_new_message(context.save_data)
                
                if not saved_message:
                    return ProcessorResult(False, context, "消息保存失败")
                
                # 更新上下文
                context.save_data = saved_message
                
                # 记录保存结果
                msg_id = saved_message.get('message_id', 'N/A')
                status = saved_message.get('status', 'unknown')
                self.logger.info(f"消息已保存: #{message.id} -> Redis {context.channel_id}:{msg_id} [状态: {status}]")
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            # 清理媒体文件
            await self._cleanup_media_files(context)
            return await self._handle_error(context, e)
    
    async def _prepare_save_data(self, context: MessageContext):
        """准备保存数据"""
        message = context.telegram_message
        
        # 处理媒体哈希
        media_hash = None
        visual_hash = None
        
        if context.media_info:
            media_hash = context.media_info.get('hash')
            if context.media_info.get('visual_hashes'):
                visual_hash = json.dumps(context.media_info['visual_hashes'])
        
        # 处理OCR结果
        ocr_text = None
        qr_codes = None
        ocr_ad_score = 0
        ocr_processed = False
        
        if context.ocr_result:
            if context.ocr_result.get('texts'):
                ocr_text = json.dumps(context.ocr_result['texts'], ensure_ascii=False)
            
            if context.ocr_result.get('qr_codes'):
                qr_codes = json.dumps(context.ocr_result['qr_codes'], ensure_ascii=False)
            
            ocr_ad_score = int(context.ocr_result.get('ad_score', 0))
            ocr_processed = bool(context.ocr_result.get('processed_files', 0) > 0)
        
        # 准备保存数据
        save_data = {
            'source_channel': context.channel_id,
            'message_id': message.id,
            'content': context.original_content,
            'filtered_content': context.filtered_content,
            'is_ad': context.is_ad,
            'media_type': self._determine_media_type(context),
            'media_url': self._determine_media_url(context),
            'media_hash': media_hash,
            'ocr_text': ocr_text,
            'qr_codes': qr_codes,
            'ocr_ad_score': ocr_ad_score,
            'ocr_processed': ocr_processed,
            'entities': context.entities,
            'removed_hidden_links': context.removed_hidden_links,
            'visual_hash': visual_hash,
            'grouped_id': str(getattr(message, 'grouped_id', None)) if getattr(message, 'grouped_id', None) else None,
            'is_combined': False,  # 单独消息不是组合消息
            'status': 'pending',   # 默认状态
            'created_at': context.created_at,
            'source_channel_link_prefix': self._generate_channel_link_prefix(context.channel_id)
        }
        
        # 添加过滤原因（如果有）
        if context.filter_reason:
            save_data['filter_reason'] = context.filter_reason
        
        context.save_data = save_data
    
    def _determine_media_type(self, context: MessageContext) -> Optional[str]:
        """确定媒体类型"""
        # 1. 优先使用实际下载的媒体信息
        if context.media_info and context.media_info.get('media_type'):
            return context.media_info['media_type']
        
        # 2. 使用检测到的媒体类型信息
        if context.media_type_info and context.media_type_info.get('media_type'):
            return context.media_type_info['media_type']
        
        return None
    
    def _determine_media_url(self, context: MessageContext) -> Optional[str]:
        """确定媒体URL"""
        # 1. 优先使用实际下载的媒体文件
        if context.media_info and context.media_info.get('file_path'):
            return context.media_info['file_path']
        
        # 2. 如果有媒体但下载失败，生成占位符
        if (context.media_type_info and 
            context.media_type_info.get('has_media') and 
            context.media_type_info.get('download_failed')):
            
            media_type = context.media_type_info.get('media_type', 'media')
            media_type_name = {
                'photo': '图片',
                'video': '视频',
                'document': '文件',
                'animation': '动图',
                'audio': '音频',
                'sticker': '贴纸'
            }.get(media_type, '媒体')
            
            return f"placeholder:{media_type_name}下载失败"
        
        return None
    
    async def _check_duplicate(self, context: MessageContext):
        """检查重复消息"""
        try:
            save_data = context.save_data
            
            # 提取视觉哈希
            visual_hashes = None
            if context.media_info and context.media_info.get('visual_hashes'):
                visual_hashes = context.media_info['visual_hashes']
            
            # 执行去重检测
            is_duplicate, orig_id, dup_type = await self.duplicate_detector.is_duplicate_message(
                source_channel=context.channel_id,
                media_hash=save_data.get('media_hash'),
                combined_media_hash=save_data.get('combined_media_hash'),
                content=save_data.get('content'),
                message_time=save_data.get('created_at'),
                visual_hashes=visual_hashes
            )
            
            if is_duplicate:
                duplicate_info = {
                    'original_id': orig_id,
                    'type': dup_type,
                    'reason': f"{dup_type}重复"
                }
                context.duplicate_info = duplicate_info
                
                # 如果尚未被标记为拒绝，则标记为去重拒绝
                if not context.should_reject:
                    context.should_reject = True
                    context.reject_reason = f"去重检测: {duplicate_info['reason']}"
                
                self.logger.info(f"检测到重复消息（{dup_type}），原始消息ID: {orig_id}")
            
        except Exception as e:
            self.logger.error(f"重复检测失败: {e}")
    
    async def _handle_grouped_message(self, context: MessageContext, grouped_id: str):
        """处理组合消息"""
        try:
            message = context.telegram_message
            
            # 注册消息到组合器
            grouper_result = await self.message_grouper.process_message(
                message,
                context.channel_id,
                context.media_info,
                filtered_content=context.filtered_content,
                is_ad=context.is_ad,
                is_batch=context.is_history
            )
            
            self.logger.debug(f"消息已注册到组合器，组ID: {grouped_id}")
            
        except Exception as e:
            self.logger.error(f"处理组合消息失败: {e}")
    
    async def _cleanup_media_files(self, context: MessageContext):
        """清理媒体文件"""
        try:
            from app.services.media_handler import media_handler
            
            # 清理单个媒体文件
            if context.media_info and context.media_info.get('file_path'):
                await media_handler.cleanup_file(context.media_info['file_path'])
            
            # 清理保存数据中的媒体文件
            if context.save_data:
                media_url = context.save_data.get('media_url')
                if media_url and not media_url.startswith('placeholder:'):
                    import os
                    if os.path.exists(media_url):
                        await media_handler.cleanup_file(media_url)
                
                # 清理组合消息的媒体文件
                if context.save_data.get('media_group'):
                    for media_item in context.save_data['media_group']:
                        file_path = media_item.get('file_path')
                        if file_path and os.path.exists(file_path):
                            await media_handler.cleanup_file(file_path)
            
        except Exception as e:
            self.logger.error(f"清理媒体文件失败: {e}")
    
    def _generate_channel_link_prefix(self, channel_id: str) -> str:
        """
        生成频道链接前缀
        优先使用公开频道用户名，否则使用内部频道ID格式
        """
        try:
            from app.storage.json_store import get_json_channel_store
            
            # 尝试从频道配置获取用户名
            channel_store = get_json_channel_store()
            channels_list = channel_store.get_all_channels() or []
            # 转换为字典格式便于查找
            channels_data = {ch.get('channel_id', ch.get('name', '')): ch for ch in channels_list}
            
            # 查找匹配的频道
            for channel_key, channel_info in channels_data.items():
                if channel_info.get('channel_id') == channel_id:
                    channel_name = channel_info.get('channel_name')
                    if channel_name and channel_name.startswith('@'):
                        # 使用公开频道用户名格式
                        # 格式：https://t.me/用户名/消息ID
                        return f"https://t.me/{channel_name[1:]}"  # 移除@符号
            
            # 如果没找到用户名，使用内部频道ID格式
            clean_id = channel_id.lstrip('-')
            return f"https://t.me/c/{clean_id}"
            
        except Exception as e:
            self.logger.error(f"生成频道链接前缀失败: {e}")
            # 降级到内部ID格式
            return f"https://t.me/c/{channel_id.lstrip('-')}"


class DuplicateChecker(MessageProcessor):
    """去重检测处理器 - 专门处理消息去重逻辑"""
    
    def __init__(self):
        super().__init__("DuplicateChecker")
        self._duplicate_detector = None
    
    @property
    def duplicate_detector(self):
        """延迟加载去重检测器"""
        if self._duplicate_detector is None:
            from app.services.duplicate_detector import DuplicateDetector
            self._duplicate_detector = DuplicateDetector()
        return self._duplicate_detector
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        执行去重检测
        - 检查内容重复
        - 检查媒体重复
        - 检查视觉相似度
        """
        try:
            # 如果已经被标记为拒绝，跳过去重检测
            if context.should_reject:
                return ProcessorResult(True, context)
            
            # 准备去重检测数据
            visual_hashes = None
            if context.media_info and context.media_info.get('visual_hashes'):
                visual_hashes = context.media_info['visual_hashes']
            
            # 执行去重检测
            is_duplicate, orig_id, dup_type = await self.duplicate_detector.is_duplicate_message(
                source_channel=context.channel_id,
                media_hash=context.media_info.get('hash') if context.media_info else None,
                combined_media_hash=None,  # 单独消息没有组合哈希
                content=context.original_content,
                message_time=context.created_at,
                visual_hashes=visual_hashes
            )
            
            if is_duplicate:
                context.duplicate_info = {
                    'original_id': orig_id,
                    'type': dup_type,
                    'reason': f"{dup_type}重复"
                }
                
                context.should_reject = True
                context.reject_reason = f"去重检测: {context.duplicate_info['reason']}"
                
                self.logger.info(f"检测到重复消息（{dup_type}），原始消息ID: {orig_id}")
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            return await self._handle_error(context, e)