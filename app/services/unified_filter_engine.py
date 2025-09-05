"""
统一的消息过滤引擎
整合所有广告检测、尾部过滤、AI检测逻辑
确保所有消息处理路径使用相同的过滤逻辑
"""
import re
import logging
import asyncio
from typing import Tuple, List, Optional, Dict, Any
from pathlib import Path
import json

# 导入新的分层过滤器架构
from app.services.filters.layer_pipeline import LayerPipeline, LayerPipelineConfig
from app.services.filters.base import FilterContext

logger = logging.getLogger(__name__)

class UnifiedFilterEngine:
    """统一的消息过滤引擎 - 使用新的分层架构"""
    
    def __init__(self):
        """初始化引擎"""
        self.layer_pipeline = None
        self.high_risk_patterns = []
        self._initialized = False
        
        # 初始化组件
        self._initialize_components()
        
    def _init_layer_pipeline(self) -> LayerPipeline:
        """初始化分层管道 - 基于配置的动态启用/禁用"""
        # 从配置中获取设置
        filter_settings = self._load_filter_settings()
        
        config = LayerPipelineConfig(
            # 内容清理层配置
            content_layer_enabled=filter_settings.get('content_layer_enabled', True),
            content_layer_timeout=30.0,
            
            # 检测器层配置  
            detector_layer_enabled=filter_settings.get('detector_layer_enabled', True),
            detector_layer_timeout=30.0,
            enable_early_stopping=True,
            
            # 管道全局配置
            pipeline_timeout=60.0,
            enable_detailed_stats=True,
            enable_performance_monitoring=True
        )
        
        logger.info(f"分层管道初始化完成 - 内容清理层: {config.content_layer_enabled}, 检测器层: {config.detector_layer_enabled}")
        
        return LayerPipeline(config)
        
    def _load_filter_settings(self) -> Dict[str, bool]:
        """从系统配置加载过滤器设置"""
        try:
            from app.services.config_manager import config_manager
            
            # 获取配置，同步调用配置管理器
            import asyncio
            loop = None
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # 如果没有事件循环，创建新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 加载系统配置
            filter_enabled = True
            tail_filter_enabled = True
            footer_promo_enabled = True
            markdown_enabled = True
            promo_vector_enabled = True
            ad_detector_enabled = False  # 默认禁用
            auto_reject_ads = True
            auto_reject_high_risk = False
            
            try:
                if loop.is_running():
                    # 如果已经在事件循环中，直接获取当前缓存值
                    from app.services.config_manager import ConfigManager
                    config_mgr = ConfigManager()
                    if hasattr(config_mgr, '_cache') and config_mgr._cache:
                        filter_enabled = config_mgr._cache.get('filter.enabled', {}).get('value', True)
                        tail_filter_enabled = config_mgr._cache.get('filter.tail_filter_enabled', {}).get('value', True)
                        footer_promo_enabled = config_mgr._cache.get('filter.footer_promo_enabled', {}).get('value', True)
                        markdown_enabled = config_mgr._cache.get('filter.markdown_enabled', {}).get('value', True)
                        promo_vector_enabled = config_mgr._cache.get('filter.promo_vector_enabled', {}).get('value', True)
                        ad_detector_enabled = config_mgr._cache.get('filter.ad_detector_enabled', {}).get('value', False)
                        auto_reject_ads = config_mgr._cache.get('review.auto_reject_ads', {}).get('value', True)
                        auto_reject_high_risk = config_mgr._cache.get('review.auto_reject_high_risk', {}).get('value', False)
                else:
                    # 如果不在事件循环中，运行异步调用
                    filter_enabled = loop.run_until_complete(config_manager.get_config('filter.enabled', True))
                    tail_filter_enabled = loop.run_until_complete(config_manager.get_config('filter.tail_filter_enabled', True))
                    footer_promo_enabled = loop.run_until_complete(config_manager.get_config('filter.footer_promo_enabled', True))
                    markdown_enabled = loop.run_until_complete(config_manager.get_config('filter.markdown_enabled', True))
                    promo_vector_enabled = loop.run_until_complete(config_manager.get_config('filter.promo_vector_enabled', True))
                    ad_detector_enabled = loop.run_until_complete(config_manager.get_config('filter.ad_detector_enabled', False))
                    auto_reject_ads = loop.run_until_complete(config_manager.get_config('review.auto_reject_ads', True))
                    auto_reject_high_risk = loop.run_until_complete(config_manager.get_config('review.auto_reject_high_risk', False))
            except Exception as e:
                logger.warning(f"从config_manager加载配置失败，使用默认值: {e}")
            
            # 转换为布尔值
            def to_bool(value):
                if isinstance(value, bool):
                    return value
                elif isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes', 'on')
                else:
                    return bool(value)
            
            filter_enabled = to_bool(filter_enabled)
            tail_filter_enabled = to_bool(tail_filter_enabled)
            footer_promo_enabled = to_bool(footer_promo_enabled)
            markdown_enabled = to_bool(markdown_enabled)
            promo_vector_enabled = to_bool(promo_vector_enabled)
            ad_detector_enabled = to_bool(ad_detector_enabled)
            auto_reject_ads = to_bool(auto_reject_ads)
            auto_reject_high_risk = to_bool(auto_reject_high_risk)
            
            # 分层架构配置
            settings = {
                # 分层控制
                'content_layer_enabled': True,  # 内容清理层默认启用
                'detector_layer_enabled': True, # 检测器层默认启用
                
                # 内容清理过滤器 - 通过层级管理
                'tail_filter': tail_filter_enabled,
                'footer_promo_filter': footer_promo_enabled,
                'markdown_filter': markdown_enabled,
                'promo_vector_filter': promo_vector_enabled,
                
                # 内容检测过滤器 - 通过层级管理
                'ad_detector': ad_detector_enabled,
                
                # 其他配置
                'auto_reject_ads': auto_reject_ads,
                'auto_reject_high_risk': auto_reject_high_risk
            }
            
            logger.info(f"过滤器设置加载完成: {settings}")
            return settings
            
        except Exception as e:
            logger.error(f"加载过滤器设置失败，使用默认配置: {e}")
            # 返回默认分层设置
            return {
                'content_layer_enabled': True,
                'detector_layer_enabled': True,
                'tail_filter': True,
                'footer_promo_filter': True,
                'markdown_filter': True,
                'promo_vector_filter': True,
                'ad_detector': False,
                'auto_reject_ads': True,
                'auto_reject_high_risk': False
            }
        
    def _initialize_components(self):
        """初始化所有组件"""
        try:
            # 初始化新的分层管道
            self.layer_pipeline = self._init_layer_pipeline()
            
            # 为了保持兼容性，同时提供filter_pipeline属性
            self.filter_pipeline = self.layer_pipeline
            
            # 初始化高风险模式
            self._init_high_risk_patterns()
            
            self._initialized = True
            logger.info("✅ 统一过滤引擎初始化成功（使用分层架构）")
            
        except Exception as e:
            logger.error(f"统一过滤引擎初始化失败: {e}")
            
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """获取分层管道统计信息"""
        if self.layer_pipeline:
            return self.layer_pipeline.get_pipeline_stats()
        return {}
        
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if self.layer_pipeline:
            return self.layer_pipeline.get_performance_metrics()
        return {}
        
    def reset_stats(self) -> None:
        """重置统计信息"""
        if self.layer_pipeline:
            self.layer_pipeline.reset_stats()
            
    def _init_high_risk_patterns(self):
        """初始化高风险广告检测模式"""
        self.high_risk_patterns = [
            # === 通用赌博模式 ===
            # 充值赠送模式
            r'首[存充]\d+.*[赠送]\d+',
            r'首[存充].*送.*\d+[%％]',
            r'充值.*[返赠].*\d+',
            r'存款.*优惠.*\d+',
            
            # 无需实名模式
            r'无需实名|無需實名',
            r'不限.*[Ii][Pp]',
            r'匿名.*[登錄]',
            r'免实名|免實名',
            
            # 大额提款模式
            r'[千万萬].*无忧|無憂',
            r'巨额.*出款',
            r'日[出入赚賺].*\d+[万萬uU]',
            r'单日.*盈利.*\d+',
            r'提款.*不限.*额度',
            
            # 平台特征词
            r'娱乐城|娛樂城',
            r'[国國][际際].*平台',
            r'线上.*博彩|線上.*博彩',
            r'体育.*平台|體育.*平台',
            r'棋牌.*游戏|遊戲',
            r'真人.*视讯|視訊',
            r'电子.*游艺|遊藝',
            
            # 支付方式
            r'[Uu]存[Uu]提',
            r'USDT.*[存充].*款',
            r'泰达币|泰達幣',
            r'虚拟币.*充值|虛擬幣.*充值',
            r'数字货币.*支付|數字貨幣.*支付',
            
            # 诱导词汇
            r'日赚|日賺|月入|月赚|月賺',
            r'暴富|暴利|稳赚|穩賺',
            r'零风险|零風險|包赢|包贏',
            r'内幕|內幕|必中|必赢|必贏',
            
            # 客服账号模式（只在有赌博背景时才算高风险）
            # 注释掉这些通用客服模式，避免误判
            
            # 多个赌博相关词汇组合
            r'(?:博彩|棋牌|体育|娱乐|平台).*(?:博彩|棋牌|体育|娱乐|平台)',
            r'(?:首存|首充|优惠|返水).*(?:首存|首充|优惠|返水)',
        ]
        
    def is_high_risk_ad(self, content: str) -> Tuple[bool, List[str]]:
        """
        检测是否为高风险广告
        
        Returns:
            (是否高风险, 匹配的模式列表)
        """
        if not content:
            return False, []
            
        matched_patterns = []
        
        # 检查高风险模式
        for pattern in self.high_risk_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                matched_patterns.append(pattern[:30])  # 记录匹配的模式
                
        # 检查多链接模式（3个以上不同域名）
        urls = re.findall(r'https?://([^/\s]+)', content)
        unique_domains = set(urls)
        if len(unique_domains) >= 3:
            matched_patterns.append("多个不同域名链接")
            
        # 特殊关键词组合检测（赌博相关组合）
        special_keywords = {
            '担保': ['担保', '联名担保', '保证'],
            '娱乐': ['娱乐城', '博彩', '体验金', '派发'],
            '赌博': ['首存', '二存', '三存', '存款', '充值', '赠送', '返水'],
            '平台': ['平台', '官网', '注册', '登录']
        }
        
        keyword_hits = 0
        for category, keywords in special_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    keyword_hits += 1
                    break
                    
        if keyword_hits >= 3:
            matched_patterns.append("多个赌博关键词组合")
            
        # 判定逻辑：更严格的高风险判定
        # 1. 匹配3个或以上模式 -> 高风险
        # 2. 匹配"首存"相关模式 + 其他2个以上赌博特征 -> 高风险
        # 3. 多个赌博关键词组合达到3个以上 -> 高风险  
        is_high_risk = (
            len(matched_patterns) >= 3 or
            (any('首[存充]' in p for p in matched_patterns) and keyword_hits >= 3) or
            keyword_hits >= 4
        )
        
        if is_high_risk:
            logger.warning(f"检测到高风险广告，匹配模式: {matched_patterns}")
            
        return is_high_risk, matched_patterns
        
    async def detect_advertisement(
        self,
        content: str,
        channel_id: Optional[str] = None,
        message_obj: Any = None,
        media_files: Optional[List[str]] = None
    ) -> Tuple[bool, str, str]:
        """
        统一的广告检测方法 - 使用新的LayerPipeline分层架构
        
        Args:
            content: 消息内容
            channel_id: 频道ID
            message_obj: 消息对象
            media_files: 媒体文件列表
            
        Returns:
            (是否广告, 过滤后内容, 过滤原因)
        """
        if not content:
            return False, content, ""
            
        if not self.layer_pipeline:
            logger.error("LayerPipeline未初始化，降级到高风险检测")
            is_high_risk, _ = self.is_high_risk_ad(content)
            return is_high_risk, content if not is_high_risk else "", "高风险广告" if is_high_risk else ""
            
        try:
            # 创建过滤器上下文
            filter_context = FilterContext(
                message_id="temp",
                channel_id=channel_id
            )
            # 添加额外信息到元数据
            if media_files:
                filter_context.add_metadata('media_files', media_files)
            if message_obj:
                filter_context.add_metadata('message_obj', message_obj)
            
            # 执行分层管道
            pipeline_result = await self.layer_pipeline.process(content, filter_context)
            
            # 提取结果
            is_ad = not pipeline_result.passed
            filtered_content = pipeline_result.final_content
            filter_reason = pipeline_result.overall_reason or ""
            
            # 如果管道没有识别为广告，进行高风险检测补充
            if not is_ad:
                is_high_risk, risk_patterns = self.is_high_risk_ad(filtered_content)
                if is_high_risk:
                    is_ad = True
                    # 不清空内容，让调用方基于内容判断
                    filter_reason = f"高风险广告({len(risk_patterns)}个特征)"
                    
            return is_ad, filtered_content, filter_reason
            
        except Exception as e:
            logger.error(f"LayerPipeline执行失败: {e}")
            # 降级到高风险检测
            is_high_risk, _ = self.is_high_risk_ad(content)
            return is_high_risk, content if not is_high_risk else "", "高风险广告" if is_high_risk else ""
        
    def detect_advertisement_sync(
        self,
        content: str,
        channel_id: Optional[str] = None,
        message_obj: Any = None
    ) -> Tuple[bool, str, str]:
        """
        同步版本的广告检测（向后兼容）- 使用FilterPipeline
        """
        try:
            # 创建新的事件循环运行异步方法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.detect_advertisement(content, channel_id, message_obj)
            )
            loop.close()
            return result
        except RuntimeError:
            # 如果已经在事件循环中，尝试直接调用
            try:
                future = asyncio.ensure_future(
                    self.detect_advertisement(content, channel_id, message_obj)
                )
                # 等待完成（这在某些情况下可能不工作）
                return asyncio.get_event_loop().run_until_complete(future)
            except:
                # 降级到高风险检测
                logger.warning("无法运行异步检测，降级到高风险检测")
                is_high_risk, _ = self.is_high_risk_ad(content)
                return is_high_risk, content if not is_high_risk else "", "高风险广告" if is_high_risk else ""

