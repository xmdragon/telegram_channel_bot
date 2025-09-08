#!/usr/bin/env python3
"""
Redis键前缀迁移脚本
将 msg:idx:* 索引键迁移到 index:msg:* 格式
"""

import redis
import logging
import sys
from typing import Dict, List

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_redis_keys():
    """迁移Redis索引键前缀"""
    try:
        # 连接Redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        logger.info("✅ Redis连接成功")
        
        # 定义迁移映射
        migrations = {
            # 状态索引
            "msg:idx:pending": "index:msg:pending",
            "msg:idx:approved": "index:msg:approved", 
            "msg:idx:rejected": "index:msg:rejected",
            "msg:idx:all": "index:msg:all",
        }
        
        # 迁移固定键
        migrated_count = 0
        for old_key, new_key in migrations.items():
            if r.exists(old_key):
                # 检查新键是否已存在
                if r.exists(new_key):
                    logger.warning(f"⚠️ 新键已存在，跳过: {new_key}")
                    continue
                    
                # 获取键的类型
                key_type = r.type(old_key)
                
                if key_type == 'zset':
                    # 有序集合：复制所有成员和分数
                    members = r.zrange(old_key, 0, -1, withscores=True)
                    if members:
                        r.zadd(new_key, dict(members))
                        migrated_count += len(members)
                        logger.info(f"✅ 迁移有序集合: {old_key} -> {new_key} ({len(members)}个成员)")
                    else:
                        logger.info(f"⚪ 空键跳过: {old_key}")
                        
                elif key_type == 'set':
                    # 集合：复制所有成员
                    members = r.smembers(old_key)
                    if members:
                        r.sadd(new_key, *members)
                        migrated_count += len(members)
                        logger.info(f"✅ 迁移集合: {old_key} -> {new_key} ({len(members)}个成员)")
                        
                else:
                    logger.warning(f"⚠️ 不支持的键类型: {key_type} for {old_key}")
                    continue
                    
                # 删除旧键
                r.delete(old_key)
                logger.info(f"🗑️ 删除旧键: {old_key}")
            else:
                logger.info(f"⚪ 键不存在，跳过: {old_key}")
        
        # 迁移频道索引 (msg:idx:{channel_id} -> index:msg:{channel_id})
        logger.info("📡 开始迁移频道索引...")
        channel_keys = r.keys("msg:idx:*")
        channel_migrated = 0
        
        for old_key in channel_keys:
            # 跳过已经处理的固定键
            if old_key in migrations:
                continue
                
            # 构建新键名
            if old_key.startswith("msg:idx:"):
                channel_id = old_key[8:]  # 移除 "msg:idx:" 前缀
                new_key = f"index:msg:{channel_id}"
                
                if r.exists(new_key):
                    logger.warning(f"⚠️ 新键已存在，跳过: {new_key}")
                    continue
                
                # 检查键类型并迁移
                key_type = r.type(old_key)
                if key_type == 'zset':
                    members = r.zrange(old_key, 0, -1, withscores=True)
                    if members:
                        r.zadd(new_key, dict(members))
                        channel_migrated += len(members)
                        logger.info(f"✅ 迁移频道索引: {old_key} -> {new_key} ({len(members)}个成员)")
                        r.delete(old_key)
                    else:
                        logger.info(f"⚪ 空频道索引: {old_key}")
                        r.delete(old_key)
        
        # 统计结果
        total_migrated = migrated_count + channel_migrated
        logger.info(f"\n🎉 迁移完成！")
        logger.info(f"   📊 固定索引键迁移: {migrated_count} 个记录")
        logger.info(f"   📺 频道索引键迁移: {channel_migrated} 个记录")
        logger.info(f"   🔢 总计迁移: {total_migrated} 个记录")
        
        # 验证迁移结果
        logger.info("\n🔍 验证迁移结果...")
        remaining_old_keys = r.keys("msg:idx:*")
        new_keys = r.keys("index:msg:*")
        
        if remaining_old_keys:
            logger.warning(f"⚠️ 仍有旧键未迁移: {len(remaining_old_keys)} 个")
            for key in remaining_old_keys[:10]:  # 只显示前10个
                logger.warning(f"   - {key}")
        else:
            logger.info("✅ 所有旧键已成功迁移")
            
        logger.info(f"✅ 新索引键总数: {len(new_keys)} 个")
        
        return True
        
    except redis.ConnectionError:
        logger.error("❌ Redis连接失败，请确保Redis服务正在运行")
        return False
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        return False


def rollback_migration():
    """回滚迁移（将新键迁移回旧键）"""
    try:
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        logger.info("✅ Redis连接成功")
        
        # 回滚映射
        rollback_migrations = {
            "index:msg:pending": "msg:idx:pending",
            "index:msg:approved": "msg:idx:approved",
            "index:msg:rejected": "msg:idx:rejected", 
            "index:msg:all": "msg:idx:all",
        }
        
        rollback_count = 0
        
        # 回滚固定键
        for new_key, old_key in rollback_migrations.items():
            if r.exists(new_key):
                if r.exists(old_key):
                    logger.warning(f"⚠️ 旧键已存在，跳过回滚: {old_key}")
                    continue
                
                key_type = r.type(new_key)
                if key_type == 'zset':
                    members = r.zrange(new_key, 0, -1, withscores=True)
                    if members:
                        r.zadd(old_key, dict(members))
                        rollback_count += len(members)
                        logger.info(f"↩️ 回滚有序集合: {new_key} -> {old_key}")
                        r.delete(new_key)
        
        # 回滚频道索引
        channel_keys = r.keys("index:msg:*")
        for new_key in channel_keys:
            if new_key.startswith("index:msg:") and new_key not in rollback_migrations:
                channel_id = new_key[10:]  # 移除 "index:msg:" 前缀
                old_key = f"msg:idx:{channel_id}"
                
                if r.exists(old_key):
                    continue
                    
                key_type = r.type(new_key) 
                if key_type == 'zset':
                    members = r.zrange(new_key, 0, -1, withscores=True)
                    if members:
                        r.zadd(old_key, dict(members))
                        rollback_count += len(members)
                        logger.info(f"↩️ 回滚频道索引: {new_key} -> {old_key}")
                        r.delete(new_key)
        
        logger.info(f"↩️ 回滚完成，处理了 {rollback_count} 个记录")
        return True
        
    except Exception as e:
        logger.error(f"❌ 回滚失败: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        print("🔄 开始回滚迁移...")
        success = rollback_migration()
    else:
        print("🚀 开始Redis键前缀迁移...")
        success = migrate_redis_keys()
    
    sys.exit(0 if success else 1)