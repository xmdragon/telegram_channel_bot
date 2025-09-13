"""
统一的内容处理管道
独立模块，避免循环依赖，便于多处复用
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from app.services.simple_tail_filter import filter_tail_content
from app.services.filters.markdown_filter import MarkdownFilter
from app.services.filters.separator_filter import SeparatorFilter
from app.services.filters.base import FilterContext
from app.services.detectors.weighted_keyword_detector import get_weighted_keyword_detector

logger = logging.getLogger(__name__)

@dataclass
class LocalMessage:
    """简化的消息对象，只包含处理需要的字段"""
    message_id: int
    channel_id: Optional[str] = None
    content: str = ""
    filtered_content: str = ""
    filter_reason: Optional[str] = None
    status: str = "pending"
    reject_reason: Optional[str] = None
    is_ad: bool = False
    ad_weight: float = 0.0
    matched_keywords: Optional[List[str]] = None
    entities: Optional[List] = None
    
    def __post_init__(self):
        if self.filtered_content == "":
            self.filtered_content = self.content


class ContentProcessingPipeline:
    """内容处理管道 - 尾部过滤 + markdown过滤 + 分隔符过滤处理"""
    
    def __init__(self):
        """初始化处理管道"""
        self.markdown_filter = MarkdownFilter()
        self.separator_filter = SeparatorFilter()
        self.keyword_detector = get_weighted_keyword_detector()
    
    async def process(self, message: LocalMessage, config_manager: Optional[Any] = None, detect_ad: bool = True) -> LocalMessage:
        """执行内容过滤处理 - 尾部过滤 → markdown过滤 → 分隔符过滤 → 广告检测
        
        Args:
            message: 要处理的消息
            config_manager: 配置管理器，用于获取自动拒绝广告配置
            detect_ad: 是否进行广告检测，默认为True
        """
        try:
            if not message.content:
                return message
            
            current_content = message.content
            filter_reasons = []
            
            # 1. 尾部过滤处理（先处理，删除尾部推广内容）
            filtered_content, is_filtered, removed_content, analysis = filter_tail_content(current_content)
            if is_filtered:
                current_content = filtered_content
                filter_reasons.append(f"尾部过滤: {analysis.get('reason', '检测到推广内容')}")
                logger.info(f"消息 {message.message_id} 尾部过滤: {len(message.content)} -> {len(current_content)} 字符")
            else:
                logger.debug(f"消息 {message.message_id} 无尾部内容需要过滤")
            
            # 2. markdown过滤处理（后处理，使用原始entities，位置仍准确）
            if message.entities:
                # 创建FilterContext
                context = FilterContext(
                    message_id=str(message.message_id),
                    channel_id=message.channel_id
                )
                context.add_metadata('entities', message.entities)
                
                # 执行markdown过滤
                markdown_result = await self.markdown_filter.filter(current_content, context)
                if markdown_result.passed and markdown_result.filtered_content != current_content:
                    current_content = markdown_result.filtered_content
                    filter_reasons.append(f"markdown过滤: {markdown_result.reason}")
                    logger.info(f"消息 {message.message_id} markdown过滤完成，最终: {len(current_content)} 字符")
                else:
                    logger.debug(f"消息 {message.message_id} 无markdown链接需要处理")
            
            # 3. 分隔符过滤处理（在markdown过滤后执行）
            separator_result, separator_stats = self.separator_filter.filter_content(current_content)
            if separator_stats.get('removed_blocks_count', 0) > 0:
                current_content = separator_result
                removed_chars = separator_stats.get('original_length', 0) - separator_stats.get('filtered_length', 0)
                filter_reasons.append(f"分隔符过滤: 移除{separator_stats['removed_blocks_count']}个内容块({removed_chars}字符)")
                logger.info(f"消息 {message.message_id} 分隔符过滤: 移除了{separator_stats['removed_blocks_count']}个内容块")
            else:
                logger.debug(f"消息 {message.message_id} 无分隔符内容块需要过滤")
            
            # 4. 广告关键词检测（在所有过滤完成后进行，可选）
            if detect_ad:
                is_ad, total_weight, matched_keywords = self.keyword_detector.detect(current_content)
                
                if is_ad:
                    message.is_ad = True
                    message.ad_weight = total_weight
                    message.matched_keywords = matched_keywords[:5]  # 保存前5个关键词
                    filter_reasons.append(f"广告检测: 权重={total_weight:.1f}, 关键词={','.join(matched_keywords[:3])}")
                    logger.info(f"消息 {message.message_id} 检测为广告: 权重={total_weight:.1f}, 关键词={matched_keywords[:3]}")
                    
                    # 根据配置决定是否自动拒绝
                    if config_manager:
                        try:
                            auto_reject = await config_manager.get_auto_reject_ads()
                            if auto_reject:
                                message.status = "rejected"
                                message.reject_reason = f"自动拒绝广告(权重:{total_weight:.1f})"
                                logger.info(f"消息 {message.message_id} 被自动拒绝（广告）")
                        except Exception as e:
                            logger.error(f"获取自动拒绝配置失败: {e}")
            else:
                logger.debug(f"消息 {message.message_id} 跳过广告检测")
            
            # 更新消息内容
            message.filtered_content = current_content
            if filter_reasons:
                message.filter_reason = "; ".join(filter_reasons)
            
            return message
            
        except Exception as e:
            logger.error(f"内容处理失败 {message.message_id}: {e}")
            # 处理失败时返回原消息
            return message