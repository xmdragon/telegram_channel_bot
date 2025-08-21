#!/usr/bin/env python3
"""
视觉哈希索引性能测试工具
验证新的高性能索引是否正常工作，并对比传统方法的性能差异
"""
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('tools/testing/visual_index_test.log')
        ]
    )

async def test_visual_index_performance():
    """测试视觉索引性能"""
    print("🚀 视觉哈希索引性能测试")
    print("=" * 50)
    
    try:
        # 初始化Redis连接
        import redis
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # 测试Redis连接
        redis_client.ping()
        print("✅ Redis连接成功")
        
        # 导入必要的模块
        from app.storage.visual_index_manager import get_visual_index_manager
        from app.storage.redis_store import get_redis_message_store
        from app.services.duplicate_detection.visual_detector import VisualDuplicateDetector
        
        # 手动初始化Redis存储
        try:
            redis_store = get_redis_message_store()
        except RuntimeError:
            # 如果未初始化，直接创建实例
            from app.storage.redis_store import RedisMessageStore
            redis_store = RedisMessageStore()
            print("✅ Redis存储已初始化")
        
        # 获取组件
        visual_index = get_visual_index_manager(redis_client)
        visual_detector = VisualDuplicateDetector(redis_store)
        
        # 测试1：索引基本功能
        print("📊 测试1: 索引基本功能")
        stats = visual_index.get_index_stats()
        print(f"   当前索引状态: {stats}")
        
        # 测试2：添加测试数据
        print("\n📊 测试2: 添加测试数据")
        test_visual_hashes = {
            "phash": "test123456789abc",
            "dhash": "test987654321def", 
            "ahash": "testabcdef123456",
            "whash": "test456789abcdef",
            "colorhash": "test123",
            "sha256": "test_sha256_hash"
        }
        
        test_channel = "-1001234567890"
        test_message_id = 999999
        test_time = datetime.utcnow()
        
        success = visual_index.add_visual_hash(
            test_channel, 
            test_message_id, 
            test_visual_hashes, 
            test_time
        )
        print(f"   添加测试数据: {'✅ 成功' if success else '❌ 失败'}")
        
        # 测试3：查询性能对比
        print("\n📊 测试3: 查询性能对比")
        time_threshold = datetime.utcnow() - timedelta(hours=96)
        
        # 测试新方法性能
        start_time = time.time()
        new_results = await visual_detector._get_recent_messages_with_visual_hash(time_threshold)
        new_method_time = time.time() - start_time
        
        # 测试传统方法性能
        start_time = time.time()
        legacy_results = await visual_detector._get_recent_messages_legacy(time_threshold)
        legacy_method_time = time.time() - start_time
        
        print(f"   🚀 新方法: {len(new_results)} 条结果，耗时 {new_method_time:.4f}s")
        print(f"   🐌 传统方法: {len(legacy_results)} 条结果，耗时 {legacy_method_time:.4f}s")
        
        if legacy_method_time > 0:
            speedup = legacy_method_time / new_method_time if new_method_time > 0 else float('inf')
            print(f"   ⚡ 性能提升: {speedup:.1f}x")
        
        # 测试4：结果一致性验证
        print("\n📊 测试4: 结果一致性验证")
        
        # 比较结果数量
        count_match = len(new_results) == len(legacy_results)
        print(f"   结果数量一致: {'✅' if count_match else '❌'} (新:{len(new_results)} vs 传统:{len(legacy_results)})")
        
        # 比较具体内容（忽略顺序）
        if new_results and legacy_results:
            new_ids = {f"{r.get('channel_id', '')}:{r.get('message_id', '')}" for r in new_results}
            legacy_ids = {f"{msg.get('source_channel', '')}:{msg.get('message_id', '')}" for msg in legacy_results}
            
            content_match = new_ids == legacy_ids
            print(f"   结果内容一致: {'✅' if content_match else '❌'}")
            
            if not content_match:
                only_new = new_ids - legacy_ids
                only_legacy = legacy_ids - new_ids
                if only_new:
                    print(f"   仅新方法有: {only_new}")
                if only_legacy:
                    print(f"   仅传统方法有: {only_legacy}")
        
        # 测试5：索引统计
        print("\n📊 测试5: 索引统计信息")
        final_stats = visual_index.get_index_stats()
        for key, value in final_stats.items():
            if key == 'oldest_timestamp' and value:
                oldest_time = datetime.fromtimestamp(value)
                print(f"   {key}: {oldest_time.strftime('%Y-%m-%d %H:%M:%S')}")
            elif key == 'newest_timestamp' and value:
                newest_time = datetime.fromtimestamp(value)
                print(f"   {key}: {newest_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print(f"   {key}: {value}")
        
        # 测试6：清理功能
        print("\n📊 测试6: 清理功能测试")
        cleanup_time = datetime.utcnow() - timedelta(hours=100)  # 100小时前
        removed = visual_index.cleanup_expired_data(cleanup_time)
        print(f"   清理结果: 删除了 {removed} 个过期条目")
        
        print("\n🎉 视觉哈希索引测试完成")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_migration():
    """测试数据迁移功能"""
    print("\n🔄 测试数据迁移功能")
    print("=" * 30)
    
    try:
        # 初始化Redis连接
        import redis
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        redis_client.ping()
        
        from app.storage.visual_index_manager import get_visual_index_manager
        
        visual_index = get_visual_index_manager(redis_client)
        
        print("开始迁移现有数据...")
        result = visual_index.migrate_existing_visual_hashes(batch_size=50)
        
        print(f"迁移结果: {result}")
        
        if 'error' in result:
            print(f"❌ 迁移失败: {result['error']}")
            return False
        else:
            migrated = result.get('migrated', 0)
            errors = result.get('errors', 0)
            total = result.get('total_processed', 0)
            
            print(f"✅ 迁移完成:")
            print(f"   - 成功迁移: {migrated} 条")
            print(f"   - 错误数量: {errors} 条")
            print(f"   - 总计处理: {total} 条")
            
            return migrated > 0 or total == 0
            
    except Exception as e:
        print(f"❌ 迁移测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def generate_test_report(results):
    """生成测试报告"""
    report_file = Path("tools/testing/visual_index_test_report.json")
    
    report = {
        "test_time": datetime.utcnow().isoformat(),
        "results": results,
        "summary": {
            "total_tests": len(results),
            "passed": sum(1 for r in results.values() if r),
            "failed": sum(1 for r in results.values() if not r)
        }
    }
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"📄 测试报告已保存: {report_file}")
    except Exception as e:
        print(f"保存测试报告失败: {e}")

async def main():
    """主函数"""
    setup_logging()
    
    print("🧪 视觉哈希索引综合测试")
    print("=" * 60)
    
    results = {}
    
    # 执行性能测试
    results['performance_test'] = await test_visual_index_performance()
    
    # 执行迁移测试
    results['migration_test'] = await test_migration()
    
    # 生成报告
    generate_test_report(results)
    
    # 汇总结果
    print("\n📋 测试汇总")
    print("=" * 20)
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    print(f"\n总体结果: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("🎉 所有测试通过！视觉哈希索引优化成功！")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查问题")
        return 1

if __name__ == "__main__":
    import asyncio
    exit_code = asyncio.run(main())
    sys.exit(exit_code)