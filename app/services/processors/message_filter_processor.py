"""
消息过滤处理器
负责内容过滤、广告检测、OCR处理和自动拒绝判断
"""
import logging
import re
from typing import Tuple, Optional

from app.services.processors.base import MessageProcessor, ProcessorResult, MessageContext
from app.services.filters.base import FilterContext

logger = logging.getLogger(__name__)


class MessageFilterProcessor(MessageProcessor):
    """消息过滤处理器 - 内容过滤和广告检测"""
    
    def __init__(self):
        super().__init__("MessageFilterProcessor")
        # 延迟初始化过滤管道
        self._filter_pipeline = None
    
    @property
    def filter_pipeline(self):
        """延迟加载过滤管道"""
        if self._filter_pipeline is None:
            from app.services.unified_filter_engine import unified_filter_engine
            self._filter_pipeline = unified_filter_engine.filter_pipeline
        return self._filter_pipeline
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        处理消息过滤阶段
        - 提取消息实体
        - 执行内容过滤
        - 进行广告检测
        - 处理OCR识别
        - 判断是否自动拒绝
        """
        try:
            message = context.telegram_message
            content = context.processed_content
            
            # 步骤1: 提取消息实体（包括隐藏链接）
            await self._extract_entities(context)
            
            # 步骤2: 准备媒体文件列表用于OCR
            media_files = []
            if context.media_info and context.media_info.get('file_path'):
                media_files.append(context.media_info['file_path'])
            
            # 步骤3: 使用过滤管道进行内容过滤
            await self._apply_content_filter(context, media_files)
            
            # 步骤4: 检查自动拒绝条件
            await self._check_auto_rejection(context)
            
            # 步骤5: 检查配置的自动过滤设置
            await self._check_auto_filter_config(context)
            
            self.logger.info(f"过滤处理完成: 广告={context.is_ad}, 拒绝={context.should_reject}")
            return ProcessorResult(True, context)
            
        except Exception as e:
            return await self._handle_error(context, e)
    
    async def _extract_entities(self, context: MessageContext):
        """提取消息实体和隐藏链接"""
        try:
            from app.services.structural_ad_detector import structural_detector
            
            message = context.telegram_message
            
            # 提取实体数据
            entities = structural_detector.extract_entity_data(message)
            context.entities = entities
            
            # 移除隐藏链接（系统默认策略）
            clean_entities, removed_links = await structural_detector.remove_hidden_links(message)
            context.removed_hidden_links = removed_links
            
            if removed_links:
                self.logger.info(f"移除了 {len(removed_links)} 个隐藏链接")
            
        except Exception as e:
            self.logger.error(f"提取实体失败: {e}")
            context.entities = []
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
            filter_context.add_metadata('is_history', context.is_history)
            filter_context.add_metadata('media_files', media_files)
            filter_context.add_metadata('message_obj', context.telegram_message)
            
            # 执行过滤管道
            pipeline_result = await self.filter_pipeline.process(content, filter_context)
            
            # 提取过滤结果
            context.filtered_content = pipeline_result.final_content
            context.filter_reason = pipeline_result.overall_reason or ""
            
            # 广告检测结果
            ad_detection_result = filter_context.get_metadata('ad_detection_result')
            context.is_ad = (not pipeline_result.passed) or (
                ad_detection_result and ad_detection_result.get('is_ad', False)
            )
            
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
            
        except Exception as e:
            self.logger.error(f"内容过滤失败: {e}")
            # 失败时保持原内容
            context.filtered_content = context.processed_content
            context.filter_reason = f"过滤失败: {e}"
    
    async def _check_auto_rejection(self, context: MessageContext):
        """检查是否应该自动拒绝消息"""
        if not context.is_ad:
            return
        
        try:
            should_reject, reject_reason = self._should_reject_pure_ad(context)
            
            if should_reject:
                context.should_reject = True
                context.auto_rejected = True
                context.reject_reason = reject_reason
                self.logger.warning(f"自动拒绝消息: {reject_reason}")
                
                # 保存被拒绝的OCR样本
                await self._save_rejected_sample(context, reject_reason)
            
        except Exception as e:
            self.logger.error(f"自动拒绝检查失败: {e}")
    
    async def _check_auto_filter_config(self, context: MessageContext):
        """检查配置的自动过滤设置"""
        if not context.is_ad or context.should_reject:
            return
        
        try:
            from app.services.config_manager import config_manager
            auto_filter = await config_manager.get_config('filter.auto_filter_ads', False)
            
            if auto_filter:
                context.should_reject = True
                context.auto_rejected = True
                context.reject_reason = f"配置自动过滤: {context.filter_reason}"
                self.logger.info(f"配置自动过滤广告消息: {context.filter_reason}")
                
        except Exception as e:
            self.logger.debug(f"检查自动过滤配置失败: {e}")
    
    def _should_reject_pure_ad(self, context: MessageContext) -> Tuple[bool, str]:
        """
        判断是否应该完全拒绝纯广告消息
        
        Returns:
            (是否拒绝, 拒绝原因)
        """
        content = context.processed_content
        filtered_content = context.filtered_content
        media_info = context.media_info
        ocr_result = context.ocr_result or {}
        filter_reason = context.filter_reason
        
        # 高危广告关键词
        HIGH_RISK_AD_KEYWORDS = [
            # 赌博平台相关
            r'(?:铂莱|博莱|Y3|AG|BBIN).*(?:娱乐|娛樂|国际|國際|平台)',
            r'(?:USDT|泰达币|虚拟币|加密货币).*(?:娱乐城|娛樂城|平台|充值|提款)',
            r'(?:博彩|赌场|賭場|棋牌|体育|體育|真人|电子).*(?:平台|官网|官網|娱乐城)',
            r'(?:首充|首存|二存|三存).*(?:返水|优惠|優惠|赠送|贈送)',
            r'(?:日出|日入|月入|日赚|日賺).*[0-9]+.*[万萬uU]',
            r'(?:实力|實力|信誉|信譽).*(?:U盘|U盤|USDT|出款)',
            r'(?:千万|千萬|巨款|巨额|大额).*(?:无忧|無憂|秒到|提款)',
            r'777.*(?:老虎机|老虎機|slots|游戏|遊戲)',
            
            # 色情相关
            r'(?:上线|上線).*(?:福利|八大|妹妹)',
            r'(?:永久|免费|免費).*(?:送|领取|領取|看片)',
            r'(?:幸运|幸運).*(?:单|單).*(?:奖|獎)',
            
            # 诈骗相关
            r'(?:一个月|一個月).*(?:奔驰|奔馳|宝马|寶馬)',
            r'(?:三个月|三個月).*(?:套房|房子)',
            r'(?:汽车|汽車).*(?:违停|違停).*(?:拍照|一张|一張).*[0-9]+',
            r'(?:想功成名就|胆子大|膽子大).*(?:灰色|看我)',
            
            # 特定平台标识
            r'(?:官方|客服).*(?:QQ|qq|微信|WeChat|wechat).*[0-9]+',
            r'(?:注册|註冊|登录|登錄).*(?:就送|即送|立即送)',
        ]
        
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
        
        # 优先级2：检查高危关键词
        for pattern in HIGH_RISK_AD_KEYWORDS:
            if re.search(pattern, all_text, re.IGNORECASE):
                if media_info:
                    return True, "高风险广告自动拒绝（赌博/色情/诈骗+媒体）"
                elif len(filtered_content.strip()) < 20:
                    return True, "高风险广告自动拒绝（赌博/色情/诈骗内容）"
        
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
        
        try:
            from app.services.ocr_service import ocr_service
            import hashlib
            import asyncio
            
            file_path = context.media_info.get('file_path')
            if not file_path:
                return
            
            # 计算文件哈希
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            
            # 异步保存样本
            asyncio.create_task(ocr_service._save_ocr_sample(
                image_path=file_path,
                image_hash=file_hash,
                texts=context.ocr_result.get('texts', []),
                qr_codes=[qr.get('data', '') for qr in context.ocr_result.get('qr_codes', []) if qr.get('data')],
                ad_score=context.ocr_result.get('ad_score', 0),
                is_ad=True,
                keywords_detected=context.ocr_result.get('ad_indicators', []),
                auto_rejected=True,
                rejection_reason=reject_reason
            ))
            
        except Exception as e:
            self.logger.debug(f"保存拒绝样本失败: {e}")


class ContentValidator(MessageProcessor):
    """内容验证处理器 - 验证消息是否有有效内容"""
    
    def __init__(self):
        super().__init__("ContentValidator")
    
    async def process(self, context: MessageContext) -> ProcessorResult:
        """
        验证消息内容有效性
        如果既没有媒体又没有有效内容，则拒绝消息
        """
        try:
            # 检查是否已被其他处理器标记为拒绝
            if context.should_reject:
                return ProcessorResult(True, context)
            
            # 检查是否有有效内容
            has_valid_content = bool(context.filtered_content.strip())
            has_media = bool(context.media_info)
            
            if not has_valid_content and not has_media:
                context.should_reject = True
                context.reject_reason = f"消息既无媒体又无有效内容（原内容长度: {len(context.processed_content)}）"
                self.logger.warning(f"消息无有效内容: {context.reject_reason}")
            
            return ProcessorResult(True, context)
            
        except Exception as e:
            return await self._handle_error(context, e)