#!/usr/bin/env python3
"""
手动设置频道checkpoint工具
用于应急情况下手动设置采集进度，避免重复采集消息

使用方法:
python3 tools/maintenance/set_checkpoint.py <channel_id> <message_id>
python3 tools/maintenance/set_checkpoint.py -1002557968812 2838

功能:
- 设置指定频道的checkpoint到指定消息ID
- 显示设置前后的checkpoint信息
- 验证设置是否成功
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

def set_checkpoint(channel_id: str, message_id: int):
    """设置频道checkpoint"""
    try:
        # 导入必要模块
        from app.storage.channel_store import RedisChannelStore
        from app.storage.redis_manager import redis_manager
        from datetime import datetime
        
        print(f"🔧 正在设置checkpoint: {channel_id} -> {message_id}")
        
        # 创建channel store
        channel_store = RedisChannelStore(redis_manager.client)
        
        # 获取当前checkpoint
        current_checkpoint = channel_store.get_checkpoint(channel_id)
        current_time = channel_store.get_checkpoint_time(channel_id)
        
        print(f"📍 当前checkpoint: {current_checkpoint or 'None'}")
        if current_time:
            print(f"⏰ 上次更新时间: {current_time}")
        
        # 设置新的checkpoint
        success = channel_store.set_checkpoint(channel_id, message_id)
        
        if success:
            # 验证设置结果
            new_checkpoint = channel_store.get_checkpoint(channel_id)
            new_time = channel_store.get_checkpoint_time(channel_id)
            
            print(f"✅ Checkpoint设置成功!")
            print(f"📍 新checkpoint: {new_checkpoint}")
            print(f"⏰ 更新时间: {new_time}")
            
            if new_checkpoint == message_id:
                print(f"✅ 验证成功: checkpoint已正确设置为 {message_id}")
            else:
                print(f"⚠️ 验证警告: 期望 {message_id}，实际 {new_checkpoint}")
        else:
            print(f"❌ Checkpoint设置失败")
            return False
            
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        print("请确保在项目根目录下运行此脚本")
        return False
    except Exception as e:
        print(f"❌ 设置checkpoint失败: {e}")
        return False
        
    return True

def get_checkpoint_info(channel_id: str):
    """获取频道checkpoint信息"""
    try:
        from app.storage.channel_store import RedisChannelStore
        from app.storage.redis_manager import redis_manager
        
        channel_store = RedisChannelStore(redis_manager.client)
        info = channel_store.get_checkpoint_info(channel_id)
        
        print(f"📋 频道 {channel_id} checkpoint信息:")
        print(f"   Checkpoint: {info.get('checkpoint') or 'None'}")
        print(f"   更新时间: {info.get('updated_at') or 'None'}")
        print(f"   是否存在: {info.get('exists', False)}")
        
        return info
        
    except Exception as e:
        print(f"❌ 获取checkpoint信息失败: {e}")
        return None

def list_all_checkpoints():
    """列出所有频道的checkpoint"""
    try:
        from app.storage.channel_store import RedisChannelStore
        from app.storage.redis_manager import redis_manager
        
        channel_store = RedisChannelStore(redis_manager.client)
        checkpoints = channel_store.get_all_checkpoints()
        
        if not checkpoints:
            print("📋 没有找到任何checkpoint")
            return
        
        print(f"📋 所有频道的checkpoint ({len(checkpoints)} 个):")
        for channel_id, checkpoint in checkpoints.items():
            checkpoint_time = channel_store.get_checkpoint_time(channel_id)
            print(f"   {channel_id}: {checkpoint} (更新于: {checkpoint_time or 'Unknown'})")
        
    except Exception as e:
        print(f"❌ 列出checkpoint失败: {e}")

def main():
    """主函数"""
    if len(sys.argv) == 1:
        print("📋 手动设置频道checkpoint工具")
        print()
        print("使用方法:")
        print("  python3 tools/maintenance/set_checkpoint.py <channel_id> <message_id>  # 设置checkpoint")
        print("  python3 tools/maintenance/set_checkpoint.py --info <channel_id>       # 查看checkpoint信息")
        print("  python3 tools/maintenance/set_checkpoint.py --list                     # 列出所有checkpoint")
        print()
        print("示例:")
        print("  python3 tools/maintenance/set_checkpoint.py -1002557968812 2838")
        print("  python3 tools/maintenance/set_checkpoint.py --info -1002557968812")
        print("  python3 tools/maintenance/set_checkpoint.py --list")
        sys.exit(0)
    
    if sys.argv[1] == "--list":
        list_all_checkpoints()
        sys.exit(0)
    
    if sys.argv[1] == "--info":
        if len(sys.argv) != 3:
            print("❌ 错误: --info 需要指定频道ID")
            print("使用方法: python3 tools/maintenance/set_checkpoint.py --info <channel_id>")
            sys.exit(1)
        
        get_checkpoint_info(sys.argv[2])
        sys.exit(0)
    
    if len(sys.argv) != 3:
        print("❌ 错误: 请提供频道ID和消息ID")
        print("使用方法: python3 tools/maintenance/set_checkpoint.py <channel_id> <message_id>")
        print("示例: python3 tools/maintenance/set_checkpoint.py -1002557968812 2838")
        sys.exit(1)
    
    channel_id = sys.argv[1]
    try:
        message_id = int(sys.argv[2])
    except ValueError:
        print(f"❌ 错误: 消息ID必须是数字，得到: {sys.argv[2]}")
        sys.exit(1)
    
    # 确认操作
    print(f"⚠️ 即将设置频道 {channel_id} 的checkpoint为 {message_id}")
    print(f"⚠️ 这将影响下次消息采集的起始位置")
    
    confirm = input("是否继续? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("❌ 操作已取消")
        sys.exit(0)
    
    success = set_checkpoint(channel_id, message_id)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()