"""
URL配置管理模块
统一管理所有URL配置，支持环境变量，消除硬编码
符合设计原则：消除特殊情况，统一配置管理
"""
import os
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量配置文件
load_dotenv()

# 导入端口配置
from app.core.config import settings


class URLConfig:
    """URL配置管理类，提供统一的URL生成方法"""
    
    def __init__(self):
        # 基础URL配置，支持环境变量覆盖
        self._base_url = os.getenv('BASE_URL', f'http://localhost:{settings.WEB_PORT}')
        
        # 确保URL末尾没有斜杠
        self._base_url = self._base_url.rstrip('/')
    
    @property
    def base_url(self) -> str:
        """获取前端基础URL (Nginx)"""
        return self._base_url
    
    @property
    def api_url(self) -> str:
        """获取后端API URL (FastAPI) - 动态读取环境变量"""
        api_url = os.getenv('API_URL', f'http://localhost:{settings.WEB_PORT}')
        return api_url.rstrip('/')
    
    # 静态页面URL生成方法
    def get_static_url(self, path: str) -> str:
        """生成静态文件URL"""
        path = path.lstrip('/')
        return f"{self._base_url}/static/{path}"
    
    def get_login_url(self) -> str:
        """获取管理员登录页面URL"""
        return self.get_static_url("login.html")
    
    def get_index_url(self) -> str:
        """获取主页URL"""
        return self.get_static_url("index.html")
    
    def get_config_url(self) -> str:
        """获取配置页面URL"""
        return self.get_static_url("config.html")
    
    def get_auth_url(self) -> str:
        """获取Telegram认证页面URL"""
        return self.get_static_url("telegram-auth.html")
    
    def get_admin_url(self) -> str:
        """获取管理页面URL"""
        return self.get_static_url("admin-manage.html")
    
    def get_status_url(self) -> str:
        """获取状态页面URL"""
        return self.get_static_url("status.html")
    
    def get_train_url(self) -> str:
        """获取训练页面URL"""
        return self.get_static_url("tail-filter-manager.html")
    
    # API URL生成方法
    def get_api_url(self, path: str) -> str:
        """生成API URL - 动态生成"""
        path = path.lstrip('/')
        return f"{self.api_url}/api/{path}"
    
    def get_health_url(self) -> str:
        """获取健康检查URL - 动态生成"""
        return f"{self.api_url}/api/health"
    
    def get_websocket_url(self) -> str:
        """获取WebSocket URL - 动态生成"""
        api_url = self.api_url
        ws_scheme = 'ws' if api_url.startswith('http://') else 'wss'
        host_port = api_url.replace('http://', '').replace('https://', '')
        return f"{ws_scheme}://{host_port}/ws"
    
    # 媒体文件URL生成方法
    def get_temp_media_url(self, filename: str) -> str:
        """获取临时媒体文件URL"""
        return f"{self._base_url}/temp_media/{filename}"
    # 环境检测方法
    def is_production(self) -> bool:
        """检查是否为生产环境"""
        return os.getenv('ENVIRONMENT', 'development') == 'production'
    
    def is_development(self) -> bool:
        """检查是否为开发环境"""
        return not self.is_production()
    
    # 调试信息
    def get_config_info(self) -> dict:
        """获取当前URL配置信息（用于调试）"""
        return {
            'base_url': self._base_url,
            'api_url': self._api_url,
            'environment': 'production' if self.is_production() else 'development',
            'auth_url': self.get_auth_url(),
            'health_url': self.get_health_url(),
            'websocket_url': self.get_websocket_url()
        }


# 全局配置实例
url_config = URLConfig()


# 向后兼容性函数（可选）
def get_auth_url() -> str:
    """向后兼容：获取认证URL"""
    return url_config.get_auth_url()


def get_health_url() -> str:
    """向后兼容：获取健康检查URL"""
    return url_config.get_health_url()