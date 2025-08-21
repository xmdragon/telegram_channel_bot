#!/usr/bin/env python3
"""
简化的规则外化功能测试脚本
快速验证基础功能
"""
import sys
import asyncio
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 禁用大部分日志输出
logging.basicConfig(level=logging.ERROR)

async def test_basic_functionality():
    """基础功能测试"""
    try:
        print("1. 测试 RuleManager 导入...")
        from app.services.rule_manager import rule_manager
        print("✅ RuleManager 导入成功")
        
        print("2. 测试配置文件是否存在...")
        config_path = Path("data/config/filter_rules.json")
        if config_path.exists():
            print("✅ 配置文件存在")
        else:
            print("❌ 配置文件不存在")
            return False
        
        print("3. 测试 RuleManager 初始化...")
        await asyncio.wait_for(rule_manager.initialize(), timeout=30)
        print("✅ RuleManager 初始化成功")
        
        print("4. 测试规则统计...")
        total_count = rule_manager.get_total_pattern_count()
        print(f"✅ 总规则数量: {total_count}")
        
        if total_count == 0:
            print("❌ 没有加载任何规则")
            return False
        
        print("5. 测试获取高危关键词...")
        high_risk_patterns = rule_manager.get_high_risk_keywords()
        print(f"✅ 高危关键词数量: {len(high_risk_patterns)}")
        
        print("6. 测试获取推广模式...")
        promo_patterns = rule_manager.get_promo_patterns()
        print(f"✅ 推广模式数量: {len(promo_patterns)}")
        
        print("7. 测试简单模式匹配...")
        # 测试一个简单的匹配
        test_content = "博彩平台官网"
        matched = False
        
        for pattern, weight in high_risk_patterns + promo_patterns:
            if pattern.search(test_content):
                matched = True
                break
        
        if matched:
            print("✅ 模式匹配工作正常")
        else:
            print("⚠️  测试内容未匹配到任何规则")
        
        print("8. 测试 RuleLearner 导入...")
        from app.services.rule_learner import rule_learner
        print("✅ RuleLearner 导入成功")
        
        print("9. 测试学习器统计...")
        stats = rule_learner.get_learning_stats()
        print(f"✅ 学习器统计: {stats}")
        
        return True
        
    except asyncio.TimeoutError:
        print("❌ 初始化超时")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    print("🧪 简化规则外化功能测试")
    print("=" * 50)
    
    try:
        result = await asyncio.wait_for(test_basic_functionality(), timeout=60)
        
        if result:
            print("\n🎉 基础功能测试通过！")
        else:
            print("\n❌ 基础功能测试失败！")
            
    except asyncio.TimeoutError:
        print("\n❌ 测试超时")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")

if __name__ == "__main__":
    asyncio.run(main())