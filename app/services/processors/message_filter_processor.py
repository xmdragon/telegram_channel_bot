"""
消息过滤处理器
负责内容过滤、广告检测、OCR处理和自动拒绝判断
"""
import logging
import re
import asyncio
from typing import Tuple, Optional

from app.services.processors.base import MessageProcessor, ProcessorResult, MessageContext
from app.services.filters.base import FilterContext
from app.services.rule_manager import rule_manager
from app.services.rule_learner import rule_learner

logger = logging.getLogger(__name__)


class MessageFilterProcessor(MessageProcessor):
    """消息过滤处理器 - 内容过滤和广告检测"""
    
    def __init__(self):
        super().__init__("MessageFilterProcessor")
        # 延迟初始化过滤管道
        self._filter_pipeline = None
        # 规则管理器初始化标志
        self._rule_manager_initialized = False
    
    @property
    def filter_pipeline(self):
        """延迟加载过滤管道"""
        if self._filter_pipeline is None:
            from app.services.unified_filter_engine import unified_filter_engine
            self._filter_pipeline = unified_filter_engine.filter_pipeline
        return self._filter_pipeline
    
    async def _ensure_rule_manager_initialized(self):
        """确保规则管理器已初始化"""
        if not self._rule_manager_initialized:
            try:
                await rule_manager.initialize()
                self._rule_manager_initialized = True
                self.logger.debug("规则管理器初始化完成")
            except Exception as e:
                self.logger.error(f"规则管理器初始化失败: {e}")
                # 即使失败也标记为已尝试，避免重复初始化
                self._rule_manager_initialized = True
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理消息过滤阶段（带性能监控）
        - 提取消息实体
        - 执行内容过滤
        - 进行广告检测
        - 处理OCR识别
        - 判断是否自动拒绝
        """
        # 导入性能监控
        try:
            from app.services.performance_monitor import PerformanceTimer, perf_logger
            filter_timer = PerformanceTimer("message_filter_processor").start()
        except ImportError:
            filter_timer = None
        
        try:
            message = context.telegram_message
            content = context.processed_content
            
            # 🔧 Linus式修复：检查是否为组合消息的子消息
            # 组合消息子消息跳过所有过滤步骤，保持原始内容
            if hasattr(message, 'grouped_id') and message.grouped_id:
                context.filtered_content = context.original_content
                context.is_ad = False
                context.filter_reason = ""
                context.should_reject = False
                context.reject_reason = ""
                
                self.logger.info(f"📦 组合消息子消息 #{message.id} (组ID: {message.grouped_id}) 跳过过滤，等待组合后统一处理")
                return ProcessorResult(True, context)
            
            # 步骤1: 提取消息实体（包括隐藏链接）
            if filter_timer:
                entity_timer = filter_timer.add_child("extract_entities").start()
            await self._extract_entities(context)
            if filter_timer:
                entity_timer.stop()
            
            # 步骤2: 准备媒体文件列表用于OCR
            media_files = []
            if context.media_info and context.media_info.get('file_path'):
                media_files.append(context.media_info['file_path'])
            
            # 步骤3: 使用过滤管道进行内容过滤（核心性能瓶颈）
            if filter_timer:
                pipeline_timer = filter_timer.add_child("content_filtering").start()
            await self._apply_content_filter(context, media_files)
            if filter_timer:
                pipeline_timer.stop()
                pipeline_timer.set_metric("media_files_count", len(media_files))
                pipeline_timer.set_metric("is_ad", context.is_ad)
            
            # 步骤4: 检查自动拒绝条件
            if filter_timer:
                rejection_timer = filter_timer.add_child("auto_rejection_check").start()
            await self._check_auto_rejection(context)
            if filter_timer:
                rejection_timer.stop()
                rejection_timer.set_metric("should_reject", context.should_reject)
            
            
            # 最终状态日志
            status_summary = f"广告={context.is_ad}, 拒绝={context.should_reject}"
            if context.should_reject:
                status_summary += f", 原因={context.reject_reason}"
            self.logger.info(f"📋 过滤处理完成: {status_summary}")
            
            # 记录性能数据
            if filter_timer:
                total_time = filter_timer.stop()
                filter_timer.set_metric("is_ad", context.is_ad)
                filter_timer.set_metric("should_reject", context.should_reject)
                filter_timer.set_metric("content_length", len(content))
                
                # 如果耗时过长，记录详细的性能日志
                if total_time > 1000:  # 超过1秒
                    perf_data = {
                        "operation": "message_filter_processor",
                        "channel_id": context.channel_id,
                        "message_id": message.id,
                        "total_time_ms": total_time,
                        "performance_breakdown": filter_timer.to_dict(),
                        "bottleneck_warning": True
                    }
                    perf_logger.log_performance(perf_data)
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            if filter_timer:
                filter_timer.stop()
                filter_timer.set_metric("error", str(e))
            return await self._handle_error(context, e)
    
    async def _extract_entities(self, context: MessageContext):
        """提取消息实体 - 简化版本"""
        # 直接设置为空，不再尝试任何导入
        context.entities = {}
        context.removed_hidden_links = []
    
    async def _apply_content_filter(self, context: MessageContext, media_files: list):
        """应用内容过滤管道"""
        try:
            content = context.processed_content
            
            # 创建过滤上下文
            filter_context = FilterContext(
                message_id=context.telegram_message.id,
                channel_id=context.channel_id
            )
            
            # 添加元数据
            filter_context.add_metadata('is_history', False)  # 统一处理：不区分历史/实时
            filter_context.add_metadata('media_files', media_files)
            filter_context.add_metadata('message_obj', context.telegram_message)
            
            # 执行过滤管道
            pipeline_result = await self.filter_pipeline.process(content, filter_context)
            
            # 提取过滤结果
            context.filtered_content = pipeline_result.final_content
            context.filter_reason = pipeline_result.overall_reason or ""
            
            # 广告检测结果 - 综合判断
            ad_detection_result = filter_context.get_metadata('ad_detection_result')
            
            # 🎯 Linus式修复：综合判断广告状态
            # 1. AI检测结果
            ai_detected_ad = bool(ad_detection_result and ad_detection_result.get('is_ad', False))
            
            # 2. 过滤器检测结果（如果有推广内容被过滤，说明检测到广告）
            filter_detected_ad = bool(
                any(
                    not result.passed and result.reason  # 有过滤器检测到问题
                    for result in pipeline_result.filter_results.values()
                    if hasattr(result, 'passed') and hasattr(result, 'reason')
                )
            )
            
            # 综合判断：AI检测或过滤器检测到广告
            context.is_ad = ai_detected_ad or filter_detected_ad
            
            # 调试日志：记录广告检测结果
            if context.is_ad:
                self.logger.info(f"🚫 消息被检测为广告: {context.filter_reason}")
            else:
                self.logger.debug(f"✅ 消息未检测为广告")
            
            # 更新广告检测原因
            if ad_detection_result and ad_detection_result.get('is_ad', False):
                ai_reason = ad_detection_result.get('main_reason', 'AI检测')
                if not context.filter_reason:
                    context.filter_reason = f"AI检测到疑似广告: {ai_reason}"
                else:
                    context.filter_reason += f" + AI检测: {ai_reason}"
            
            # 提取OCR结果
            if 'ad_detector' in pipeline_result.filter_results:
                ad_result = pipeline_result.filter_results['ad_detector']
                context.ocr_result = ad_result.details.get('ocr_result', {}) if ad_result.details else {}
            
            # 记录过滤效果
            if content != context.filtered_content:
                original_len = len(content)
                filtered_len = len(context.filtered_content)
                self.logger.info(f"内容过滤: {original_len} -> {filtered_len} 字符 (减少 {original_len - filtered_len})")
            
            if context.is_ad:
                self.logger.info(f"检测到广告: {context.filter_reason}")
                
                # 调用自动学习机制（异步，不阻塞主流程）
                asyncio.create_task(self._learn_from_ad_detection(context, ad_detection_result))
            
        except Exception as e:
            self.logger.error(f"内容过滤失败: {e}")
            # 失败时保持原内容
            context.filtered_content = context.processed_content
            context.filter_reason = f"过滤失败: {e}"
    
    async def _check_auto_rejection(self, context: MessageContext):
        """检查是否应该自动拒绝消息"""
        self.logger.info(f"🔍 自动拒绝检查: is_ad={context.is_ad}")
        
        if not context.is_ad:
            self.logger.debug("消息未被标记为广告，跳过自动拒绝检查")
            return
        
        # 检查自动拒绝配置
        try:
            from app.services.config_manager import config_manager
            auto_reject_ads = await config_manager.get_config('review.auto_reject_ads', False)
            self.logger.info(f"🔧 自动拒绝广告配置: {auto_reject_ads}")
            
            if not auto_reject_ads:
                self.logger.info("自动拒绝广告未启用，保持待审核状态")
                return
                
        except Exception as e:
            self.logger.error(f"获取自动拒绝配置失败: {e}")
            return
        
        try:
            should_reject, reject_reason = await self._should_reject_pure_ad(context)
            self.logger.info(f"📋 精准拒绝判断结果: should_reject={should_reject}, reason={reject_reason}")
            
            if should_reject:
                context.should_reject = True
                context.auto_rejected = True
                context.reject_reason = reject_reason
                self.logger.info(f"⚡ 自动拒绝消息: {reject_reason}")
                
                # 保存被拒绝的OCR样本
                await self._save_rejected_sample(context, reject_reason)
            else:
                # 🚀 如果精准逻辑没有拒绝但配置了自动拒绝，根据配置直接拒绝
                context.should_reject = True
                context.auto_rejected = True
                context.reject_reason = "自动拒绝广告消息"
                self.logger.info(f"⚡ 根据配置自动拒绝广告消息: {context.filter_reason}")
            
        except Exception as e:
            self.logger.error(f"自动拒绝检查失败: {e}")
    
    async def _should_reject_pure_ad(self, context: MessageContext) -> Tuple[bool, str]:
        """
        判断是否应该完全拒绝纯广告消息
        
        Returns:
            (是否拒绝, 拒绝原因)
        """
        # 确保规则管理器已初始化
        await self._ensure_rule_manager_initialized()
        
        content = context.processed_content
        filtered_content = context.filtered_content
        media_info = context.media_info
        ocr_result = context.ocr_result or {}
        filter_reason = context.filter_reason
        
        # 从规则管理器获取高危关键词
        high_risk_patterns = rule_manager.get_high_risk_keywords()
        
        # 提取所有文本内容（包括OCR）
        all_text = content
        if ocr_result.get('texts'):
            all_text += " " + " ".join(ocr_result['texts'])
        if ocr_result.get('qr_codes'):
            for qr in ocr_result['qr_codes']:
                if qr.get('data'):
                    all_text += " " + qr['data']
        
        # 优先级1：OCR检测到高分广告内容
        if ocr_result.get('ad_score', 0) >= 50:
            return True, f"图片广告内容自动拒绝（OCR分数:{ocr_result.get('ad_score', 0)}）"
        
        # 优先级2：检查高危关键词（从规则管理器获取）
        # 🚀 简化逻辑：检测到高危关键词直接拒绝
        for pattern, weight in high_risk_patterns:
            if pattern.search(all_text):
                return True, f"高风险广告自动拒绝（检测到赌博/色情/诈骗关键词）"
        
        # 优先级3：纯媒体广告
        if not content.strip() and media_info and ocr_result.get('ad_score', 0) >= 30:
            return True, "纯媒体广告自动拒绝（无文字内容，OCR检测为广告）"
        
        # 优先级4：文本被完全过滤且有媒体
        if not filtered_content.strip() and media_info:
            if ocr_result.get('ad_score', 0) >= 30:
                return True, "纯广告媒体自动拒绝（文字+媒体都是广告）"
            
            if len(content) > 10 and len(filtered_content) < len(content) * 0.05:
                return True, "疑似纯广告自动拒绝（文本过滤超95%）"
        
        # 优先级5：整条消息都是广告
        if "整条消息都是广告" in filter_reason or "高风险广告" in filter_reason:
            if not media_info:
                return True, "纯文字广告自动拒绝"
            elif ocr_result.get('ad_score', 0) >= 30:
                return True, "纯广告消息自动拒绝（文字+媒体都是广告）"
        
        return False, ""
    
    async def _save_rejected_sample(self, context: MessageContext, reject_reason: str):
        """保存被拒绝的OCR样本"""
        if not context.media_info or not context.ocr_result:
            return
        
        # OCR功能已移除，不再保存OCR样本
        pass
    
    async def _learn_from_ad_detection(self, context: MessageContext, ad_detection_result: dict):
        """从广告检测结果中学习新规则"""
        try:
            if not ad_detection_result or not ad_detection_result.get('is_ad', False):
                return
            
            content = context.processed_content
            confidence = ad_detection_result.get('confidence', 0.0)
            detection_method = ad_detection_result.get('method', 'unknown')
            
            # 根据检测方法确定类别
            category = 'unknown'
            if 'AI' in detection_method or 'ai' in detection_method:
                category = 'ai_detected'
            elif 'pattern' in detection_method or '模式' in detection_method:
                category = 'pattern_detected'
            elif 'ocr' in detection_method or 'OCR' in detection_method:
                category = 'ocr_detected'
            
            # 分析消息并学习模式
            learning_result = await rule_learner.analyze_ad_message(
                content=content,
                confidence=confidence,
                detection_method=detection_method,
                category=category
            )
            
            if learning_result.get('learned', False):
                learned_count = learning_result.get('patterns_learned', 0)
                self.logger.info(f"从广告检测中学习了 {learned_count} 个新模式")
            
        except Exception as e:
            self.logger.error(f"从广告检测学习失败: {e}")


class ContentValidator(MessageProcessor):
    """内容验证处理器 - Linus式简化版本"""
    
    def __init__(self):
        super().__init__("ContentValidator")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        Linus式验证：由于MessageReceiver已在源头丢弃空消息，
        此处只需处理已通过基础验证的消息，简化逻辑消除特殊情况
        """
        try:
            # 能到达此处的消息已通过源头验证，直接通过
            # 消除原有的重复检查逻辑，遵循"好品味"原则
            self.logger.debug("消息已通过源头验证，继续处理")
            return ProcessorResult(True, context)
            
        except Exception as e:
            return await self._handle_error(context, e)