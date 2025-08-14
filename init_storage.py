#!/usr/bin/env python3
"""
新存储系统初始化脚本
初始化Redis和JSON存储，替代原来的数据库初始化
"""
import asyncio
import logging
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from app.storage.redis_store import init_redis_stores
from app.storage.json_store import init_json_stores
from app.services.auth_service import init_auth_service
from app.services.config_manager import config_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_storage_systems():
    """初始化所有存储系统"""
    logger.info("开始初始化存储系统...")
    
    try:
        # 1. 初始化Redis存储
        logger.info("初始化Redis存储...")
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        if not init_redis_stores(redis_url):
            logger.error("Redis存储初始化失败")
            return False
        
        # 2. 初始化JSON存储
        logger.info("初始化JSON存储...")
        data_dir = Path(__file__).parent / "data" / "config"
        if not init_json_stores(str(data_dir)):
            logger.error("JSON存储初始化失败")
            return False
        
        # 3. 初始化认证服务
        logger.info("初始化认证服务...")
        if not init_auth_service():
            logger.error("认证服务初始化失败")
            return False
        
        # 4. 初始化配置管理器
        logger.info("初始化配置管理器...")
        # 配置管理器不需要异步初始化
        
        # 5. 创建默认管理员（如果不存在）
        await create_default_admin()
        
        # 6. 初始化默认配置
        await initialize_default_configs()
        
        logger.info("✅ 存储系统初始化完成!")
        return True
        
    except Exception as e:
        logger.error(f"❌ 存储系统初始化失败: {e}")
        return False

async def create_default_admin():
    """创建默认管理员账户"""
    try:
        from app.services.auth_service import get_auth_service
        from app.storage.json_store import get_json_admin_store
        
        auth_service = get_auth_service()
        admin_store = get_json_admin_store()
        
        # 检查是否已有管理员
        admin_file = admin_store._get_file_path(admin_store.ADMIN_FILE)
        if admin_file.exists():
            admins = admin_store._load_json(admin_store.ADMIN_FILE)
            if admins:
                logger.info("管理员账户已存在，跳过创建")
                return
        
        # 创建默认超级管理员
        default_admin = await auth_service.create_user(
            username="admin",
            password="admin123",
            is_super_admin=True
        )
        
        if default_admin:
            logger.info("✅ 默认管理员创建成功")
            logger.info("用户名: admin")
            logger.info("密码: admin123")
            logger.warning("⚠️  请立即修改默认密码!")
        else:
            logger.error("❌ 默认管理员创建失败")
            
    except Exception as e:
        logger.error(f"创建默认管理员失败: {e}")

async def initialize_default_configs():
    """初始化默认配置"""
    try:
        # 基础系统配置
        default_configs = {
            # Telegram相关配置
            "telegram.api_id": "",
            "telegram.api_hash": "",
            "telegram.session_string": "",
            
            # 频道配置
            "channels.source_channels": [],
            "channels.review_group_id": "",
            "channels.target_channels": [],
            
            # 过滤配置
            "filter.enable_ad_detection": True,
            "filter.enable_duplicate_detection": True,
            "filter.enable_ocr_detection": True,
            "filter.ad_keywords": [],
            
            # 审核配置
            "review.auto_forward_delay": 30,
            "review.require_manual_review": True,
            "review.enable_batch_operations": True,
            
            # 媒体配置
            "media.download_media": True,
            "media.media_storage_path": "./temp_media",
            "media.max_file_size": 50 * 1024 * 1024,  # 50MB
            
            # 系统配置
            "system.log_level": "INFO",
            "system.max_daily_messages": 1000,
            "system.enable_statistics": True,
            
            # 账号管理配置
            "accounts.blacklist": [],
            "accounts.whitelist": [],
            "accounts.enable_account_filtering": True,
        }
        
        # 批量设置默认配置（只设置未存在的配置项）
        for key, default_value in default_configs.items():
            current_value = config_manager.get_config(key)
            if current_value is None:  # 配置不存在时才设置默认值
                config_manager.set_config(key, default_value)
        
        logger.info("✅ 默认配置初始化完成")
        
    except Exception as e:
        logger.error(f"初始化默认配置失败: {e}")

def check_environment():
    """检查环境依赖"""
    logger.info("检查环境依赖...")
    
    # 检查Redis连接
    try:
        import redis
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        r = redis.from_url(redis_url)
        r.ping()
        logger.info("✅ Redis连接正常")
    except Exception as e:
        logger.error(f"❌ Redis连接失败: {e}")
        logger.error("请确保Redis服务正在运行")
        return False
    
    # 检查数据目录
    data_dir = Path(__file__).parent / "data"
    if not data_dir.exists():
        data_dir.mkdir(parents=True)
        logger.info(f"✅ 创建数据目录: {data_dir}")
    
    config_dir = data_dir / "config"
    if not config_dir.exists():
        config_dir.mkdir(parents=True)
        logger.info(f"✅ 创建配置目录: {config_dir}")
    
    return True

async def main():
    """主函数"""
    logger.info("🚀 开始初始化新存储系统...")
    
    # 检查环境
    if not check_environment():
        logger.error("❌ 环境检查失败，请解决依赖问题后重试")
        return False
    
    # 初始化存储系统
    success = await init_storage_systems()
    
    if success:
        logger.info("🎉 存储系统初始化成功!")
        logger.info("您现在可以启动应用程序了")
        logger.info("运行: python3 main.py")
    else:
        logger.error("💥 存储系统初始化失败")
        logger.error("请检查错误信息并解决问题后重试")
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)