#!/usr/bin/env python3
"""
测试频道管理功能
"""
import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.channel_manager import channel_manager
from app.core.database import init_db

async def test_channel_management():
    """测试频道管理功能"""
    print("🧪 开始测试频道管理功能...")
    
    try:
        # 初始化数据库
        await init_db()
        
        # 测试添加频道
        print("\n1. 测试添加频道...")
        success = await channel_manager.add_channel(
            channel_id="test_channel_1",
            channel_name="测试频道1",
            description="这是一个测试频道",
            channel_type="source"
        )
        print(f"   添加频道结果: {'成功' if success else '失败'}")
        
        success = await channel_manager.add_channel(
            channel_id="test_channel_2",
            channel_name="测试频道2",
            description="这是另一个测试频道",
            channel_type="source"
        )
        print(f"   添加第二个频道结果: {'成功' if success else '失败'}")
        
        # 测试获取频道列表
        print("\n2. 测试获取频道列表...")
        channels = await channel_manager.get_source_channels()
        print(f"   源频道数量: {len(channels)}")
        for channel in channels:
            print(f"   - {channel['channel_name']} ({channel['channel_id']}) - 状态: {'启用' if channel['is_active'] else '禁用'}")
        
        # 测试更新频道状态
        print("\n3. 测试更新频道状态...")
        success = await channel_manager.update_channel("test_channel_1", is_active=False)
        print(f"   禁用频道结果: {'成功' if success else '失败'}")
        
        # 测试获取活跃频道
        print("\n4. 测试获取活跃频道...")
        active_channels = await channel_manager.get_active_source_channels()
        print(f"   活跃频道数量: {len(active_channels)}")
        print(f"   活跃频道ID: {active_channels}")
        
        # 测试获取单个频道信息
        print("\n5. 测试获取单个频道信息...")
        channel_info = await channel_manager.get_channel_by_id("test_channel_1")
        if channel_info:
            print(f"   频道信息: {channel_info['channel_name']} - 状态: {'启用' if channel_info['is_active'] else '禁用'}")
        else:
            print("   未找到频道信息")
        
        # 测试删除频道
        print("\n6. 测试删除频道...")
        success = await channel_manager.delete_channel("test_channel_2")
        print(f"   删除频道结果: {'成功' if success else '失败'}")
        
        # 最终频道列表
        print("\n7. 最终频道列表...")
        final_channels = await channel_manager.get_source_channels()
        print(f"   剩余频道数量: {len(final_channels)}")
        for channel in final_channels:
            print(f"   - {channel['channel_name']} ({channel['channel_id']}) - 状态: {'启用' if channel['is_active'] else '禁用'}")
        
        print("\n✅ 频道管理功能测试完成！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_channel_management()) 