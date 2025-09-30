"""
内容处理器 - 统一的实现
统一的内容处理管道，使用独立的过滤器类，无抽象层

Author: Claude ()
Created: 2025-09-13
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import logging

from app.services.filters.tail_filter import TailFilter
from app.services.filters.markdown_filter import MarkdownFilter
from app.services.filters.separator_filter import SeparatorFilter
from app.services.filters.text_filter import TextFilter
from app.services.filters.ad_detector import AdDetector

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
    hit_keywords: Optional[List[Dict]] = None
    entities: Optional[List] = None
    # 去重检测相关字段
    duplicate_status: str = "none"  # "none", "suspected", "confirmed", "not_duplicate"
    original_message_id: Optional[str] = None  # 原消息ID
    similarity_score: float = 0.0  # 相似度分数
    duplicate_reason: Optional[str] = None  # 检测原因
    # 过滤器详细信息
    filter_details: Optional[List[Dict[str, Any]]] = None  # 存储每个过滤器的详细结果

    def __post_init__(self):
        if self.filtered_content == "":
            self.filtered_content = self.content
        if self.filter_details is None:
            self.filter_details = []


class ContentProcessor:
    """内容处理器 - 性能优化版本

    处理流程（按性能优化顺序）：
    1. 快速预筛选 - 跳过明显的正常内容
    2. 尾部过滤 - 删除推广内容（最常见）
    3. 分隔符过滤 - 删除特定内容块
    4. 文本过滤 - 删除特定关键词和正则匹配
    5. Markdown过滤 - 删除链接
    6. 广告检测 - 识别广告内容（最慢，放最后）

    性能特性：
    - 延迟初始化过滤器
    - 智能缓存机制
    - 早期退出优化
    - 批量处理支持
    """

    def __init__(self):
        """延迟初始化处理器"""
        # 延迟初始化过滤器，避免启动开销
        self._tail_filter = None
        self._markdown_filter = None
        self._separator_filter = None
        self._text_filter = None
        self._ad_detector = None

    @property
    def tail_filter(self):
        """延迟初始化尾部过滤器"""
        if self._tail_filter is None:
            self._tail_filter = TailFilter()
        return self._tail_filter

    @property
    def markdown_filter(self):
        """延迟初始化Markdown过滤器"""
        if self._markdown_filter is None:
            self._markdown_filter = MarkdownFilter()
        return self._markdown_filter

    @property
    def separator_filter(self):
        """延迟初始化分隔符过滤器"""
        if self._separator_filter is None:
            self._separator_filter = SeparatorFilter()
        return self._separator_filter

    @property
    def text_filter(self):
        """延迟初始化文本过滤器"""
        if self._text_filter is None:
            self._text_filter = TextFilter()
        return self._text_filter

    @property
    def ad_detector(self):
        """延迟初始化广告检测器"""
        if self._ad_detector is None:
            self._ad_detector = AdDetector()
        return self._ad_detector


    async def process(self, message: LocalMessage, config_manager: Optional[Any] = None, detect_ad: bool = True, filter_config: Optional[dict] = None) -> LocalMessage:
        """处理消息内容 - 性能优化版本

        Args:
            message: 要处理的消息
            config_manager: 配置管理器（用于获取自动拒绝广告配置）
            detect_ad: 是否进行广告检测

        Returns:
            处理后的消息对象
        """
        try:
            if not message.content:
                return message

            original_content = message.content
            current_content = original_content
            filter_reasons = []

            # 初始化过滤器详细信息列表
            message.filter_details = []

            # 获取过滤器配置
            if filter_config is None:
                filter_config = {
                    'enabled': True,
                    'tail_filter': True,
                    'separator_filter': True,
                    'text_filter': True,
                    'markdown_filter': True,
                    'ad_detector': False
                }

            # 如果主开关关闭，直接返回
            if not filter_config.get('enabled', True):
                message.filtered_content = current_content
                return message

            # 1. 尾部过滤（最常见，最快，放第一）
            if filter_config.get('tail_filter', True):
                filtered_content, is_filtered, removed_tail, _ = self.tail_filter.filter(current_content)
                # 收集详细信息
                filter_detail = {
                    'name': '尾部过滤',
                    'enabled': True,
                    'filtered_content': filtered_content,
                    'removed_length': len(removed_tail) if is_filtered else 0,
                    'removed_content': removed_tail if is_filtered else "",
                    'description': f"移除尾部内容: {removed_tail[:50]}..." if is_filtered and removed_tail else "未检测到尾部内容"
                }
                message.filter_details.append(filter_detail)
            else:
                filtered_content, is_filtered, removed_tail = current_content, False, ""
                message.filter_details.append({
                    'name': '尾部过滤',
                    'enabled': False,
                    'description': '尾部过滤已禁用'
                })
            if is_filtered:
                current_content = filtered_content
                filter_reasons.append(f"尾部过滤: 删除{len(removed_tail)}字符")
                logger.debug(f"消息 {message.message_id} 尾部过滤: {len(original_content)} -> {len(current_content)} 字符")

            # 2. 分隔符过滤（较快，处理结构化内容）
            if filter_config.get('separator_filter', True):
                filtered_content, separator_stats = self.separator_filter.filter_content(current_content)
                removed_blocks = separator_stats.get('removed_blocks_count', 0)
                # 收集详细信息
                filter_detail = {
                    'name': '分隔符过滤',
                    'enabled': True,
                    'filtered_content': filtered_content,
                    'removed_length': len(current_content) - len(filtered_content),
                    'removed_blocks': separator_stats.get('removed_blocks', []),
                    'matched_patterns': separator_stats.get('matched_patterns', []),
                    'description': f"移除{removed_blocks}个内容块" if removed_blocks > 0 else "未检测到需要过滤的分隔符内容"
                }
                message.filter_details.append(filter_detail)
            else:
                filtered_content = current_content
                removed_blocks = 0
                separator_stats = {}
                message.filter_details.append({
                    'name': '分隔符过滤',
                    'enabled': False,
                    'description': '分隔符过滤已禁用'
                })
            if removed_blocks > 0:
                current_content = filtered_content
                removed_chars = separator_stats.get('original_length', 0) - separator_stats.get('filtered_length', 0)
                filter_reasons.append(f"分隔符过滤: 移除{removed_blocks}个块({removed_chars}字符)")
                logger.debug(f"消息 {message.message_id} 分隔符过滤: 移除{removed_blocks}个内容块")

            # 3. 文本过滤（关键词和正则表达式过滤）
            if filter_config.get('text_filter', True):
                filtered_content, is_filtered, matched_keywords = self.text_filter.filter(current_content)
                # 收集详细信息
                filter_detail = {
                    'name': '文本过滤',
                    'enabled': True,
                    'filtered_content': filtered_content,
                    'removed_length': len(current_content) - len(filtered_content) if is_filtered else 0,
                    'matched_keywords': [{'keyword': kw} for kw in matched_keywords] if matched_keywords else [],
                    'description': f"匹配{len(matched_keywords)}个关键词" if is_filtered and matched_keywords else "未检测到需要过滤的文本内容"
                }
                message.filter_details.append(filter_detail)
            else:
                filtered_content, is_filtered, matched_keywords = current_content, False, []
                message.filter_details.append({
                    'name': '文本过滤',
                    'enabled': False,
                    'description': '文本过滤已禁用'
                })
            if is_filtered:
                removed_chars = len(current_content) - len(filtered_content)
                current_content = filtered_content
                filter_reasons.append(f"文本过滤: 匹配{len(matched_keywords)}个关键词({removed_chars}字符)")
                logger.debug(f"消息 {message.message_id} 文本过滤: 移除{len(matched_keywords)}个关键词")

            # 4. Markdown链接过滤（中等开销）
            if filter_config.get('markdown_filter', True):
                if message.entities and len(message.entities) > 0:
                    filtered_content, links_removed = self.markdown_filter.filter(current_content, message.entities)
                    filter_detail = {
                        'name': 'Markdown过滤',
                        'enabled': True,
                        'filtered_content': filtered_content,
                        'removed_length': len(current_content) - len(filtered_content),
                        'description': f"移除{links_removed}个链接" if links_removed > 0 else "无需处理Markdown"
                    }
                    message.filter_details.append(filter_detail)
                    if links_removed > 0:
                        current_content = filtered_content
                        filter_reasons.append(f"Markdown过滤: 移除{links_removed}个链接")
                        logger.debug(f"消息 {message.message_id} Markdown过滤: 移除{links_removed}个链接")
                else:
                    # 没有entities，Markdown过滤器不执行
                    message.filter_details.append({
                        'name': 'Markdown过滤',
                        'enabled': True,
                        'description': '无Markdown实体需要处理'
                    })
            else:
                message.filter_details.append({
                    'name': 'Markdown过滤',
                    'enabled': False,
                    'description': 'Markdown过滤已禁用'
                })

            # 5. 广告检测（最慢，放最后，支持早期退出）
            if detect_ad and filter_config.get('ad_detector', False):
                if current_content and len(current_content.strip()) > 10:
                    is_ad, total_weight, matched_keywords = self.ad_detector.detect(current_content)

                    # 收集详细信息
                    filter_detail = {
                        'name': '广告检测',
                        'enabled': True,
                        'is_ad': is_ad,
                        'total_score': total_weight,
                        'threshold': self.ad_detector.threshold,
                        'confidence': total_weight / self.ad_detector.threshold if self.ad_detector.threshold > 0 else 0,
                        'matched_keywords': matched_keywords if is_ad else [],
                        'description': f"检测为广告，得分: {total_weight}/{self.ad_detector.threshold}" if is_ad else "未检测为广告"
                    }
                    message.filter_details.append(filter_detail)

                    # 无论是否判定为广告，只要找到了关键词就保存
                    if matched_keywords:
                        message.ad_weight = total_weight
                        message.hit_keywords = matched_keywords[:10]  # 保存前10个关键词

                        # 详细的调试日志仅在DEBUG级别输出
                        keyword_details = [f"{k['keyword']}({k['weight']:.1f})" for k in matched_keywords]
                        logger.debug(f"广告检测详情 - 消息:{message.channel_id}:{message.message_id}")
                        logger.debug(f"  命中关键词: {', '.join(keyword_details)}")
                        logger.debug(f"  总权重: {total_weight:.1f} (阈值: 3.0)")

                        # 添加到过滤原因
                        keyword_names = [item['keyword'] for item in matched_keywords[:3]]
                        filter_reasons.append(f"广告检测: 权重={total_weight:.1f}, 关键词={','.join(keyword_names)}")

                    # 只有权重≥阈值才标记为广告
                    if is_ad:
                        message.is_ad = True

                        # 获取auto_reject配置
                        auto_reject = True  # 默认值
                        if config_manager:
                            try:
                                auto_reject = await config_manager.get_auto_reject_ads()
                            except Exception as e:
                                logger.error(f"获取自动拒绝配置失败: {e}")
                                auto_reject = True  # 配置失败时默认拒绝
                        else:
                            logger.debug("未提供config_manager，默认自动拒绝广告")
                            auto_reject = True  # 无配置时默认拒绝

                        # 合并为一条调试日志，避免在生产日志中刷屏
                        keyword_names = [k['keyword'] for k in matched_keywords[:3]]
                        logger.debug(
                            "🚫 检测到广告: %s:%s (权重:%.1f, 关键词:%s)",
                            message.channel_id,
                            message.message_id,
                            total_weight,
                            ','.join(keyword_names)
                        )

                        if auto_reject:
                            old_status = message.status
                            message.status = "ad_rejected"
                            message.reject_reason = f"自动拒绝广告(权重:{total_weight:.1f})"
                            logger.debug(f"消息被自动拒绝 - 状态从'{old_status}'改为'rejected'")
                        else:
                            logger.debug(f"广告检测已禁用自动拒绝，消息保持待审核状态")
                else:
                    # 内容太短，跳过广告检测
                    message.filter_details.append({
                        'name': '广告检测',
                        'enabled': True,
                        'description': '内容太短，跳过检测'
                    })
            else:
                # 广告检测被禁用
                message.filter_details.append({
                    'name': '广告检测',
                    'enabled': False,
                    'description': '广告检测已禁用'
                })

            # 6. 🔍 去重检测（在广告检测之后）
            try:
                from app.services.duplicate_detector import duplicate_detector

                # 检查是否启用去重检测
                duplicate_detection_enabled = True
                if config_manager:
                    try:
                        from app.services.config_manager import config_manager as cm
                        duplicate_detection_enabled = await cm.get_config('duplicate_detection.enabled', True)
                    except:
                        pass

                # 如果已经是广告且被拒绝，跳过去重检测
                if message.is_ad and message.status == 'ad_rejected':
                    logger.debug(f"跳过广告消息的去重检测: {message.channel_id}:{message.message_id}")
                    message.duplicate_status = 'skipped'
                elif duplicate_detection_enabled and current_content and len(current_content.strip()) >= 10:
                    # 构建完整的消息ID
                    full_message_id = f"{message.channel_id}:{message.message_id}" if message.channel_id else str(message.message_id)

                    # 执行去重检测
                    duplicate_result = await duplicate_detector.detect_duplicate(
                        current_content,
                        full_message_id
                    )

                    # 更新消息的去重字段
                    if duplicate_result.is_duplicate:
                        score = duplicate_result.similarity_score
                        message.original_message_id = duplicate_result.original_message_id
                        message.similarity_score = score
                        message.duplicate_reason = duplicate_result.detection_reason

                        # 获取配置的阈值
                        try:
                            from app.services.config_manager import config_manager as cm
                            confirmed_threshold = float(await cm.get_config('duplicate_detection.confirmed_threshold', '0.95'))
                            suspected_threshold = float(await cm.get_config('duplicate_detection.suspected_threshold', '0.82'))
                        except:
                            # 使用默认值作为fallback
                            confirmed_threshold = 0.95
                            suspected_threshold = 0.82

                        # 根据配置的阈值判断重复状态
                        if score >= confirmed_threshold:
                            message.duplicate_status = 'confirmed'
                            message.status = 'dup_rejected'
                            message.reject_reason = f"重复消息(相似度:{score:.1%})"
                            logger.info(f"🔁 拒绝重复消息: {full_message_id} -> {duplicate_result.original_message_id} (相似度: {score:.1%})")
                            filter_reasons.append(f"去重检测: 重复消息({score:.1%})")
                        elif score >= suspected_threshold:
                            # 疑似重复范围
                            message.duplicate_status = 'suspected'
                            logger.info(f"🔍 疑似重复消息: {full_message_id} -> {duplicate_result.original_message_id} (相似度: {score:.1%})")
                            filter_reasons.append(f"去重检测: 疑似重复({score:.1%})")
                        else:
                            # 相似度过低，标记为无重复
                            message.duplicate_status = 'none'
                            message.similarity_score = 0.0
                    else:
                        message.duplicate_status = 'none'
                        message.similarity_score = 0.0

            except Exception as e:
                logger.error(f"去重检测失败: {e}")
                # 去重失败不影响消息处理
                message.duplicate_status = 'none'

            # 更新消息
            message.filtered_content = current_content
            if filter_reasons:
                message.filter_reason = "; ".join(filter_reasons)

            return message

        except Exception as e:
            logger.error(f"内容处理失败 {message.message_id}: {e}")
            return message
