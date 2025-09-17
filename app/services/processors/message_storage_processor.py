"""
消息存储处理器
负责数据准备、消息保存和组合消息处理
"""
import logging
import hashlib
import json
import asyncio
from typing import Optional, Dict

from app.services.processors.base import MessageProcessor, ProcessorResult, MessageContext

logger = logging.getLogger(__name__)


class MessageStorageProcessor(MessageProcessor):
    """消息存储处理器 - 准备数据并保存到存储系统"""
    
    def __init__(self):
        super().__init__("MessageStorageProcessor")
        # 延迟初始化依赖
        self._redis_store = None
        self._message_grouper = None
    
    @property
    def redis_store(self):
        """直接使用Redis存储，避免循环依赖"""
        if self._redis_store is None:
            from app.storage.redis_manager import redis_manager
            self._redis_store = redis_manager
        return self._redis_store
    
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
        - 保存单独消息
        - 处理组合消息（如果有）
        """
        try:
            message = context.telegram_message
            
            # 步骤1: 准备保存数据
            await self._prepare_save_data(context)
            
            # 步骤2: 处理拒绝状态
            if context.should_reject:
                context.save_data['status'] = 'rejected'
                context.save_data['reject_reason'] = context.reject_reason
                
            
            # 【方案1修改】检查是否为已合并的组消息
            is_combined = getattr(context, 'is_combined_message', False)
            
            # 🚀 新增：检查历史采集器传递的完整组消息
            is_complete_group = getattr(message, '_is_complete_group', False)
            
            if is_combined or is_complete_group:
                # 已合并的组消息，直接保存，添加组合消息标记
                group_type = "历史采集组消息" if is_complete_group else "已合并组消息"
                group_size = getattr(message, '_group_size', 'unknown')
                self.logger.info(f"📦 检测到{group_type}: #{message.id} | channel: {context.channel_id} | 大小: {group_size}")
                context.save_data['is_combined'] = True
                
                # 保存合并信息
                if is_complete_group and hasattr(message, '_group_messages'):
                    # 历史采集器传递的完整组消息
                    group_messages = message._group_messages
                    context.save_data['combined_messages'] = json.dumps([msg.id for msg in group_messages])
                    context.save_data['group_size'] = len(group_messages)
                    
                    # 合并所有消息的内容
                    combined_content = []
                    for msg in group_messages:
                        if hasattr(msg, 'message') and msg.message:
                            combined_content.append(msg.message)
                        elif hasattr(msg, 'text') and msg.text:
                            combined_content.append(msg.text)
                    
                    if combined_content:
                        context.save_data['content'] = '\n\n'.join(combined_content)
                        self.logger.debug(f"合并组消息内容: {len(combined_content)} 段")
                    
                elif hasattr(context, 'combined_messages') and context.combined_messages:
                    # 原有的已合并消息处理
                    context.save_data['combined_messages'] = json.dumps(context.combined_messages)
                if hasattr(context, 'media_group') and context.media_group:
                    context.save_data['media_group'] = json.dumps(context.media_group)
                
                # 直接保存已合并的组消息
                saved_message = await self._save_to_redis_directly(context.save_data)
                
                if not saved_message:
                    return ProcessorResult(False, context, "已合并组消息保存失败")
                
                context.save_data = saved_message
                msg_id = saved_message.get('message_id', 'N/A')
                status = saved_message.get('status', 'unknown')
                self.logger.info(f"✅ 已合并组消息保存成功: #{message.id} -> Redis {context.channel_id}:{msg_id} [状态: {status}]")
                
            else:
                # 修复：直接从context获取，消除getattr特殊情况
                grouped_id = getattr(message, 'grouped_id', None)
                
                if grouped_id:
                    # 【方案1】不应该再有未处理的组消息，记录警告
                    self.logger.warning(f"⚠️ 收到未处理的组消息 #{message.id} (grouped_id: {grouped_id}) - 可能是配置错误或旧数据")
                    # 降级为单消息处理，保留grouped_id信息
                    context.save_data['grouped_id'] = str(grouped_id)
                    context.save_data['is_combined'] = False
                
                # 步骤3: 保存到Redis
                saved_message = await self._save_to_redis_directly(context.save_data)
                
                if not saved_message:
                    return ProcessorResult(False, context, "消息保存失败")
                
                # 更新上下文
                context.save_data = saved_message
                
                # 记录保存结果
                msg_id = saved_message.get('message_id', 'N/A')
                status = saved_message.get('status', 'unknown')
                message_type_desc = "已合并组消息" if is_combined else ("组消息(降级)" if grouped_id else "单消息")
                self.logger.info(f"{message_type_desc}已保存: #{message.id} -> Redis {context.channel_id}:{msg_id} [状态: {status}]")
                
                # ✅ 关键修复：消息保存成功后立即更新checkpoint
                await self._update_checkpoint_after_save(context, saved_message)
            
            # 如果消息已自动批准（人工审核关闭），自动提交发布任务
            if context.save_data and context.save_data.get('status') == 'approved':
                try:
                    from app.services.message_forward_queue import forward_queue
                    message_id_str = f"{context.channel_id}:{context.save_data.get('message_id')}"
                    await forward_queue.submit_forward_task(message_id_str, "forward_to_target")
                    self.logger.info(f"人工审核已关闭，消息 {message_id_str} 已自动提交发布任务")
                except Exception as e:
                    self.logger.error(f"自动提交发布任务失败 {message_id_str}: {e}")
            
            # 发送WebSocket通知更新统计数据（异步，不等待）
            asyncio.create_task(self._notify_stats_update())
            
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
            'ad_detection_score': getattr(context, 'ad_detection_score', None),
            'ad_detection_threshold': getattr(context, 'ad_detection_threshold', None),
            'ad_detected': getattr(context, 'ad_detected', False),
            'media_type': self._determine_media_type(context),
            'media_url': self._determine_media_url(context),
            'media_hash': media_hash,
            'ocr_text': ocr_text,
            'qr_codes': qr_codes,
            'ocr_ad_score': ocr_ad_score,
            'ocr_processed': ocr_processed,
            'removed_hidden_links': context.removed_hidden_links,
            'visual_hash': visual_hash,
            'grouped_id': str(getattr(message, 'grouped_id', None)) if getattr(message, 'grouped_id', None) else None,
            'is_combined': False,  # 单独消息不是组合消息
            'status': 'pending',   # 状态将在下面根据配置设置
            'created_at': context.created_at,
            'source_channel_link_prefix': self._generate_channel_link_prefix(context.channel_id)
        }
        
        # 检查是否需要人工审核
        from app.services.config_manager import config_manager
        require_approval = await config_manager.get_config('review.require_approval', True)
        
        if require_approval:
            # 需要人工审核，保持待审核状态
            save_data['status'] = 'pending'
        else:
            # 不需要人工审核，直接设置为已批准状态
            save_data['status'] = 'approved'
            self.logger.info(f"人工审核已关闭，消息 #{message.id} 自动批准")
        
        # 🔧 修复：为组合消息子消息添加特殊标记
        if hasattr(message, 'grouped_id') and message.grouped_id:
            save_data['is_group_child'] = True
            save_data['grouped_id'] = str(message.grouped_id)
            self.logger.debug(f"标记子消息 #{message.id} 属于组合消息 {message.grouped_id}")
        
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
    
    
    async def _handle_grouped_message(self, context: MessageContext, grouped_id: str):
        """处理组合消息 - 增强版，支持智能选择处理方式"""
        try:
            message = context.telegram_message
            
            # 智能决策：是否使用主动获取
            should_use_active_fetch = await self._should_use_active_fetch(context, grouped_id)
            
            if should_use_active_fetch:
                # 使用主动获取完整组（现在包含媒体下载）
                self.logger.info(f"使用主动获取处理组合消息: {grouped_id}")
                
                # 直接调用主动获取方法
                complete_group = await self.message_grouper._fetch_complete_group(
                    context.channel_id,
                    grouped_id,
                    message.id
                )
                
                if complete_group:
                    # 创建并保存完整的组合消息
                    combined_message = await self.message_grouper._create_combined_message(complete_group, context.channel_id)
                    processed_data = await self.message_grouper._save_combined_message(combined_message, context.channel_id)
                    
                    if processed_data:
                        # 保存到Redis
                        await self.message_grouper._save_to_redis(processed_data, combined_message, context.channel_id)
                        self.logger.info(f"✅ 处理完成，组合消息包含 {len(complete_group)} 条消息")
                    else:
                        self.logger.error(f"❌ 处理失败，数据处理错误")
                else:
                    self.logger.error(f"❌ 主动获取失败，回退到传统方式")
                    # 回退到传统方式
                    await self._handle_grouped_message_traditional(context, grouped_id)
            else:
                # 使用传统的被动等待方式
                await self._handle_grouped_message_traditional(context, grouped_id)
            
        except Exception as e:
            self.logger.error(f"处理组合消息失败: {e}")
    
    async def _should_use_active_fetch(self, context: MessageContext, grouped_id: str) -> bool:
        """判断是否应该使用主动获取"""
        try:
            # 检查是否已经存在不完整的组合消息
            existing_combined = await self.message_grouper._get_existing_combined_message(context.channel_id, grouped_id)
            if existing_combined:
                # 检查是否可能不完整（文本长度过短）
                content = existing_combined.get('content', '')
                text_length = len(content.replace('[📎 媒体组:', '').split(']')[0])
                if text_length < 50:  # 可能不完整
                    self.logger.info(f"检测到可能不完整的组合消息，使用主动获取: {grouped_id}")
                    return True
            
            # 3. 对于实时消息，检查配置
            from app.services.config_manager import config_manager
            use_active_fetch = await config_manager.get_config('grouper.use_active_fetch', False)
            if use_active_fetch:
                return True
            
            # 4. 默认使用传统方式（保持向后兼容）
            return False
            
        except Exception as e:
            self.logger.error(f"判断处理方式失败，使用默认方式: {e}")
            return False
    
    async def _handle_grouped_message_traditional(self, context: MessageContext, grouped_id: str):
        """传统的组合消息处理方式（被动等待）"""
        try:
            message = context.telegram_message
            
            # 注册消息到组合器
            grouper_result = await self.message_grouper.process_message(
                message,
                context.channel_id,
                context.media_info,
                filtered_content=context.filtered_content,
                is_ad=context.is_ad,
                is_batch=False  # 统一处理：不区分批量/单个
            )
            
            self.logger.debug(f"消息已注册到传统组合器，组ID: {grouped_id}")
            
        except Exception as e:
            self.logger.error(f"传统组合消息处理失败: {e}")
    
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
    
    async def _save_to_redis_directly(self, save_data: dict) -> dict:
        """直接保存到Redis，避免循环依赖"""
        try:
            # 生成消息ID
            from app.utils.timezone import get_current_time
            import time
            
            message_id = f"{save_data['source_channel']}:{save_data['message_id']}"
            save_data['id'] = message_id
            save_data['timestamp'] = get_current_time().isoformat()
            
            # 直接保存到Redis
            success = self.redis_store.save_message(
                save_data['source_channel'],
                save_data['message_id'], 
                save_data
            )
            
            if success:
                self.logger.debug(f"消息已保存到Redis: {message_id}")
                return save_data
            else:
                self.logger.error(f"保存到Redis失败: {message_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"直接保存到Redis失败: {e}")
            return None
    
    def _generate_channel_link_prefix(self, channel_id: str, channel_username: str = None) -> str:
        """
        生成频道链接前缀 - 简化逻辑
        优先使用已知的频道用户名，否则查找配置，最后使用内部ID格式
        """
        try:
            # 第一优先级：直接使用传入的频道用户名
            if channel_username:
                clean_username = channel_username.lstrip('@')
                if clean_username:
                    return f"https://t.me/{clean_username}"
            
            # 第二优先级：从频道配置查找用户名
            from app.storage.json_store import get_json_channel_store
            channel_store = get_json_channel_store()
            channels_list = channel_store.get_all_channels() or []
            
            # 查找匹配的频道
            for channel_info in channels_list:
                if channel_info.get('channel_id') == channel_id:
                    channel_name = channel_info.get('channel_name')
                    if channel_name:
                        clean_username = channel_name.lstrip('@')
                        if clean_username:
                            return f"https://t.me/{clean_username}"
            
            # 第三优先级：使用内部频道ID格式
            clean_id = channel_id.lstrip('-')
            return f"https://t.me/c/{clean_id}"
            
        except Exception as e:
            self.logger.error(f"生成频道链接前缀失败: {e}")
            # 降级到内部ID格式
            return f"https://t.me/c/{channel_id.lstrip('-')}"
    
    async def _notify_stats_update(self):
        """发送WebSocket通知更新统计数据"""
        try:
            from app.api.websocket import websocket_manager
            from datetime import datetime
            import json
            
            # 获取最新统计数据
            stats = self.redis_store.get_statistics()
            
            # 构造通知数据
            notification_data = {
                "type": "stats_update",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "total_messages": stats.get("total_messages", 0),
                    "pending_count": stats.get("pending_messages", 0),
                    "approved_count": stats.get("approved_messages", 0),
                    "rejected_count": stats.get("rejected_messages", 0)
                }
            }
            
            # 通过WebSocket广播统计更新
            await websocket_manager.broadcast(json.dumps(notification_data, ensure_ascii=False))
            
        except Exception as e:
            # 通知失败不应该影响消息处理流程，只记录错误
            self.logger.debug(f"发送统计更新通知失败: {e}")
    
    async def _update_checkpoint_after_save(self, context, saved_message):
        """消息保存成功后立即更新checkpoint"""
        try:
            if not saved_message:
                return
            
            channel_id = context.channel_id
            message_id = saved_message.get('message_id')
            
            if not channel_id or not message_id:
                self.logger.warning(f"无法更新checkpoint：channel_id={channel_id}, message_id={message_id}")
                return
            
            # 导入必要的模块
            from app.storage.channel_store import RedisChannelStore
            from app.storage.redis_manager import redis_manager
            
            # 创建channel store
            try:
                channel_store = RedisChannelStore(redis_manager.client)
                
                # 设置checkpoint
                success = channel_store.set_checkpoint(channel_id, int(message_id))
                
                if success:
                    self.logger.info(f"✅ Checkpoint已更新: {channel_id} -> {message_id}")
                else:
                    self.logger.error(f"❌ Checkpoint更新失败: {channel_id} -> {message_id}")
                    
            except Exception as store_error:
                self.logger.error(f"创建channel store失败: {store_error}")
                
        except Exception as e:
            # checkpoint更新失败不应该影响消息保存流程
            self.logger.error(f"更新checkpoint失败: {e}")

