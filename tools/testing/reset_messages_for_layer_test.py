#!/usr/bin/env python3
"""
逐层测试前的消息数据重置工具
清空Redis历史消息，重置checkpoint为0，为干净的测试环境做准备
"""
import sys
import json
import redis
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.storage.redis_manager import redis_manager
from app.services.config_manager import ConfigManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_redis_messages():
    """清空Redis中所有telegram:messages:*的键"""
    try:
        client = redis_manager.client
        
        # 查找所有telegram:messages:*键
        pattern = "telegram:messages:*"
        keys = client.keys(pattern)
        
        if keys:
            logger.info(f"发现 {len(keys)} 个消息键，准备删除...")
            deleted = client.delete(*keys)
            logger.info(f"✅ 已删除 {deleted} 个消息键")
        else:
            logger.info("✅ 没有找到消息键，Redis已经是干净状态")
            
    except Exception as e:
        logger.error(f"❌ 清空Redis消息失败: {e}")
        return False
    
    return True

def reset_channels_checkpoint():
    """重置所有频道的last_message_id为0"""
    try:
        config_manager = ConfigManager()
        
        # 读取频道配置
        channels_file = Path("data/config/channels.json")
        if not channels_file.exists():
            logger.warning("⚠️ channels.json文件不存在")
            return True
            
        with open(channels_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        reset_count = 0
        total_channels = 0
        
        # 重置所有源频道的checkpoint
        if 'source_channels' in data:
            for channel in data['source_channels']:
                total_channels += 1
                if 'last_message_id' in channel and channel['last_message_id'] != 0:
                    old_id = channel['last_message_id']
                    channel['last_message_id'] = 0
                    reset_count += 1
                    logger.info(f"重置频道 {channel.get('channel_name', 'Unknown')}: {old_id} -> 0")
                else:
                    channel['last_message_id'] = 0  # 确保字段存在
        
        # 写回文件
        with open(channels_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 已重置 {reset_count}/{total_channels} 个频道的checkpoint")
        
    except Exception as e:
        logger.error(f"❌ 重置checkpoint失败: {e}")
        return False
    
    return True

def show_reset_summary():
    """显示重置后的环境状态"""
    try:
        # 检查Redis状态
        client = redis_manager.client
        message_keys = client.keys("telegram:messages:*")
        
        # 检查频道配置
        channels_file = Path("data/config/channels.json")
        channel_count = 0
        if channels_file.exists():
            with open(channels_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'source_channels' in data:
                    channel_count = len(data['source_channels'])
        
        logger.info("🎯 重置完成，环境状态:")
        logger.info(f"   - Redis消息键数量: {len(message_keys)}")
        logger.info(f"   - 源频道数量: {channel_count}")
        logger.info(f"   - 所有checkpoint已重置为0")
        logger.info("🚀 环境已准备好进行层级测试")
        
    except Exception as e:
        logger.warning(f"状态检查失败: {e}")

def main():
    """主函数"""
    print("🔄 开始重置消息数据以进行逐层测试...")
    
    # 步骤1：清空Redis消息
    print("\n1️⃣ 清空Redis历史消息...")
    if not reset_redis_messages():
        print("❌ Redis重置失败，停止执行")
        return 1
    
    # 步骤2：重置checkpoint
    print("\n2️⃣ 重置频道checkpoint...")
    if not reset_channels_checkpoint():
        print("❌ Checkpoint重置失败，停止执行")
        return 1
    
    # 步骤3：显示状态摘要
    print("\n3️⃣ 环境状态检查...")
    show_reset_summary()
    
    print("\n✅ 消息数据重置完成！可以开始层级测试。")
    return 0

if __name__ == "__main__":
    sys.exit(main())