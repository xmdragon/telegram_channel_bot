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

# 导入新的过滤器架构
from app.services.filters.filter_pipeline import FilterPipeline, PipelineConfig
from app.services.filters.base import FilterContext
from app.services.filters.duplicate_detector import DuplicateDetectorFilter
from app.services.filters.ad_detector import AdDetectorFilter  
from app.services.filters.tail_filter import TailFilter
from app.services.filters.footer_promo_filter import FooterPromoFilter
from app.services.filters.markdown_filter import MarkdownFilter
from app.services.filters.promo_link_filter import PromoLinkFilter
from app.services.filters.chat_content_filter import ChatContentFilter

logger = logging.getLogger(__name__)

class UnifiedFilterEngine:
    """统一的消息过滤引擎 - 使用新的FilterPipeline架构"""
    
    def __init__(self):
        """初始化引擎"""
        self.filter_pipeline = None
        self.high_risk_patterns = []
        self._initialized = False
        
        # 初始化组件
        self._initialize_components()
        
    def _init_filter_pipeline(self) -> FilterPipeline:
        """初始化过滤器管道"""
        config = PipelineConfig(
            enable_early_stopping=True,
            early_stop_filters={'duplicate_detector', 'ad_detector', 'chat_content_filter'},
            filter_timeout=30.0,
            pipeline_timeout=60.0
        )
        
        pipeline = FilterPipeline(config)
        
        # 按新顺序添加7个过滤器
        # 1-4: 内容清理类过滤器（先清理推广内容）
        pipeline.add_filter(TailFilter())                # 1. 尾部过滤
        pipeline.add_filter(FooterPromoFilter())         # 2. 尾部推广链接过滤器
        pipeline.add_filter(MarkdownFilter())            # 3. Markdown格式清理
        pipeline.add_filter(PromoLinkFilter())           # 4. 推广链接过滤
        
        # 5-7: 内容检测类过滤器（清理后再检测，避免误判）
        pipeline.add_filter(DuplicateDetectorFilter())   # 5. 去重检测
        pipeline.add_filter(AdDetectorFilter())          # 6. 广告检测
        pipeline.add_filter(ChatContentFilter())         # 7. 聊天内容检测
        
        return pipeline
        
    def _initialize_components(self):
        """初始化所有组件"""
        try:
            # 初始化新的过滤器管道
            self.filter_pipeline = self._init_filter_pipeline()
            
            # 初始化高风险模式
            self._init_high_risk_patterns()
            
            self._initialized = True
            logger.info("✅ 统一过滤引擎初始化成功（使用FilterPipeline架构）")
            
        except Exception as e:
            logger.error(f"统一过滤引擎初始化失败: {e}")
            
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """获取过滤器管道统计信息"""
        if self.filter_pipeline:
            return self.filter_pipeline.get_pipeline_stats()
        return {}
        
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if self.filter_pipeline:
            return self.filter_pipeline.get_performance_metrics()
        return {}
        
    def reset_stats(self) -> None:
        """重置统计信息"""
        if self.filter_pipeline:
            self.filter_pipeline.reset_stats()
            
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
        统一的广告检测方法 - 使用新的FilterPipeline架构
        
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
            
        if not self.filter_pipeline:
            logger.error("FilterPipeline未初始化，降级到高风险检测")
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
            
            # 执行过滤器管道
            pipeline_result = await self.filter_pipeline.process(content, filter_context)
            
            # 提取结果
            is_ad = not pipeline_result.passed
            filtered_content = pipeline_result.final_content
            filter_reason = pipeline_result.overall_reason or ""
            
            # 如果管道没有识别为广告，进行高风险检测补充
            if not is_ad:
                is_high_risk, risk_patterns = self.is_high_risk_ad(filtered_content)
                if is_high_risk:
                    is_ad = True
                    filtered_content = ""
                    filter_reason = f"高风险广告({len(risk_patterns)}个特征)"
                    
            return is_ad, filtered_content, filter_reason
            
        except Exception as e:
            logger.error(f"FilterPipeline执行失败: {e}")
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