"""
媒体和静态文件路径配置
统一管理所有媒体路径和静态文件路径，避免硬编码
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class MediaPathsConfig:
    """媒体路径配置类"""
    
    # 媒体路径 - 使用ROUTES配置
    @property
    def TEMP_MEDIA_PATH(self):
        from app.core.route_config import ROUTES
        return ROUTES.web_server.temp_media_mount

    @property
    def STATIC_PATH(self):
        from app.core.route_config import ROUTES
        return ROUTES.web_server.static_mount
    
    # 页面路径 - 使用ROUTES配置
    @property
    def INDEX_PAGE(self):
        from app.core.route_config import ROUTES
        return f"{ROUTES.web_server.static_mount}/index.html"

    @property
    def ADMIN_PAGE(self):
        from app.core.route_config import ROUTES
        return f"{ROUTES.web_server.static_mount}/admin-manage.html"

    @property
    def CONFIG_PAGE(self):
        from app.core.route_config import ROUTES
        return f"{ROUTES.web_server.static_mount}/config.html"

    @property
    def AUTH_PAGE(self):
        from app.core.route_config import ROUTES
        return f"{ROUTES.web_server.static_mount}/telegram-auth.html"

    @property
    def STATUS_PAGE(self):
        from app.core.route_config import ROUTES
        return f"{ROUTES.web_server.static_mount}/status.html"

    @property
    def TRAIN_PAGE(self):
        from app.core.route_config import ROUTES
        return f"{ROUTES.web_server.static_mount}/tail-filter-manager.html"

    @property
    def LOGIN_PAGE(self):
        from app.core.route_config import ROUTES
        return f"{ROUTES.web_server.static_mount}/login.html"
    
    def get_temp_media_url(self, filename: str) -> str:
        """获取临时媒体文件URL"""
        return f"{self.TEMP_MEDIA_PATH}/{filename}"

    def get_static_url(self, filename: str) -> str:
        """获取静态文件URL"""
        return f"{self.STATIC_PATH}/{filename}"


# 全局配置实例
media_paths = MediaPathsConfig()