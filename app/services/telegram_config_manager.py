"""
Telegram配置独立管理器
专门管理telegram.json文件，与system.json完全分离
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)

class TelegramConfigManager:
    """Telegram配置管理器"""

    def __init__(self):
        self.config_file = Path("./data/config/telegram.json")
        self._ensure_config_file()

    def _ensure_config_file(self):
        """确保配置文件存在"""
        if not self.config_file.exists():
            default_config = {
                "api_id": "",
                "api_hash": "",
                "sender_session": "",
                "listener_session": ""
            }
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            SafeFileOperation.write_json_safe(self.config_file, default_config)
            logger.info("创建默认telegram.json配置文件")

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        try:
            config = SafeFileOperation.read_json_safe(self.config_file)
            return config or {}
        except Exception as e:
            logger.error(f"读取telegram.json失败: {e}")
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        """获取单个配置项"""
        config = self.get_all()
        return config.get(key, default)

    async def get_api_id(self) -> Optional[str]:
        """获取API ID"""
        return self.get("api_id")

    async def get_api_hash(self) -> Optional[str]:
        """获取API Hash"""
        return self.get("api_hash")

    async def get_sender_session(self) -> Optional[str]:
        """获取Sender Session - 从telegram.json读取"""
        return self.get("sender_session")

    async def get_listener_session(self) -> Optional[str]:
        """获取Listener Session - 从telegram.json读取"""
        return self.get("listener_session")

    def update(self, updates: Dict[str, Any]) -> bool:
        """更新配置"""
        try:
            config = self.get_all()
            config.update(updates)
            success = SafeFileOperation.write_json_safe(self.config_file, config)
            if success:
                logger.info(f"更新telegram.json配置: {list(updates.keys())}")
            return success
        except Exception as e:
            logger.error(f"更新telegram.json失败: {e}")
            return False

    def update_api_credentials(self, api_id: str, api_hash: str) -> bool:
        """更新API凭据"""
        return self.update({
            "api_id": api_id,
            "api_hash": api_hash
        })

    async def update_session(self, session_type: str, session_string: str) -> bool:
        """更新Session - 写入telegram.json"""
        if session_type == "sender":
            return self.update({"sender_session": session_string})
        elif session_type == "listener":
            return self.update({"listener_session": session_string})
        return False

    def validate_config(self) -> Dict[str, bool]:
        """验证配置完整性"""
        config = self.get_all()
        return {
            "has_api_id": bool(config.get("api_id")),
            "has_api_hash": bool(config.get("api_hash")),
            "is_valid": bool(config.get("api_id")) and bool(config.get("api_hash"))
        }

# 全局实例
telegram_config_manager = TelegramConfigManager()