#!/usr/bin/env python3
"""
Telegram锁清理工具
用于清理Redis中的Telegram进程锁，解决死锁问题
"""
import sys
import os
import asyncio
import logging
import time
from typing import Optional, Dict, Any

# 添加项目根路径到sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from app.telegram.process_lock import telegram_lock
import redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TelegramLockCleaner:
    """Telegram锁清理器"""
    
    def __init__(self):
        self.redis = None
    
    def connect_redis(self):
        """连接Redis"""
        try:
            from app.core.config import settings
            self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self.redis.ping()
            logger.info("Redis连接成功")
            return True
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            return False
    
    def get_lock_info(self) -> Optional[Dict[str, Any]]:
        """获取当前锁信息"""
        try:
            if not self.redis:
                self.connect_redis()
            
            lock_key = "telegram:process:lock"
            owner_key = "telegram:process:owner"
            heartbeat_key = "telegram:process:heartbeat"
            
            lock_owner = self.redis.get(lock_key)
            owner_info = self.redis.get(owner_key)
            last_heartbeat = self.redis.get(heartbeat_key)
            
            if not lock_owner:
                return None
            
            info = {
                "lock_owner": lock_owner,
                "owner_info": owner_info,
                "last_heartbeat": float(last_heartbeat) if last_heartbeat else None,
                "heartbeat_age": time.time() - float(last_heartbeat) if last_heartbeat else None,
                "is_expired": False
            }
            
            # 判断是否过期（超过30秒无心跳认为过期，与进程锁超时保持一致）
            if info["heartbeat_age"] and info["heartbeat_age"] > 30:
                info["is_expired"] = True
            
            return info
            
        except Exception as e:
            logger.error(f"获取锁信息失败: {e}")
            return None
    
    def clear_lock(self, force: bool = False) -> bool:
        """清理锁"""
        try:
            if not self.redis:
                self.connect_redis()
            
            # 先检查锁状态
            lock_info = self.get_lock_info()
            
            if not lock_info:
                logger.info("✅ 没有发现锁，无需清理")
                return True
            
            logger.info("🔍 发现锁信息:")
            logger.info(f"  锁持有者: {lock_info['lock_owner']}")
            logger.info(f"  持有者信息: {lock_info['owner_info']}")
            logger.info(f"  最后心跳: {lock_info['last_heartbeat']}")
            logger.info(f"  心跳年龄: {lock_info['heartbeat_age']:.1f}秒" if lock_info['heartbeat_age'] else "  心跳年龄: 未知")
            logger.info(f"  是否过期: {'是' if lock_info['is_expired'] else '否'}")
            
            # 如果不是强制清理，检查是否过期
            if not force and not lock_info['is_expired']:
                logger.warning("⚠️  锁未过期，不建议清理。使用 --force 强制清理")
                return False
            
            # 清理锁相关的所有键
            lock_key = "telegram:process:lock"
            owner_key = "telegram:process:owner"
            heartbeat_key = "telegram:process:heartbeat"
            
            deleted_count = 0
            for key in [lock_key, owner_key, heartbeat_key]:
                if self.redis.delete(key):
                    deleted_count += 1
                    logger.info(f"  ✅ 已清理: {key}")
            
            if deleted_count > 0:
                logger.info(f"🧹 锁清理完成，清理了 {deleted_count} 个键")
                return True
            else:
                logger.warning("⚠️  没有清理任何键")
                return False
            
        except Exception as e:
            logger.error(f"清理锁失败: {e}")
            return False
    
    def check_and_clear(self) -> bool:
        """检查并智能清理锁"""
        lock_info = self.get_lock_info()
        
        if not lock_info:
            logger.info("✅ 系统正常，没有锁")
            return True
        
        if lock_info['is_expired']:
            logger.warning("🚨 检测到死锁，正在自动清理...")
            return self.clear_lock(force=True)
        else:
            logger.info("ℹ️  锁存在但未过期，系统正常运行中")
            return True
    
    def cleanup(self):
        """清理资源"""
        if self.redis:
            self.redis.close()

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Telegram锁清理工具")
    parser.add_argument('--check', action='store_true', help='仅检查锁状态')
    parser.add_argument('--clear', action='store_true', help='清理过期锁')
    parser.add_argument('--force', action='store_true', help='强制清理所有锁')
    parser.add_argument('--auto', action='store_true', help='自动检查并清理过期锁')
    
    args = parser.parse_args()
    
    cleaner = TelegramLockCleaner()
    
    try:
        if args.check:
            # 仅检查状态
            lock_info = cleaner.get_lock_info()
            if lock_info:
                print("🔍 锁状态:")
                print(f"  持有者: {lock_info['lock_owner']}")
                print(f"  心跳年龄: {lock_info['heartbeat_age']:.1f}秒" if lock_info['heartbeat_age'] else "  心跳年龄: 未知")
                print(f"  状态: {'过期' if lock_info['is_expired'] else '正常'}")
            else:
                print("✅ 没有锁")
        
        elif args.clear:
            # 清理过期锁
            success = cleaner.clear_lock(force=False)
            sys.exit(0 if success else 1)
        
        elif args.force:
            # 强制清理
            success = cleaner.clear_lock(force=True)
            sys.exit(0 if success else 1)
        
        elif args.auto:
            # 自动检查并清理
            success = cleaner.check_and_clear()
            sys.exit(0 if success else 1)
        
        else:
            # 默认行为：自动检查并清理
            success = cleaner.check_and_clear()
            sys.exit(0 if success else 1)
    
    finally:
        cleaner.cleanup()

if __name__ == "__main__":
    main()