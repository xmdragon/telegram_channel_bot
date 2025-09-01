#!/usr/bin/env python3
"""
存储系统初始化脚本（Redis + JSON）
"""
import asyncio
import os
import json
import logging
from pathlib import Path
import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_manager import redis_manager
from app.storage.json_store import init_json_stores
from app.services.config_manager import config_manager

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def init_default_configs():
    """初始化默认配置"""
    
    DEFAULT_CONFIGS = {
        # Telegram相关配置
        "telegram.api_id": {
            "value": "",
            "config_type": "string", 
            "description": "Telegram API ID",
            "category": "telegram"
        },
        "telegram.api_hash": {
            "value": "",
            "config_type": "string",
            "description": "Telegram API Hash", 
            "category": "telegram"
        },
        "telegram.session_string": {
            "value": "",
            "config_type": "text",
            "description": "Telegram Session String",
            "category": "telegram"
        },
        "telegram.bot_token": {
            "value": "",
            "config_type": "string",
            "description": "Telegram Bot Token（可选）",
            "category": "telegram"
        },
        
        # 频道配置
        "channels.source_channels": {
            "value": "[]",
            "config_type": "json",
            "description": "源频道列表",
            "category": "channels"
        },
        "channels.target_channels": {
            "value": "[]", 
            "config_type": "json",
            "description": "目标频道列表",
            "category": "channels"
        },
        "channels.review_chat_id": {
            "value": "",
            "config_type": "string",
            "description": "审核群组ID",
            "category": "channels"
        },
        
        # 过滤配置
        "filter.enabled": {
            "value": "true",
            "config_type": "boolean",
            "description": "启用内容过滤",
            "category": "filter"
        },
        "filter.ad_keywords": {
            "value": "[]",
            "config_type": "json", 
            "description": "广告关键词列表",
            "category": "filter"
        },
        "filter.tail_filter_enabled": {
            "value": "true",
            "config_type": "boolean",
            "description": "启用尾部过滤",
            "category": "filter"
        },
        "filter.ocr_enabled": {
            "value": "true",
            "config_type": "boolean",
            "description": "启用OCR图片文字识别",
            "category": "filter"
        },
        
        # 审核配置
        "review.auto_forward_delay": {
            "value": "30",
            "config_type": "integer",
            "description": "自动转发延时（分钟）",
            "category": "review"
        },
        "review.require_approval": {
            "value": "true",
            "config_type": "boolean",
            "description": "需要人工审核",
            "category": "review"
        },
        "review.auto_reject_ads": {
            "value": "false",
            "config_type": "boolean", 
            "description": "自动拒绝广告消息",
            "category": "review"
        },
        
        # 采集配置
        "collection.enabled": {
            "value": "true",
            "config_type": "boolean",
            "description": "启用消息采集",
            "category": "collection"
        },
        "collection.max_messages_per_batch": {
            "value": "50",
            "config_type": "integer",
            "description": "每批最大消息数",
            "category": "collection"
        },
        
        # 系统配置
        "system.log_level": {
            "value": "INFO",
            "config_type": "string",
            "description": "日志级别",
            "category": "system"
        },
        "system.max_message_age_days": {
            "value": "30",
            "config_type": "integer",
            "description": "消息最大保留天数",
            "category": "system"
        },
        "system.cleanup_enabled": {
            "value": "true",
            "config_type": "boolean",
            "description": "启用定期清理",
            "category": "system"
        },
        
        # Web界面配置
        "web.page_size": {
            "value": "20",
            "config_type": "integer",
            "description": "页面显示消息数",
            "category": "web"
        },
        "web.auto_refresh_interval": {
            "value": "30",
            "config_type": "integer",
            "description": "自动刷新间隔（秒）",
            "category": "web"
        }
    }
    
    updated_count = 0
    for key, config in DEFAULT_CONFIGS.items():
        try:
            # 检查是否已存在
            existing = await config_manager.get_config(key)
            if existing is None:
                success = await config_manager.set_config(
                    key, 
                    config["value"], 
                    config["description"], 
                    config["config_type"]
                )
                if success:
                    updated_count += 1
                    logger.debug(f"初始化配置: {key}")
        except Exception as e:
            logger.error(f"初始化配置失败 {key}: {e}")
    
    if updated_count > 0:
        logger.info(f"✅ 初始化了 {updated_count} 个默认配置")
    else:
        logger.info("ℹ️  配置已存在，跳过初始化")
    
    return updated_count

