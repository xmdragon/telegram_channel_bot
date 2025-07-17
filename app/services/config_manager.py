"""
配置管理服务
"""
import json
import logging
from typing import Any, Dict, List, Optional, Union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, SystemConfig

logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self._cache = {}
        self._cache_loaded = False
    
    async def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        if not self._cache_loaded:
            await self._load_cache()
        
        if key in self._cache:
            return self._parse_value(self._cache[key]['value'], self._cache[key]['config_type'])
        
        return default
    
    async def set_config(self, key: str, value: Any, description: str = "", config_type: str = "string") -> bool:
        """设置配置值"""
        try:
            async with AsyncSessionLocal() as db:
                # 查找现有配置
                result = await db.execute(
                    select(SystemConfig).where(SystemConfig.key == key)
                )
                config = result.scalar_one_or_none()
                
                # 序列化值
                serialized_value = self._serialize_value(value, config_type)
                
                if config:
                    # 更新现有配置
                    config.value = serialized_value
                    config.description = description or config.description
                    config.config_type = config_type
                else:
                    # 创建新配置
                    config = SystemConfig(
                        key=key,
                        value=serialized_value,
                        description=description,
                        config_type=config_type
                    )
                    db.add(config)
                
                await db.commit()
                
                # 更新缓存
                self._cache[key] = {
                    'value': serialized_value,
                    'config_type': config_type,
                    'description': description
                }
                
                return True
                
        except Exception as e:
            logger.error(f"设置配置失败: {key} = {value}, 错误: {e}")
            return False
    
    async def get_all_configs(self) -> Dict[str, Dict]:
        """获取所有配置"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SystemConfig).where(SystemConfig.is_active == True)
            )
            configs = result.scalars().all()
            
            return {
                config.key: {
                    'value': self._parse_value(config.value, config.config_type),
                    'raw_value': config.value,
                    'description': config.description,
                    'config_type': config.config_type,
                    'created_at': config.created_at,
                    'updated_at': config.updated_at
                }
                for config in configs
            }
    
    async def delete_config(self, key: str) -> bool:
        """删除配置"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(SystemConfig).where(SystemConfig.key == key)
                )
                config = result.scalar_one_or_none()
                
                if config:
                    await db.delete(config)
                    await db.commit()
                    
                    # 从缓存中移除
                    if key in self._cache:
                        del self._cache[key]
                    
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"删除配置失败: {key}, 错误: {e}")
            return False
    
    async def reload_cache(self):
        """重新加载缓存"""
        self._cache = {}
        self._cache_loaded = False
        await self._load_cache()
    
    async def _load_cache(self):
        """加载配置到缓存"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(SystemConfig).where(SystemConfig.is_active == True)
                )
                configs = result.scalars().all()
                
                for config in configs:
                    self._cache[config.key] = {
                        'value': config.value,
                        'config_type': config.config_type,
                        'description': config.description
                    }
                
                self._cache_loaded = True
                logger.info(f"已加载 {len(self._cache)} 个配置项到缓存")
                
        except Exception as e:
            logger.error(f"加载配置缓存失败: {e}")
    
    def _serialize_value(self, value: Any, config_type: str) -> str:
        """序列化配置值"""
        if config_type == "json" or config_type == "list":
            return json.dumps(value, ensure_ascii=False)
        elif config_type == "boolean":
            return str(bool(value)).lower()
        elif config_type == "integer":
            return str(int(value))
        else:
            return str(value)
    
    def _parse_value(self, value: str, config_type: str) -> Any:
        """解析配置值"""
        if not value:
            return None
            
        try:
            if config_type == "json" or config_type == "list":
                return json.loads(value)
            elif config_type == "boolean":
                return value.lower() in ('true', '1', 'yes', 'on')
            elif config_type == "integer":
                return int(value)
            else:
                return value
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"解析配置值失败: {value}, 类型: {config_type}, 错误: {e}")
            return value

# 全局配置管理器实例
config_manager = ConfigManager()

# 配置项定义
DEFAULT_CONFIGS = {
    # Telegram配置
    "telegram.bot_token": {
        "value": "",
        "description": "Telegram机器人Token",
        "config_type": "string"
    },
    "telegram.api_id": {
        "value": "",
        "description": "Telegram API ID",
        "config_type": "string"
    },
    "telegram.api_hash": {
        "value": "",
        "description": "Telegram API Hash",
        "config_type": "string"
    },
    
    # 频道配置
    "channels.source_channels": {
        "value": [],
        "description": "源频道列表",
        "config_type": "list"
    },
    "channels.review_group_id": {
        "value": "",
        "description": "审核群ID",
        "config_type": "string"
    },
    "channels.target_channel_id": {
        "value": "",
        "description": "目标频道ID",
        "config_type": "string"
    },
    
    # 审核配置
    "review.auto_forward_delay": {
        "value": 1800,
        "description": "自动转发延迟(秒)",
        "config_type": "integer"
    },
    "review.auto_filter_ads": {
        "value": False,
        "description": "是否自动过滤广告消息",
        "config_type": "boolean"
    },
    
    # 过滤配置
    "filter.ad_keywords": {
        "value": ["广告", "推广", "代理", "加微信", "联系方式", "优惠", "折扣", "限时", "抢购", "秒杀"],
        "description": "广告关键词列表",
        "config_type": "list"
    },
    "filter.channel_replacements": {
        "value": {
            "@原频道": "@你的频道",
            "原频道链接": "你的频道链接"
        },
        "description": "频道信息替换规则",
        "config_type": "json"
    },
    
    # 系统配置
    "system.secret_key": {
        "value": "your-secret-key-change-this-in-production",
        "description": "系统密钥",
        "config_type": "string"
    },
    "system.database_url": {
        "value": "sqlite:///./telegram_system.db",
        "description": "数据库连接URL",
        "config_type": "string"
    },
    "system.redis_url": {
        "value": "redis://localhost:6379",
        "description": "Redis连接URL",
        "config_type": "string"
    }
}

async def init_default_configs():
    """初始化默认配置"""
    logger.info("正在初始化默认配置...")
    
    for key, config_info in DEFAULT_CONFIGS.items():
        existing_value = await config_manager.get_config(key)
        if existing_value is None:
            await config_manager.set_config(
                key=key,
                value=config_info["value"],
                description=config_info["description"],
                config_type=config_info["config_type"]
            )
            logger.info(f"已初始化配置: {key}")
    
    logger.info("默认配置初始化完成")