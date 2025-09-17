"""
媒体和静态文件路径配置
统一管理所有媒体路径和静态文件路径，避免硬编码
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class MediaPathsConfig:
    """媒体路径配置类"""
    
    # 媒体路径
    TEMP_MEDIA_PATH = "/temp_media"
    STATIC_PATH = "/static"
    
    # 页面路径
    INDEX_PAGE = "/static/index.html"
    ADMIN_PAGE = "/static/admin-manage.html"
    CONFIG_PAGE = "/static/config.html"
    AUTH_PAGE = "/static/telegram-auth.html"
    STATUS_PAGE = "/static/status.html"
    TRAIN_PAGE = "/static/tail-filter-manager.html"
    LOGIN_PAGE = "/static/login.html"
    
    @classmethod
    def get_temp_media_url(cls, filename: str) -> str:
        """获取临时媒体文件URL"""
        return f"{cls.TEMP_MEDIA_PATH}/{filename}"
    
    @classmethod
    def get_static_url(cls, filename: str) -> str:
        """获取静态文件URL"""
        return f"{cls.STATIC_PATH}/{filename}"


# 全局配置实例
media_paths = MediaPathsConfig()