def init_default_permissions():
    """初始化默认权限数据（JSON文件）"""
    
    PERMISSION_DEFINITIONS = [
        # 消息管理
        {"name": "messages.view", "module": "messages", "action": "view", "description": "查看消息"},
        {"name": "messages.approve", "module": "messages", "action": "approve", "description": "批准消息"},
        {"name": "messages.reject", "module": "messages", "action": "reject", "description": "拒绝消息"},
        {"name": "messages.edit", "module": "messages", "action": "edit", "description": "编辑消息"},
        {"name": "messages.delete", "module": "messages", "action": "delete", "description": "删除消息"},
        
        # 配置管理
        {"name": "config.view", "module": "config", "action": "view", "description": "查看配置"},
        {"name": "config.edit", "module": "config", "action": "edit", "description": "修改配置"},
        
        # 频道管理
        {"name": "channels.view", "module": "channels", "action": "view", "description": "查看频道"},
        {"name": "channels.add", "module": "channels", "action": "add", "description": "添加频道"},
        {"name": "channels.edit", "module": "channels", "action": "edit", "description": "编辑频道"},
        {"name": "channels.delete", "module": "channels", "action": "delete", "description": "删除频道"},
        {"name": "channels.refetch", "module": "channels", "action": "refetch", "description": "补抓消息"},
        
        # 训练管理
        {"name": "training.view", "module": "training", "action": "view", "description": "查看训练数据"},
        {"name": "training.submit", "module": "training", "action": "submit", "description": "提交训练数据"},
        {"name": "training.mark_ad", "module": "training", "action": "mark_ad", "description": "标记为广告"},
        {"name": "training.mark_tail", "module": "training", "action": "mark_tail", "description": "标记尾部内容"},
        {"name": "training.manage", "module": "training", "action": "manage", "description": "管理训练数据"},
        
        # 过滤管理
        {"name": "filter.view", "module": "filter", "action": "view", "description": "查看过滤规则"},
        {"name": "filter.add_keyword", "module": "filter", "action": "add_keyword", "description": "添加过滤关键词"},
        {"name": "filter.execute", "module": "filter", "action": "execute", "description": "执行过滤操作"},
        {"name": "filter.manage", "module": "filter", "action": "manage", "description": "管理过滤规则"},
        
        # 系统管理
        {"name": "system.view_status", "module": "system", "action": "view_status", "description": "查看系统状态"},
        {"name": "system.view_logs", "module": "system", "action": "view_logs", "description": "查看系统日志"},
        {"name": "system.restart", "module": "system", "action": "restart", "description": "重启系统"},
        
        # 管理员管理
        {"name": "admin.manage_users", "module": "admin", "action": "manage_users", "description": "管理用户"},
        {"name": "admin.manage_permissions", "module": "admin", "action": "manage_permissions", "description": "管理权限"},
    ]
    
    from app.core.path_config import PathConfig
    permissions_file = PathConfig.PERMISSIONS_CONFIG_FILE
    permissions_file.parent.mkdir(parents=True, exist_ok=True)
    
    if permissions_file.exists():
        logger.info("ℹ️  权限文件已存在，跳过初始化")
        return 0
    
    try:
        permissions_data = {
            "permissions": PERMISSION_DEFINITIONS,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00"
        }
        
        with open(permissions_file, 'w', encoding='utf-8') as f:
            json.dump(permissions_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 初始化 {len(PERMISSION_DEFINITIONS)} 个权限项")
        return len(PERMISSION_DEFINITIONS)
        
    except Exception as e:
        logger.error(f"初始化权限文件失败: {e}")
        return 0

def init_directory_structure():
    """初始化目录结构"""
    
    # 使用PathConfig进行统一路径管理
    from app.core.path_config import PathConfig
    PathConfig.ensure_directories()
    
    # 额外创建静态文件目录
    try:
        static_dir = Path("static")
        static_dir.mkdir(exist_ok=True)
        logger.info("✅ 目录结构初始化完成")
        return 1
    except Exception as e:
        logger.error(f"创建静态目录失败: {e}")
        return 0

def init_default_data_files():
    """初始化默认数据文件"""
    
    from app.core.path_config import PathConfig
    
    DATA_FILES = {
        str(PathConfig.TAIL_FILTER_SAMPLES_FILE): {
            "samples": [],
            "created_at": "2024-01-01T00:00:00",
            "total_count": 0
        },
        str(PathConfig.OCR_SAMPLES_FILE): {
            "samples": [],
            "created_at": "2024-01-01T00:00:00", 
            "total_count": 0
        },
        str(PathConfig.AD_TRAINING_FILE): {
            "positive_samples": [],
            "negative_samples": [],
            "created_at": "2024-01-01T00:00:00",
            "version": "1.0"
        }
    }
    
    created_count = 0
    for file_path, default_content in DATA_FILES.items():
        file_obj = Path(file_path)
        file_obj.parent.mkdir(parents=True, exist_ok=True)
        
        if not file_obj.exists():
            try:
                with open(file_obj, 'w', encoding='utf-8') as f:
                    json.dump(default_content, f, ensure_ascii=False, indent=2)
                created_count += 1
                logger.debug(f"创建数据文件: {file_path}")
            except Exception as e:
                logger.error(f"创建数据文件失败 {file_path}: {e}")
    
    if created_count > 0:
        logger.info(f"✅ 创建了 {created_count} 个数据文件")
    else:
        logger.info("ℹ️  数据文件已存在")
    
    return created_count

async def initialize_storage_system():
    """初始化存储系统"""
    logger.info("🚀 正在初始化 Telegram 消息审核系统存储层...")
    
    # 1. 创建目录结构
    logger.info("📁 初始化目录结构...")
    init_directory_structure()
    
    # 2. 初始化JSON存储
    logger.info("📄 初始化JSON存储...")
    json_success = init_json_stores()
    if json_success:
        logger.info("✅ JSON存储初始化完成")
    else:
        logger.error("❌ JSON存储初始化失败")
        return False
    
    # 3. 初始化Redis存储
    logger.info("🔴 初始化Redis存储...")
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    redis_success = redis_manager.is_healthy()
    if redis_success:
        logger.info("✅ Redis存储初始化完成")
    else:
        logger.error("❌ Redis存储初始化失败")
        return False
    
    # 4. 初始化默认数据文件
    logger.info("📊 初始化默认数据文件...")
    init_default_data_files()
    
    # 5. 初始化权限数据
    logger.info("🔐 初始化权限数据...")
    init_default_permissions()
    
    # 6. 初始化默认配置
    logger.info("⚙️  初始化默认配置...")
    try:
        config_count = await init_default_configs()
        logger.info("✅ 默认配置初始化完成")
    except Exception as e:
        logger.error(f"❌ 默认配置初始化失败: {e}")
        return False
    
    logger.info("\n🎉 存储系统初始化完成！")
    logger.info("\n📋 下一步操作：")
    logger.info("1. 运行 python3 init_admin.py 创建超级管理员")
    logger.info("2. 启动系统: python3 main.py 或 ./start.sh")
    logger.info("3. 访问 http://localhost:8000/static/auth.html 完成Telegram认证")
    logger.info("4. 访问 http://localhost:8000/static/config.html 配置频道")
    logger.info("5. 访问 http://localhost:8000 开始使用系统")
    
    return True

async def check_storage_status():
    """检查存储系统状态"""
    logger.info("🔍 检查存储系统状态...")
    
    # 检查Redis连接
    try:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        if redis_manager.is_healthy():
            logger.info("✅ Redis连接正常")
            
            # 获取Redis统计信息
            # from app.storage.redis_store import get_redis_message_store  # 已删除
            # store = redis_manager  # 直接使用redis_manager
            
            total_messages = len(redis_manager.get_all_messages(limit=1000))
            pending_messages = len(redis_manager.get_messages_by_status('pending', 100))
            
            logger.info(f"📊 Redis消息统计: 总计 {total_messages} 条，待审核 {pending_messages} 条")
        else:
            logger.error("❌ Redis连接失败")
    except Exception as e:
        logger.error(f"❌ Redis检查失败: {e}")
    
    # 检查JSON配置
    try:
        if init_json_stores():
            logger.info("✅ JSON存储正常")
            
            config_count = await config_manager.get_all_configs()
            logger.info(f"📋 配置项数量: {len(config_count)}")
        else:
            logger.error("❌ JSON存储失败")
    except Exception as e:
        logger.error(f"❌ JSON配置检查失败: {e}")
    
    # 检查数据文件
    data_files = [
        str(PathConfig.TAIL_FILTER_SAMPLES_FILE),
        str(PathConfig.OCR_SAMPLES_FILE), 
        str(PathConfig.AD_TRAINING_FILE),
        str(PathConfig.PERMISSIONS_CONFIG_FILE)
    ]
    
    existing_files = 0
    for file_path in data_files:
        if Path(file_path).exists():
            existing_files += 1
    
    logger.info(f"📄 数据文件: {existing_files}/{len(data_files)} 个存在")
    
    logger.info("✅ 存储系统状态检查完成")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='存储系统管理工具')
    parser.add_argument('--init', action='store_true', help='初始化存储系统')
    parser.add_argument('--check', action='store_true', help='检查存储状态')
    parser.add_argument('--reset', action='store_true', help='重置存储系统（危险操作）')
    
    args = parser.parse_args()
    
    if args.check:
        await check_storage_status()
    elif args.reset:
        response = input("⚠️  确认要重置存储系统吗？这将删除所有数据！(yes/no): ")
        if response.lower() == 'yes':
            logger.warning("🗑️  重置存储系统功能待实现...")
        else:
            logger.info("取消重置操作")
    elif args.init or len(sys.argv) == 1:  # 默认行为
        success = await initialize_storage_system()
        if not success:
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main())