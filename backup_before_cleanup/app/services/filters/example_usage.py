"""
过滤器基础架构使用示例

展示如何实现具体的过滤器和使用管道系统

Author: Claude
Created: 2025-08-15
"""

import asyncio
import time
import logging
from typing import Dict, Any

from .base import BaseFilter, FilterContext, FilterResult
from .filter_pipeline import FilterPipeline, PipelineConfig

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DuplicateDetectorFilter(BaseFilter):
    """去重检测过滤器示例"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("duplicate_detector", config)
        self.seen_hashes = set()
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """检测重复内容"""
        # 简单的哈希去重
        content_hash = hash(content.strip())
        
        if content_hash in self.seen_hashes:
            return FilterResult(
                filtered_content=content,
                passed=False,
                reason="检测到重复内容",
                confidence=1.0,
                should_early_stop=True,  # 去重可以早停
                details={
                    'content_hash': content_hash,
                    'duplicate_detected': True
                }
            )
        
        self.seen_hashes.add(content_hash)
        return FilterResult(
            filtered_content=content,
            passed=True,
            reason="内容唯一",
            confidence=1.0,
            details={'content_hash': content_hash}
        )


class AdDetectorFilter(BaseFilter):
    """广告检测过滤器示例"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("ad_detector", config)
        # 简单的广告关键词
        self.ad_keywords = {'广告', '推广', '营销', '加微信', '免费试用', '立即购买'}
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """检测广告内容"""
        content_lower = content.lower()
        found_keywords = []
        
        for keyword in self.ad_keywords:
            if keyword in content_lower:
                found_keywords.append(keyword)
        
        if found_keywords:
            confidence = min(1.0, len(found_keywords) * 0.3)
            return FilterResult(
                filtered_content=content,
                passed=False,
                reason=f"检测到广告关键词: {', '.join(found_keywords)}",
                confidence=confidence,
                should_early_stop=True,  # 广告检测可以早停
                details={
                    'detected_keywords': found_keywords,
                    'keyword_count': len(found_keywords)
                }
            )
        
        return FilterResult(
            filtered_content=content,
            passed=True,
            reason="未检测到广告内容",
            confidence=0.9,
            details={'scanned_keywords': len(self.ad_keywords)}
        )


class ContentCleanerFilter(BaseFilter):
    """内容清理过滤器示例"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("content_cleaner", config)
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """清理内容格式"""
        # 简单的内容清理
        cleaned_content = content.strip()
        cleaned_content = ' '.join(cleaned_content.split())  # 标准化空白字符
        
        modifications = []
        if len(cleaned_content) != len(content):
            modifications.append("移除多余空白字符")
        
        return FilterResult(
            filtered_content=cleaned_content,
            passed=True,
            reason="内容清理完成",
            confidence=1.0,
            details={'original_length': len(content), 'cleaned_length': len(cleaned_content)},
            modifications=modifications
        )


class LengthValidatorFilter(BaseFilter):
    """长度验证过滤器示例"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("length_validator", config)
        self.min_length = self.config.get('min_length', 1)
        self.max_length = self.config.get('max_length', 4000)
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """验证内容长度"""
        content_length = len(content)
        
        if content_length < self.min_length:
            return FilterResult(
                filtered_content=content,
                passed=False,
                reason=f"内容过短: {content_length} < {self.min_length}",
                confidence=1.0,
                details={'length': content_length, 'min_required': self.min_length}
            )
        
        if content_length > self.max_length:
            return FilterResult(
                filtered_content=content,
                passed=False,
                reason=f"内容过长: {content_length} > {self.max_length}",
                confidence=1.0,
                details={'length': content_length, 'max_allowed': self.max_length}
            )
        
        return FilterResult(
            filtered_content=content,
            passed=True,
            reason="长度验证通过",
            confidence=1.0,
            details={'length': content_length}
        )