# 全局实例
unified_filter_engine = UnifiedFilterEngine()

# ========== 兼容层接口 ==========
# 为了支持从旧的content_filter平滑迁移到新架构

class FilterEngineCompat:
    """
    统一过滤引擎的兼容层接口
    提供与旧content_filter相同的接口，但使用新的LayerPipeline分层架构
    """
    
    def __init__(self):
        self.engine = unified_filter_engine
    
    def filter_message_sync(self, content: str, channel_id: str = None, message_obj: Any = None) -> Tuple[bool, str, str]:
        """
        同步版本的消息过滤方法（兼容旧接口）
        完全替代content_filter.filter_message_sync
        """
        try:
            return self.engine.detect_advertisement_sync(content, channel_id, message_obj)
        except Exception as e:
            logger.error(f"兼容层过滤失败: {e}")
            # 降级到高风险检测
            is_high_risk, _ = self.engine.is_high_risk_ad(content)
            return is_high_risk, content if not is_high_risk else "", "高风险广告" if is_high_risk else ""
    
    async def filter_message(self, content: str, channel_id: str = None, message_obj: Any = None, media_files: List[str] = None) -> Tuple[bool, str, str, dict]:
        """
        异步版本的消息过滤方法（兼容旧接口）
        完全替代content_filter.filter_message
        """
        try:
            is_ad, filtered_content, filter_reason = await self.engine.detect_advertisement(
                content, channel_id, message_obj, media_files
            )
            # 兼容返回格式：添加空的OCR结果
            ocr_result = {}
            return is_ad, filtered_content, filter_reason, ocr_result
        except Exception as e:
            logger.error(f"兼容层异步过滤失败: {e}")
            # 降级处理
            is_high_risk, _ = self.engine.is_high_risk_ad(content)
            return is_high_risk, content if not is_high_risk else "", "高风险广告" if is_high_risk else "", {}
    
    def is_meaningless_content(self, content: str) -> bool:
        """
        检测内容是否无意义（兼容旧接口）
        """
        if not content or not content.strip():
            return True
        
        # 移除所有空白字符
        clean_content = ''.join(content.split())
        
        # 如果内容太短，可能无意义
        if len(clean_content) < 5:
            import unicodedata
            meaningful_chars = 0
            for char in clean_content:
                cat = unicodedata.category(char)
                if cat[0] in ('L', 'N'):
                    meaningful_chars += 1
            
            if meaningful_chars < len(clean_content) * 0.2:
                return True
        
        return False
    
    async def is_pure_advertisement_ai(self, content: str) -> bool:
        """
        使用AI判断是否为广告内容（兼容旧接口）
        """
        try:
            is_ad, _, _ = await self.engine.detect_advertisement(content)
            return is_ad
        except Exception as e:
            logger.error(f"AI广告检测失败: {e}")
            return False
    
    def is_pure_advertisement(self, content: str) -> bool:
        """
        判断是否纯广告内容（兼容旧接口）
        """
        try:
            is_ad, _, _ = self.engine.detect_advertisement_sync(content)
            return is_ad
        except Exception as e:
            logger.error(f"广告检测失败: {e}")
            return False
    
    def add_channel_signature(self, content: str, channel_name: str) -> str:
        """
        添加频道签名（兼容旧接口）
        """
        if not content:
            return content
        
        # 添加频道标识
        signature = f"\n\n【来源：{channel_name}】"
        return content + signature

# 创建兼容层实例
filter_engine_compat = FilterEngineCompat()