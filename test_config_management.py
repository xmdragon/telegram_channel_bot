#!/usr/bin/env python3
"""
配置管理功能测试脚本
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import init_db
from app.services.config_manager import config_manager, init_default_configs

async def test_config_management():
    """测试配置管理功能"""
    print("🧪 测试配置管理功能")
    print("=" * 50)
    
    try:
        # 初始化数据库和配置
        await init_db()
        await init_default_configs()
        
        print("✅ 数据库初始化成功")
        
        # 测试获取所有配置
        print("\n📋 测试获取所有配置...")
        all_configs = await config_manager.get_all_configs()
        print(f"  总配置项数量: {len(all_configs)}")
        
        # 测试分类配置
        print("\n📱 测试 Telegram 配置...")
        telegram_configs = {k: v for k, v in all_configs.items() if k.startswith('telegram.')}
        print(f"  Telegram 配置项: {len(telegram_configs)}")
        for key, config in telegram_configs.items():
            print(f"    {key}: {config['config_type']} - {config['description']}")
        
        print("\n📺 测试频道配置...")
        channel_configs = {k: v for k, v in all_configs.items() if k.startswith('channels.')}
        print(f"  频道配置项: {len(channel_configs)}")
        for key, config in channel_configs.items():
            print(f"    {key}: {config['config_type']} - {config['description']}")
        
        print("\n🔍 测试过滤配置...")
        filter_configs = {k: v for k, v in all_configs.items() if k.startswith('filter.')}
        print(f"  过滤配置项: {len(filter_configs)}")
        for key, config in filter_configs.items():
            print(f"    {key}: {config['config_type']} - {config['description']}")
        
        print("\n✅ 测试审核配置...")
        review_configs = {k: v for k, v in all_configs.items() if k.startswith('review.')}
        print(f"  审核配置项: {len(review_configs)}")
        for key, config in review_configs.items():
            print(f"    {key}: {config['config_type']} - {config['description']}")
        
        # 测试配置更新
        print("\n💾 测试配置更新...")
        test_key = "test.config_item"
        test_value = "test_value"
        test_description = "测试配置项"
        
        success = await config_manager.set_config(
            key=test_key,
            value=test_value,
            description=test_description,
            config_type="string"
        )
        
        if success:
            print("✅ 配置创建成功")
            
            # 测试获取配置
            retrieved_value = await config_manager.get_config(test_key)
            if retrieved_value == test_value:
                print("✅ 配置获取成功")
            else:
                print(f"❌ 配置获取失败: 期望 {test_value}, 实际 {retrieved_value}")
            
            # 测试更新配置
            new_value = "updated_test_value"
            success = await config_manager.set_config(
                key=test_key,
                value=new_value,
                description=test_description,
                config_type="string"
            )
            
            if success:
                print("✅ 配置更新成功")
                
                # 验证更新
                updated_value = await config_manager.get_config(test_key)
                if updated_value == new_value:
                    print("✅ 配置更新验证成功")
                else:
                    print(f"❌ 配置更新验证失败: 期望 {new_value}, 实际 {updated_value}")
            else:
                print("❌ 配置更新失败")
        else:
            print("❌ 配置创建失败")
        
        # 测试批量操作
        print("\n🔄 测试批量操作...")
        batch_configs = [
            {
                "key": "batch.test1",
                "value": "batch_value1",
                "description": "批量测试配置1",
                "config_type": "string"
            },
            {
                "key": "batch.test2",
                "value": "batch_value2",
                "description": "批量测试配置2",
                "config_type": "string"
            }
        ]
        
        success_count = 0
        for config in batch_configs:
            success = await config_manager.set_config(**config)
            if success:
                success_count += 1
        
        print(f"✅ 批量操作成功: {success_count}/{len(batch_configs)}")
        
        # 测试缓存重载
        print("\n🔄 测试缓存重载...")
        try:
            await config_manager.reload_cache()
            print("✅ 缓存重载成功")
        except Exception as e:
            print(f"❌ 缓存重载失败: {e}")
        
        print("\n🎉 配置管理功能测试完成!")
        print("\n📝 使用方法:")
        print("1. 启动系统: python main.py")
        print("2. 访问配置界面: http://localhost:8000/config")
        print("3. 在 Web 界面上管理所有配置")
        print("4. 支持分类管理、批量操作、导入导出")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """主函数"""
    try:
        success = asyncio.run(test_config_management())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ 测试已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 