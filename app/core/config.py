"""
系统配置管理 - 统一的配置类
"""
import os
from typing import List, Optional, Any


class AppSettings:
    """统一的应用配置管理器"""
    
    def __init__(self):
        # 端口配置
        self.WEB_PORT: int = int(os.getenv("WEB_PORT", "8008"))
        self.NGINX_PORT: int = int(os.getenv("NGINX_PORT", "8080"))
        
        # URL配置 - 支持域名部署
        self.BASE_URL: str = self._get_base_url()
        self.API_URL: str = self._get_api_url()
        
        # 环境变量配置
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        self.WORKERS: int = int(os.getenv("WORKERS", "4"))
        
        # 兼容性属性
        self.redis_url = self.REDIS_URL

        # 配置管理器（延迟初始化）
        self._config_manager = None
        self._initialized = False

    def _get_base_url(self) -> str:
        """智能获取BASE_URL，支持域名部署"""
        # 优先使用环境变量
        if base_url := os.getenv("BASE_URL"):
            return base_url

        # 检查是否有域名配置
        domain = os.getenv("DOMAIN_NAME")
        if domain:
            # 检查是否启用SSL
            if os.getenv("ENABLE_SSL", "false").lower() == "true":
                return f"https://{domain}"
            else:
                return f"http://{domain}:{self.NGINX_PORT}"

        # 默认使用localhost
        return f"http://localhost:{self.NGINX_PORT}"

    def _get_api_url(self) -> str:
        """智能获取API_URL，支持域名部署"""
        # 优先使用环境变量
        if api_url := os.getenv("API_URL"):
            return api_url

        # 检查是否有域名配置
        domain = os.getenv("DOMAIN_NAME")
        if domain:
            # 生产环境域名通常API通过Nginx代理，使用BASE_URL
            return self.BASE_URL

        # 默认使用localhost的直接API端口
        return f"http://localhost:{self.WEB_PORT}"
    
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
        return await channel_manager.get_source_channels()
    
    async def get_review_group_id(self) -> str:
        """获取审核群ID配置（URL或用户名格式）"""
        await self._ensure_initialized()
        return await self._config_manager.get_config("review.group_id", "")
    
    async def get_review_group_resolved_id(self) -> str:
        """获取解析后的审核群ID（数字格式，优先使用cached值，否则尝试解析）"""
        await self._ensure_initialized()
        
        # 首先尝试获取缓存的数字ID
        cached_id = await self._config_manager.get_config("channels.review_group_id_cached", "")
        if cached_id and cached_id.startswith("-100"):
            return cached_id
        
        # 如果没有缓存，获取主配置并检查是否为数字ID
        main_id = await self.get_review_group_id()
        if main_id and main_id.startswith("-100"):
            return main_id
        
        # 如果主配置是URL或用户名格式，需要解析为数字ID
        if main_id and (main_id.startswith("@") or main_id.startswith("http") or "t.me" in main_id):
            try:
                from app.services.telegram_link_resolver import link_resolver
                resolved_id = await link_resolver.resolve_and_cache_group_id(main_id)
                if resolved_id and resolved_id.startswith("-100"):
                    return resolved_id
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"解析审核群ID失败 {main_id}: {e}")
        
        # 如果解析失败，返回原始配置
        return main_id
    
    async def get_target_channel_id(self) -> str:
        """获取目标频道ID配置（用户名格式，如@channelname）"""
        await self._ensure_initialized()
        return await self._config_manager.get_config("target.channel_id", "")
    
    async def get_target_channel_resolved_id(self) -> str:
        """获取解析后的目标频道ID（数字格式，优先使用cached值，否则尝试解析）"""
        await self._ensure_initialized()
        
        # 首先尝试获取缓存的数字ID
        cached_id = await self._config_manager.get_config("channels.target_channel_id_cached", "")
        if cached_id and cached_id.startswith("-100"):
            return cached_id
        
        # 如果没有缓存，获取主配置并检查是否为数字ID
        main_id = await self.get_target_channel_id()
        if main_id and main_id.startswith("-100"):
            return main_id
        
        # 如果主配置是用户名格式，需要解析为数字ID
        if main_id and (main_id.startswith("@") or not main_id.startswith("-")):
            try:
                from app.services.channel_id_resolver import channel_id_resolver
                resolved_id = await channel_id_resolver.resolve_channel_id(main_id)
                if resolved_id and resolved_id.startswith("-100"):
                    # 缓存解析结果
                    await self._config_manager.set_config("channels.target_channel_id_cached", resolved_id)
                    return resolved_id
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"解析目标频道ID失败 {main_id}: {e}")
        
        # 如果解析失败，返回原始配置
        return main_id
    
    async def get_history_message_limit(self) -> int:
        await self._ensure_initialized()
        return await self._config_manager.get_config("source.history_limit", 50)
    
    async def get_history_limit(self) -> int:
        """获取历史消息采集限制"""
        return await self.get_history_message_limit()
    
    async def get_auto_forward_delay(self) -> int:
        await self._ensure_initialized()
        return await self._config_manager.get_config("review.auto_forward_delay", 1800)
    
    # ============= 端口配置方法 =============
    
    def get_web_port(self) -> int:
        """获取Web服务端口"""
        return self.WEB_PORT
    
    def get_nginx_port(self) -> int:
        """获取Nginx服务端口"""
        return self.NGINX_PORT
    
    def get_base_url(self) -> str:
        """获取基础URL"""
        return self.BASE_URL
    
    def get_api_url(self) -> str:
        """获取API URL"""
        return self.API_URL
    
    # ============= 兼容性方法 =============
    
    async def load_db_configs(self):
        """兼容性方法，确保配置管理器已初始化"""
        await self._ensure_initialized()


# 全局配置实例
settings = AppSettings()

# 向后兼容的别名
config = settings
db_settings = settings