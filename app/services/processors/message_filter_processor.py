"""
消息过滤处理器
负责内容过滤处理
"""
import logging
import re
import asyncio
from typing import Tuple, Optional

from app.services.processors.base import MessageProcessor, ProcessorResult, MessageContext
from app.services.filters.base import FilterContext
# 延迟导入rule_manager，避免模块导入时阻塞
# from app.services.rule_manager import rule_manager

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
            from app.services.filters.filter_pipeline import FilterPipeline
            self._filter_pipeline = FilterPipeline()
        return self._filter_pipeline
    
    async def _ensure_rule_manager_initialized(self):
        """确保规则管理器已初始化"""
        if not self._rule_manager_initialized:
            try:
                import asyncio
                # 延迟导入rule_manager
                from app.services.rule_manager import rule_manager
                # 添加5秒超时，防止无限阻塞
                await asyncio.wait_for(rule_manager.initialize(), timeout=5.0)
                self._rule_manager_initialized = True
                self.logger.debug("规则管理器初始化完成")
            except asyncio.TimeoutError:
                self.logger.error("规则管理器初始化超时（5秒），跳过初始化")
                # 标记为已尝试，避免重复初始化
                self._rule_manager_initialized = True
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
        - 判断是否自动拒绝
        """
        # 立即输出debug日志确认进入方法
        self.logger.debug(f"🔍 MessageFilterProcessor.process() 开始处理消息 #{context.telegram_message.id}")
        
        # 导入性能监控
        try:
            from app.services.performance_monitor import PerformanceTimer, perf_logger
            filter_timer = PerformanceTimer("message_filter_processor").start()
        except ImportError:
            filter_timer = None
        
        try:
            message = context.telegram_message
            content = context.processed_content
            
            # 🔧 修复：检查是否为组合消息的子消息
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
            self.logger.debug(f"开始提取实体 #{message.id}")
            await self._extract_entities(context)
            self.logger.debug(f"完成提取实体 #{message.id}")
            if filter_timer:
                entity_timer.stop()
            
            media_files = []
            if context.media_info and context.media_info.get('file_path'):
                media_files.append(context.media_info['file_path'])
            
            # 步骤3: 使用过滤管道进行内容过滤（核心性能瓶颈）
            if filter_timer:
                pipeline_timer = filter_timer.add_child("content_filtering").start()
            self.logger.debug(f"开始内容过滤 #{message.id}")
            
            # 🛡️ 修复：多层超时保护，确保永不阻塞
            import asyncio
            try:
                # 第一层：内容过滤超时保护（10秒）
                await asyncio.wait_for(self._apply_content_filter(context, media_files), timeout=10.0)
                self.logger.debug(f"完成内容过滤 #{message.id}")
            except asyncio.TimeoutError:
                self.logger.warning(f"🕐 内容过滤超时（10秒），使用快速模式处理 #{message.id}")
                # 使用快速安全模式：跳过复杂过滤，保持基本功能
                await self._apply_safe_mode_filter(context)
            except Exception as e:
                self.logger.error(f"🚨 内容过滤异常，使用安全模式: {e}")
                await self._apply_safe_mode_filter(context)
            
            if filter_timer:
                pipeline_timer.stop()
                pipeline_timer.set_metric("media_files_count", len(media_files))
                pipeline_timer.set_metric("is_ad", context.is_ad)
            
            # 步骤4: 检查自动拒绝条件
            if filter_timer:
                rejection_timer = filter_timer.add_child("auto_rejection_check").start()
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
        """应用内容过滤管道 - 带超时控制"""
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
            
            # 🎯 简化：直接调用简单尾部过滤器，绕过复杂管道
            from app.services.simple_tail_filter import filter_tail_content
            
            # 直接过滤尾部推广内容
            filtered_content, was_filtered, removed_tail, filter_analysis = filter_tail_content(content)
            
            # 提取过滤结果
            context.filtered_content = filtered_content
            context.filter_reason = ""
            
            # 🎯 使用增强的AdDetector进行广告检测
            from app.services.filters.ad_detector import AdDetector
            ad_detector = AdDetector()
            
            # 对过滤后的内容进行广告检测，获取关键词位置信息
            is_ad, ad_weight, matched_keywords = ad_detector.detect(filtered_content)
            
            # 设置广告检测结果
            context.is_ad = is_ad
            context.ad_weight = ad_weight
            context.ad_keywords_detail = {
                'matched_keywords': matched_keywords,
                'total_weight': ad_weight,
                'threshold': ad_detector.threshold
            }
            
            # 构建过滤原因
            filter_reasons = []
            if was_filtered:
                filter_reasons.append(f"移除了推广尾部内容({filter_analysis.get('removed_lines_count', 0)}行)")
            
            if is_ad:
                keyword_names = [k['keyword'] for k in matched_keywords[:3]]
                filter_reasons.append(f"广告检测(权重{ad_weight:.1f}, 关键词: {', '.join(keyword_names)})")
            
            context.filter_reason = "; ".join(filter_reasons) if filter_reasons else ""
            
            # 调试日志：记录广告检测结果
            if context.is_ad:
                self.logger.info(f"🚫 消息被检测为广告: 权重={ad_weight:.1f}, 关键词={len(matched_keywords)}个")
            else:
                self.logger.debug(f"✅ 消息未检测为广告")
            
            
            # 记录过滤效果
            if content != context.filtered_content:
                original_len = len(content)
                filtered_len = len(context.filtered_content)
                self.logger.info(f"内容过滤: {original_len} -> {filtered_len} 字符 (减少 {original_len - filtered_len})")
            
            if context.is_ad:
                self.logger.info(f"检测到广告: {context.filter_reason}")
                
            
        except asyncio.TimeoutError:
            self.logger.warning(f"⚡ 过滤管道超时，切换到安全模式")
            await self._apply_safe_mode_filter(context)
        except Exception as e:
            self.logger.error(f"内容过滤失败: {e}")
            # 失败时保持原内容
            context.filtered_content = context.processed_content
            context.filter_reason = f"过滤失败: {e}"
    
    async def _apply_safe_mode_filter(self, context: MessageContext):
        """安全模式过滤 - 基础过滤，无复杂AI检测，确保不阻塞"""
        try:
            content = context.processed_content
            
            # 🔇 安全模式：跳过所有复杂过滤，只做基础处理
            context.filtered_content = content
            context.is_ad = False
            context.filter_reason = "安全模式：跳过复杂过滤"
            
            # 基础安全检测：只检测明显的垃圾内容
            content_lower = content.lower()
            
            # 检测明显的广告关键词（简单字符串匹配，无AI）
            spam_keywords = ['首存', '充值送', '无需实名', '免费注册', '点击链接', '私聊联系']
            for keyword in spam_keywords:
                if keyword in content:
                    context.is_ad = True
                    context.filter_reason = f"安全模式检测到广告关键词: {keyword}"
                    self.logger.info(f"🚫 安全模式检测到广告: {keyword}")
                    break
            
            if not context.is_ad:
                self.logger.debug(f"✅ 安全模式：消息未检测为广告")
                
        except Exception as e:
            # 即使安全模式也失败，使用最基础的默认值
            self.logger.error(f"安全模式过滤也失败: {e}")
            context.filtered_content = context.processed_content  
            context.is_ad = False
            context.filter_reason = f"安全模式失败: {e}"
    
    
    


