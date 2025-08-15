#!/usr/bin/env python3
"""
尾部过滤器使用示例

演示如何在过滤器管道中使用TailFilter，
以及与其他过滤器的集成。

Author: Claude
Created: 2025-08-15
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.services.filters import (
    FilterPipeline, 
    FilterContext,
    create_default_filters,
    tail_filter
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


async def demonstrate_tail_filter():
    """演示尾部过滤器的基本使用"""
    logger.info("📝 尾部过滤器基本使用示例")
    
    # 测试内容
    test_content = """柬埔寨重要新闻

当地时间今天上午，柬埔寨政府发布了重要公告。

这一决定将对当地华人社区产生重要影响。

政府表示将在未来几天内提供更多详细信息。

════════════════

🚩 柬埔寨华人群组  
📱 失联导航：@cambodia_nav  
💬 交流群：https://t.me/cambodia_chat  
📮 投稿爆料：欢迎联系"""

    # 创建过滤上下文
    context = FilterContext(
        message_id=7987,
        channel_id=12345,
        user_id=67890,
        message_type='text'
    )
    
    # 执行尾部过滤
    result = await tail_filter.filter(test_content, context)
    
    logger.info("📊 过滤结果:")
    logger.info(f"   原始长度: {len(test_content)} 字符")
    logger.info(f"   过滤后长度: {len(result.filtered_content)} 字符")
    logger.info(f"   处理时间: {result.processing_time_ms:.1f}ms")
    logger.info(f"   置信度: {result.confidence:.3f}")
    logger.info(f"   使用方法: {result.details.get('method', 'none')}")
    
    if result.filtered_content != test_content:
        logger.info("🎯 检测到并移除了尾部推广内容")
        removed_content = result.details.get('removed_tail', '')
        logger.info(f"   移除内容预览: {removed_content[:100]}...")
    else:
        logger.info("✅ 未检测到需要移除的尾部内容")


async def demonstrate_pipeline_integration():
    """演示与过滤器管道的集成"""
    logger.info("\n🔄 过滤器管道集成示例")
    
    # 创建包含尾部过滤器的管道
    pipeline = FilterPipeline()
    
    # 添加尾部过滤器（通常在内容过滤之前，广告检测之后）
    pipeline.add_filter(tail_filter)
    
    # 可以添加其他过滤器
    # pipeline.add_filter(duplicate_detector_filter)  # 去重
    # pipeline.add_filter(ad_detector_filter)         # 广告检测
    
    # 测试内容
    test_messages = [
        {
            'content': """重要新闻更新

市场分析师表示，这种趋势可能会持续到下个季度。

投资者应该密切关注相关政策变化。""",
            'description': '正常新闻，不应过滤'
        },
        {
            'content': """今日头条新闻

发生了一件令人震惊的事情。

更多详情正在调查中。

---

📢 关注我们获取最新消息 @news_bot
🔔 投稿爆料联系 @editor
💰 广告合作请私信""",
            'description': '带推广尾部，应该被过滤'
        }
    ]
    
    for i, msg in enumerate(test_messages, 1):
        logger.info(f"\n📨 处理消息 {i}: {msg['description']}")
        
        # 创建上下文
        context = FilterContext(
            message_id=i,
            channel_id=54321,
            message_type='text'
        )
        
        # 执行管道过滤
        pipeline_result = await pipeline.process(msg['content'], context)
        
        logger.info(f"   管道结果: {'✅ 通过' if pipeline_result.passed else '❌ 被拒绝'}")
        logger.info(f"   最终内容长度: {len(pipeline_result.final_content)} 字符")
        logger.info(f"   总处理时间: {pipeline_result.total_processing_time_ms:.1f}ms")
        
        # 显示各过滤器的执行情况
        for filter_name, filter_result in pipeline_result.filter_results.items():
            if filter_result.filtered_content != msg['content']:
                logger.info(f"   {filter_name}: 内容被修改 (置信度: {filter_result.confidence:.2f})")
            else:
                logger.info(f"   {filter_name}: 内容未变")


async def demonstrate_custom_configuration():
    """演示自定义配置的使用"""
    logger.info("\n⚙️ 自定义配置示例")
    
    # 创建不同配置的过滤器实例
    configs = [
        {
            'name': '保守模式',
            'config': {
                'intelligent_threshold': 0.8,  # 更高的智能过滤阈值
                'semantic_threshold': 0.7,     # 更高的语义过滤阈值
            },
            'description': '更严格的过滤标准'
        },
        {
            'name': '敏感模式', 
            'config': {
                'intelligent_threshold': 0.4,  # 更低的智能过滤阈值
                'semantic_threshold': 0.3,     # 更低的语义过滤阈值
            },
            'description': '更宽松的过滤标准'
        }
    ]
    
    # 测试内容（边界情况）
    borderline_content = """投资理财新观点

专家建议投资者应该：
1. 分散投资风险
2. 关注长期收益
3. 定期评估投资组合

如需专业指导，请咨询我们的理财顾问。"""

    context = FilterContext(message_id=999, channel_id=11111, message_type='text')
    
    for config_info in configs:
        logger.info(f"\n🔧 {config_info['name']} ({config_info['description']}):")
        
        # 导入TailFilter类并创建实例
        from app.services.filters.tail_filter import TailFilter
        custom_filter = TailFilter(config_info['config'])
        
        result = await custom_filter.filter(borderline_content, context)
        
        logger.info(f"   过滤结果: {'内容被修改' if result.filtered_content != borderline_content else '内容未变'}")
        logger.info(f"   置信度: {result.confidence:.3f}")
        logger.info(f"   使用方法: {result.details.get('method', 'none')}")
        
        # 显示配置信息
        stats = custom_filter.get_stats()
        logger.info(f"   智能阈值: {custom_filter.intelligent_threshold}")
        logger.info(f"   语义阈值: {custom_filter.semantic_threshold}")


async def main():
    """主演示函数"""
    logger.info("🚀 尾部过滤器使用示例开始")
    
    try:
        # 基本使用演示
        await demonstrate_tail_filter()
        
        # 管道集成演示
        await demonstrate_pipeline_integration()
        
        # 自定义配置演示
        await demonstrate_custom_configuration()
        
        logger.info("\n✅ 所有演示完成")
        
    except Exception as e:
        logger.error(f"❌ 演示执行异常: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)