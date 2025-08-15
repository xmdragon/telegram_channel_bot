"""
过滤器使用示例
展示如何使用新实现的去重和广告检测器

Author: Claude
Created: 2025-08-15
"""

import asyncio
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, '/Users/eric/workspace/telegram_channel_bot')

from app.services.filters import (
    FilterContext,
    create_early_stop_pipeline,
    duplicate_detector_filter,
    ad_detector_filter,
    create_default_filters,
    DuplicateDetectorFilter,
    AdDetectorFilter
)


async def example_single_filter_usage():
    """示例1：单独使用过滤器"""
    print("=" * 60)
    print("示例1：单独使用过滤器")
    print("=" * 60)
    
    # 创建过滤上下文
    context = FilterContext(
        message_id=1001,
        channel_id=123456,
        timestamp=datetime.now().timestamp(),
        message_type="text"
    )
    
    # 测试广告检测器
    ad_content = "📢本频道推荐 博彩平台现已上线！USDT充值立即到账！"
    print(f"测试内容: {ad_content}")
    
    result = await ad_detector_filter.filter(ad_content, context)
    
    print(f"检测结果:")
    print(f"  ✅ 通过检测: {result.passed}")
    print(f"  ⚡ 早停标志: {result.should_early_stop}")
    print(f"  🎯 置信度: {result.confidence:.2f}")
    print(f"  📝 原因: {result.reason}")
    print(f"  ⏱️ 处理时间: {result.processing_time_ms:.1f}ms")


async def example_pipeline_usage():
    """示例2：使用管道处理"""
    print("\n" + "=" * 60)
    print("示例2：使用过滤器管道")
    print("=" * 60)
    
    # 创建早停管道
    pipeline = create_early_stop_pipeline()
    print(f"管道配置: 启用早停机制")
    
    # 测试内容列表
    test_cases = [
        {
            'content': '正常的新闻内容，没有广告也不重复。',
            'description': '正常内容'
        },
        {
            'content': '📢本频道推荐 交易所现已上线！',
            'description': '广告内容'  
        },
        {
            'content': '这是一个包含联系方式的推广：WeChat: test123',
            'description': '推广内容'
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {case['description']}")
        print(f"内容: {case['content']}")
        
        context = FilterContext(
            message_id=2000 + i,
            channel_id=654321,
            timestamp=datetime.now().timestamp()
        )
        
        # 使用管道处理
        pipeline_result = await pipeline.process(case['content'], context)
        
        print(f"管道结果:")
        print(f"  ✅ 通过管道: {pipeline_result.passed}")
        print(f"  📊 最终内容: {pipeline_result.final_content[:50]}...")
        print(f"  ⏱️ 总处理时间: {pipeline_result.total_processing_time_ms:.1f}ms")
        
        if not pipeline_result.passed:
            print(f"  🚫 过滤原因: {pipeline_result.overall_reason}")
            if pipeline_result.early_stopped_at:
                print(f"  ⚡ 早停于: {pipeline_result.early_stopped_at}")
        
        # 显示各个过滤器的结果
        print(f"  📈 过滤器结果:")
        for filter_name, filter_result in pipeline_result.filter_results.items():
            status = "✅通过" if filter_result.passed else "❌拒绝"
            print(f"    - {filter_name}: {status} (置信度: {filter_result.confidence:.2f})")


async def example_custom_configuration():
    """示例3：自定义配置"""
    print("\n" + "=" * 60)
    print("示例3：自定义过滤器配置")
    print("=" * 60)
    
    # 自定义去重检测器配置
    custom_dup_filter = DuplicateDetectorFilter({
        'text_similarity_threshold': 0.9,  # 更严格的文本相似度阈值
        'media_cache_hours': 48,           # 48小时媒体缓存
        'enabled': True
    })
    
    # 自定义广告检测器配置  
    custom_ad_filter = AdDetectorFilter({
        'final_threshold': 0.8,            # 更严格的综合阈值
        'ai_threshold': 0.8,               # 更严格的AI检测阈值
        'enabled': True
    })
    
    print("自定义配置:")
    print(f"  去重检测器 - 文本相似度阈值: {custom_dup_filter.text_similarity_threshold}")
    print(f"  广告检测器 - 综合阈值: {custom_ad_filter.final_threshold}")
    
    # 测试边界情况
    context = FilterContext(message_id=3001, channel_id=111111)
    test_content = "交易所最新消息：某平台因违规被查处。"
    
    result = await custom_ad_filter.filter(test_content, context)
    print(f"\n边界情况测试:")
    print(f"  内容: {test_content}")  
    print(f"  结果: {'通过' if result.passed else '拒绝'}")
    print(f"  置信度: {result.confidence:.2f}")


async def example_statistics_monitoring():
    """示例4：统计信息监控"""
    print("\n" + "=" * 60)
    print("示例4：过滤器统计信息")
    print("=" * 60)
    
    filters = create_default_filters()
    
    # 批量处理测试
    test_contents = [
        "正常内容1", "正常内容2", "📢推广内容",
        "博彩平台", "正常内容3", "本频道推荐"
    ]
    
    for i, content in enumerate(test_contents):
        context = FilterContext(message_id=4000 + i, channel_id=888888)
        
        # 每个过滤器都处理
        for filter_name, filter_instance in filters.items():
            await filter_instance.filter(content, context)
    
    # 显示统计信息
    print("过滤器统计信息:")
    for filter_name, filter_instance in filters.items():
        stats = filter_instance.get_stats()
        print(f"\n{filter_name}:")
        print(f"  总处理数: {stats['total_processed']}")
        print(f"  过滤数: {stats['total_filtered']}")
        print(f"  过滤率: {stats['filter_rate']:.1%}")
        print(f"  平均处理时间: {stats['avg_processing_time_ms']:.1f}ms")
        print(f"  启用状态: {stats['enabled']}")


async def main():
    """主函数"""
    print("🚀 过滤器基础架构使用示例")
    print("基于BaseFilter接口的统一过滤器系统")
    
    try:
        # 运行所有示例
        await example_single_filter_usage()
        await example_pipeline_usage() 
        await example_custom_configuration()
        await example_statistics_monitoring()
        
        print("\n" + "=" * 60)
        print("✅ 所有示例运行完成！")
        print("=" * 60)
        print("\n使用总结:")
        print("1. 单独使用过滤器 - 直接调用 filter() 方法")
        print("2. 管道处理 - 使用 FilterPipeline 协调多个过滤器")  
        print("3. Early Stop - 重复和广告检测可触发早停机制")
        print("4. 自定义配置 - 灵活调整检测阈值和参数")
        print("5. 统计监控 - 跟踪处理性能和过滤效果")
        
    except Exception as e:
        print(f"❌ 运行示例时出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())