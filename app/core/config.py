"""
系统配置管理
"""
import os
import asyncio
from typing import List, Optional, Any
from pydantic import BaseSettings

# 基础环境配置（仍从环境变量读取）
class BaseSettings(BaseSettings):
    """基础配置（从环境变量读取）"""
    
    # 数据库配置（启动时需要）
    DATABASE_URL: str = "sqlite:///./telegram_system.db"
    
    # Redis配置
    REDIS_URL: str = "redis://localhost:6379"
    
    # 开发模式
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"

base_settings = BaseSettings()

class DatabaseSettings:
    """数据库配置管理器"""
    
    def __init__(self):
        self._config_manager = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """确保配置管理器已初始化"""
        if not self._initialized:
            from app.services.config_manager import config_manager
            self._config_manager = config_manager
            self._initialized = True
    
    async def get_telegram_bot_token(self) -> str:
        await self._ensure_initialized()
        return await self._config_manager.get_config("telegram.bot_token", "")
    
    async def get_telegram_api_id(self) -> str:
        await self._ensure_initialized()
        return await self._config_manager.get_config("telegram.api_id", "")
    
    async def get_telegram_api_hash(self) -> str:
        await self._ensure_initialized()
        return await self._config_manager.get_config("telegram.api_hash", "")
    
    async def get_source_channels(self) -> List[str]:
        await self._ensure_initialized()
        return await self._config_manager.get_config("channels.source_channels", [])
    
    async def get_review_group_id(self) -> str:
        await self._ensure_initialized()
        return await self._config_manager.get_config("channels.review_group_id", "")
    
    async def get_target_channel_id(self) -> str:
        await self._ensure_initialized()
        return await self._config_manager.get_config("channels.target_channel_id", "")
    
    async def get_auto_forward_delay(self) -> int:
        await self._ensure_initialized()
        return await self._config_manager.get_config("review.auto_forward_delay", 1800)
    
    async def get_auto_filter_ads(self) -> bool:
        await self._ensure_initialized()
        return await self._config_manager.get_config("review.auto_filter_ads", False)
    
    async def get_ad_keywords(self) -> List[str]:
        await self._ensure_initialized()
        return await self._config_manager.get_config("filter.ad_keywords", [])
    
    async def get_channel_replacements(self) -> dict:
        await self._ensure_initialized()
        return await self._config_manager.get_config("filter.channel_replacements", {})
    
    async def get_secret_key(self) -> str:
        await self._ensure_initialized()
        return await self._config_manager.get_config("system.secret_key", "default-secret-key")

# 全局数据库配置实例
db_settings = DatabaseSettings()

# 兼容性设置类（用于需要同步访问的地方）
class Settings:
    """兼容性配置类"""
    
    def __init__(self):
        # 基础配置
        self.DATABASE_URL = base_settings.DATABASE_URL
        self.REDIS_URL = base_settings.REDIS_URL
        self.DEBUG = base_settings.DEBUG
        
        # 数据库配置（异步获取）
        self._db_configs = {}
        self._config_loaded = False
    
    async def load_db_configs(self):
        """加载数据库配置"""
        if self._config_loaded:
            return
            
        try:
            self._db_configs = {
                'TELEGRAM_BOT_TOKEN': await db_settings.get_telegram_bot_token(),
                'TELEGRAM_API_ID': await db_settings.get_telegram_api_id(),
                'TELEGRAM_API_HASH': await db_settings.get_telegram_api_hash(),
                'SOURCE_CHANNELS': await db_settings.get_source_channels(),
                'REVIEW_GROUP_ID': await db_settings.get_review_group_id(),
                'TARGET_CHANNEL_ID': await db_settings.get_target_channel_id(),
                'AUTO_FORWARD_DELAY': await db_settings.get_auto_forward_delay(),
                'AUTO_FILTER_ADS': await db_settings.get_auto_filter_ads(),
                'AD_KEYWORDS': await db_settings.get_ad_keywords(),
                'CHANNEL_REPLACEMENTS': await db_settings.get_channel_replacements(),
                'SECRET_KEY': await db_settings.get_secret_key(),
            }
            self._config_loaded = True
        except Exception as e:
            print(f"加载数据库配置失败: {e}")
    
    def __getattr__(self, name):
        """动态获取配置属性"""
        if name in self._db_configs:
            return self._db_configs[name]
        
        # 如果配置未加载，返回默认值
        defaults = {
            'TELEGRAM_BOT_TOKEN': '',
            'TELEGRAM_API_ID': '',
            'TELEGRAM_API_HASH': '',
            'SOURCE_CHANNELS': [],
            'REVIEW_GROUP_ID': '',
            'TARGET_CHANNEL_ID': '',
            'AUTO_FORWARD_DELAY': 1800,
            'AUTO_FILTER_ADS': False,
            'AD_KEYWORDS': [],
            'CHANNEL_REPLACEMENTS': {},
            'SECRET_KEY': 'default-secret-key',
        }
        
        return defaults.get(name, None)

settings = Settings()