"""
系统配置管理 - 统一的配置类
"""
import os
from typing import List, Optional, Any


class AppSettings:
    """统一的应用配置管理器"""
    
    def __init__(self):
        # 环境变量配置
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
        
        # 兼容性属性
        self.redis_url = self.REDIS_URL
        
        # 配置管理器（延迟初始化）
        self._config_manager = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """确保配置管理器已初始化"""
        if not self._initialized:
            from app.services.config_manager import config_manager
            self._config_manager = config_manager
            self._initialized = True
    
    # ============= JSON配置读取方法 =============
    
    async def get_source_channels(self) -> List[str]:
        """获取活跃的源频道ID列表"""
        from app.services.channel_manager import channel_manager
        return await channel_manager.get_active_source_channels()
    
    async def get_review_group_id(self) -> str:
        await self._ensure_initialized()
        return await self._config_manager.get_config("channels.review_group_id", "")
    
    async def get_target_channel_id(self) -> str:
        await self._ensure_initialized()
        return await self._config_manager.get_config("channels.target_channel_id", "")
    
    async def get_history_message_limit(self) -> int:
        await self._ensure_initialized()
        return await self._config_manager.get_config("channels.history_message_limit", 50)
    
    async def get_history_limit(self) -> int:
        """获取历史消息采集限制"""
        return await self.get_history_message_limit()
    
    async def get_auto_forward_delay(self) -> int:
        await self._ensure_initialized()
        return await self._config_manager.get_config("review.auto_forward_delay", 1800)
    
    async def get_ad_keywords_text(self) -> List[str]:
        await self._ensure_initialized()
        return await self._config_manager.get_config("filter.ad_keywords_text", [])
    
    # ============= 兼容性方法 =============
    
    async def load_db_configs(self):
        """兼容性方法，确保配置管理器已初始化"""
        await self._ensure_initialized()


# 全局配置实例
settings = AppSettings()

# 向后兼容的别名
config = settings
db_settings = settings