class SensitiveWordFilter(BaseFilter):
    """敏感词过滤器示例"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("sensitive_word_filter", config)
        self.sensitive_words = {'敏感词1', '敏感词2', '违规内容'}
        self.replacement = self.config.get('replacement', '*')
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """过滤敏感词"""
        filtered_content = content
        found_words = []
        
        for word in self.sensitive_words:
            if word in filtered_content:
                found_words.append(word)
                filtered_content = filtered_content.replace(word, self.replacement * len(word))
        
        if found_words:
            return FilterResult(
                filtered_content=filtered_content,
                passed=True,  # 替换后通过
                reason=f"替换敏感词: {', '.join(found_words)}",
                confidence=1.0,
                details={'replaced_words': found_words, 'replacement_char': self.replacement},
                modifications=[f"替换敏感词: {word}" for word in found_words]
            )
        
        return FilterResult(
            filtered_content=content,
            passed=True,
            reason="未发现敏感词",
            confidence=1.0,
            details={'scanned_words': len(self.sensitive_words)}
        )


async def demo_pipeline():
    """演示管道使用"""
    logger.info("🚀 开始过滤器管道演示")
    
    # 创建管道配置
    config = PipelineConfig(
        enable_early_stopping=True,
        early_stop_filters={'duplicate_detector', 'ad_detector'},
        filter_timeout=10.0
    )
    
    # 创建管道
    pipeline = FilterPipeline(config)
    
    # 添加过滤器
    pipeline.add_filter(DuplicateDetectorFilter())
    pipeline.add_filter(AdDetectorFilter())
    pipeline.add_filter(ContentCleanerFilter())
    pipeline.add_filter(LengthValidatorFilter({'min_length': 5, 'max_length': 1000}))
    pipeline.add_filter(SensitiveWordFilter())
    
    logger.info(f"管道配置完成: {pipeline}")
    
    # 测试数据
    test_cases = [
        "这是一条正常的消息",
        "   这是一条需要清理的消息   ",
        "这是广告内容，立即购买我们的产品！",
        "短",  # 过短
        "这是重复内容",
        "这是重复内容",  # 重复
        "这条消息包含敏感词1和违规内容"
    ]
    
    # 处理每个测试案例
    for i, content in enumerate(test_cases, 1):
        logger.info(f"\n--- 测试案例 {i}: '{content}' ---")
        
        context = FilterContext(
            message_id=i,
            channel_id=12345,
            user_id=67890,
            message_type="text"
        )
        
        # 处理内容
        result = await pipeline.process(content, context)
        
        # 显示结果
        logger.info(f"处理结果: passed={result.passed}")
        logger.info(f"最终内容: '{result.final_content}'")
        logger.info(f"处理时间: {result.total_processing_time_ms:.2f}ms")
        
        if not result.passed:
            logger.info(f"过滤原因: {result.overall_reason}")
        
        if result.early_stopped_at:
            logger.info(f"早停于: {result.early_stopped_at}")
        
        # 显示各过滤器结果
        for filter_name, filter_result in result.filter_results.items():
            status = "✅ 通过" if filter_result.passed else "❌ 拦截"
            logger.info(f"  {filter_name}: {status} ({filter_result.processing_time_ms:.1f}ms)")
            if filter_result.reason:
                logger.info(f"    原因: {filter_result.reason}")
            if filter_result.modifications:
                logger.info(f"    修改: {', '.join(filter_result.modifications)}")
    
    # 显示统计信息
    logger.info("\n📊 管道统计信息:")
    stats = pipeline.get_pipeline_stats()
    
    pipeline_stats = stats['pipeline']
    logger.info(f"总处理数: {pipeline_stats['total_processed']}")
    logger.info(f"通过数: {pipeline_stats['total_passed']}")
    logger.info(f"过滤数: {pipeline_stats['total_filtered']}")
    logger.info(f"早停数: {pipeline_stats['early_stopped']}")
    logger.info(f"错误数: {pipeline_stats['errors']}")
    logger.info(f"平均处理时间: {pipeline_stats['avg_processing_time_ms']:.2f}ms")
    
    if pipeline_stats['total_processed'] > 0:
        logger.info(f"通过率: {pipeline_stats.get('pass_rate', 0):.2%}")
        logger.info(f"过滤率: {pipeline_stats.get('filter_rate', 0):.2%}")
        logger.info(f"早停率: {pipeline_stats.get('early_stop_rate', 0):.2%}")
    
    # 显示各过滤器统计
    logger.info("\n🔧 过滤器统计:")
    for filter_name, filter_stats in stats['filters'].items():
        logger.info(f"{filter_name}:")
        logger.info(f"  处理数: {filter_stats['total_processed']}")
        logger.info(f"  过滤数: {filter_stats['total_filtered']}")
        logger.info(f"  过滤率: {filter_stats.get('filter_rate', 0):.2%}")
        logger.info(f"  平均时间: {filter_stats['avg_processing_time_ms']:.2f}ms")


if __name__ == "__main__":
    # 运行演示
    asyncio.run(demo_pipeline())